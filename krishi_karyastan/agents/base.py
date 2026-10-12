"""Autonomous Agent base class implementing perception-deliberation-action cycle."""

from __future__ import annotations
from typing import Dict, List, Optional
from krishi_karyastan.core.models import (
    Coordinates,
    AgentType,
    AgentStatus,
    SectorState,
)
from krishi_karyastan.core.environment import FarmGrid
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase
from krishi_karyastan.protocols.messages import ACLMessage, Performative
from krishi_karyastan.protocols.message_bus import MessageBus


class BaseAgent:
    """Base class for all specialized autonomous physical nodes in the farm cooperative.
    
    Implements a BDI-inspired loop:
    1. Perceive: Local sensor scanning (partially observable).
    2. Update Beliefs: Dispatches observation updates to Shared Knowledge Base.
    3. Deliberate: Processes messages, negotiates, resolves goals.
    4. Act: Navigates or actuates physical tools.
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        initial_position: Coordinates,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
        sensor_radius: float = 1.5,
        battery_pct: float = 100.0,
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.position = initial_position
        self.status = AgentStatus.IDLE
        self.env = env
        self.knowledge_base = knowledge_base
        self.message_bus = message_bus
        self.sensor_radius = sensor_radius
        self.battery_pct = battery_pct

        self.target_position: Optional[Coordinates] = None
        self.patrol_route: List[Coordinates] = []
        self.patrol_index: int = 0
        self.action_log: List[dict] = []

        # Register self on message bus
        self.message_bus.register_agent(self.agent_id)

    def send_message(
        self,
        receiver: str,
        performative: Performative,
        content: any,
        current_tick: int,
        conversation_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> ACLMessage:
        """Constructs and publishes an ACLMessage through the message bus."""
        msg = ACLMessage(
            sender=self.agent_id,
            receiver=receiver,
            performative=performative,
            content=content,
            timestamp=current_tick,
            conversation_id=conversation_id or f"conv_{self.agent_id}_{current_tick}",
            in_reply_to=in_reply_to,
        )
        self.message_bus.publish(msg)
        return msg

    def perceive(self, current_tick: int) -> Dict[Coordinates, SectorState]:
        """Observes local physical surroundings within sensor radius (Partial Observability)."""
        percepts = self.env.observe(
            agent_pos=self.position,
            sensor_radius=self.sensor_radius,
            noise_std=0.2,
        )
        return percepts

    def update_beliefs(self, percepts: Dict[Coordinates, SectorState], current_tick: int) -> None:
        """Transmits localized sensor observations to update the Shared Knowledge Base."""
        for coords, state in percepts.items():
            self.knowledge_base.update_belief(
                coords=coords,
                observed_state=state,
                confidence=0.92,
                current_tick=current_tick,
                agent_id=self.agent_id,
            )

    def deliberate(self, current_tick: int) -> None:
        """Processes incoming ACL messages and selects intentions/goals. Subclasses override."""
        pass

    def act(self, current_tick: int) -> None:
        """Executes physical movement or tool actuation. Subclasses override."""
        pass

    def step(self, current_tick: int) -> None:
        """Main operational cycle executed each simulation tick."""
        if self.battery_pct <= 5.0:
            self.status = AgentStatus.CHARGING
            self.battery_pct = min(100.0, self.battery_pct + 10.0)
            return

        percepts = self.perceive(current_tick)
        self.update_beliefs(percepts, current_tick)
        self.deliberate(current_tick)
        self.act(current_tick)

        # Baseline battery consumption
        self.battery_pct = max(0.0, round(self.battery_pct - 0.1, 2))

    def navigate_towards(self, target: Coordinates) -> bool:
        """Moves one grid step towards target coordinate. Returns True if arrived."""
        if self.position == target:
            return True

        self.status = AgentStatus.NAVIGATING
        dx = target.x - self.position.x
        dy = target.y - self.position.y

        # Manhattan-style discrete movement: move along larger delta axis first
        new_x = self.position.x
        new_y = self.position.y

        if abs(dx) >= abs(dy) and dx != 0:
            new_x += 1 if dx > 0 else -1
        elif dy != 0:
            new_y += 1 if dy > 0 else -1

        next_pos = Coordinates(x=new_x, y=new_y)
        if self.env.is_valid_coordinate(next_pos):
            self.position = next_pos

        return self.position == target

    def navigate_patrol(self) -> None:
        """Advances along pre-assigned patrol waypoints."""
        if not self.patrol_route:
            return

        dest = self.patrol_route[self.patrol_index]
        arrived = self.navigate_towards(dest)
        if arrived:
            self.patrol_index = (self.patrol_index + 1) % len(self.patrol_route)

    def log_action(self, tick: int, action_name: str, details: dict) -> None:
        self.action_log.append({
            "tick": tick,
            "agent_id": self.agent_id,
            "position": self.position.to_tuple(),
            "action": action_name,
            **details,
        })
