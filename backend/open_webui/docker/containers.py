from copy import Error
import logging
import docker
from docker.models.containers import Container as DockerContainer
import os
from fastapi import HTTPException
from open_webui.socket.main import sio


log = logging.getLogger(__name__)


class Container:
    def __init__(self) -> None:
        self.client = docker.from_env()
        self.model_mapping: dict[str, DockerContainer] = {}

    async def run_model_container(self, model: str, **kwargs):
        command = ["--model", model]
        for k, v in kwargs:
            command.append(k)
            command.append(v)

        return self.client.containers.run(
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

    async def toggle_model_container(self, model: str, emit=False, **kwargs):
        if container := self.model_mapping.get(model):
            container.stop()
            del self.model_mapping[model]
        else:
            container = await self.run_model_container(model, **kwargs)

            if container.id is None:
                raise Error(
                    "Model Container do not create successfully for {}".format(model)
                )
            self.model_mapping[model] = container

        if emit:
            for event in self.client.events(decode=True):
                log.debug(event)
                id = event["id"]
                status = event["status"]
                if id == container.id:
                    await sio.emit(
                        "docker:container:model",
                        {"model": model, "id": id, status: status},
                    )

                    if status == "start":
                        break

    def get_model_container_status(self, model: str):
        container = self.client.containers.get(model)

        if container is None:
            raise HTTPException(400)

        return {"id": container.id, "status": container.status}

    @classmethod
    def get_model_container_list(cls):
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

            dirs.append("/".join(splited[1:]))

        dirs.sort()
        return dirs


container = Container()
