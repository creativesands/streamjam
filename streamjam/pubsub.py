"""
In-memory PubSub based async message passing.
    - supports message priority
    - tasks within a channel must be unique
"""


import asyncio
from collections import defaultdict


class PubSub:
    def __init__(self):
        # channel: { topic: {sid...}}
        self.subscribers: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self.message_queues: dict[str, asyncio.PriorityQueue] = {}
        self.room_subscriptions: dict[tuple[str, str], set[str]] = defaultdict(set)  # (channel, room): {sid...}

    def register(self, sid, queue):
        self.message_queues[sid] = queue

    def subscribe(self, sid, channel, topic):
        self.subscribers[channel][topic].add(sid)

    def unsubscribe(self, sid, channel, topic):
        self.subscribers[channel][topic].discard(sid)

    def publish(self, channel, topic, message, priority=1, rooms: list[str] = None, recipients: list[str] = None):
        rooms = rooms or []
        all_recipients = set(recipients or [])
        for room in rooms:
            all_recipients.update(self.room_subscriptions[channel, room])
        for sid in self.subscribers[channel][topic]:
            if all_recipients and sid not in all_recipients:
                continue
            if sid in self.message_queues:
                self.message_queues[sid].put_nowait((priority, (topic, message)))

    def join_room(self, sid, channel, room):
        self.room_subscriptions[channel, room].add(sid)
        for topic in self.subscribers[channel]:
            self.subscribers[channel][topic].add(sid)

    def leave_room(self, sid, channel, room):
        self.room_subscriptions[channel, room].discard(sid)
        for topic in self.subscribers[channel]:
            self.subscribers[channel][topic].discard(sid)

    def quit(self, sid, channel=None):
        if channel is None:
            # Remove the subscriber from all channels and rooms
            for (c, r) in self.room_subscriptions:
                if sid in self.room_subscriptions[c, r]:
                    self.room_subscriptions[c, r].discard(sid)
                for t in self.subscribers[c]:
                    self.subscribers[c][t].discard(sid)
        else:
            # Remove the subscriber from the specified channel and its rooms
            for r in [r for (c, r) in self.room_subscriptions if c == channel]:
                self.room_subscriptions[channel, r].discard(sid)
            for t in self.subscribers[channel]:
                self.subscribers[channel][t].discard(sid)

        # Remove the subscriber's message queue
        if sid in self.message_queues:
            del self.message_queues[sid]
