import typing as tp

if tp.TYPE_CHECKING:
    from .server import ClientHandler


class Component:
    def __init__(self, _parent_id, _id, _client: 'ClientHandler', **kwargs):
        self._parent_id = _parent_id
        self._id = _id
        self._client = _client
        self.__child_components__: tp.List[Component] = []
        self.__rpcs__: tp.Dict[str, tp.Callable] = {}
        self.__state__ = {}

    async def __exec_rpc__(self, rpc_name, args):
        ...

    def __get_state__(self):
        return {
            'id': self._id,
            'state': self.__state__,
            'type': self.__class__.__name__,  # TODO: how to guarantee comp names are unique
            'children': [comp.__get_state__() for comp in self.__child_components__]
        }

    def __repr__(self):
        return f'<Component:{self.__class__.__name__} ({self._id})>'


class RootComponent(Component):
    def __init__(self, _parent_id=None, _id='root', _client: 'ClientHandler' = None, **kwargs):
        super().__init__(_parent_id, _id, _client)
