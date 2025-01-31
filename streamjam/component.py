import asyncio
import inspect
import logging
import typing as tp
from collections import defaultdict

from .service import Service, ServiceProxy
from .base import ComponentEvent, final, ServiceEvent

if tp.TYPE_CHECKING:
    from .server import SessionHandler


logger = logging.getLogger('streamjam.component')
logger.setLevel(logging.INFO)


class Component:
    __prop_defaults__ = {}
    __services__ = {}
    __has_server__ = True

    class UI:
        """@
        """
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
        self.__message_queue__: 'asyncio.Queue[ServiceEvent]' = asyncio.PriorityQueue()
        self._register_handlers()
        self.create_task(self.__message_receiver())

        logger.debug(f"Component {self.id} initialized with parent {self.__parent_id}")

    async def __message_receiver(self):
        """
        The __message_receiver coroutine runs indefinitely, continuously processing events from the event queue
        and dispatching them to the appropriate event handlers.

        :return: None
        """
        while True:
            event = await self.__message_queue__.get()
            logger.debug(f"Processing event {event.name} for component {self.id}")
            for handler in self.__service_event_handlers[event.name]:
                if hasattr(handler, '$event_handler'):  # todo: not needed
                    self.create_task(handler())
                else:
                    self.create_task(handler(event))
            self.__message_queue__.task_done()

    def __init_subclass__(cls, **kwargs):
        """
        This method is called when a subclass of Component is created. It's used to automatically register
        event handlers, services, and component properties.

        The method takes in arbitrary keyword arguments. If the 'server' keyword argument is provided and is
        set to False, the component will not have a server part.

        The method iterates through all the class attributes and annotations of the subclass, and does the
        following:

        - If an attribute is a subclass of Service or ServiceProxy, it's added to the class's __services__
          dictionary.
        - If an attribute is not a subclass of Service or ServiceProxy, it's added to the class's
          __prop_defaults__ dictionary.
        - If an attribute is annotated with a type that is a subclass of Service or ServiceProxy, it's added
          to the class's __services__ dictionary.
        - If an attribute is annotated with a type that is not a subclass of Service or ServiceProxy, a
          property is created for the attribute, and the property is added to the class.

        After iterating through all the class attributes and annotations, the method registers system event
        handlers.
        """
        cls.__has_server__ = kwargs.get('server', True)

        if not hasattr(cls, '__annotations__'):
            cls.__annotations__ = {}

        cls.__services__ = {}
        cls.__prop_defaults__ = {}
        for name, ann_type in cls.__annotations__.items():
            default_value = cls.__dict__.get(name, ...)
            if inspect.isclass(ann_type) and issubclass(ann_type, (Service, ServiceProxy)):
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
        setattr(cls.on_connect, '$event_handler', True)
        setattr(cls.on_disconnect, '$event_handler', True)

        logger.debug(f"Subclass {cls.__name__} initialized with services: {cls.__services__} and properties: {cls.__prop_defaults__}")

    @classmethod
    def __make_property(cls, name):
        """
        Creates a property for a given name.

        The property getter and setter are implemented as follows:

        - The getter returns the value of the given name from the component's state dictionary, or the default value if the name is not in the state dictionary.
        - The setter sets the value of the given name in the component's state dictionary, and also updates the store of the session with the new value.

        :param name: the name of the property
        :return: a tuple of (getter, setter)
        """
        default_value = cls.__dict__.get(name)

        def getter(self):
            return self.__state__.get(name, default_value)

        def setter(self, value):
            self.__state__.__setitem__(name, value)
            self.__session.update_store(self.id, name, value)
            logger.debug(f"Property {name} updated to {value} for component {self.id}")

        return getter, setter

    @final
    async def __exec_rpc__(self, rpc_name, args):
        """
        Executes an RPC method on this component.

        This method is called by the StreamJam server when an RPC call is received from a client.
        It looks up the given RPC method name in the component's instance methods, and calls
        it with the given arguments. If the method is not found, it raises an AttributeError.

        :param rpc_name: the name of the RPC method to call
        :param args: the arguments to pass to the method
        :return: the result of the method call
        """
        method = getattr(self, rpc_name, None)
        if callable(method):
            logger.debug(f"Executing RPC {rpc_name} with args {args} for component {self.id}")
            return await method(*args)
        else:
            logger.error(f"RPC method {rpc_name} not found in {self.__class__.__name__}")
            raise AttributeError(f"RPC method {rpc_name!r} not found in {self.__class__.__name__}")

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
        """
        Creates a new task in the component's task registry.

        This method wraps the built-in `asyncio.create_task` function and adds the created task
        to the component's task registry. It also sets up a callback to remove the task from the
        registry when it is done.

        :param coro: the coroutine to run in the new task
        :param name: the name to assign to the new task
        :return: the created task
        """
        task = asyncio.create_task(coro, name=name)
        self.__task_registry.add(task)
        task.add_done_callback(self.__task_registry.discard)
        logger.debug(f"Task {name} created for component {self.id}")
        return task

    async def _message_handler(self):
        """
        The _message_handler coroutine runs indefinitely, continuously processing messages from the message queue
        and dispatching them to the appropriate event handlers. The coroutine is responsible for processing both
        system events and custom events. System events are processed by calling the appropriate method on the component,
        while custom events are dispatched to the appropriate event handlers, which are registered using the
        `on_event` decorator.

        :return: None
        """
        while True:
            priority, (topic, message) = await self.__message_queue__.get()
            logger.debug(f"Handling message {topic} with priority {priority} for component {self.id}")
            if topic in self.__service_event_handlers:
                for handler in self.__service_event_handlers[topic]:
                    self.create_task(handler(message))

    def _register_handlers(self):
        """
        The _register_handlers method registers the component's event handlers and store update handlers with the session.
        It does this by iterating over the attributes of the component and checking if they are event handlers or store update
        handlers. If they are, the method registers them with the session using the `register_event_handler` and
        `register_store_update_handler` methods of the session.

        :return: None
        """
        # register system events
        self.__session.register_event_handler('$session_connect', self.on_connect)
        self.__session.register_event_handler('$session_disconnect', self.on_disconnect)

        # register custom events
        for attr_name in dir(self):
            handler = getattr(self, attr_name)

            if isinstance(handler, ServiceProxy):
                logger.debug(f"Ignoring service proxy attribute {attr_name} for component {self.id}")
                continue  # ignore service proxy attributes
            if hasattr(handler, 'event_handler'):
                event_name = getattr(handler, 'event_handler')
                self.__session.register_event_handler(event_name, handler)
                logger.debug(f"Registered event handler {attr_name} for event {event_name} in component {self.id}")
            if hasattr(handler, 'store_update_handler'):
                store_name = getattr(handler, 'store_update_handler')
                self.__session.register_store_update_handler(self.id, store_name, handler)
                logger.debug(f"Registered store update handler {attr_name} for store {store_name} in component {self.id}")
            if hasattr(handler, 'service_event_handler'):
                event_name, service_proxy = getattr(handler, 'service_event_handler')
                self.__session.pubsub.subscribe(
                    sid=f'{self.__session.id}/{self.id}',
                    channel=f'$Service/{service_proxy.__service_name__}',
                    topic=event_name
                )
                self.__service_event_handlers[event_name].add(handler)
                logger.debug(f"Registered service event handler {attr_name} for event {event_name} in component {self.id}")

    def _remove_handlers(self):
        """
        The _remove_handlers method removes the component's event handlers and store update handlers from the session.
        It does this by iterating over the attributes of the component and checking if they are event handlers or store update
        handlers. If they are, the method removes them from the session using the `remove_event_handler` and
        `remove_store_update_handler` methods of the session.

        :return: None
        """
        for attr_name in dir(self):
            handler = getattr(self, attr_name)
            if hasattr(handler, 'event_handler'):
                event_name = getattr(handler, 'event_handler')
                self.__session.remove_event_handler(event_name, handler)
                logger.debug(f"Removed event handler {attr_name} for event {event_name} in component {self.id}")
            if hasattr(handler, 'store_update_handler'):
                store_name = getattr(handler, 'store_update_handler')
                self.__session.remove_store_update_handler(self.id, store_name)
                logger.debug(f"Removed store update handler {attr_name} for store {store_name} in component {self.id}")

    @final
    def dispatch(self, name, data=None):
        """
        Dispatches a custom event to the component's event queue.

        :param name: the name of the event to dispatch
        :param data: the data associated with the event
        :return: None
        """
        self.__session.event_queue.put_nowait(ComponentEvent(name, self, data))
        logger.debug(f"Dispatched event {name} with data {data} for component {self.id}")

    async def on_destroy(self):
        logger.debug(f"Component {self.id} is being destroyed")

    async def on_connect(self):
        logger.debug(f"Component {self.id} has been connected")

    async def on_disconnect(self):
        logger.debug(f"Component {self.id} has been disconnected")

    @final
    async def __destroy__(self):
        """
        The __destroy__ method is called when the component is being destroyed. It is responsible for cleaning
        up any resources that the component may have allocated, such as event handlers and store update handlers.
        It also removes the component's message queue from the session's message queue map.

        :return: None
        """
        await self.on_destroy()
        self._remove_handlers()
        self.__session.pubsub.quit(self.id)
        logger.debug(f"Component {self.id} destroyed and resources cleaned up")
