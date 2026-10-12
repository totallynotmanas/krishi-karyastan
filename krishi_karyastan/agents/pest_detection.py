"""Pest Detection Agent for optical pathogen scouting and infestation alerts."""

from __future__ import annotations
from typing import Dict, List, Optional
from krishi_karyastan.agents.base import BaseAgent
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


class PestDetectionAgent(BaseAgent):
    """Specialized optical surveillance agent scouting for weed outbreaks and insect infestation."""

    def __init__(
        self,
        agent_id: str,
        initial_position: Coordinates,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
        pest_threshold: float = 0.25,
        sensor_radius: float = 2.0,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.PEST_DETECTOR,
            initial_position=initial_position,
            env=env,
            knowledge_base=knowledge_base,
            message_bus=message_bus,
            sensor_radius=sensor_radius,
        )
        self.pest_threshold = pest_threshold

    def deliberate(self, current_tick: int) -> None:
        """Evaluates localized vision percepts for pest outbreaks."""
        percepts = self.perceive(current_tick)
        for coords, state in percepts.items():
            if state.pest_index >= self.pest_threshold:
                # Transmit pest warning
                msg = ACLMessage(
                    sender=self.agent_id,
                    receiver="alerts",
                    performative=Performative.INFORM,
                    protocol="fipa-request-inform",
                    conversation_id=f"alert_pest_{coords.x}_{coords.y}",
                    content={
                        "type": "PestInfestationAlert",
                        "coords": coords.model_dump(),
                        "pest_index": state.pest_index,
                        "crop_stage": state.crop_stage.value,
                        "flagged_by": self.agent_id,
                        "tick": current_tick,
                    },
                    timestamp=current_tick,
                )
                self.message_bus.publish(msg)
                self.log_action(
                    tick=current_tick,
                    action_name="FLAG_PEST_INFESTATION",
                    details={"target": coords.to_tuple(), "pest_index": state.pest_index},
                )

    def act(self, current_tick: int) -> None:
        """Patrols farm sectors."""
        self.navigate_patrol()
