from .server import (
    StreamJam
)

from .service import (
    Service,
    ServiceClient,
    SocketService
)

from .base import (
    ComponentEvent,
    ServiceEvent
)

from .component import (
    Component
)


__all__ = [
    "StreamJam",
    "Service",
    "ServiceClient",
    "SocketService",
    "ComponentEvent",
    "ServiceEvent",
    "Component"
]


"""
Todos:
    - [ ] component __post_init__ -> init
    - [ ] component on_connect so that every time it is re/connected it can update state if neededftp
    - [ ] rewrite server as a service so that other services can access it 
    - [ ] client rpc-response handler
    - [ ] setup logging
    - [ ] rpc generator in FE if backend is async generator
    - [ ] server dev mode with transpilation based on 'watchfiles' module
    - [ ] jsondiff store updates
    - [ ] move to AnyIO
    - [ ] error handling and propagation
    - [ ] close connection but maintain state for a preset time
    - [ ] with block batch update in both FE and BE
    - [ ] global state stores
    - [ ] batch calls for create-component and remove-component
    - [ ] server on: add-component if no id then add to client_components pool which can be cleared on ws close
    - [ ] debounce store-update of same component & store
    - [ ] ability to turn off store-sync on select stores
    - [ ] debounce rpc calls with decorator
    - [ ] Hot Module Replacement: reload all server instances of component and copy over state if all props exists
    - [?] use hash('component_path') to represent component type (no longer required!)
    - [?] deal with duplicate component names (no longer required!)
    - [x] event dispatch from methods
    - [x] on_update(prop) handler in component
    - [x] delete local component objects when delete in FE
"""
