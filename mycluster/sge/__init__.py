import os
import re
from string import Template

""""
SGE notes

list PARALLEL_ENV: qconf -spl
details: qconf -sp $PARALLEL_ENV

List avail resources: qstat -pe $PARALLEL_ENV -g c

submit: qsub -pe $PARALLEL_ENV $NUM_SLOTS

delete: qdel job-id

checks: qalter -w p job-id
        qalter -w v job-id
        
        qconf -shgrp_resolved @el6nodes
        
list hosts qhost -q
        
Useful sites:
https://confluence.rcs.griffith.edu.au/display/v20zCluster/SGE+cheat+sheet
http://www.uibk.ac.at/zid/systeme/hpc-systeme/common/tutorials/sge-howto.html

"""

def queues():
    
    # list all parallel env
    # for parallel_env list queues associated
    # Find first node with queue and record node config
    
    queue_list = []
    parallel_env_list = []
    
    with os.popen('qconf -spl') as f:
        for line in f:
            parallel_env_list.append(line.strip())

    for parallel_env in parallel_env_list:
        with os.popen('qstat -pe '+parallel_env+' -g c') as f:
            f.readline(); # read header
            f.readline(); # read separator
            for line in f:
                queue_name = line.split(' ')[0]
                queue_list.append(parallel_env+':'+queue_name)
    
    return queue_list

def available_tasks(queue_id):
    
    # split queue id into queue and parallel env
    # list free slots
    free_tasks = 0
    max_tasks = 0
    parallel_env = queue_id.split(':')[0]
    queue_name   = queue_id.split(':')[1]
    with os.popen(' qstat -pe '+parallel_env+' -g c') as f:
        f.readline(); # read header
        f.readline(); # read separator
        for line in f:
            # remove multiple white space
            new_line = re.sub(' +',' ',line)
            qn = new_line.split(' ')[0]
            if qn == queue_name:
                free_tasks = int(new_line.split(' ')[4])
                max_tasks = int(new_line.split(' ')[5])
                
    return {'available' : free_tasks, 'max tasks' : max_tasks}

def tasks_per_node(queue_id):
    parallel_env = queue_id.split(':')[0]
    queue_name   = queue_id.split(':')[1]
    tasks=0
    with os.popen('qconf -sq '+queue_name) as f:
        for line in f:
            if line.split(' ')[0] == 'slots':
                new_line = re.sub(' +',' ',line)
                tasks = int(new_line.split(' ')[1])
    return tasks

def node_config(queue_id):
    # Find first node with queue and record node config
    parallel_env = queue_id.split(':')[0]
    queue_name   = queue_id.split(':')[1]
    host_group=0
    with os.popen('qconf -sq '+queue_name) as f:
        for line in f:
            if line.split(' ')[0] == 'hostlist':
                new_line = re.sub(' +',' ',line)
                host_group = new_line.split(' ')[1]
    
    host_name=''
    with os.popen('qconf -shgrp_resolved '+host_group) as f:
        for line in f:
            host_name = line.split(' ')[0]
            break

    config = {}

    with os.popen('qhost -q -h '+host_name) as f:
        f.readline(); # read header
        f.readline(); # read separator
        for line in f:
            if line[0] != ' ':
                name = line.split(' ')[0]
                if name != 'global':
                    new_line = re.sub(' +',' ',line)
                    config['max task']   = int(new_line.split(' ')[4])
                    config['max thread'] = int(new_line.split(' ')[5])
                    config['max memory'] =     new_line.split(' ')[7]
                
    return config

def create_submit(queue_id,**kwargs):

    parallel_env = queue_id.split(':')[0]
    queue_name   = queue_id.split(':')[1]
    
    num_tasks = 1
    if 'num_tasks' in kwargs:
        num_tasks = kwargs['num_tasks']
    num_threads_per_task = 1
    if 'num_threads_per_task' in kwargs:
        num_threads_per_task = kwargs['num_threads_per_task']
    
    tpn = tasks_per_node(queue_id)
    queue_tpn = tpn
    if 'tasks_per_node' in kwargs:
        tpn = min(tpn,kwargs['tasks_per_node'])
    
    nc = node_config(queue_id)
    
    num_tasks = min(num_tasks,nc['max task'])
    num_threads_per_task = min(num_threads_per_task,nc['max thread']/tpn)
    
    my_name = "myclusterjob"
    if 'my_name' in kwargs:
        my_name = kwargs['my_name']
    my_output = "myclusterjob.out"
    if 'my_output' in kwargs:
        my_output = kwargs['my_output']
    if 'my_script' not in kwargs['my_script']:
        pass
    my_script = kwargs['my_script']
    if 'user_email' not in kwargs['user_email']:
        pass
    user_email = kwargs['user_email']
    
    
    num_nodes = num_tasks*tpn

    num_queue_slots = num_nodes*queue_tpn
    
    script=Template(r"""#!/bin/bash

# Job name
#$$ -N $my_name
# The batch system should use the current directory as working directory.
#$$ -cwd
# Redirect output stream to this file.
#$$ -o $my_output
# Join the error stream to the output stream.
#$$ -j yes
# Send status information to this email address. 
#$$ -M $user_email
# Send me an e-mail when the job has finished. 
#$$ -m be
# Queue name
#$$ -q $queue_name
# Parallel environment
#$$ -pe $parallel_env $num_queue_slots

export NUM_TASKS=$num_tasks
export TASK_PER_NODE=$tpn
export THREADS_PER_TASK=$num_threads_per_task

export OMP_NUM_THREADS=$$THREADS_PER_TASK

export OMPI_CMD='mpiexec -n $$NUM_TASKS -npernode $$TASK_PER_NODE -bysocket -bind-to-socket' 
export MVAPICH_CMD=''
export IMPI_CMD=''

# Summarise environment
echo -e "JobID: $$JOB_ID\n======"
echo "Time: `date`"
echo "Running on master node: `hostname`"
echo "Current directory: `pwd`"

if [ "$$PE_HOSTFILE" ]; then
        #! Create a machine file:
        cat $$PE_HOSTFILE | uniq > machine.file.$$JOB_ID
        echo -e "\nNodes allocated:\n================"
        echo `cat machine.file.$$JOB_ID | sed -e 's/\..*$$//g'`
fi

echo -e "\nnumtasks=$num_tasks, numnodes=$num_nodes, tasks_per_node=$tpn (OMP_NUM_THREADS=$$OMP_NUM_THREADS)"

echo -e "\nExecuting command:\n==================\n$my_script\n"

# Run user script
./$my_script

# Report on completion
qstat -j $$JOB_ID

""")
    str = script.substitute({'my_name':my_name,
                       'my_script':my_script,
                       'my_output':my_output,
                       'user_email':user_email,
                       'queue_name':queue_name,
                       'parallel_env':parallel_env,
                       'num_queue_slots':num_queue_slots,
                       'num_tasks':num_tasks,
                       'tpn':tpn,
                       'num_threads_per_task':num_threads_per_task,
                       'num_queue_slots':num_queue_slots,
                       'num_nodes':num_nodes,
                       })
    
    return str

def submit(script_name):
    job_id = None
    with os.popen('qsub -terse'+script_name) as f:
        job_id = int(f.readline().strip())
        # Get job id and record in database
    return job_id

def delete(job_id):
    pass

def status(job_id=None):
    pass