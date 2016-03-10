
import os
import re
import math
from string import Template
# from datetime import timedelta
from mycluster import get_timedelta
# from subprocess import Popen, PIPE, check_output
from mycluster import get_data

"""
sacctmgr show cluster
"""


def scheduler_type():
    return 'slurm'


def name():
    with os.popen('sacctmgr show cluster') as f:
        f.readline()
        f.readline()
        return f.readline().strip().split(' ')[0]


def accounts():
    pass


def queues():
    queue_list = []

    with os.popen('sinfo -sh') as f:
        for line in f:
            q = line.split(' ')[0].strip().replace("*", "")
            queue_list.append(q)

    return queue_list


def available_tasks(queue_id):

    # split queue id into queue and parallel env
    # list free slots
    free_tasks = 0
    max_tasks = 0
    queue_name = queue_id
    nc = node_config(queue_id)
    with os.popen('sinfo -sh -p '+queue_name) as f:
        line = f.readline()
        new_line = re.sub(' +', ' ', line.strip())
        line = new_line.split(' ')[3]
        free_tasks = int(line.split('/')[1])*nc['max task']
        max_tasks = int(line.split('/')[3])*nc['max task']

    return {'available' : free_tasks, 'max tasks' : max_tasks}


def tasks_per_node(queue_id):
    queue_name = queue_id
    tasks = 0
    with os.popen('sinfo -Nelh -p '+queue_name) as f:
        line = f.readline()
        new_line = re.sub(' +', ' ', line.strip())
        tasks = int(new_line.split(' ')[4])
    return tasks


def node_config(queue_id):
    # Find first node with queue and record node config
    queue_name = queue_id
    tasks = 0
    config = {}
    with os.popen('sinfo -Nelh -p '+queue_name) as f:
        line = f.readline()
        if len(line):
            new_line = re.sub(' +', ' ', line.strip())
            tasks = int(new_line.split(' ')[4])
            memory = int(new_line.split(' ')[6])
            config['max task'] = tasks
            config['max thread'] = tasks
            config['max memory'] = memory
        else:
            raise StandardError("Requested partition %s has no nodes" % queue_name)

    return config



def create_submit(queue_id, **kwargs):

    queue_name = queue_id

    num_tasks = 1
    if 'num_tasks' in kwargs:
        num_tasks = kwargs['num_tasks']

    tpn = tasks_per_node(queue_id)
    queue_tpn = tpn
    if 'tasks_per_node' in kwargs:
        tpn = min(tpn, kwargs['tasks_per_node'])

    nc = node_config(queue_id)
    qc = available_tasks(queue_id)

    num_tasks = min(num_tasks, qc['max tasks'])

    num_threads_per_task = nc['max thread']
    if 'num_threads_per_task' in kwargs:
        num_threads_per_task = kwargs['num_threads_per_task']
    num_threads_per_task = min(num_threads_per_task, int(math.ceil(float(nc['max thread'])/float(tpn))))

    my_name = "myclusterjob"
    if 'my_name' in kwargs:
        my_name = kwargs['my_name']
    my_output = "myclusterjob.out"
    if 'my_output' in kwargs:
        my_output = kwargs['my_output']
    if 'my_script' not in kwargs:
        pass
    my_script = kwargs['my_script']
    if 'mycluster-' in my_script:
        my_script = get_data(my_script)

    if 'user_email' not in kwargs:
        pass
    user_email = kwargs['user_email']

    project_name = 'default'
    if 'project_name' in kwargs:
        project_name = kwargs['project_name']

    wall_clock = '12:00:00'
    if 'wall_clock' in kwargs:
        if ':' not in str(kwargs['wall_clock']):
            wall_clock = str(kwargs['wall_clock'])+':00:00'
        else:
            wall_clock = str(kwargs['wall_clock'])

    num_nodes = int(math.ceil(float(num_tasks)/float(tpn)))

    num_queue_slots = num_nodes*queue_tpn

    record_job = "True"
    if 'no_syscribe' in kwargs:
        record_job = ""

    if 'openmpi_args' not in kwargs:
        openmpi_args = "-bysocket -bind-to-socket"
    else:
        openmpi_args =  kwargs['openmpi_args']

    script = Template(r"""#!/bin/bash
#
# SLURM job submission script generated by MyCluster
#
# Job name
#SBATCH -J $my_name
# Send status information to this email address.
#SBATCH --mail-user=$user_email
# Send me an e-mail when the job has finished.
#SBATCH --mail-type=ALL
# Redirect output stream to this file.
#SBATCH --output $my_output.%j
# Which project should be charged
#SBATCH -A $project_name
# Partition name
#SBATCH -p $queue_name
# Number of nodes
#SBATCH --nodes $num_nodes
# Number of tasks
#SBATCH --ntasks $num_tasks
# Exclusive node use
#SBATCH --exclusive
# Do not requeue job on node failure
#SBATCH --no-requeue
# How much wallclock time will be required?
#SBATCH --time=$wall_clock


export MYCLUSTER_QUEUE=$queue_name
export MYCLUSTER_JOB_NAME=$my_name
export NUM_TASKS=$num_tasks
export TASKS_PER_NODE=$tpn
export THREADS_PER_TASK=$num_threads_per_task
export NUM_NODES=$num_nodes
export JOBID=$$SLURM_JOB_ID

# OpenMP configuration
export OMP_NUM_THREADS=$$THREADS_PER_TASK
export OMP_PROC_BIND=true
export OMP_PLACES=sockets

# OpenMPI
export OMPI_CMD="mpiexec -n $$NUM_TASKS -npernode $$TASKS_PER_NODE $openmpi_args"

# MVAPICH2
export MV2_CPU_BINDING_LEVEL=SOCKET
export MV2_CPU_BINDING_POLICY=scatter
export MVAPICH_CMD="mpiexec -n $$NUM_TASKS -ppn $$TASKS_PER_NODE -bind-to-socket"

# Intel MPI
# The following variables define a sensible pinning strategy for Intel MPI tasks -
# this should be suitable for both pure MPI and hybrid MPI/OpenMP jobs:
export I_MPI_PIN_DOMAIN=omp:compact # Domains are $$OMP_NUM_THREADS cores in size
export I_MPI_PIN_ORDER=scatter # Adjacent domains have minimal sharing of caches/sockets
#export I_MPI_FABRICS=shm:ofa
export IMPI_CMD="mpiexec -n $$NUM_TASKS -ppn $$TASKS_PER_NODE"

# Summarise environment
echo -e "JobID: $$JOBID\n======"
echo "Time: `date`"
echo "Running on master node: `hostname`"
echo "Current directory: `pwd`"

if [ "$$SLURM_JOB_NODELIST" ]; then
        #! Create a machine file:
        echo $$SLURM_JOB_NODELIST | uniq > machine.file.$$JOBID
        echo -e "\nNodes allocated:\n================"
        echo `cat machine.file.$$JOBID | sed -e 's/\..*$$//g'`
fi

echo -e "\nnumtasks=$num_tasks, numnodes=$num_nodes, tasks_per_node=$tpn (OMP_NUM_THREADS=$$OMP_NUM_THREADS)"

echo -e "\nExecuting command:\n==================\n$my_script\n"

# Run user script
. $my_script

# Report on completion
echo -e "\nJob Complete:\n==================\n"
if [ $record_job ]; then
    echo -e "\nRecording hardware setup\n==================\n"
    mycluster --sysscribe $$JOBID
    if [ "$$MYCLUSTER_APP_NAME" ]; then
        mycluster --jobid $$JOBID --appname=$$MYCLUSTER_APP_NAME
    fi
    if [ "$$MYCLUSTER_APP_DATA" ]; then
        mycluster --jobid $$JOBID --appdata=$$MYCLUSTER_APP_DATA
    fi
fi

echo -e "Complete========\n"
""")
    script_str = script.substitute({'my_name':my_name,
                                    'my_script':my_script,
                                    'my_output':my_output,
                                    'user_email':user_email,
                                    'queue_name':queue_name,
                                    'num_queue_slots':num_queue_slots,
                                    'num_tasks':num_tasks,
                                    'tpn':tpn,
                                    'num_threads_per_task':num_threads_per_task,
                                    'num_nodes':num_nodes,
                                    'project_name': project_name,
                                    'wall_clock' : wall_clock,
                                    'record_job' : record_job,
                                    'openmpi_args': openmpi_args,
                                   })

    return script_str


def submit(script_name, immediate):
    job_id = None
    if not immediate:
        with os.popen('sbatch '+script_name) as f:
            output = f.readline()
            try:
                job_id = int(output.split(' ')[-1].strip())
            except:
                print 'Job submission failed: '+output
            # Get job id and record in database
    else:
        with os.popen('grep -- "SBATCH -p" '+script_name+' | sed \'s/#SBATCH//\'') as f:
            partition = f.readline().rstrip()
        with os.popen('grep -- "SBATCH --nodes" '+script_name+' | sed \'s/#SBATCH//\'') as f:
            nnodes = f.readline().rstrip()
        with os.popen('grep -- "SBATCH --ntasks" '+script_name+' | sed \'s/#SBATCH//\'') as f:
            ntasks = f.readline().rstrip()
        with os.popen('grep -- "SBATCH -A" '+script_name+' | sed \'s/#SBATCH//\'') as f:
            project = f.readline().rstrip()
        with os.popen('grep -- "SBATCH -J" '+script_name+' | sed \'s/#SBATCH//\'') as f:
            job = f.readline().rstrip()

        cmd_line = 'salloc --exclusive '+nnodes+' '+partition+' '+ntasks+' '+project+' '+job+' srun -n 1 ./'+script_name
        print cmd_line

        with os.popen(cmd_line) as f:
            output = f.readline()
            try:
                job_id = int(output.split(' ')[-1].strip())
            except:
                print('Job submission failed: '+output)
    return job_id


def delete(job_id):
    with os.popen('scancel '+job_id) as f:
        pass


def status():
    status_dict = {}
    with os.popen('squeue -u `whoami`') as f:
        try:
            f.readline() # read header
            for line in f:
                new_line = re.sub(' +', ' ', line.strip())
                job_id = int(new_line.split(' ')[0])
                state = new_line.split(' ')[4]
                if state == 'R':
                    status_dict[job_id] = 'r'
                else:
                    status_dict[job_id] = state
        except e:
            print e

    return status_dict


def job_stats(job_id):
    stats_dict = {}
    with os.popen('sacct --noheader --format JobId,Elapsed,TotalCPU,Partition,NTasks,AveRSS,State,ExitCode -P -j '+str(job_id)) as f:
        try:
            line = f.readline()
            first_line = line.split('|')

            line = f.readline()
            if len(line) > 0:
                next_line = line.split('|')

            wallclock_str = first_line[1]
            stats_dict['wallclock'] = get_timedelta(wallclock_str)

            cpu_str = first_line[2]
            stats_dict['cpu'] = get_timedelta(cpu_str)

            if len(first_line[3]) > 0:
                stats_dict['queue'] = first_line[3]
            elif next_line:
                stats_dict['queue'] = next_line[3]

            if len(first_line[4]) > 0:
                stats_dict['ntasks'] = int(first_line[4])
            elif next_line:
                stats_dict['ntasks'] = int(next_line[4])

            if len(first_line[6]) > 0:
                stats_dict['status'] = first_line[6]
            elif next_line:
                stats_dict['status'] = next_line[6]

            if len(first_line[7]) > 0:
                stats_dict['exit_code'] = int(first_line[7].split(':')[0])
            elif next_line:
                stats_dict['exit_code'] = int(next_line[7].split(':')[0])

            # stats_dict['mem'] = 0 #float(new_line.split(' ')[4])*int(new_line.split(' ')[3])
        except:
            print('SLURM: Error reading job stats')
    with os.popen('squeue --format %%S -h -j '+str(job_id)) as f:
        try:
            line = f.readline()
            if len(line) > 0:
                stats_dict['start_time'] = line
            else:
                stats_dict['start_time'] = ""
        except:
            print('SLURM: Error getting start time')
    return stats_dict


def job_stats_enhanced(job_id):
    """
    Get full job and step stats for job_id
    """
    stats_dict = {}
    with os.popen('sacct --noheader --format JobId,Elapsed,TotalCPU,Partition,NTasks,AveRSS,State,ExitCode,start,end -P -j '+str(job_id)) as f:
        try:
            line = f.readline()
            cols = line.split('|')
            stats_dict['job_id'] = cols[0]
            stats_dict['wallclock'] = get_timedelta(cols[1])
            stats_dict['cpu'] = get_timedelta(cols[2])
            stats_dict['queue'] = cols[3]
            stats_dict['status'] = cols[6]
            stats_dict['exit_code'] = cols[7].split(':')[0]
            stats_dict['start'] = cols[8]
            stats_dict['end'] = cols[9]

            steps = []
            for line in f:
                step = {}
                cols = line.split('|')
                step_val = cols[0].split('.')[1]
                step['step'] = step_val
                step['wallclock'] = get_timedelta(cols[1])
                step['cpu'] = get_timedelta(cols[2])
                step['ntasks'] = cols[4]
                step['status'] = cols[6]
                step['exit_code'] = cols[7].split(':')[0]
                step['start'] = cols[8]
                step['end'] = cols[9]
                steps.append(step)
            stats_dict['steps'] = steps
        except:
            with os.popen('squeue -j %s' % str(job_id)) as f:
                try:
                    f.readline() # read header
                    for line in f:
                        new_line = re.sub(' +', ' ', line.strip())
                        job_id = int(new_line.split(' ')[0])
                        state = new_line.split(' ')[4]
                        stats_dict['job_id'] = str(job_id)
                        stats_dict['status'] = state
                except:
                    print('SLURM: Error reading job stats')
    with os.popen('squeue --format %%S -h -j '+str(job_id)) as f:
        try:
            line = f.readline()
            if len(line) > 0:
                stats_dict['start_time'] = line
            else:
                stats_dict['start_time'] = ""
        except:
            print('SLURM: Error getting start time')
    return stats_dict

def is_in_queue(job_id):
    with os.popen('squeue -j %s' % job_id) as f:
        try:
            f.readline() # read header
            for line in f:
                new_line = re.sub(' +',' ',line.strip())
                q_id = int(new_line.split(' ')[0])
                if q_id == job_id:
                    return True
        except e:
            pass
    return False


def running_stats(job_id):
    stats_dict = {}
    with os.popen('sacct --noheader --format Elapsed -j '+str(job_id)) as f:
        try:
            line = f.readline()
            new_line = re.sub(' +', ' ', line.strip())
            stats_dict['wallclock']  = get_timedelta(new_line)
        except:
            pass

    with os.popen('sstat --noheader --format AveCPU,AveRSS,NTasks -j '+str(job_id)) as f:
        try:
            line = f.readline();
            new_line = re.sub(' +', ' ', line.strip())
            ntasks = int(new_line.split(' ')[2])
            stats_dict['mem']  = float(new_line.split(' ')[1].replace('K',''))*ntasks
            stats_dict['cpu']  = '-' #float(new_line.split(' ')[0])*ntasks
        except:
            pass

    return stats_dict









