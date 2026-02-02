import threading
from fastapi import Depends
from fastapi.routing import APIRouter
import nvsmi
from open_webui.socket.main import sio
from open_webui.utils.auth import get_verified_user
import time

router = APIRouter()


class Monitor:
    def __init__(self) -> None:
        self.stop_monitoring = False
        self.task: threading.Thread | None = None


monitor = Monitor()


def _get_gpu_info():
    gpus = list(nvsmi.get_gpus())
    return [x.__dict__ for x in gpus]


@router.get("/get_gpu_info")
def get_gpu_info(user=Depends(get_verified_user)):
    return _get_gpu_info()


async def _start_monitoring():
    while not monitor.stop_monitoring:
        data = {"type": "monitor:gpu", "data": _get_gpu_info()}
        await sio.emit("monitor", data)
        time.sleep(3)


@router.post("/start")
def start_monitor(user=Depends(get_verified_user)):
    if monitor.task and not monitor.stop_monitoring:
        return {"status": "already running"}
    monitor.stop_monitoring = False
    monitor.task = threading.Thread(target=_start_monitoring)
    return {"status": "running"}


@router.post("/stop")
def stop_monitor(user=Depends(get_verified_user)):
    monitor.stop_monitoring = True
    if monitor.task:
        monitor.task.join()

    monitor.task = None
    return {"status": "stopped"}
