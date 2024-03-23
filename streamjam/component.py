import asyncio
import typing as tp
from collections import defaultdict

from .base import ComponentEvent, final
from .service import Service, ServiceProxy

if tp.TYPE_CHECKING:
    from .server import SessionHandler


class Component:
    __prop_defaults__ = {}
    __services__ = {}
    __has_server__ = True

    class UI:
        ...

    async def __post_init__(self):
        pass

    @final
    def __init__(self, id: str, parent_id: str, session: 'SessionHandler'):
        self.id = id
        self.__parent_id = parent_id
        self.__session = session
        self._session = session

        self.__state__ = {}
        self.__child_components__: tp.List[Component] = []
        self.__task_registry: set[asyncio.Task] = set()
        self.__service_event_handlers: dict[str, set] = defaultdict(set)  # event_name: {handler}
        self.__message_queue__: 'asyncio.Queue[tuple[str, tp.Any]]' = asyncio.PriorityQueue()  # (topic_name, message)
        self._register_handlers()
        self.create_task(self.__message_receiver())

    async def __message_receiver(self):
        while True:
            priority, (event_name, message) = await self.__message_queue__.get()
            for handler in self.__service_event_handlers[event_name]:
                if hasattr(handler, '$event_handler'):  # todo: not needed
                    self.create_task(handler())
                else:
                    self.create_task(handler(message))

    def __init_subclass__(cls, **kwargs):
        cls.__has_server__ = kwargs.get('server', True)

        if not hasattr(cls, '__annotations__'):
            cls.__annotations__ = {}

        cls.__services__ = {}
        cls.__prop_defaults__ = {}
        for name, ann_type in cls.__annotations__.items():
            default_value = cls.__dict__.get(name, ...)
            if issubclass(ann_type, (Service, ServiceProxy)):
                cls.__services__[name] = default_value
            else:
                cls.__prop_defaults__[name] = default_value
                getter, setter = cls.__make_property(name)
                setattr(cls, name, property(getter, setter))

        for attr_name in dir(cls):
            item = getattr(cls, attr_name)
            if isinstance(item, ServiceProxy):
                cls.__services__[attr_name] = item

        # register system event handlers
        setattr(cls.on_disconnect, '$event_handler', True)

    @classmethod
    def __make_property(cls, name):
        default_value = cls.__dict__.get(name)

        def getter(self):
            return self.__state__.get(name, default_value)

        def setter(self, value):
            self.__state__.__setitem__(name, value)
            self.__session.update_store(self.id, name, value)

        return getter, setter

    @final
    async def __exec_rpc__(self, rpc_name, args):
        method = getattr(self, rpc_name, None)
        if callable(method):
            return await method(*args)
        else:
            raise AttributeError(f"RPC method {method!r} not found in {self.__class__.__name__}")

    def __repr__(self):
        return f'<Component: {self.__class__.__name__} ({self.id})>'

    @staticmethod
    @final
    def rpc(fn):
        setattr(fn, 'rpc', True)
        return fn

    @staticmethod
    @final
    def on_event(event_name):
        def handler(fn):
            setattr(fn, 'event_handler', event_name)
            return fn
        return handler

    @staticmethod
    @final
    def on_update(prop):
        def handler(fn):
            setattr(fn, 'store_update_handler', prop)
            return fn
        return handler

    @final
    def create_task(self, coro, name='$task') -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self.__task_registry.add(task)
        task.add_done_callback(self.__task_registry.discard)
        return task

    async def _message_handler(self):
        while True:
            priority, (topic, message) = await self.__message_queue__.get()
            if topic in self.__service_event_handlers:
                for handler in self.__service_event_handlers[topic]:
                    self.create_task(handler(message))

    def _register_handlers(self):
        # register system events
        self.__session.register_event_handler('$session_disconnect', self.on_disconnect)

        # register custom events
        for attr_name in dir(self):
            handler = getattr(self, attr_name)

            if isinstance(handler, ServiceProxy):
                print('ignoring', handler)
                continue  # ignore service proxy attributes
            if hasattr(handler, 'event_handler'):
                event_name = getattr(handler, 'event_handler')
                self.__session.register_event_handler(event_name, handler)
            if hasattr(handler, 'store_update_handler'):
                store_name = getattr(handler, 'store_update_handler')
                self.__session.register_store_update_handler(self.id, store_name, handler)
            if hasattr(handler, 'service_event_handler'):
                event_name, service_proxy = getattr(handler, 'service_event_handler')
                self.__session.pubsub.subscribe(
                    sid=f'{self.__session.id}/{self.id}',
                    channel=f'$Service/{service_proxy.__service_name__}',
                    topic=event_name
                )
                self.__service_event_handlers[event_name].add(handler)

    def _remove_handlers(self):
        for attr_name in dir(self):
            handler = getattr(self, attr_name)
            if hasattr(handler, 'event_handler'):
                event_name = getattr(handler, 'event_handler')
                self.__session.remove_event_handler(event_name, handler)
            if hasattr(handler, 'store_update_handler'):
                store_name = getattr(handler, 'store_update_handler')
                self.__session.remove_store_update_handler(self.id, store_name)

    @final
    def dispatch(self, name, data=None):
        self.__session.event_queue.put_nowait(ComponentEvent(name, self, data))

    async def on_destroy(self):
        pass

    async def on_disconnect(self):
        pass

    @final
    async def __destroy__(self):
        await self.on_destroy()
        self._remove_handlers()
        self.__session.pubsub.quit(self.id)
