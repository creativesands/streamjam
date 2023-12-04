"""
Todos:
    - [ ] use hash('component_path') to represent component type
    - [ ] deal with duplicate component names
    - [ ] close connection but maintain state for a preset time
    - [ ] delete local component objects when delete in FE
    - [ ] with block batch update in both FE and BE
    - [ ] global state stores
    - [ ] error handling and propagation
    - [x] event dispatch from methods
    - [ ] client rpc-response handler
    - [x] on_update(prop) handler in component
    - [ ] batch calls for create-component and remove-component
    - [ ] jsondiff store updates
    - [ ] server on: add-component if no id then add to client_components pool which can be cleared on ws close
    - [ ] debounce store-update of same component & store
    - [ ] server dev mode with transpilation based on 'watchfiles' module
"""

from .server import StreamJam
from .component import Component, Event
