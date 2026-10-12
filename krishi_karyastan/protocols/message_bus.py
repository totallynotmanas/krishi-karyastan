"""Decentralized and pub-sub message bus for FIPA-ACL inter-agent communication."""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Optional, Set
from krishi_karyastan.protocols.messages import ACLMessage, Performative


class MessageBus:
    """Asynchronous/tick-based in-memory message broker.
    
    Supports:
    - Point-to-point direct agent messaging
    - Broadcast and topic subscriptions (e.g. 'alerts', 'proposals', 'knowledge_base')
    - Conversation audit trails and telemetry tracing
    """

    def __init__(self):
        self._inboxes: Dict[str, List[ACLMessage]] = defaultdict(list)
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)  # topic -> set of agent_ids
        self._history: List[ACLMessage] = []
        self._registered_agents: Set[str] = set()

    def register_agent(self, agent_id: str) -> None:
        """Registers an agent on the message bus."""
        self._registered_agents.add(agent_id)
        # Automatically subscribe agent to broadcast topic
        self.subscribe(agent_id, "broadcast")

    def unregister_agent(self, agent_id: str) -> None:
        """Unregisters an agent and removes all topic subscriptions."""
        self._registered_agents.discard(agent_id)
        for subscribers in self._subscriptions.values():
            subscribers.discard(agent_id)
        if agent_id in self._inboxes:
            del self._inboxes[agent_id]

    def subscribe(self, agent_id: str, topic: str) -> None:
        """Subscribes an agent to a specific broadcast or topic channel."""
        self._subscriptions[topic].add(agent_id)

    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribes an agent from a topic."""
        self._subscriptions[topic].discard(agent_id)

    def publish(self, message: ACLMessage) -> int:
        """Dispatches an ACLMessage to recipient agent or topic subscribers.
        
        Returns:
            The number of recipients that received the message.
        """
        self._history.append(message)
        delivered_count = 0

        receiver = message.receiver

        # Case 1: Topic or Broadcast delivery
        if receiver in self._subscriptions or receiver == "broadcast":
            topic = "broadcast" if receiver == "broadcast" else receiver
            subscribers = self._subscriptions.get(topic, set())
            for sub_agent in subscribers:
                # Do not deliver broadcast messages back to sender unless explicitly configured
                if sub_agent != message.sender:
                    self._inboxes[sub_agent].append(message)
                    delivered_count += 1
            return delivered_count

        # Case 2: Direct Point-to-Point delivery
        self._inboxes[receiver].append(message)
        delivered_count = 1
        return delivered_count

    def receive(self, agent_id: str) -> List[ACLMessage]:
        """Drains and returns all queued messages for an agent."""
        if agent_id not in self._inboxes:
            return []
        messages = self._inboxes[agent_id]
        self._inboxes[agent_id] = []
        return messages

    def peek(self, agent_id: str) -> List[ACLMessage]:
        """Views messages in agent's inbox without consuming them."""
        return list(self._inboxes.get(agent_id, []))

    def get_history(self, limit: Optional[int] = None) -> List[ACLMessage]:
        """Returns ordered history of dispatched messages."""
        if limit:
            return self._history[-limit:]
        return list(self._history)

    def get_conversation_trace(self, conversation_id: str) -> List[ACLMessage]:
        """Filters message history by conversation ID for negotiation review."""
        return [msg for msg in self._history if msg.conversation_id == conversation_id]

    def get_alerts(self) -> List[ACLMessage]:
        """Retrieves all deficiency alerts flagged in the message stream."""
        return [
            msg for msg in self._history
            if msg.performative == Performative.INFORM and "alert" in msg.conversation_id.lower()
        ]

    def clear(self) -> None:
        """Resets the message bus state."""
        self._inboxes.clear()
        self._subscriptions.clear()
        self._history.clear()
        self._registered_agents.clear()
