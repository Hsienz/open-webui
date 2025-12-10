from copy import Error
import logging
from typing import Optional
import docker
from docker import errors
from docker.models.containers import Container as DockerContainer
import os
from fastapi import HTTPException
from open_webui.socket.main import sio


log = logging.getLogger(__name__)


class Container:
    def __init__(self) -> None:
        self.client = docker.from_env()
        self.model_mapping: dict[str, Optional[DockerContainer]] = {}

        for model in Container.get_model_container_list():
            try:
                self.model_mapping[model] = self.client.containers.get(model)
            except errors.NotFound:
                self.model_mapping[model] = None

    async def run_model_container(self, **kwargs):
        model = kwargs["model"]
        command = []
        for k, v in kwargs:
            if v is None:
                continue

            command.append("--{}".format(k))
            command.append(v)

        container = self.client.containers.run(
            image="vllm/vllm-openai:latest",
            command=command,
            detach=True,
            remove=True,
            volumes={
                "~/.cache/huggingface": {
                    "bind": "/root/.cache/hugginface",
                    "mode": "ro",
                },
            },
        )

        self.model_mapping[model] = container

        return container

    async def toggle_model_container(self, emit=False, **kwargs):
        model = kwargs["model"]
        if container := self.model_mapping.get(model):
            container.stop()
            self.model_mapping[model] = None
        else:
            container = await self.run_model_container(**kwargs)

            if container.id is None:
                raise Error(
                    "Model Container do not create successfully for {}".format(model)
                )

        if emit:
            for event in self.client.events(decode=True):
                log.debug(event)
                id = event["id"]
                status = event["status"]
                if id == container.id:
                    await sio.emit(
                        "container",
                        {
                            "type": "container:model",
                            "data": {"model": model, "status": status},
                        },
                    )

                    if status == "start":
                        break

    def get_model_container_status(self, model: str, use_cache: bool = False):
        if use_cache:
            if model in self.model_mapping:
                container = self.model_mapping.get(model)
                return {"status": "close" if container is None else container.status}
        else:
            try:
                container = self.client.containers.get(model)
            except errors.NotFound:
                return {"status": "not exist"}

            self.model_mapping[model] = container
            return {"status": container.status}

    @classmethod
    def parse_model_container_name_to_model(cls, name: str) -> str:
        return "/".join(name.split("--")[1:])

    @classmethod
    def get_model_container_list(cls, use_cache: bool = False):
        if use_cache:
            return sorted(container.model_mapping.keys())
        else:
            path = "/root/.cache/huggingface/hub"
            dirs = []
            for name in os.listdir(path):
                if not os.path.isdir(os.path.join(path, name)):
                    continue
                splited = name.split("--")
                if len(splited) != 3 or splited[0] != "models":
                    log.warning(
                        "Format of model directory not acceptable, should be models--[model-maker]--[model-name], get %s, skipped",
                        name,
                    )
                    continue

                dirs.append(name)

            dirs.sort()
            return dirs


container = Container()
