import json
import asyncio
import traceback
import websockets
import typing as tp
from collections import defaultdict

from .protocol import Message
from .component import Component, Event
from .transpiler import get_components_in_project


class ClientHandler:
    def __init__(self, ws, component_map: tp.Dict[str, tp.Type[Component]] = None):
        self.ws = ws
        self.id = self.ws.path
        self.component_map = component_map
        self.components: tp.Dict[str, Component] = {}
        self.msg_queue = asyncio.Queue()
        self.event_queue: 'asyncio.Queue[Event]' = asyncio.Queue()
        self.event_handlers = defaultdict(list)
        self.store_update_handlers: tp.Dict[tp.Tuple[str, str], tp.Callable] = {}
        asyncio.create_task(self.msg_sender())
        asyncio.create_task(self.event_dispatcher())

    def register_event_handler(self, event: str, handler: tp.Callable):
        self.event_handlers[event].append(handler)

    def remove_event_handler(self, event: str, handler: tp.Callable):
        self.event_handlers[event].remove(handler)

    def register_store_update_handler(self, id: str, store: str, handler: tp.Callable):
        self.store_update_handlers[(id, store)] = handler

    def remove_store_update_handler(self, id: str, store: str):
        del self.store_update_handlers[(id, store)]

    def add_component(self, comp_id, parent_id, comp_type, props):
        comp_class = self.component_map[comp_type]
        component = comp_class(id=comp_id, parent_id=parent_id, client=self)
        component.__state__.update(props)
        self.components[comp_id] = component
        parent = self.components[parent_id]
        parent.__child_components__.append(self.components[comp_id])

    async def destroy_component(self, comp_id):
        await self.components[comp_id].__destroy__()
        del self.components[comp_id]

    def update_store(self, comp_id, store_name, value):
        self.send_msg(Message(('store-value', comp_id, store_name), value))

    def send_state(self):
        if len(self.components):
            state = {}
            for name, comp in self.components.items():
                state[name] = comp.__state__
            self.send_msg(Message('app-state', state))
        else:
            self.send_msg(Message('app-state', None))

    def set_store(self, comp_id, store_name, value):
        # Note: store property's value is set by return value of on_update handler if it exists
        if (comp_id, store_name) in self.store_update_handlers:
            asyncio.create_task(self.exec_update_store_handler(comp_id, store_name, value))
        else:
            self.components[comp_id].__state__[store_name] = value

    async def exec_update_store_handler(self, comp_id, store_name, value):
        handler = self.store_update_handlers[(comp_id, store_name)]
        self.components[comp_id].__state__[store_name] = await handler(value)

    async def exec_rpc(self, req_id, comp_id, rpc_name, args):
        result = await self.components[comp_id].__exec_rpc__(rpc_name, args)
        self.send_msg(Message('rpc-result', result, req_id))

    def send_msg(self, msg: Message):
        self.msg_queue.put_nowait(msg)

    async def msg_sender(self):
        while True:
            msg: Message = await self.msg_queue.get()
            try:
                await self.ws.send(msg.serialize())
            except websockets.exceptions.ConnectionClosedError:
                print('Connection Closed. Draining messages to client.')
            except websockets.WebSocketException as exc:
                print('Websocket Exception', exc)

    async def event_dispatcher(self):
        while True:
            event = await self.event_queue.get()
            for handler in self.event_handlers[event.name]:
                asyncio.create_task(handler(event))

    async def handle(self):
        try:
            async for msg in self.ws:
                print('>>> Received message:', msg)
                req_id, topic, content = json.loads(msg)

                if topic == 'add-component':
                    comp_id, parent_id, comp_type, props = content
                    self.add_component(comp_id, parent_id, comp_type, props)

                elif topic == 'exec-rpc':
                    comp_id, rpc_name, args = content
                    asyncio.create_task(self.exec_rpc(req_id, comp_id, rpc_name, args))

                elif topic == 'store-set':
                    comp_id, store_name, value = content
                    self.set_store(comp_id, store_name, value)

                elif topic == 'destroy-component':
                    (comp_id,) = content
                    asyncio.create_task(self.destroy_component(comp_id))

        except Exception as e:
            print("Exception:", traceback.format_exc())
        finally:
            print('!!! Client disconnected:', self.ws.id)


class StreamJam:
    def __init__(
            self,
            name: str = "StreamJam",
            host: str = "localhost",
            port: int = 7755
    ):
        self.name = name
        self.host = host
        self.port = port
        self.addr = f'ws://{host}:{port}'
        self.clients: tp.Dict[str, ClientHandler] = {}
        self.component_map = get_components_in_project(name)

    async def router(self, ws):
        print('>>> Received new connection:', ws.path, ws.id, len(self.clients))
        if ws.path not in self.clients:
            print('No prior state')
            self.clients[ws.path] = ClientHandler(ws, self.component_map)
        else:
            print('Prior state: \n', self.clients[ws.path].components)
        client = self.clients[ws.path]
        client.ws = ws
        # todo: add try-catch to remove client on client-disconnect after timeout
        client.send_state()  # TODO: can this be SSR'd instead?
        await client.handle()

    async def serve(self):
        async with websockets.serve(self.router, self.host, self.port):
            print(f'Running StreamJam server on {self.addr!r}')
            await asyncio.Future()

