import typing as tp

from .base import ServiceBase, ComponentEvent

if tp.TYPE_CHECKING:
    from .server import ClientHandler


class Component:
    __prop_defaults__ = {}
    __services__ = {}
    __has_server__ = True

    class Client:
        ...

    def __post_init__(self):
        pass

    def __init__(self, id: str, parent_id: str, client: 'ClientHandler'):
        self.id = id
        self.__parent_id = parent_id
        self.__client = client

        self.__state__ = {}
        self.__child_components__: tp.List[Component] = []
        self._register_handlers()

    def __init_subclass__(cls, **kwargs):
        cls.__has_server__ = kwargs.get('server', True)

        if not hasattr(cls, '__annotations__'):
            cls.__annotations__ = {}

        cls.__services__ = {}
        cls.__prop_defaults__ = {}
        for name, ann_type in cls.__annotations__.items():
            default_value = cls.__dict__.get(name, ...)
            if issubclass(ann_type, ServiceBase):
                cls.__services__[name] = default_value
            else:
                cls.__prop_defaults__[name] = default_value
                getter, setter = cls.__make_property(name)
                setattr(cls, name, property(getter, setter))

        # register system event handlers
        setattr(cls.on_disconnect, '$event_handler', True)

    @classmethod
    def __make_property(cls, name):
        default_value = cls.__dict__.get(name)

        def getter(self):
            return self.__state__.get(name, default_value)

        def setter(self, value):
            self.__state__.__setitem__(name, value)
            self.__client.update_store(self.id, name, value)

        return getter, setter

    async def __exec_rpc__(self, rpc_name, args):
        method = getattr(self, rpc_name, None)
        if callable(method):
            return await method(*args)
        else:
            raise AttributeError(f"RPC method {method!r} not found in {self.__class__.__name__}")

    def __repr__(self):
        return f'<Component: {self.__class__.__name__} ({self.id})>'

    @staticmethod
    def rpc(fn):
        setattr(fn, 'rpc', True)
        return fn

    @staticmethod
    def on_event(event_name):
        def handler(fn):
            setattr(fn, 'event_handler', event_name)
            return fn
        return handler

    @staticmethod
    def on_update(prop):
        def handler(fn):
            setattr(fn, 'store_update_handler', prop)
            return fn
        return handler

    def _register_handlers(self):
        # register system events
        self.__client.register_event_handler('$client_disconnect', self.on_disconnect)

        # register custom events
        for attr_name in dir(self):
            handler = getattr(self, attr_name)
            if hasattr(handler, 'event_handler'):
                event_name = getattr(handler, 'event_handler')
                self.__client.register_event_handler(event_name, handler)
            if hasattr(handler, 'store_update_handler'):
                store_name = getattr(handler, 'store_update_handler')
                self.__client.register_store_update_handler(self.id, store_name, handler)

    def _remove_handlers(self):
        for attr_name in dir(self):
            handler = getattr(self, attr_name)
            if hasattr(handler, 'event_handler'):
                event_name = getattr(handler, 'event_handler')
                self.__client.remove_event_handler(event_name, handler)
            if hasattr(handler, 'store_update_handler'):
                store_name = getattr(handler, 'store_update_handler')
                self.__client.remove_store_update_handler(self.id, store_name)

    def dispatch(self, name, data=None):
        self.__client.event_queue.put_nowait(ComponentEvent(name, self, data))

    async def on_destroy(self):
        pass

    async def on_disconnect(self):
        pass

    async def __destroy__(self):
        await self.on_destroy()
        self._remove_handlers()
