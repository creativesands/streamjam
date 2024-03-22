import time
import json
import signal
import asyncio
import traceback
import websockets
import typing as tp
from collections import defaultdict

from .pubsub import PubSub
from .protocol import Message
from .component import Component
from .base import ServerEvent, ComponentEvent
from .transpiler import get_components_in_project
from .service import ServiceConfig, SocketService, ServiceExecutor, AsyncServiceExecutor


class ClientHandler:
    def __init__(
            self,
            ws: websockets.WebSocketServerProtocol,
            pubsub: PubSub,
            component_map: dict[str, tp.Type[Component]],
            service_executors: dict[str, type(ServiceExecutor)]
    ):
        self.ws = ws
        self.id = self.ws.path
        self.pubsub = pubsub
        self.component_map = component_map
        self.service_executors: dict[str, ServiceExecutor] = service_executors
        self.components: dict[str, Component] = {}
        self.msg_queue = asyncio.Queue()
        self.event_queue: 'asyncio.Queue[ServerEvent | ComponentEvent]' = asyncio.Queue()
        self.event_handlers = defaultdict(list)
        self.store_update_handlers: dict[tuple[str, str], tp.Callable] = {}
        self.task_registry: set[asyncio.Task] = set()
        self.create_task(self.msg_sender(), name='$msg_sender')  # $ indicates "system" task
        self.create_task(self.event_dispatcher(), name='$event_dispatcher')

    def register_event_handler(self, event: str, handler: tp.Callable):
        self.event_handlers[event].append(handler)

    def remove_event_handler(self, event: str, handler: tp.Callable):
        self.event_handlers[event].remove(handler)

    def register_store_update_handler(self, id: str, store: str, handler: tp.Callable):
        self.store_update_handlers[(id, store)] = handler

    def remove_store_update_handler(self, id: str, store: str):
        del self.store_update_handlers[(id, store)]

    async def add_component(self, comp_id, parent_id, comp_type, props):
        comp_class = self.component_map[comp_type]
        component = comp_class(id=comp_id, parent_id=parent_id, client=self)
        self.pubsub.register(f'{self.id}/{component.id}', component.__message_queue__)
        self.assign_services(component)
        component.__state__.update(props)
        await component.__post_init__()
        self.components[comp_id] = component
        parent = self.components[parent_id]
        parent.__child_components__.append(self.components[comp_id])

    async def destroy_component(self, comp_id):
        await self.components[comp_id].__destroy__()
        del self.components[comp_id]

    def assign_services(self, component: Component):
        for attr_name in component.__services__:
            service_proxy = getattr(component, attr_name)
            service_proxy.__init_proxy__(self)

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
            self.create_task(
                self.exec_update_store_handler(comp_id, store_name, value),
                name='$exec_update_store_handler'
            )
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

    async def execute_service_method(self, future, service_name, method_name, args, kwargs):
        service_executor = self.service_executors[service_name]
        result = await service_executor.execute_method(method_name, *args, **kwargs)  # todo: handle exceptions
        future.set_result(result)

    def trigger_service_method(self, service_name, method_name, args, kwargs):
        task_id = f'SERVICE/{service_name}/{method_name}@{time.time()}'
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.create_task(
            self.execute_service_method(future, service_name, method_name, args, kwargs),
            name=task_id
        )
        return future

    def create_task(self, coro, name='$task') -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self.task_registry.add(task)
        task.add_done_callback(self.task_registry.discard)
        return task

    async def event_dispatcher(self):
        while True:
            event = await self.event_queue.get()
            for handler in self.event_handlers[event.name]:
                if hasattr(handler, '$event_handler'):  # system event
                    self.create_task(handler())
                else:
                    self.create_task(handler(event))

    async def handle(self):
        try:
            async for msg in self.ws:
                print('>>> Received message:', msg)
                req_id, topic, content = json.loads(msg)

                if topic == 'add-component':
                    comp_id, parent_id, comp_type, props = content
                    await self.add_component(comp_id, parent_id, comp_type, props)

                elif topic == 'exec-rpc':
                    comp_id, rpc_name, args = content
                    self.create_task(self.exec_rpc(req_id, comp_id, rpc_name, args), name='$exec_rpc')

                elif topic == 'store-set':
                    comp_id, store_name, value = content
                    self.set_store(comp_id, store_name, value)

                elif topic == 'destroy-component':
                    (comp_id,) = content
                    self.create_task(self.destroy_component(comp_id), name='$destroy_component')

        except Exception as e:
            print("Exception:", traceback.format_exc())
        finally:
            self.event_queue.put_nowait(ServerEvent('$client_disconnect'))
            print('!!! Client disconnected:', self.ws.id)


class StreamJam:
    def __init__(
            self,
            name: str = "StreamJam",
            host: str = "localhost",
            port: int = 7755,
            services: dict[str, ServiceConfig] = None
    ):
        self.name = name
        self.host = host
        self.port = port
        self.addr = f'ws://{host}:{port}'
        self.service_executors: dict[str, type(ServiceExecutor)] = {}
        self.clients: dict[str, ClientHandler] = {}
        self.component_map = get_components_in_project(name)
        self.pubsub = PubSub()
        self.init_services(services)

    def init_services(self, services: dict[str, ServiceConfig]):
        if 'SocketService' not in services:
            services['SocketService'] = ServiceConfig(SocketService, (), {})

        for service_name, service_config in services.items():
            self.service_executors[service_name] = AsyncServiceExecutor(service_config, service_name, self.pubsub)

    async def router(self, ws: websockets.WebSocketServerProtocol):
        print('>>> Received new connection:', ws.path, ws.id, len(self.clients))

        socket_service = self.service_executors['SocketService']
        connection_id = await socket_service.execute_method('connect', ws)
        if not connection_id:
            return  # returning from the router will close the connection
        elif connection_id not in self.clients:
            print('No prior state')
            self.clients[connection_id] = ClientHandler(
                ws,
                self.pubsub,
                self.component_map,
                self.service_executors
            )
        else:
            print('Prior state: \n', self.clients[connection_id].components)

        client = self.clients[connection_id]
        client.ws = ws
        # todo: add try-catch to remove client on client-disconnect after timeout
        client.send_state()  # TODO: can this be SSR'd instead?
        await client.handle()

    async def serve(self):
        # Set the stop condition when receiving SIGTERM.
        loop = asyncio.get_running_loop()
        stop = loop.create_future()
        loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

        async with websockets.serve(self.router, self.host, self.port):
            print(f'Running StreamJam server on {self.addr!r}')
            await stop
