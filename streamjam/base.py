import inspect
import typing as tp
from functools import partial
from dataclasses import dataclass

if tp.TYPE_CHECKING:
    from .component import Component
    from .server import ClientHandler


@dataclass
class ComponentEvent:
    name: str
    source: 'Component'
    data: tp.Any


@dataclass
class ServerEvent:
    name: str


class ServiceBase:
    def __init__(self, **kwargs):
        pass

    def dispatch(self, name, data=None, to: 'str | list[str]' = '*'):
        pass


class ServiceProxyMeta(type):
    def __getitem__(self, item) -> type(ServiceBase):
        return item


class Service(metaclass=ServiceProxyMeta):

    @staticmethod
    def on_event(event_name):
        def handler(fn):
            setattr(fn, 'event_handler', event_name)
            return fn

        return handler


def final(fn):
    """A decorator to mark methods as final (non-overridable)."""
    setattr(fn, 'final', True)
    return fn


def deny_final_method_override(cls, base_cls):
    # Iterate through attributes of the base class (Service in this case)
    for name, value in base_cls.__dict__.items():
        # Check if the attribute is a method marked with `final`
        if callable(value) and getattr(value, 'final', False):
            # Check if this method was overridden in the subclass
            if getattr(cls, name) != value:
                raise PermissionError(
                    f"Method {name!r} should not be overridden in subclass {cls.__name__!r}"
                )


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
        raise NotImplementedError

    @final
    async def set_name(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise NotImplementedError

    @final
    async def join_group(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise NotImplementedError

    @final
    async def leave_group(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise NotImplementedError

    @final
    def disconnect(self):
        """Shadow for Proxy, does nothing"""
        raise NotImplementedError

    @final
    def connect(self):
        """Shadow for Proxy, does nothing"""
        raise NotImplementedError


class ServiceProxy:
    def __init__(self, service_name: str):
        self.__service_name = service_name
        self.__client_handler: tp.Optional[ClientHandler] = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        deny_final_method_override(cls, Service)

    def __init_proxy(self, client_handler: 'ClientHandler'):
        self.__client_handler = client_handler

    @final
    def dispatch(self, name: str, data=None, to: 'str | list[str]' = ...):
        """Shadow for Service, does nothing"""
        raise NotImplementedError

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
    def disconnect(self):
        raise NotImplementedError

    @final
    def connect(self):
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
