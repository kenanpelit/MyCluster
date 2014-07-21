import sys
import os
import time
import uuid
from fabric.api import env, run, cd, get, hide, settings, remote_tunnel, show
from fabric.tasks import execute
from fabric.decorators import with_settings

JOB_SCHEDULERS = ('SGE','SLURM','LSF','PBS','TORQUE','MAUI','LOADLEVELER')

scheduler = None 
job_db = None

def detect_scheduling_sys():

    if os.getenv('SGE_CLUSTER_NAME') != None:
        return my_import('mycluster.sge')
    
    if os.getenv('SLURMHOME') != None:
        return my_import('mycluster.slurm')
    
    if os.getenv('LSB_DEFAULTQUEUE') != None:
        return my_import('mycluster.lsf')
    
    return None

def queues():
    if scheduler != None:
        return scheduler.queues()
    else:
        return []

def remote_sites():
    if job_db != None:
        return job_db.remote_site_db
    else:
        return []
    
@with_settings(warn_only=True)
def remote_cmd():
    output_file =  '~/.mycluster/'+str(uuid.uuid4())
    with hide('output','running','warnings'), settings(warn_only=True): 
        run('mycluster -p >'+output_file,pty=False)
        import StringIO
        contents = StringIO.StringIO()
        get(output_file, contents)
        # operate on 'contents' like a file object here, e.g. 'print
        return contents.getvalue()
    
def remote_job_list(site):
    env.use_ssh_config = True
    return execute(remote_cmd,hosts=[site])

def print_timedelta(td):
    if (td.days > 0):
        if td.days > 1:
            out = str(td).replace(" days, ", ":")
        else:
            out = str(td).replace(" day, ", ":")
    else:
        out = "0:" + str(td)
    outAr = out.split(':')
    outAr = ["%02d" % (int(float(x))) for x in outAr]
    out   = ":".join(outAr)
    return out

def get_stats_time(stats):
    import datetime
    wallclock =  '-' if 'wallclock' not in stats else stats['wallclock']
    wallclock_delta = None
    cputime_delta = None
    try:
        wallclock_delta = datetime.timedelta(seconds=int(wallclock))
        wallclock = print_timedelta(wallclock_delta)
    except:
        pass
    cputime = '-' if 'cpu' not in stats else stats['cpu']
    try:
        cputime_delta = datetime.timedelta(seconds=int(cputime.split('.')[0]))
        cputime = print_timedelta(cputime_delta)
    except:
        pass
    
    time_ratio = None
    if cputime_delta and wallclock_delta:
        time_ratio = float(cputime_delta.total_seconds())/wallclock_delta.total_seconds()
    
    return cputime, wallclock, time_ratio

def printjobs(num_lines):
    print('User name: {0} {1}'.format(job_db.user_db['user'].first_name,job_db.user_db['user'].last_name))
    jobs = job_list()
    print('     | {0:^10} | {1:^10} | {2:^10} | {3:^12} | {4:^12} | {5:^5} | {6:^20} | {7:50}'.format('Job ID',
                                                                                             'Status',
                                                                                             'NTasks',
                                                                                             'CPU Time',
                                                                                             'Wallclock',
                                                                                             'Util %',
                                                                                             'Job Name',
                                                                                             'Job Dir')
          )
    for i,j in enumerate(jobs):
        status = jobs[j].status
        cputime, wallclock, time_ratio = get_stats_time(jobs[j].stats)
        efficiency = '-'
        if time_ratio:
            try:
                efficiency = time_ratio/(int(jobs[j].num_tasks) * int(jobs[j].threads_per_task))*100.0
                efficiency  = '{:.1f}'.format(efficiency)
            except:
                pass          
        
        if status == 'completed':
            print('{0:4} | {1:^10} | {2:^10} | {3:^10} | {4:^12} | {5:^12} | {6:^5} | {7:^20} | {8:50}'.format(i+1,
                                                             j,
                                                             status,
                                                             str(jobs[j].num_tasks)+' ('+str(jobs[j].threads_per_task)+')',
                                                             cputime,
                                                             wallclock,
                                                             efficiency,
                                                             jobs[j].job_name,
                                                             jobs[j].job_dir,
                                                             )
                  )
        elif status == 'running':
            stats = scheduler.running_stats(j)
            cputime, wallclock, time_ratio = get_stats_time(stats)
            efficiency = '-'
            if time_ratio:
                try:
                    efficiency = time_ratio/(int(jobs[j].num_tasks) * int(jobs[j].threads_per_task))*100.0
                    efficiency  = '{:.1f}'.format(efficiency)
                except:
                    pass          
            print('{0:4} | {1:^10} | {2:^10} | {3:^10} | {4:^12} | {5:^12} | {6:^5} | {7:^20} | {8:50}'.format(i+1,
                                                             j,
                                                             status,
                                                             str(jobs[j].num_tasks)+' ('+str(jobs[j].threads_per_task)+')',
                                                             cputime,
                                                             wallclock,
                                                             efficiency,
                                                             jobs[j].job_name,
                                                             jobs[j].job_dir,
                                                             )
                  )
        else:
            print('{0:4} | {1:^10} | {2:^10} | {3:^10} | {4:^10} | {5:^12} | {6:^5} | {7:^20} | {8:50}'.format(i+1,
                                                             j,
                                                             status,
                                                             str(jobs[j].num_tasks)+' ('+str(jobs[j].threads_per_task)+')',
                                                             '-',
                                                             '-',
                                                             efficiency,
                                                             jobs[j].job_name,
                                                             jobs[j].job_dir,
                                                             )
                  )
            
    remotes = remote_sites()
    for i,j in enumerate(remotes):
        print 'Remote Site: '+remotes[j].name
        remote_list = remote_job_list(remotes[j].user+'@'+remotes[j].name)
        for r in remote_list:
            print remote_list[r]

def print_queue_info():
    print('{0:25} | {1:^15} | {2:^15} | {3:^15} | {4:^15} | {5:^15}'.format('Queue Name','Node Max Task','Node Max Thread','Node Max Memory','Max Task','Available Task'))
    for q in queues():
        nc = scheduler.node_config(q)
        tpn = scheduler.tasks_per_node(q)
        avail = scheduler.available_tasks(q)
        print('{0:25} | {1:^15} | {2:^15} | {3:^15} | {4:^15} | {5:^15}'.format(q, tpn, nc['max thread'], nc['max memory'],avail['max tasks'],avail['available']))

def create_submit(queue_id,script_name=None,**kwargs):

    if job_db != None:
        if 'user_email' not in kwargs:
            email = job_db.user_db['user'].email
            if email != 'unknown':
                kwargs['user_email'] = email
    
    script = scheduler.create_submit(queue_id,**kwargs)
    
    if script_name != None:
        import os.path
        if not os.path.isfile(script_name):
            with open(script_name,'w') as f:
                f.write(script)
        else:
            print('Warning file: {0} already exists. Please choose a different name'.format(script_name))
    
    return script

def submit(script_name):
    
    job_id = -1
    import os.path
    if os.path.isfile(script_name):    
        job_id = scheduler.submit(script_name)
        if job_db != None:
            from mycluster.persist import Job
            job = Job(job_id,time.time())
            with open(script_name,'r') as f:
                for line in f:
                    if line.split('=')[0] == 'export NUM_TASKS':
                        job.num_tasks = line.split('=')[1].strip()
                    if line.split('=')[0] == 'export TASKS_PER_NODE':
                        job.tasks_per_node = line.split('=')[1].strip()
                    if line.split('=')[0] == 'export THREADS_PER_TASK':
                        job.threads_per_task = line.split('=')[1].strip()
                    if line.split('=')[0] == 'export NUM_NODES':
                        job.num_nodes = line.split('=')[1].strip()
                    if line.split('=')[0] == 'export MYCLUSTER_QUEUE':
                        job.queue = line.split('=')[1].strip()
                    if line.split('=')[0] == 'export MYCLUSTER_JOB_NAME':
                        job.job_name = line.split('=')[1].strip()
            
            job.script_name = script_name
            job.job_dir = os.path.dirname(os.path.abspath(script_name))
            job_db.add(job)
            job_db.add_queue(job.queue,scheduler.name())
    else:
        print('Error file: {0} does not exist.'.format(script_name))
        
    return job_id

def delete(job_id):
    scheduler.delete(job_id)

def add_remote(remote_site):
    if job_db != None:
        job_db.add_remote(remote_site)

def export(job_id):
    pass

def job_list():
    if job_db != None:
        return job_db.job_db
    return None
    
def get_job(job_id):
    if job_db != None:
        return job_db.get(job_id)
    return None

def my_import(name):
    mod = __import__(name)
    components = name.split('.')
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod

def get_directory():
    from os.path import expanduser
    home = expanduser("~")
    directory = home+'/.mycluster/'
    return directory

def create_directory():
    directory = get_directory()
    if not os.path.exists(directory):
        os.makedirs(directory)

def create_db():
    global job_db
    try:
        from mycluster.persist import JobDB
        job_db = JobDB()    
    except Exception as e:
        print 'Database failed to initialise. Error Message: ' + str(e)
        
    return job_db
        
def update_db():
    if scheduler != None:
        status_dict = scheduler.status()
        jobs = job_list()
        for j in jobs:
            if jobs[j].status != 'completed':
                if j in status_dict:
                    state = status_dict[j]
                    if state == 'r':
                        jobs[j].update_status('running')
                else:
                    jobs[j].update_status('completed')
                    jobs[j].update_stats(scheduler.job_stats(j))
                
def sysscribe_update(job_id):
    if job_db != None:
        from sysscribe import system
        job_db.get(job_id).update_sysscribe(system.system_dict())

def email_update(email):
    if job_db != None:
        job_db.user_db['user'].update_email(email)
def firstname_update(name):
    if job_db != None:
        job_db.user_db['user'].firstname(name)
def lastname_update(name):
    if job_db != None:
        job_db.user_db['user'].lastname(name)

def appname_update(job_id,appname):
    if job_db != None:
        job_db.get()['job_id'].appname(appname)
def appdata_update(job_id,appdata):
    if job_db != None:
        job_db.get()['job_id'].appdata(appdata)
    

def init():
    global scheduler
    scheduler = detect_scheduling_sys()
    create_directory()
    if create_db() != None:
        update_db()
    if not scheduler:
        print('No local job schedulers found')
    
    
"""
Module initialiser functions
"""
init()

