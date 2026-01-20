from functools import cache
from fastapi.routing import APIRouter
from open_webui.utils.auth import get_verified_user
from fastapi import BackgroundTasks, Depends
from open_webui.docker.containers import container
from pydantic import BaseModel
from typing import Optional
from docker.types import DeviceRequest
from open_webui.docker.containers import Container


router = APIRouter()


class ModelForm(BaseModel):
    model: str
    port: int
    device_ids: Optional[str] = None
    tool_call_parser: Optional[str] = None
    tensor_parallel_size: Optional[int] = None
    gpu_memory_utilization: Optional[float] = None


class StopModelForm(BaseModel):
    model: str


@router.get("/models")
async def get_model_container(user=Depends(get_verified_user)):
    return container.get_model_container_list(use_cache=False)


@router.post("/model/run")
async def run_model_container(
    request: ModelForm,
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
):
    port = 8000
    background_tasks.add_task(
        container.run_model_container_wrapper,
        model=request.model,
        name=request.model,
        ports={"{}/tcp".format(port): request.port},
        port=request.port,
        tensor_parallel_size=request.tensor_parallel_size,
        tool_call_parser=request.tool_call_parser,
        gpu_memory_utilization=request.gpu_memory_utilization,
        device_requests=[
            DeviceRequest(
                driver="nvidia",
                capabilities=[["gpu"]],
                device_ids=[id.strip() for id in request.device_ids.split(",")]
                if request.device_ids is not None
                else None,
                count=-1 if request.device_ids is None else None,
            )
        ],
    )

    return {}


@router.post("/model/stop")
async def stop_model_container(
    request: StopModelForm,
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
):
    background_tasks.add_task(container.stop_model_container, model=request.model)

    return {}


@router.get("/model/{model}")
async def get_container_status(model: str, user=Depends(get_verified_user)):
    return container.get_model_container_status(model)


@router.put("/emit/start")
async def start_emit(user=Depends(get_verified_user)):
    container.start_emit_thread()


@router.put("/emit/stop")
async def stop_emit(user=Depends(get_verified_user)):
    container.stop_emit_thread()
