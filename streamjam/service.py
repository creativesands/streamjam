import inspect
import websockets
import typing as tp
from dataclasses import dataclass

from .pubsub import PubSub
from .base import final, deny_final_method_override, ServiceEvent

if tp.TYPE_CHECKING:
    from .server import ClientHandler


@dataclass
class ServiceConfig:
    service_cls: tp.Type
    args: tp.Tuple
    kwargs: tp.Dict


class ServiceBase:
    ...


class Service(ServiceBase):
    def __init__(self, **kwargs):
        self.__pubsub: PubSub | None = None
        self.__name: str | None = None

    def __init_service__(self, name: str, pubsub: PubSub):
        self.__name = name
        self.__pubsub = pubsub

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        deny_final_method_override(cls, Service)

    @classmethod
    def configure(cls, *args, **kwargs):
        return ServiceConfig(cls, args, kwargs)

    @final
    def dispatch(
            self,
            name: str,
            data=None,
            priority: int = 1,
            rooms: str | list[str] = None,
            recipients: str | list[str] = None):
        self.__pubsub.publish(
            channel=f'$Service/{self.__name}',
            topic=name,
            message=ServiceEvent(name, self.__name, data),
            priority=priority,
            rooms=rooms,
            recipients=recipients
        )

    @final
    def on_event(self, event_name: str):
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

    @final
    def _register_client(self):
        ...


class ServiceProxy(ServiceBase):
    def __init__(self, service_name: str):
        self.__service_name__ = service_name
        self.__client_handler: 'tp.Optional[ClientHandler]' = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        deny_final_method_override(cls, Service)

    def __init_proxy__(self, client_handler: 'ClientHandler'):
        self.__client_handler = client_handler

    @final
    def dispatch(self, name: str, data=None, to: 'str | list[str]' = ...):
        """Shadow for Service, does nothing"""
        raise AttributeError("'dispatch' method cannot be called for ServiceProxy object.")

    @final
    def on_event(self, event_name: str):
        def handler(fn):
            setattr(fn, 'service_event_handler', (event_name, self))
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
        return ServiceMethodProxy(self.__service_name__, method_name, self.__client_handler)

    def __getattr__(self, method):
        return self.__proxy_method_call(method)


class ServiceMethodProxy:
    def __init__(self, service_name, method_name, client_handler):
        self.service_name = service_name
        self.method_name = method_name
        self.client_handler = client_handler

    async def __call__(self, *args, **kwargs):
        return await self.client_handler.trigger_service_method(self.service_name, self.method_name, args, kwargs)


class ServiceExecutor:
    async def execute_method(self, method_name, args, kwargs):
        raise NotImplementedError


class AsyncServiceExecutor(ServiceExecutor):
    def __init__(self, config: ServiceConfig, name: str, pubsub: PubSub):
        self.name = name
        self.pubsub = pubsub
        self.instance: Service = config.service_cls(*config.args, **config.kwargs)
        self.instance.__init_service__(self.name, self.pubsub)

    async def execute_method(self, method_name, *args, **kwargs):
        args = args or ()
        kwargs = kwargs or {}
        if not hasattr(self.instance, method_name):
            raise AttributeError(f'Method {method_name!r} does not exist for {self.instance.__class__!r}')
        method = getattr(self.instance, method_name)
        if inspect.iscoroutinefunction(method):
            # asyncio.create_task(method(*args, **kwargs))
            val = await method(*args, **kwargs)
            return val
        else:
            print('! Running non coro', method, args, kwargs)  # TODO: doesn't happen
            return method(*args, **kwargs)


class SocketService(Service):
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
