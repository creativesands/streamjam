import json
import asyncio
import websockets
import typing as tp
from dataclasses import dataclass


"""
    - with block batch update
"""


class StreamJamComponent:
    def __init__(self, _id, _client: 'StreamJamClientHandler'):
        self._id = _id
        self._client = _client
        self.__rpcs__: tp.Dict[str, tp.Callable] = {}

    async def __exec_rpc__(self, rpc_name, args):
        ...


class CounterComponent(StreamJamComponent):
    def __init__(self, _id, _client: 'StreamJamClientHandler'):
        super().__init__(_id, _client)

        self.__rpcs__: tp.Dict[str, tp.Callable] = {
            'inc': self.inc,
            'dec': self.dec
        }

        self._count = 0
        self._offset = 1

    @property
    def count(self):
        return self._count

    @count.setter
    def count(self, value):
        self._count = value
        self._client.update_store(self._id, 'count', self._count)

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, value):
        self._offset = value
        self._client.update_store(self._id, 'offset', self._offset)

    async def inc(self):
        for i in range(self.offset):
            await asyncio.sleep(0.1)
            self.count += 1
        print('inc', self.count)

    async def dec(self):
        self.count -= 1
        print('dec', self.count)

    async def __exec_rpc__(self, rpc_name, args):
        await self.__rpcs__.get(rpc_name)(*args)


component_class_map: tp.Dict[str, tp.Type[StreamJamComponent]] = {
    'Counter': CounterComponent
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


class StreamJamClientHandler:
    def __init__(self, ws):
        self.ws = ws
        self.id = self.ws.path
        self.components: tp.Dict[str, StreamJamComponent] = {}
        self.msg_queue = asyncio.Queue()
        asyncio.create_task(self.msg_sender())

    def add_component(self, comp_type, comp_id):
        comp_class = component_class_map[comp_type]
        self.components[comp_id] = comp_class(comp_id, self)

    def update_store(self, comp_id, store_name, value):
        self.send_msg(Message(('store-value', comp_id, store_name), value))

    def set_store(self, comp_id, store_name, value):
        setattr(self.components[comp_id], store_name, value)

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
                    comp_type, comp_id = content
                    self.add_component(comp_type, comp_id)

                elif topic == 'exec-rpc':
                    comp_id, rpc_name, args = content
                    asyncio.create_task(self.exec_rpc(req_id, comp_id, rpc_name, args))

                elif topic == 'store-set':
                    comp_id, store_name, value = content
                    self.set_store(comp_id, store_name, value)

        except Exception as e:
            print(e)
        finally:
            print('Client disconnected:', self.ws.id)


class StreamJamServer:
    def __init__(self, host='localhost', port=7755):
        self.host = host
        self.port = port
        self.addr = f'ws://{host}:{port}'
        self.msg_queue = asyncio.Queue()
        self.components = {}
        self.clients: tp.Dict[str, StreamJamClientHandler] = {}

    def send_msg(self, client_id, msg: Message):
        self.msg_queue.put_nowait((client_id, msg))

    async def router(self, ws):
        print('Received new connection:', ws.path, ws.id, len(self.clients))
        if ws.id not in self.clients:
            self.clients[ws.id] = StreamJamClientHandler(ws)
        client = self.clients[ws.id]
        # todo: add try-catch to remove client on client-disconnect after timeout
        await client.handle()

    async def serve(self):
        async with websockets.serve(self.router, self.host, self.port):
            print(f'Running StreamJam server on {self.addr!r}')
            await asyncio.Future()


if __name__ == '__main__':
    server = StreamJamServer()
    asyncio.run(server.serve())
