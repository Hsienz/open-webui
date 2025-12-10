from functools import cache
from fastapi.routing import APIRouter
from open_webui.utils.auth import get_verified_user
from fastapi import Depends
from open_webui.docker.containers import container
from pydantic import BaseModel
from typing import Optional


router = APIRouter()


class ModelForm(BaseModel):
    model: str
    port: int
    gpus: Optional[str] = None
    tool_call_parser: Optional[str] = None
    tensor_parallel_size: Optional[int] = None


@router.get("/models")
async def get_model_container(user=Depends(get_verified_user)):
    return container.get_model_container_list(use_cache=True)


@router.post("/model/toggle")
async def toggle_model_container(request: ModelForm, user=Depends(get_verified_user)):
    port = 8000
    await container.toggle_model_container(
        model=request.model,
        gpus="device={}".format(request.gpus) if request.gpus else None,
        emit=True,
        ports={"{}/tcp".format(port): request.port},
        port=port,
        tensor_parallel_size=request.tensor_parallel_size,
        tool_call_parser=request.tool_call_parser,
    )


@router.get("/model/{model}")
async def get_container_status(model: str, user=Depends(get_verified_user)):
    return container.get_model_container_status(model, use_cache=True)
