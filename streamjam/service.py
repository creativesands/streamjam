import time
import inspect
import logging
import asyncio
import websockets
import typing as tp
from asyncio import Semaphore
from dataclasses import dataclass
from collections import defaultdict
from websockets.asyncio.server import ServerConnection

import websockets.asyncio

from .pubsub import PubSub
from .base import final, deny_final_method_override, ServiceEvent

if tp.TYPE_CHECKING:
    from .server import SessionHandler


T = tp.TypeVar('T')


logger = logging.getLogger('streamjam.service')
logger.setLevel(logging.INFO)



@dataclass
class ServiceConfig:
    service_cls: tp.Type
    args: tp.Tuple
    kwargs: tp.Dict


class ServiceBase:
    ...


class Service(ServiceBase):
    __service_dependencies__ = {}
    __prop_defaults__ = {}

    def __init__(self, **kwargs):
        self.__pubsub: PubSub | None = None
        self.__name: str | None = None
        self.__message_queue__: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.__service_event_handlers: dict[str, set] = defaultdict(set)
        self.__service_event_handlers__ = self.__service_event_handlers
        self.__task_registry: set[asyncio.Task] = set()
        self.__state__ = {}  # Add state dictionary for properties
        self.__service_executors: dict[str, 'ServiceExecutor'] = {}  # FIXME: temporary hack to get service executors

        # Initialize service dependencies from class definition
        for name, proxy in self.__class__.__service_dependencies__.items():
            if isinstance(proxy, ServiceProxy):
                setattr(self, name, proxy)

        # Initialize properties from kwargs
        for name, value in kwargs.items():
            if name in self.__class__.__prop_defaults__:
                setattr(self, name, value)

    def __init_subclass__(cls, **kwargs):
        """
        Initialize service subclass by processing annotations and class attributes.
        Similar to Component's implementation, this:
        - Processes service dependencies (ServiceProxy instances)
        - Handles property defaults
        - Prevents overriding of final methods
        """
        super().__init_subclass__(**kwargs)
        deny_final_method_override(cls, Service)

        if not hasattr(cls, '__annotations__'):
            cls.__annotations__ = {}

        cls.__service_dependencies__ = {}
        cls.__prop_defaults__ = {}

        # Process annotations
        for name, ann_type in cls.__annotations__.items():
            default_value = cls.__dict__.get(name, ...)
            if inspect.isclass(ann_type) and issubclass(ann_type, (Service, ServiceProxy)):
                cls.__service_dependencies__[name] = default_value
            else:
                cls.__prop_defaults__[name] = default_value
                getter, setter = cls.__make_property(name)
                setattr(cls, name, property(getter, setter))

        # Process class attributes
        for attr_name in dir(cls):
            item = getattr(cls, attr_name)
            if isinstance(item, ServiceProxy):
                cls.__service_dependencies__[attr_name] = item

    async def __init_service__(self, name: str, pubsub: PubSub, service_executors: dict[str, 'ServiceExecutor']):
        """Initialize the service and run init (user defined __init__)"""
        self.__name = name
        self.__pubsub = pubsub
        self.__pubsub__ = pubsub
        self.__pubsub.register(self.__name, self.__message_queue__)
        self.__service_executors = service_executors
        self.create_task(self.__message_receiver())
        self._register_handlers()

        # Initialize service dependencies from class definition
        for name, proxy in self.__class__.__service_dependencies__.items():
            if isinstance(proxy, ServiceProxy):
                proxy.__init_proxy__(self.__service_executors)  # FIXME: remove this once we have a proper way to get service executors
        
        await self.init()

    async def init(self):
        """Override this method to initialize your service instead of __init__"""
        pass

    @classmethod
    def __make_property(cls, name):
        """Create a property with getter/setter for state management"""
        default_value = cls.__dict__.get(name)

        def getter(self):
            return self.__state__.get(name, default_value)

        def setter(self, value):
            self.__state__[name] = value

        return getter, setter

    def _register_handlers(self):
        """Register service event handlers using existing ServiceProxy decorators"""
        for attr_name in dir(self):
            handler = getattr(self, attr_name)
            if hasattr(handler, 'service_event_handler'):
                event_handler_data = getattr(handler, 'service_event_handler')
                if isinstance(event_handler_data, ServiceMethodProxy):
                    continue # Skip if handler is a ServiceMethodProxy - these are service dependencies 
                             # injected via ServiceClient and not actual event handlers
                event_name, service_proxy = getattr(handler, 'service_event_handler')
                # Use the same pattern as components
                self.__pubsub: PubSub
                self.__pubsub.subscribe(
                    sid=self.__name,
                    channel=f'$Service/{service_proxy.__service_name__}',
                    topic=event_name
                )
                self.__service_event_handlers[event_name].add(handler)

    async def __message_receiver(self):
        """Process incoming service events"""
        while True:
            event = await self.__message_queue__.get()
            if event.name in self.__service_event_handlers: 
                for handler in self.__service_event_handlers[event.name]:
                    self.create_task(handler(event))
            self.__message_queue__.task_done()

    @final
    def create_task(self, coro, name='$task') -> asyncio.Task:
        """Create and track service tasks"""
        task = asyncio.create_task(coro, name=name)
        self.__task_registry.add(task)
        task.add_done_callback(self.__task_registry.discard)
        return task

    @staticmethod
    @final
    def concurrency_limit(fn, n: int | None = None):
        """
        - Set a concurrency limit on a service method.
        - If `n` is `None`, there is no limit on the number of concurrent calls to the decorated
        method.
        - Otherwise, the decorated method will only allow `n` calls to run concurrently.

        Args:
            n (int | None): The concurrency limit.

        Returns:
            callable: The decorated function.
        """
        if n is None:
            return fn

        async def wrapper(self, *args, **kwargs):
            semaphore = getattr(self, '__concurrency_semaphore', None)
            if semaphore is None:
                semaphore = Semaphore(n)
                setattr(self, '__concurrency_semaphore', semaphore)

            async with semaphore:
                return await fn(self, *args, **kwargs)

        return wrapper

    @classmethod
    def configure(cls, *args, **kwargs):
        """
        Creates a `ServiceConfig` instance that can be used to configure
        an instance of the service.

        :param args: The positional arguments to be passed to the service
            constructor.
        :param kwargs: The keyword arguments to be passed to the service
            constructor.

        :return: A `ServiceConfig` instance.
        """
        return ServiceConfig(cls, args, kwargs)

    @final
    def dispatch(
            self,
            name: str,
            data=None,
            priority: int = 1,
            rooms: list[str] = None,
            recipients: list[str] = None,
            exclude: list[str] = None):
        """
        Publishes a service event to the PubSub system.

        :param name: The event name to be published.
        :param data: The data associated with the event.
        :param priority: The event priority.
        :param rooms: The rooms to which the event should be published.
        :param recipients: The specific recipients to which the event should be published.

        The event is published to the channel that is specific to this service, and the event name is
        prefixed with the service name.

        This method is marked as `final` to prevent subclasses from overriding it.
        """
        if self.__pubsub is None:
            raise RuntimeError('Service is not initialized. No PubSub instance found.')
        
        self.__pubsub.publish(
            channel=f'$Service/{self.__name}',
            event=ServiceEvent(name, self.__name, data, priority),
            rooms=rooms,
            recipients=recipients,
            exclude=exclude
        )

    @final
    def on_event(self, event_name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError(f"'on_event' method cannot be called for Service object.")

    @final
    async def set_name(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'set_name' method cannot be called for Service object.")

    @final
    async def join_group(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'join_group' method cannot be called for Service object.")

    @final
    async def leave_group(self, name: str):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'leave_group' method cannot be called for Service object.")

    @final
    def disconnect_service(self):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'disconnect_service' method cannot be called for Service object.")

    @final
    def connect_service(self):
        """Shadow for Proxy, does nothing"""
        raise AttributeError("'connect_service' method cannot be called for Service object.")


class ServiceProxy(ServiceBase):
    """
    ServiceProxy is a proxy object for Service objects on the server.
    It provides a way for Components to interact with Services without having a direct reference to the Service object.
    """

    def __init__(self, service_name: str):
        self.__service_name__ = service_name
        # self.__session_handler: 'tp.Optional[SessionHandler]' = None
        self.__service_executors: dict[str, 'ServiceExecutor'] = {}
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        deny_final_method_override(cls, Service)

    # def __init_proxy__(self, session_handler: 'SessionHandler'):
    #     self.__session_handler = session_handler

    def __init_proxy__(self, service_executors: dict[str, 'ServiceExecutor']):
        self.__service_executors = service_executors

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
        return ServiceMethodProxy(self.__service_name__, method_name, self.__service_executors)

    def __getattr__(self, method):
        return self.__proxy_method_call(method)


class ServiceClientFactory:
    def __call__(self, cls: tp.Type[T], name: str) -> T:
        return ServiceProxy(name)


ServiceClient = ServiceClientFactory()


class _ServiceMethodProxy:
    def __init__(self, service_name, method_name, session_handler):
        self.service_name = service_name
        self.method_name = method_name
        self.session_handler: 'SessionHandler' = session_handler

    async def __call__(self, *args, **kwargs):
        return await self.session_handler.trigger_service_method(self.service_name, self.method_name, args, kwargs)
    
    def __repr__(self):
        return f'ServiceMethodProxy({self.service_name}, {self.method_name})'
    

class ServiceMethodProxy:
    def __init__(self, service_name, method_name, service_executors: dict[str, 'ServiceExecutor']):
        self.service_name = service_name
        self.method_name = method_name
        self.service_executors = service_executors

    async def __call__(self, *args, **kwargs):
        return await self.trigger_service_method(self.service_name, self.method_name, args, kwargs)
    
    async def execute_service_method(self, future, service_name, method_name, args, kwargs):
        """
        execute_service_method is a coroutine that executes a method on a service executor
        instance and stores the result in a Future object.

        Args:
            future: A Future object to store the result of the method call.
            service_name: The name of the service executor instance to use.
            method_name: The name of the method to call.
            args: The positional arguments to pass to the method.
            kwargs: The keyword arguments to pass to the method.

        Returns:
            None
        """
        service_executor = self.service_executors[service_name]
        try:
            result = await service_executor.execute_method(method_name, *args, **kwargs)
            future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)
    
    def trigger_service_method(self, service_name, method_name, args, kwargs):
        """
        Trigger a method call on a service executor instance.

        This method triggers a method call on a service executor instance and returns a Future object
        that resolves to the result of the method call.

        Args:
            service_name: The name of the service executor instance to use.
            method_name: The name of the method to call.
            args: The positional arguments to pass to the method.
            kwargs: The keyword arguments to pass to the method.

        Returns:
            A Future object that resolves to the result of the method call.
        """
        task_id = f'SERVICE/{service_name}/{method_name}@{time.time_ns()}'
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        # TODO: wire to session handler's create_task
        asyncio.create_task(
            self.execute_service_method(future, service_name, method_name, args, kwargs),
            name=task_id
        )
        return future
    
    def __repr__(self):
        return f'ServiceMethodProxy({self.service_name}, {self.method_name})'


class ServiceExecutor:
    async def execute_method(self, method_name, *args, **kwargs):
        raise NotImplementedError


class AsyncServiceExecutor(ServiceExecutor):
    def __init__(self, config: ServiceConfig, name: str, pubsub: PubSub):
        self.name = name
        self.config = config
        self.pubsub = pubsub
        self.instance: Service | None = None

    async def initialize(self, service_executors: dict[str, 'ServiceExecutor']):
        """Initialize the service instance"""
        self.instance: Service = self.config.service_cls(*self.config.args, **self.config.kwargs)
        await self.instance.__init_service__(self.name, self.pubsub, service_executors)
        logger.debug(f'Initialized service: {self.name}')

    async def execute_method(self, method_name, *args, **kwargs):
        """
        Execute a method on the underlying service instance.

        Args:
            method_name: name of the method to call
            *args: positional arguments to pass to the method
            **kwargs: keyword arguments to pass to the method

        Returns:
            The result of the method call if it is a coroutine, otherwise the result of calling the method synchronously.

        Raises:
            AttributeError: if the method does not exist on the service instance
        """
        args = args or ()
        kwargs = kwargs or {}
        if not hasattr(self.instance, method_name):
            logger.error(f'Method {method_name!r} does not exist for {self.instance.__class__!r}')
            raise AttributeError(f'Method {method_name!r} does not exist for {self.instance.__class__!r}')
        
        method = getattr(self.instance, method_name)
        logger.debug(f'Executing service method: {method_name} with args={args}, kwargs={kwargs}')
        
        if inspect.iscoroutinefunction(method):
            return await method(*args, **kwargs)
        else:
            logger.warning(f'Non-coroutine method called: {method_name}')
            return method(*args, **kwargs)


class SocketService(Service):
    def __init__(self, session_strategy: tp.Literal['path', 'connection_id', 'remote_ip'] = 'path', **kwargs):
        super().__init__(**kwargs)
        self.session_strategy = session_strategy
        self.connections = {}

    async def connect(self, ws: ServerConnection):
        connection_id = await self.on_connect(ws)
        if connection_id:
            self.connections[connection_id] = ws
        return connection_id
    
    async def disconnect(self, ws: ServerConnection):
        connection_id = await self.on_disconnect(ws)
        if connection_id:
            self.connections.pop(connection_id)

    async def on_connect(self, ws: ServerConnection) -> str:
        if self.session_strategy == 'path':
            return ws.request.path
        elif self.session_strategy == 'connection_id':
            return str(ws.id)
        elif self.session_strategy == 'remote_ip':
            return ws.remote_address[0]

    async def on_disconnect(self, ws: ServerConnection):
        pass
