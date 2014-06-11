MyCluster
=========

Utilities to support interacting with multiple HPC clusters

Tested with SGE 

SLURM interface under development

Example usage

List all queues
mycluster -q

Create
mycluster --create JOB_SCRIPT --jobqueue QUEUE --script SCRIPT --ntasks=TASKS --jobname=JOB_NAME

Submit
mycluster --submit JOB_SCRIPT

Delete job
mycluster --delete JOB_ID

Print job table
mycluster -p

Print help
mycluster --help

The SCRIPT to be executed by the JOB_SCRIPT can make use of the following predefined environment variables
```bash
export NUM_TASKS=
export TASKS_PER_NODE=
export THREADS_PER_TASK=
export NUM_NODES=

# OpenMP configuration
export OMP_NUM_THREADS=$THREADS_PER_TASK

# Default mpiexec commnads for each flavour of mpi
export OMPI_CMD="mpiexec -n $NUM_TASKS -npernode $TASKS_PER_NODE -bysocket -bind-to-socket"
export MVAPICH_CMD="mpiexec -n $$NUM_TASKS -ppn $$TASKS_PER_NODE -bind-to-socket"
export IMPI_CMD="mpiexec -n $$NUM_TASKS -ppn $$TASKS_PER_NODE"
```

In order to capture the relevant information it is recommended that the SCRIPT also exports the following
environment variables

```bash
# Application name
export MYCLUSTER_APP_NAME=
# Data size that typifies application performance for this job (e.g number of points or number of cells)
export MYCLUSTER_APP_DATA=
```