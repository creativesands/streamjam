"""
In-memory PubSub based async message passing.
    - supports message priority
    - tasks within a channel must be unique
"""


import asyncio
import logging
import time
from collections import defaultdict

from .base import ServiceEvent


logger = logging.getLogger('streamjam.pubsub')
logger.setLevel(logging.INFO)


class PubSub:
    def __init__(self):
        # channel: { topic: {sid...}}
        self.subscribers: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self.message_queues: dict[str, asyncio.PriorityQueue] = {}
        self.room_subscriptions: dict[tuple[str, str], set[str]] = defaultdict(set)  # (channel, room): {sid...}
        
        # Stats tracking
        self.event_count = 0
        self.last_event_count = 0
        self.last_stats_time = time.time()
        self.stats_task = None  # Don't create task in __init__

    async def start_stats_publisher(self):
        """Start the background task that publishes stats"""
        if self.stats_task is None:  # Only create task if it doesn't exist
            self.stats_task = asyncio.create_task(self._publish_stats())

    async def _publish_stats(self):
        """Periodically publish stats about the pubsub system"""
        while True:
            await asyncio.sleep(1.0)  # Publish every second
            
            logger.debug(f"Publishing stats - event_count: {self.event_count}, last_event_count: {self.last_event_count}, last_stats_time: {self.last_stats_time}")
            
            # Calculate events per second
            current_time = time.time()
            elapsed = current_time - self.last_stats_time
            events_per_second = (self.event_count - self.last_event_count) / elapsed
            
            # Update tracking variables
            self.last_event_count = self.event_count
            self.last_stats_time = current_time
            
            # Count unique channels and topics
            channel_count = len(self.subscribers)
            topic_count = sum(len(topics) for topics in self.subscribers.values())
            subscriber_count = len(self.message_queues)
            
            # Create and publish stats event
            stats = {
                "events_per_second": round(events_per_second, 2),
                "channel_count": channel_count,
                "topic_count": topic_count,
                "subscriber_count": subscriber_count
            }
            
            stats_event = ServiceEvent("stats", "PubSub", data=stats)
            self.publish("$PubSub", stats_event)

    def register(self, sid, queue):
        self.message_queues[sid] = queue

    def subscribe(self, sid, channel, topic):
        self.subscribers[channel][topic].add(sid)

    def unsubscribe(self, sid, channel, topic):
        self.subscribers[channel][topic].discard(sid)

    def publish(self, channel, event: ServiceEvent, rooms: list[str] = None, recipients: list[str] = None, exclude: list[str] = None):
        # Increment event counter
        self.event_count += 1
        
        logger.debug(f"<-- Publishing event - {event.name} to channel: {channel}, rooms: {rooms}, recipients: {recipients}, exclude: {exclude}")
        
        # Initialize sets
        rooms = rooms or []
        all_recipients = set(recipients or [])
        exclude_set = set(exclude or [])
        
        # Gather room members
        for room in rooms:
            room_members = self.room_subscriptions[channel, room]
            logger.debug(f"Room '{room}' members: {room_members}")
            all_recipients.update(room_members)
        
        # Apply exclusions
        all_recipients = all_recipients - exclude_set
        logger.debug(f"Potential recipients after room expansion and exclusions: {all_recipients}")
        
        # Get subscribers for this event
        event_subscribers = self.subscribers[channel][event.name]
        logger.debug(f"Subscribed to {channel}/{event.name}: {event_subscribers}")
        
        # Track delivery statistics
        delivery_count = 0
        skipped_excluded = 0
        skipped_not_in_recipients = 0
        skipped_no_queue = 0
        
        # Process deliveries
        for sid in event_subscribers:
            if sid in exclude_set:
                skipped_excluded += 1
                logger.debug(f"Skipping {sid}: in exclude list")
                continue
            
            if all_recipients and sid not in all_recipients:
                skipped_not_in_recipients += 1
                logger.debug(f"Skipping {sid}: not in recipients list")
                continue
            
            if sid not in self.message_queues:
                skipped_no_queue += 1
                logger.debug(f"Skipping {sid}: no message queue")
                continue
            
            logger.debug(f"Delivering to {sid}")
            self.message_queues[sid].put_nowait(event)
            delivery_count += 1
        
        logger.debug(f"--> Delivery stats - delivered: {delivery_count}, skipped: excluded={skipped_excluded}, no_recipient={skipped_not_in_recipients}, no_queue={skipped_no_queue}")

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
