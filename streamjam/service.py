import inspect
import websockets
import typing as tp
from functools import partial
from dataclasses import dataclass

from .base import final, deny_final_method_override, ServiceBase

if tp.TYPE_CHECKING:
    from .server import ClientHandler


@dataclass
class ServiceConfig:
    service_cls: tp.Type
    args: tp.Tuple
    kwargs: tp.Dict


class _Service:
    def __init__(self, **kwargs):
        ...

    @final
    def __new__(cls, *args, **kwargs):
        return ServiceConfig(cls, args, kwargs)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        deny_final_method_override(cls, Service)

    def _register_client(self):
        ...

    @final
    def dispatch(self, name: str, data=None, to: 'str | list[str]' = ...):
        ...

    @staticmethod
    @final
    def on_event(event_name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError(f"'on_event' method cannot be called for Service object.")

    @final
    async def set_name(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'def' method cannot be called for Service object.")

    @final
    async def join_group(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'def' method cannot be called for Service object.")

    @final
    async def leave_group(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'def' method cannot be called for Service object.")

    @final
    def disconnect_service(self):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'disconnect' method cannot be called for Service object.")

    @final
    def connect_service(self):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'connect' method cannot be called for Service object.")


class ServiceProxy:
    def __init__(self, service_name: str):
        self.__service_name = service_name
        self.__client_handler: 'tp.Optional[ClientHandler]' = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        deny_final_method_override(cls, Service)

    def __init_proxy(self, client_handler: 'ClientHandler'):
        self.__client_handler = client_handler

    @final
    def dispatch(self, name: str, data=None, to: 'str | list[str]' = ...):
        """Shadow for Service, does nothing"""
        raise AttributeError("'dispatch' method cannot be called for ServiceProxy object.")

    @staticmethod
    @final
    def on_event(event_name: str):
        def handler(fn):
            setattr(fn, 'service_event_handler', event_name)
            return fn

        return handler

    @final
    async def set_name(self, name: str):
        raise NotImplementedError

    @final
    async def join_group(self, name: str):
        raise NotImplementedError

    @final
    async def leave_group(self, name: str):
        raise NotImplementedError

    @final
    def disconnect_service(self):
        raise NotImplementedError

    @final
    def connect_service(self):
        raise NotImplementedError

    def __proxy_method_call(self, method_name):
        async def service_proxy_method(*args, **kwargs):
            # return self.__client_handler.call_service_method(self.__service_name, method_name, args, kwargs)
            print(f'self.__client_handler.call_service_method({self.__service_name}, {method_name}, {args}, {kwargs})')

        return service_proxy_method

    def __getattr__(self, method):
        return self.__proxy_method_call(method)


class AsyncServiceExecutor:
    def __init__(self, config: ServiceConfig):
        self.instance = config.service_cls(*config.args, **config.kwargs)

    async def execute_method(self, method_name, args, kwargs):
        if not hasattr(self.instance, method_name):
            raise AttributeError(f'Method {method_name!r} does not exist for {self.instance.__class__!r}')
        method = getattr(self.instance, method_name)
        if inspect.iscoroutine(method):
            # asyncio.create_task(method(*args, **kwargs))
            return await method(*args, **kwargs)
        else:
            partial_method = partial(method, *args, **kwargs)
            # asyncio.get_event_loop().run_in_executor(None, partial_method)
            return partial_method()


class SocketService(ServiceBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connections = {}

    async def connect(self, ws: websockets.WebSocketServerProtocol):
        connection_id = await self.on_connect(ws)
        if connection_id:
            self.connections[connection_id] = ws
        return connection_id

    async def on_connect(self, ws: websockets.WebSocketServerProtocol) -> str:
        return str(ws.id)

    async def on_disconnect(self, ws):
        ...
