from fastapi.routing import APIRouter
from open_webui.utils.auth import get_verified_user
from fastapi import Depends
from open_webui.docker.containers import container
from pydantic import BaseModel


router = APIRouter()


class ModelForm(BaseModel):
    model: str


@router.get("/models")
async def get_model_container(user=Depends(get_verified_user)):
    return container.get_model_container_list()


@router.post("/model/toggle")
async def toggle_model_container(form_data: ModelForm, user=Depends(get_verified_user)):
    await container.toggle_model_container(form_data.model)


@router.get("/model/{model}")
async def get_container_status(model: str, user=Depends(get_verified_user)):
    return container.get_model_container_status(model)
