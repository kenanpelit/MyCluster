
import os
import re
import math
from string import Template
from subprocess import Popen, PIPE, check_output

"""

bjobs -u all -q emerald
bqueues -l emerald

"""


def scheduler_type():
    return 'lsf'

def name():
    lsid_output = check_output(['lsid']).splitlines()
    for line in lsid_output:
        if line.startswith('My cluster name is'):
            return line.rsplit(' ',1)[1].strip()

    return 'undefined'

def queues():
    queue_list = []
    
    with os.popen('bqueues -w -u `whoami`') as f:
        f.readline(); # read header
        for line in f:
            q = line.split(' ')[0].strip()
            queue_list.append(q)
    
    return queue_list

def available_tasks(queue_id):
    
    # split queue id into queue and parallel env
    # list free slots
    free_tasks = 0
    max_tasks = 0
    queue_name   = queue_id
    q_output = check_output(['bqueues',queue_name]).splitlines()
    for line in q_output:
        if line.startswith(queue_name):
            new_line = re.sub(' +',' ',line).strip()
            max_tasks = int(new_line.split(' ')[4])
            pen_tasks   = int(new_line.split(' ')[8])
            run_tasks   = int(new_line.split(' ')[9])
            sus_tasks   = int(new_line.split(' ')[10])
        

    return {'available' : max_tasks-run_tasks, 'max tasks' : max_tasks}

def tasks_per_node(queue_id):
    host_list = None
    q_output = check_output(['bqueues','-l',queue_id]).splitlines()
    for line in q_output:
        if line.startswith('HOSTS:'):
            host_list = line.strip().rsplit(' ',1)[1].replace('/','')
   
    bhosts_output = check_output(['bhosts','-l',host_list]).splitlines()
    line = re.sub(' +',' ',bhosts_output[2]).strip()
    tasks = int(line.split(' ')[3])    

    return tasks

def node_config(queue_id):
    # Find first node with queue and record node config
    #bqueues -l queue_id
    host_list = None
    config = {}
    q_output = check_output(['bqueues','-l',queue_id]).splitlines()
    for line in q_output:
        if line.startswith('HOSTS:'):
            host_list = line.strip().rsplit(' ',1)[1].replace('/','')

    bhosts_output = check_output(['bhosts','-l',host_list]).splitlines()
    line = re.sub(' +',' ',bhosts_output[2]).strip()
    tasks = int(line.split(' ')[3])
    line = re.sub(' +',' ',bhosts_output[6]).strip()
    memory = int(line.split(' ')[11].replace('G',''))
    config['max task']   = tasks
    config['max thread'] = tasks
    config['max memory'] = memory
                        
    return config

def create_submit(queue_id,**kwargs):

    queue_name   = queue_id
    
    num_tasks = 1
    if 'num_tasks' in kwargs:
        num_tasks = kwargs['num_tasks']
    
    tpn = tasks_per_node(queue_id)
    queue_tpn = tpn
    if 'tasks_per_node' in kwargs:
        tpn = min(tpn,kwargs['tasks_per_node'])
    
    nc = node_config(queue_id)
    qc = available_tasks(queue_id)
    
    num_tasks = min(num_tasks,qc['max tasks'])
    
    num_threads_per_task = nc['max thread']
    if 'num_threads_per_task' in kwargs:
        num_threads_per_task = kwargs['num_threads_per_task']
    num_threads_per_task = min(num_threads_per_task,int(math.ceil(float(nc['max thread'])/float(tpn))))
    
    my_name = "myclusterjob"
    if 'my_name' in kwargs:
        my_name = kwargs['my_name']
    my_output = "myclusterjob.out"
    if 'my_output' in kwargs:
        my_output = kwargs['my_output']
    if 'my_script' not in kwargs:
        pass
    my_script = kwargs['my_script']
    if 'user_email' not in kwargs:
        pass
    user_email = kwargs['user_email']
    
    project_name = 'default'
    if 'project_name' in kwargs:
        project_name = kwargs['project_name']

    wall_clock = '12:00:00'
    if 'wall_clock' in kwargs:
        wall_clock = str(kwargs['wall_clock'])+':00'
   
    num_nodes = int(math.ceil(float(num_tasks)/float(tpn)))

    num_queue_slots = num_nodes*queue_tpn
    
    script=Template(r"""#!/bin/bash
#
# LSF job submission script generated by MyCluster 
#
# Job name
#BSUB -J $my_name
# The batch system should use the current directory as working directory.
#BSUB -cwd
# Send status information to this email address. 
#BSUB -u $user_email
# Send me an e-mail when the job starts. 
#BSUB -B
# Send me an e-mail when the job has finished. 
#BSUB -N
# Redirect output stream to this file.
#BSUB -oo ./$my_output.%J
# Which project should be charged 
#BSUB -P $project_name
# Queue name
#BSUB -q $queue_name
# Number of tasks
#BSUB -n $num_tasks
# Number of tasks per node
#BSUB -R "span[ptile=$tpn]"
# Exclusive node use
#BSUB -x
# How much wallclock time will be required?
#BSUB -W $wall_clock

export JOBID=$LSB_JOBID

export MYCLUSTER_QUEUE=$queue_name
export MYCLUSTER_JOB_NAME=$my_name
export NUM_TASKS=$num_tasks
export TASKS_PER_NODE=$tpn
export THREADS_PER_TASK=$num_threads_per_task
export NUM_NODES=$num_nodes

# OpenMP configuration
export OMP_NUM_THREADS=$$THREADS_PER_TASK
export OMP_PROC_BIND=true
export OMP_PLACES=sockets

# OpenMPI
export OMPI_CMD="mpiexec -n $$NUM_TASKS -npernode $$TASKS_PER_NODE -bysocket -bind-to-socket" 

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

if [ "$$LSB_DJOB_HOSTFILE" ]; then
        #! Create a machine file:
        cat $$LSB_DJOB_HOSTFILE | uniq > machine.file.$$JOBID
        echo -e "\nNodes allocated:\n================"
        echo `cat machine.file.$$JOBID | sed -e 's/\..*$$//g'`
fi

echo -e "\nnumtasks=$num_tasks, numnodes=$num_nodes, tasks_per_node=$tpn (OMP_NUM_THREADS=$$OMP_NUM_THREADS)"

echo -e "\nExecuting command:\n==================\n$my_script\n"

# Run user script
./$my_script

# Report on completion
echo -e "\nJob Complete:\n==================\n"
echo -e "\nRecording hardware setup\n==================\n"
mycluster --sysscribe $$JOBID
if [ "$$MYCLUSTER_APP_NAME" ]; then
    mycluster --jobid $$JOBID --appname=$$MYCLUSTER_APP_NAME
fi
if [ "$$MYCLUSTER_APP_DATA" ]; then
    mycluster --jobid $$JOBID --appdata=$$MYCLUSTER_APP_DATA
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
                                   'num_queue_slots':num_queue_slots,
                                   'num_nodes':num_nodes,
                                   'project_name': project_name,
                                   'wall_clock' : wall_clock,
                                   })
    
    return script_str

def submit(script_name):
    job_id = None
    with os.popen('bsub <'+script_name) as f:
        job_id = int(f.readline().split(' ')[1].replace('<','').replace('>',''))
        # Get job id and record in database
    return job_id

def delete(job_id):
    with os.popen('bkill '+job_id) as f:
        pass
    
def status():
    status_dict = {}
    with os.popen('bjobs -w') as f:
        try:
            f.readline(); # read header
            for line in f:
                new_line = re.sub(' +',' ',line.strip())
                job_id = int(new_line.split(' ')[0])
                state = new_line.split(' ')[2]
                if state == 'RUN':
                    status_dict[job_id] = 'r'
                else:
                    status_dict[job_id] = state
        except e:
            print e
        
    return status_dict
    
def job_stats(job_id):
    stats_dict = {}
    with os.popen('bacct '+str(job_id)) as f:
        try:
            line = f.readline(); 
            new_line = re.sub(' +',' ',line.strip())
            stats_dict['wallclock']  = new_line.split(' ')[0]
            stats_dict['cpu'] = new_line.split(' ')[1]
            stats_dict['queue'] = new_line.split(' ')[2]
            stats_dict['mem'] = '-'#float(new_line.split(' ')[4])*int(new_line.split(' ')[3])
        except:
            print('LSF: Error reading job stats')
            
    return stats_dict

def running_stats(job_id):
    stats_dict = {}
    with os.popen('sacct --noheader --format Elapsed -j '+str(job_id)) as f:
        try:
            line = f.readline(); 
            new_line = re.sub(' +',' ',line.strip())
            stats_dict['wallclock']  = new_line.split(' ')[0]
        except:
            pass
        
    with os.popen('sstat --noheader --format AveCPU,AveRSS,NTasks -j '+str(job_id)) as f:
        try:
            line = f.readline(); 
            new_line = re.sub(' +',' ',line.strip())
            ntasks = int(new_line.split(' ')[2])
            stats_dict['mem']  = float(new_line.split(' ')[1])*ntasks
            stats_dict['cpu']  = float(new_line.split(' ')[0])*ntasks
        except:
            pass
    
    return stats_dict
