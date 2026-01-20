from fastapi import Depends
from fastapi.routing import APIRouter
import asyncio
import nvsmi
from open_webui.socket.main import sio
from open_webui.utils.auth import get_verified_user

router = APIRouter()


class Monitor:
    def __init__(self) -> None:
        self.stop_monitoring = asyncio.Event()
        self.task: asyncio.Task | None = None


monitor = Monitor()


def _get_gpu_info():
    gpus = list(nvsmi.get_gpus())
    return [x.to_json() for x in gpus]


@router.get("/get_gpu_info")
def get_gpu_info(user=Depends(get_verified_user)):
    return _get_gpu_info()


async def _start_monitoring():
    while not monitor.stop_monitoring.is_set():
        data = {"type": "monitor:gpu", "data": _get_gpu_info()}
        await sio.emit("monitor", data)
        await asyncio.sleep(3)


@router.post("/start")
async def start_monitor(user=Depends(get_verified_user)):
    if monitor.task and not monitor.task.done():
        return {"status": "already running"}
    monitor.stop_monitoring.clear()
    monitor.task = asyncio.create_task(_start_monitoring())
    return {"status": "running"}


@router.post("/stop")
async def stop_monitor(user=Depends(get_verified_user)):
    monitor.stop_monitoring.set()
    if monitor.task:
        await monitor.task

    monitor.task = None
    return {"status": "stopped"}
