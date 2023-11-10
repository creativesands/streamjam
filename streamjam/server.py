import json
import asyncio
import traceback
import websockets
import typing as tp
from dataclasses import dataclass


"""
    - with block batch update
"""


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


class Counter(Component):
    def __init__(self, _parent_id, _id, _client: 'ClientHandler', count=0, offset=1):
        super().__init__(_parent_id, _id, _client)

        self.__rpcs__: tp.Dict[str, tp.Callable] = {
            'inc': self.inc,
            'dec': self.dec
        }

        self.__state__['count'] = count
        self.__state__['offset'] = offset

    @property
    def count(self):
        return self.__state__['count']

    @count.setter
    def count(self, value):
        self.__state__['count'] = value
        self._client.update_store(self._id, 'count', value)

    @property
    def offset(self):
        return self.__state__['offset']

    @offset.setter
    def offset(self, value):
        self.__state__['offset'] = value
        self._client.update_store(self._id, 'offset', value)

    async def inc(self):
        for i in range(self.offset):
            await asyncio.sleep(0.1)
            self.count += 1
        print('inc', self.count)

    async def dec(self):
        for i in range(self.offset):
            await asyncio.sleep(0.1)
            self.count -= 1
        print('dec', self.count)

    async def __exec_rpc__(self, rpc_name, args):
        await self.__rpcs__.get(rpc_name)(*args)


component_class_map: tp.Dict[str, tp.Type[Component]] = {
    'Counter': Counter
}


@dataclass
class Message:
    topic: tp.Union[str, tp.Tuple]
    content: tp.Any = None
    req_id: tp.Optional[str] = None

    def serialize(self):
        if isinstance(self.topic, tuple):
            self.topic = '>'.join(self.topic)
        return json.dumps((self.req_id, self.topic, self.content))


class ClientHandler:
    def __init__(self, ws):
        self.ws = ws
        self.id = self.ws.path
        self.components: tp.Dict[str, Component] = {'root': RootComponent()}
        self.msg_queue = asyncio.Queue()
        asyncio.create_task(self.msg_sender())

    def add_component(self, parent_id, comp_id, comp_type, kwargs):
        comp_class = component_class_map[comp_type]
        self.components[comp_id] = comp_class(_parent_id=parent_id, _id=comp_id, _client=self, **kwargs)
        # if parent_id in self.components:
        parent = self.components[parent_id]
        parent.__child_components__.append(self.components[comp_id])

    def update_store(self, comp_id, store_name, value):
        self.send_msg(Message(('store-value', comp_id, store_name), value))

    def send_state(self):
        root_component = self.components.get('root')
        if root_component is not None:
            self.send_msg(Message('app-state', root_component.__get_state__()['children']))
        else:
            self.send_msg(Message('app-state', None))

    def set_store(self, comp_id, store_name, value):
        # updating store shadow var to avoid calling setter and sending updates back to client
        setattr(self.components[comp_id], f'_{store_name}', value)

    async def exec_rpc(self, req_id, comp_id, rpc_name, args):
        result = await self.components[comp_id].__exec_rpc__(rpc_name, args)
        self.send_msg(Message('rpc-result', result, req_id))

    def send_msg(self, msg: Message):
        self.msg_queue.put_nowait(msg)

    async def msg_sender(self):
        while True:
            msg: Message = await self.msg_queue.get()
            await self.ws.send(msg.serialize())

    async def handle(self):
        try:
            async for msg in self.ws:
                print('got message:', msg)
                req_id, topic, content = json.loads(msg)

                if topic == 'add-component':
                    parent_id, comp_id, comp_type, kwargs = content
                    self.add_component(parent_id, comp_id, comp_type, kwargs)

                elif topic == 'exec-rpc':
                    comp_id, rpc_name, args = content
                    asyncio.create_task(self.exec_rpc(req_id, comp_id, rpc_name, args))

                elif topic == 'store-set':
                    comp_id, store_name, value = content
                    self.set_store(comp_id, store_name, value)

        except Exception as e:
            print("Exception:", traceback.format_exc())
        finally:
            print('Client disconnected:', self.ws.id)


class StreamJam:
    def __init__(self, host='localhost', port=7755):
        self.host = host
        self.port = port
        self.addr = f'ws://{host}:{port}'
        self.msg_queue = asyncio.Queue()
        self.components = {}
        self.clients: tp.Dict[str, ClientHandler] = {}

    def send_msg(self, client_id, msg: Message):
        self.msg_queue.put_nowait((client_id, msg))

    async def router(self, ws):
        print('Received new connection:', ws.path, ws.id, len(self.clients))
        if ws.path not in self.clients:
            print('No prior state')
            self.clients[ws.path] = ClientHandler(ws)
        else:
            print('Prior state:', self.clients[ws.path].components)
        client = self.clients[ws.path]
        client.ws = ws
        # todo: add try-catch to remove client on client-disconnect after timeout
        client.send_state()  # TODO: can this be SSR'd instead?
        await client.handle()

    async def serve(self):
        async with websockets.serve(self.router, self.host, self.port):
            print(f'Running StreamJam server on {self.addr!r}')
            await asyncio.Future()


if __name__ == '__main__':
    server = StreamJam()
    asyncio.run(server.serve())
