"""
Todos:
    - [ ] close connection but maintain state for a preset time
    - [ ] delete local component objects when delete in FE
    - [ ] with block batch update in both FE and BE
    - [ ] global state stores
    - [ ] error handling and propagation
    - [ ] event dispatch from methods
"""

from .server import StreamJam, Component
from .component import rpc
