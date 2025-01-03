import uvicorn
import fcntl
from contextlib import asynccontextmanager
import asyncio
import logging
import copy

import rpyc
from rpyc.utils.server import ThreadedServer

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

from periodic_task import periodic_task
from reorganisation_task import reorganisation_task

from defines import SESSION_SECRET, FRONTEND_URL, RPYX_PORT, SLEEP_TIME


async def background_process(app: FastAPI):
    '''background_process() starts the scheduler ansd the rpyc-server'''
    app.logger.info("background_process() started")

    app.scheduler = BackgroundScheduler()
    app.scheduler.configure(
        misfire_grace_time=300,  # 5 Minuten
        coalesce=True
    )
    
    # Add background task
    app.scheduler.add_job(periodic_task, 'date', id='periodic_task_1', run_date=datetime.now() + timedelta(seconds=3))
    app.scheduler.add_job(periodic_task, 'interval', id='periodic_task_2', seconds=SLEEP_TIME)
    app.scheduler.add_job(reorganisation_task, 'interval', id='reorganisation_task', seconds=60*60*24)
    app.scheduler.start()

    protocol_config = {"allow_public_attrs": True, "allow_pickle": True}
    app.server = ThreadedServer(
       SchedulerService, port=RPYX_PORT, protocol_config=protocol_config
    )

    try:
        app.server._start_in_thread()
        #blocking server start
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        app.logger.error("Error while Server stopped with: "+str(e))  
       
    app.servers.close()
    app.servers = None

    app.scheduler.shutdown()
    app.scheduler = None



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code for Startup
    app.server = None
    app.scheduler = None
    app.scheduler_task = None
    try:
        #we need only one scheduler

        # +++++++
        _ = open("/tmp/fastapi.lock","w")
        _fd = _.fileno()
        fcntl.lockf(_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # +++++++

        app.scheduler_task =  asyncio.create_task(background_process(app))

    except BlockingIOError:
            pass

    app.logger.info("Server starts...")

    yield
    # Code  for Shutdown
    if app.server != None: app.server.close()
    if app.scheduler != None: app.scheduler.shutdown()
    if app.scheduler_task != None: app.scheduler_task.cancel(msg='Shutting down...')
    app.logger.info("Server shuts down...")

app = FastAPI(lifespan=lifespan, title="FastAPI MQTT Client", version="0.1.0", debug=False)
logging.basicConfig(level=logging.INFO)
app.logger = logging.getLogger("py_tas")

class SchedulerService(rpyc.Service):

    def on_connect(self, conn):
        # code that runs when a connection is created
        # (to init the service, if needed)
        app.logger.info("on_connect() called")

    def on_disconnect(self, conn):
        # code that runs after the connection has already closed
        # (to finalize the service, if needed)
        app.logger.info("on_disconnect() called")


    def exposed_add_job(self, func, *args, **kwargs):
        if app.scheduler is None: return
        return app.scheduler.add_job(func, *args, **kwargs)

    def exposed_modify_job(self, job_id, jobstore=None, **changes):
        if app.scheduler is None: return
        return app.scheduler.modify_job(job_id, jobstore, **changes)

    def exposed_reschedule_job(
        self, job_id, jobstore=None, trigger=None, **trigger_args
    ):
        if app.scheduler is None: return
        return app.scheduler.reschedule_job(job_id, jobstore, trigger, **trigger_args)

    def exposed_pause_job(self, job_id, jobstore=None):
        if app.scheduler is None: return
        return app.scheduler.pause_job(job_id, jobstore)

    def exposed_resume_job(self, job_id, jobstore=None):
        if app.scheduler is None: return
        return app.scheduler.resume_job(job_id, jobstore)

    def exposed_remove_job(self, job_id, jobstore=None):
        if app.scheduler is None: return
        app.scheduler.remove_job(job_id, jobstore)

    def exposed_get_job(self, job_id):
        if app.scheduler is None: return
        return app.scheduler.get_job(job_id)

    def exposed_get_jobs(self, jobstore=None):
        app.logger.info("get_jobs() called")
        if app.scheduler is None: return []
        return app.scheduler.get_jobs(jobstore)
    

#--------------------------------------------------
@app.middleware("http")
async def apply_x_forwarded_headers_to_client(request: Request, call_next):
    """Apply the x-forwarded-for to the client host if available"""
    ip_list = request.headers.get('x-forwarded-for')
    port = request.headers.get('x-forwarded-port')

    # Grab the client scope and turn it into a list
    client = list(request.scope.get('client'))

    # Apply our client and port if available
    if client is not None:
        if ip_list:
            client_ip = ip_list.split(',')
            client[0] = client_ip[0]
        if port:
            client[1] = int(port)

        # Transform it back into a tuple and update the request
        request.scope.update({'client': tuple(client)})

    response = await call_next(request)
    return response

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# allow requests from own frontend running on a different port
app.add_middleware(
    CORSMiddleware,
    # Work around for now :)
    allow_origins=[
        FRONTEND_URL,
        'http://localhost:*',
        'http://127.0.0.1:*',
        'http://192.168.1.*:*',
    ],
    allow_origin_regex=r"http?://(localhost|127\.0\.0\.1|192\.168\.1\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
#--------------------------------------------------
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root():
    '''root() redirect to client'''
    return RedirectResponse(url="/client/index.html", status_code=301)

app.mount("/client", StaticFiles(directory="client"), name="client")
@app.get("/client/{path:path}", include_in_schema=False)
async def get_client(path: str):
    print(path)
    if (path == ""): 
        return RedirectResponse(url="/client/index.html", status_code=301)
    return StaticFiles(directory="client")(path)

#--------------------------------------------------
@app.get("/jobs")
async def get_jobs():
    jobs = []
    try:
        conn = rpyc.connect("localhost", RPYX_PORT)
        conn_jobs  = conn.root.get_jobs() 
        jobs = copy.deepcopy(conn_jobs) # deep copy required for buld response
        conn.close() 
    except Exception as e:
        app.logger.error("Error while getting jobs: " + str(e))
        raise HTTPException(status_code=404, detail="No Items found")
        

    return [{"id": f"{obj.id}", "func": f"{obj.func.__name__}", "trigger": f"{obj.trigger}", "next_run_time": f"{obj.next_run_time}"} for obj in jobs]

#--------------------------------------------------
# extra routes
import api
app.include_router(api.router)

#--------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)