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
        self.served_model_name: str = ""
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

    def run_model_container(self, command=None, **kwargs):
        log.debug(command, kwargs)
        container = self.client.containers.run(
            image="vllm/vllm-openai:latest",
            command=command,
            detach=True,
            remove=True,
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

    @staticmethod
    def is_running_in_docker() -> bool:
        return os.path.exists("/.dockerenv")

    @staticmethod
    def get_model_path(model: str) -> str:
        if Container.is_running_in_docker():
            return os.path.join("/opt/models", model)
        else:
            model_dir = os.getenv("MODEL_DIR")
            if model_dir is None:
                raise EnvironmentError("MODEL_DIR is not set")

            return os.path.join(model_dir, model)

    @staticmethod
    def is_model_folder(path: str) -> bool:
        if not os.path.isdir(path):
            return False
        config_path = os.path.join(path, "config.json")
        if not os.path.exists(config_path) or not os.path.isfile(config_path):
            return False
        return True

    def run_model_container_wrapper(
        self,
        model: str,
        port: int,
        served_model_name: str = "",
        gpu_memory_utilization: Optional[float] = None,
        tensor_parallel_size: Optional[int] = None,
        **kwargs,
    ):
        info = self.info_mapping.get(model)
        if info is None:
            log.warning("info for %s is not found", model)
            return
        container = info.container
        command = []
        command.append(Container.get_model_path(model))

        command.append("--port")
        command.append(8000)

        command.append("--enable-auto-tool")
        command.append("--tool-tool-parser")
        command.append("hermes")

        if served_model_name:
            command.append("--served-model-name")
            command.append(served_model_name)

        if gpu_memory_utilization is not None:
            command.append("--gpu_memory_utilization")
            command.append(gpu_memory_utilization)

        if tensor_parallel_size is not None:
            command.append("--tensor_parallel_size")
            command.append(tensor_parallel_size)

        command = [str(c) for c in command]
        container = self.run_model_container(
            command=command,
            **kwargs,
        )

        info.container = container
        info.set_status_with_priority(container.status)
        info.port = port
        info.tensor_parallel_size = tensor_parallel_size
        info.gpu_memory_utilization = gpu_memory_utilization
        info.served_model_name = served_model_name
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
            self.emit_thread.start()

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
            "model": model,
            "status": info.status.to_str(),
            "device_ids": info.device_ids,
            "served_model_name": info.served_model_name,
            "port": info.port,
            "tensor_parallel_size": info.tensor_parallel_size,
            "gpu_memory_utilization": info.gpu_memory_utilization,
        }

    def get_model_container_list(self, use_cache: bool = False):
        if use_cache:
            return sorted(container.info_mapping.keys())
        else:
            path = os.getenv("MODEL_DIR", "/opt/models")
            dirs = []
            for name in os.listdir(path):
                model_path = os.path.join(path, name)
                if not Container.is_model_folder(model_path):
                    continue

                dirs.append(name)

            dirs.sort()

            for x in dirs:
                if x not in self.info_mapping:
                    self.info_mapping[x] = ContainerInfo(None)

            return dirs


container = Container()
