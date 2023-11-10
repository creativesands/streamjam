import json
import typing as tp
from dataclasses import dataclass


@dataclass
class Message:
    topic: tp.Union[str, tp.Tuple]
    content: tp.Any = None
    req_id: tp.Optional[str] = None

    def serialize(self):
        if isinstance(self.topic, tuple):
            self.topic = '>'.join(self.topic)
        return json.dumps((self.req_id, self.topic, self.content))
