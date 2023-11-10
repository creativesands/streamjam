import json
import asyncio
import traceback
import websockets
import typing as tp

from .protocol import Message
from .component import Component, RootComponent


"""
Notes:
    - with block batch update
"""


class ClientHandler:
    def __init__(self, ws, component_map: tp.Dict[str, tp.Type[Component]] = None):
        self.ws = ws
        self.id = self.ws.path
        self.component_map = component_map
        self.components: tp.Dict[str, Component] = {'root': RootComponent()}
        self.msg_queue = asyncio.Queue()
        asyncio.create_task(self.msg_sender())

    def add_component(self, parent_id, comp_id, comp_type, kwargs):
        comp_class = self.component_map[comp_type]
        self.components[comp_id] = comp_class(_parent_id=parent_id, _id=comp_id, _client=self, **kwargs)
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
    def __init__(self, host='localhost', port=7755, component_map: tp.Dict[str, tp.Type[Component]] = None):
        self.host = host
        self.port = port
        self.addr = f'ws://{host}:{port}'
        self.msg_queue = asyncio.Queue()
        self.components = {}
        self.clients: tp.Dict[str, ClientHandler] = {}
        self.component_map = component_map or {}

    def send_msg(self, client_id, msg: Message):
        self.msg_queue.put_nowait((client_id, msg))

    async def router(self, ws):
        print('Received new connection:', ws.path, ws.id, len(self.clients))
        if ws.path not in self.clients:
            print('No prior state')
            self.clients[ws.path] = ClientHandler(ws, self.component_map)
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

