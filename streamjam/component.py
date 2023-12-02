import typing as tp

if tp.TYPE_CHECKING:
    from .server import ClientHandler


def rpc(fn):
    setattr(fn, 'rpc', True)
    return fn


class Component:
    __prop_defaults__ = {}
    __has_server__ = True

    class Layout:
        ...

    class Style:
        ...

    class Script:
        ...

    def __init__(self, id: str, parent_id: str, client: 'ClientHandler'):
        self.__id = id
        self.__parent_id = parent_id
        self.__client = client

        self.__state__ = {}
        self.__child_components__: tp.List[Component] = []

    def __init_subclass__(cls, **kwargs):
        cls.__has_server__ = kwargs.get('server', True)

        if not hasattr(cls, '__annotations__'):
            cls.__annotations__ = {}

        cls.__prop_defaults__ = {}
        for name in cls.__annotations__:
            default_value = cls.__dict__.get(name, ...)
            cls.__prop_defaults__[name] = default_value
            getter, setter = cls.__make_property(name)
            setattr(cls, name, property(getter, setter))

    @classmethod
    def __make_property(cls, name):
        default_value = cls.__dict__.get(name)

        def getter(self):
            return self.__state__.get(name, default_value)

        def setter(self, value):
            self.__state__.__setitem__(name, value)
            self.__client.update_store(self.__id, name, value)

        return getter, setter

    async def __exec_rpc__(self, rpc_name, args):
        method = getattr(self, rpc_name, None)
        if callable(method):
            return await method(*args)
        else:
            raise AttributeError(f"RPC method {method!r} not found in {self.__class__.__name__}")

    def __get_state__(self):
        return {
            'id': self.__id,
            'state': self.__state__,
            'type': self.__class__.__name__,  # TODO: how to guarantee comp names are unique
            'children': [comp.__get_state__() for comp in self.__child_components__]
        }

    def __repr__(self):
        return f'<Component: {self.__class__.__name__} ({self.__id})>'
