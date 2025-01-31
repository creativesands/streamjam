import os
import time
import uvloop
import signal
import logging
import asyncio
import traceback
import typing as tp
import orjson as json
from datetime import datetime
from collections import defaultdict
from websockets.protocol import State
from websockets.asyncio.server import serve, ServerConnection
from websockets.exceptions import ConnectionClosedError, WebSocketException



from .pubsub import PubSub
from .protocol import Message
from .component import Component
from .base import ServerEvent, ComponentEvent
from .transpiler import get_components_in_project
from .service import ServiceConfig, SocketService, ServiceExecutor, AsyncServiceExecutor, ServiceEvent


logger = logging.getLogger('streamjam.server')
logger.setLevel(logging.INFO)


uvloop.install()


class SessionHandler:
    def __init__(
            self,
            ws: ServerConnection,
            pubsub: PubSub,
            component_map: dict[str, tp.Type[Component]],
            service_executors: dict[str, type(ServiceExecutor)],
            msg_stats: dict
    ):
        self.ws = ws
        self.id = self.ws.request.path
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
        self.msg_stats = msg_stats

    def register_event_handler(self, event: str, handler: tp.Callable):
        self.event_handlers[event].append(handler)

    def remove_event_handler(self, event: str, handler: tp.Callable):
        self.event_handlers[event].remove(handler)

    def register_store_update_handler(self, id: str, store: str, handler: tp.Callable):
        self.store_update_handlers[(id, store)] = handler

    def remove_store_update_handler(self, id: str, store: str):
        del self.store_update_handlers[(id, store)]

    async def add_component(self, comp_id, parent_id, comp_type, props):
        """
        Creates a new component in the session.

        :param comp_id: component ID
        :param parent_id: parent component ID
        :param comp_type: component type
        :param props: props to initialize the component with
        :return:
        """
        comp_class = self.component_map[comp_type]
        component = comp_class(id=comp_id, parent_id=parent_id, session=self)
        self.pubsub.register(f'{self.id}/{component.id}', component.__message_queue__)
        self.assign_services(component)
        component.__state__.update(props)
        await component.__post_init__()
        await component.on_connect()
        self.components[comp_id] = component
        parent = self.components[parent_id]
        parent.__child_components__.append(self.components[comp_id])

    async def destroy_component(self, comp_id):
        """
        Destroys the component with the given ID in the session.

        :param comp_id: component ID to destroy
        :return:
        """
        await self.components[comp_id].__destroy__()
        del self.components[comp_id]

    def assign_services(self, component: Component):
        """
        Initializes the service proxies of the given component.

        :param component: component to assign services to
        :type component: Component
        """
        for attr_name in component.__services__:
            service_proxy = getattr(component, attr_name)
            # service_proxy.__init_proxy__(self)
            service_proxy.__init_proxy__(self.service_executors)

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
        """
        Execute the on_update handler for the given component and store.

        :param comp_id: ID of the component to update
        :type comp_id: str
        :param store_name: Name of the store to update
        :type store_name: str
        :param value: New value for the store
        :type value: Any
        """
        handler = self.store_update_handlers[(comp_id, store_name)]
        self.components[comp_id].__state__[store_name] = await handler(value)

    async def exec_rpc(self, req_id, comp_id, rpc_name, args):
        result = await self.components[comp_id].__exec_rpc__(rpc_name, args)
        self.send_msg(Message('rpc-result', result, req_id))

    def send_msg(self, msg: Message):
        """
        Put a message into the session's message queue to be sent to the connected client over the
        WebSocket connection.

        :param msg: Message to be sent
        :type msg: Message
        """
        self.msg_queue.put_nowait(msg)

    async def msg_sender(self):
        """
        msg_sender is a coroutine that continuously sends messages from the session's message queue to
        the connected client over the WebSocket connection. It handles exceptions raised when the client
        disconnects or the connection is closed.
        """
        while True:
            msg: Message = await self.msg_queue.get()
            try:
                if self.ws.state is State.OPEN:  # Check if WebSocket is still open
                    await self.ws.send(msg.serialize())
                    self.msg_stats['messages_sent'] += 1
                else:
                    logger.debug('WebSocket closed. Dropping message.')
                    # TODO: add try-catch to remove session on client-session-disconnect after timeout
            except ConnectionClosedError:
                logger.debug('Connection Closed. Draining messages to session client.')
            except WebSocketException as exc:
                logger.error(f'Websocket Exception. Draining messages to session client. Exception: {exc!r}')

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
        """
        event_dispatcher is a coroutine that continuously processes events from the session's event queue
        and dispatches them to the appropriate event handlers.

        The event_dispatcher coroutine is responsible for processing events from the session's event queue,
        which is populated by the handle coroutine. The event_dispatcher coroutine dispatches events to the
        appropriate event handlers, which are registered using the on_event method.

        The event_dispatcher coroutine runs indefinitely, continuously processing events from the event queue
        and dispatching them to the appropriate event handlers.

        :return: None
        """
        while True:
            event = await self.event_queue.get()
            for handler in self.event_handlers[event.name]:
                if hasattr(handler, '$event_handler'):  # system event
                    self.create_task(handler())
                else:
                    self.create_task(handler(event))

    async def handle(self):
        """
        handle is a coroutine that continuously receives messages from the connected client over the
        WebSocket connection, processes them, and dispatches them to the appropriate event handlers.

        The handle coroutine is responsible for receiving messages from the connected client over the
        WebSocket connection, processing them, and dispatching them to the appropriate event handlers.
        The handle coroutine runs indefinitely, continuously receiving messages from the client and
        dispatching them to the appropriate event handlers.

        The handle coroutine handles exceptions raised when the client disconnects or the connection is
        closed. When an exception is raised, the handle coroutine prints the exception and then puts a
        ServerEvent('$session_disconnect') into the session's event queue to signal that the client has
        disconnected.

        :return: None
        """
        try:
            # TODO: the event handlers for this may not be registered until the components are initialized
            #       so we need to rethink how we handle this
            self.event_queue.put_nowait(ServerEvent('$session_connect'))

            async for msg in self.ws:
                self.msg_stats['messages_received'] += 1
                logger.info(f'Received message: {msg}')
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
            logger.error(f'Exception: {traceback.format_exc()}')
        finally:
            self.event_queue.put_nowait(ServerEvent('$session_disconnect'))
            socket_service = self.service_executors['SocketService']
            await socket_service.execute_method('disconnect', self.ws)
            logger.info(f'Client disconnected: {self.ws.id}')


class StreamJam:
    def __init__(
            self,
            name: str = "StreamJam",
            host: str = "localhost",
            port: int = 7755,
            services: dict[str, ServiceConfig] = None
    ):
        """
        Initialize StreamJam server.

        This method initializes the StreamJam server with the given name, host, port and services.

        Args:
            name: The name of the StreamJam server.
            host: The host address of the StreamJam server.
            port: The port on which the StreamJam server should listen.
            services: A dictionary of service configurations.

        Returns:
            None
        """
        self.name = name
        self.host = host
        self.port = port
        self.addr = f'ws://{host}:{port}'
        self.service_executors: dict[str, type(ServiceExecutor)] = {}
        self.sessions: dict[str, SessionHandler] = {}
        self.component_map = get_components_in_project(name)
        self.pubsub = PubSub()
        self.service_configs: dict[str, ServiceConfig] = services or {}
        self.msg_stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'last_print': datetime.now()
        }
        self._stats_task = None  # Store task reference for cleanup

    async def init_services(self):
        """
        Initialize StreamJam services.

        This method takes a dictionary of service configurations and initializes them.
        It also ensures that the 'SocketService' is present, as it is required for handling
        client connections.

        Args:
            services: A dictionary of service configurations.

        Returns:
            None
        """
        if 'SocketService' not in self.service_configs:
            self.service_configs['SocketService'] = ServiceConfig(SocketService, (), {})
            logger.debug('SocketService not found, adding default SocketService')

        for service_name, service_config in self.service_configs.items():
            logger.debug(f'Initializing service executor: {service_name}')
            executor = AsyncServiceExecutor(service_config, service_name, self.pubsub)
            self.service_executors[service_name] = executor

        for service_name, executor in self.service_executors.items():
            await executor.initialize(self.service_executors)
            logger.debug(f'Initialized service: {service_name}')

    async def router(self, ws: ServerConnection):
        """
        Handle a new connection.

        This is the entry point for new connections. It's responsible for
        initializing a new session and dispatching the client to the
        :meth:`SessionHandler.handle` method.

        :param ws: The WebSocketServerProtocol object representing the connection.
        """
        logger.info(f'Received new connection. Path: {ws.request.path}, ID: {ws.id}, Total Connections: {len(self.sessions)}')

        socket_service = self.service_executors['SocketService']
        connection_id = await socket_service.execute_method('connect', ws)
        if not connection_id:
            logger.warning(f'Connection rejected for websocket ID: {ws.id}')
            return  # returning from the router will close the connection
        elif connection_id not in self.sessions:
            logger.debug('No prior state found, creating new session')
            self.sessions[connection_id] = SessionHandler(
                ws,
                self.pubsub,
                self.component_map,
                self.service_executors,
                self.msg_stats
            )
        else:
            logger.debug(f'Restoring prior state for connection: {connection_id}')
            logger.debug(f'Components: {self.sessions[connection_id].components}')

        session = self.sessions[connection_id]
        session.ws = ws
        # todo: add try-catch to remove session on client-session-disconnect after timeout
        session.send_state()  # TODO: can this be SSR'd instead?
        await session.handle()

    async def serve(self):
        """
        Run the StreamJam server on the specified host and port.

        This method blocks until it receives a SIGINT (Ctrl+C) signal.

        :return: None
        :rtype: None
        """
        loop = asyncio.get_running_loop()
        stop = loop.create_future()

        try:
            loop.add_signal_handler(signal.SIGINT, stop.set_result, None)
        except NotImplementedError:
            pass  # Not available on Windows.

        await self.init_services()
        
        # Start the stats printer task when serving
        self._stats_task = asyncio.create_task(self.print_message_stats(), name='$stats_printer')

        await self.pubsub.start_stats_publisher()

        async with serve(self.router, self.host, self.port) as server:
            logger.info(f'Event Loop: {type(asyncio.get_running_loop())}')
            logger.info(f'Running StreamJam server on {self.addr!r} | PID: {os.getpid()}')
            # await server.serve_forever()
            try:
                await stop
            finally:
                # Clean up stats task when server stops
                if self._stats_task:
                    self._stats_task.cancel()
                    try:
                        await self._stats_task
                    except asyncio.CancelledError:
                        pass

    async def print_message_stats(self):
        """Print message statistics every second"""
        while True:
            await asyncio.sleep(1)
            now = datetime.now()
            delta = (now - self.msg_stats['last_print']).total_seconds()
            sent_rate = self.msg_stats['messages_sent'] / delta
            received_rate = self.msg_stats['messages_received'] / delta
            
            # Create stats dict
            stats = {
                "messages_sent": self.msg_stats['messages_sent'],
                "messages_received": self.msg_stats['messages_received'],
                "messages_sent_per_sec": round(sent_rate, 2),
                "messages_received_per_sec": round(received_rate, 2),
                "active_sessions": len(self.sessions)
            }
            
            # Publish stats through pubsub
            stats_event = ServiceEvent("stats", "Server", data=stats)
            self.pubsub.publish("$Server", stats_event)
            
            # Log stats
            logger.debug(
                f"Message Stats | Sent: {stats['messages_sent']} ({stats['messages_sent_per_sec']}/s) | "
                f"Received: {stats['messages_received']} ({stats['messages_received_per_sec']}/s)"
            )
            
            self.msg_stats.update({
                'messages_sent': 0, 
                'messages_received': 0,
                'last_print': now
            })
