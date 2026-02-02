import asyncio
from concurrent.futures import thread
from copy import Error
import logging
import threading
from typing import Optional
import docker
from docker.models.containers import Container as DockerContainer
import os
from docker.types import DeviceRequest
from open_webui.socket.main import sio
from enum import IntEnum, auto
import re


log = logging.getLogger(__name__)


class ContainerStatus(IntEnum):
    Closed = auto()
    Start = auto()
    Created = auto()
    Destroyed = auto()
    Die = auto()

    @classmethod
    def from_str(cls, s: str):
        for x in ContainerStatus:
            if x.to_str() == s:
                return x
        return None

    def to_str(self):
        return self.name.lower()


class ContainerInfo:
    def __init__(self, container: Optional[DockerContainer]):
        self.status: ContainerStatus = ContainerStatus.Closed
        if container is not None:
            self.set_status_with_priority(container.status)
        self.container = container
        self.device_ids: str = ""
        self.port: int | None = None
        self.tensor_parallel_size: int | None = None
        self.gpu_memory_utilization: float | None = None

    def set_status_with_priority(self, status: str | ContainerStatus) -> bool:
        if isinstance(status, str):
            temp = ContainerStatus.from_str(status)
            if temp is None:
                return False
            status = temp

        self.status = status
        return True


class Container:
    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
        except Exception as e:
            pass
        self.info_mapping: dict[str, ContainerInfo] = {}

        self.emit_thread: threading.Thread | None = None
        self.stop_emit = False

        self.get_model_container_list()

    def run_model_container(self, model: str, command=None, **kwargs):
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
        return container

    async def _wait_log_finish(self, event: threading.Event):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, event.wait)

    def stop_model_container(self, model: str):
        info = self.info_mapping.get(model)
        if info is None:
            log.warning("info for %s is not found", model)
            return

        container = info.container
        if container is not None:
            container.stop()
            self.info_mapping[model] = ContainerInfo(None)

    def run_model_container_wrapper(
        self,
        model: str,
        port: int,
        gpu_memory_utilization: Optional[float] = None,
        tensor_parallel_size: Optional[int] = None,
        tool_call_parser: Optional[str] = None,
        **kwargs,
    ):
        info = self.info_mapping.get(model)
        if info is None:
            log.warning("info for %s is not found", model)
            return
        container = info.container
        command = []
        command.append("--model")
        command.append(Container.parse_model_container_name_to_model(model))

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
        container = self.run_model_container(
            model=model,
            command=command,
            **kwargs,
        )

        info.container = container
        info.set_status_with_priority(container.status)
        info.port = port
        info.tensor_parallel_size = tensor_parallel_size
        info.gpu_memory_utilization = gpu_memory_utilization
        device_requests = kwargs.get("device_requests")
        log.debug("kwargs: %s", kwargs)
        log.debug("device_requests: %s", device_requests)
        if device_requests and isinstance(device_requests, list):
            request: DeviceRequest = device_requests[0]
            info.device_ids = request.device_ids

        self.info_mapping[model] = info
        if container.id is None:
            raise Error(
                "Model Container do not create successfully for {}".format(model)
            )

    def start_emit_thread(self):
        if self.emit_thread is None or not self.emit_thread:
            self.stop_emit = False
            self.emit_thread = threading.Thread(
                target=self.emit_container_events_wrapper
            )

    def stop_emit_thread(self):
        self.stop_emit = True
        if self.emit_thread:
            self.emit_thread.join()

        self.emit_thread = None

    async def _emit_model_container_info(self, name, status, id):
        data = {
            "type": "container:model",
            "data": {"name": name, "status": status, "id": id},
        }
        log.debug(data)
        await sio.emit("container", data)

    def emit_container_events_wrapper(self):
        asyncio.run(self.emit_container_events())

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
            info = self.info_mapping.get(name)
            if info and status:
                if info.set_status_with_priority(status):
                    await self._emit_model_container_info(
                        name, info.status.to_str(), id
                    )

    def get_model_container_status(self, model: str):
        info = self.info_mapping.get(model)
        if not info:
            log.warning("container %s not found", model)
            return
        return {
            "status": info.status.to_str(),
            "device_ids": info.device_ids,
            "port": info.port,
            "tensor_parallel_size": info.tensor_parallel_size,
            "gpu_memory_utilization": info.gpu_memory_utilization,
        }

    @classmethod
    def parse_model_container_name_to_model(cls, name: str) -> str:
        return "/".join(name.split("--")[1:])

    def get_model_container_list(self, use_cache: bool = False):
        if use_cache:
            return sorted(container.info_mapping.keys())
        else:
            path = "/opt/models"
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

            for x in dirs:
                if x not in self.info_mapping:
                    self.info_mapping[x] = ContainerInfo(None)

            return dirs


container = Container()
