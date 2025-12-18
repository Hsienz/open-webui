import asyncio
from base64 import decode
from copy import Error
import logging
import threading
from typing import Optional
import docker
from docker import errors
from docker.models.containers import Container as DockerContainer
import os
from fastapi import HTTPException
from open_webui.socket.main import sio
from redis import client
from starlette.datastructures import CommaSeparatedStrings
import re


log = logging.getLogger(__name__)


class Container:
    def __init__(self) -> None:
        self.client = docker.from_env()
        self.model_mapping: dict[str, Optional[DockerContainer]] = {}
        self.emit_thread = None
        self.log_thread = None
        self.stop_emit = False

        for model in Container.get_model_container_list():
            try:
                self.model_mapping[model] = self.client.containers.get(model)
            except errors.NotFound:
                self.model_mapping[model] = None

    async def run_model_container(self, model: str, command=None, **kwargs):
        container = self.client.containers.run(
            image="vllm/vllm-openai:latest",
            command=command,
            detach=True,
            remove=True,
            volumes={
                "/root/.cache/huggingface": {
                    "bind": "/root/.cache/hugginface",
                    "mode": "ro",
                },
            },
            **{k: v for k, v in kwargs.items() if v is not None},
        )

        self.model_mapping[model] = container

        if self.log_thread is None or not self.log_thread.is_alive():
            event = threading.Event()
            self.log_thread = threading.Thread(
                target=self.follow_logs_until_match,
                args=[model, r"Application startup complete\.$", event],
            )
            self.log_thread.start()

            await self._wait_log_finish(event=event)
            await self._emit_model_container_info(
                name=model, status="started", id=container.id
            )

        return container

    async def _wait_log_finish(self, event: threading.Event):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, event.wait)

    async def toggle_model_container(
        self,
        model: str,
        port: int,
        gpu_memory_utilization: Optional[float] = None,
        tensor_parallel_size: Optional[int] = None,
        tool_call_parser: Optional[str] = None,
        **kwargs,
    ):
        if container := self.model_mapping.get(model):
            container.stop()
            self.model_mapping[model] = None
        else:
            command = []
            command.append("--model")
            command.append(model)

            command.append("--port")
            command.append(port)

            command.append("--enable-auto-tool")
            command.append("--tool-call-parser")
            command.append("hermes")
            if gpu_memory_utilization is not None:
                command.append("--gpu_memory_utilization")
                command.append(gpu_memory_utilization)

            if tensor_parallel_size is not None:
                command.append("--tensor_parallel_size")
                command.append(tensor_parallel_size)

            if tool_call_parser is not None:
                command.append("--tool-call-parser")
                command.append(tool_call_parser)

            command = [str(c) for c in command]
            container = await self.run_model_container(
                model=model,
                command=command,
                **kwargs,
            )

            if container.id is None:
                raise Error(
                    "Model Container do not create successfully for {}".format(model)
                )

    def start_emit_thread(self):
        if self.emit_thread is None or not self.emit_thread.is_alive():
            self.stop_emit = False
            self.emit_thread = threading.Thread(target=self._run_async_emit)
            self.emit_thread.start()

    def stop_emit_thread(self):
        self.stop_emit = True
        if self.emit_thread:
            self.emit_thread.join()

        self.emit_thread = None

    def _run_async_emit(self):
        asyncio.run(self.emit_container_events())

    def follow_logs_until_match(self, name, re_str: str, evnet: threading.Event):
        if container := self.model_mapping.get(name):
            if container is None:
                log.warning("container for %s not found", name)

            for line in container.logs(stream=True, follow=True):
                line = line.decode().strip()
                if re.search(re_str, line):
                    evnet.set()

    async def _emit_model_container_info(self, name, status, id):
        data = {
            "type": "container:model",
            "data": {"name": name, "status": status, "id": id},
        }
        log.debug(data)
        await sio.emit("container", data)

    async def emit_container_events(self):
        for event in self.client.events(decode=True):
            if self.stop_emit:
                self.stop_emit = False
                break
            # log.debug(event)
            actor = event.get("Actor", {})
            attributes = actor.get("Attributes", {})
            name = attributes.get("name")
            id = event.get("id")
            status = event.get("status")
            await self._emit_model_container_info(name, status, id)

    def get_model_container_status(self, model: str):
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
