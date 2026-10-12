"""Harvesting Agent for maturity monitoring and coordinated crop yield collection."""

from __future__ import annotations
from typing import Dict, List, Optional
from krishi_karyastan.agents.base import BaseAgent
from krishi_karyastan.core.models import (
    Coordinates,
    AgentType,
    AgentStatus,
    CropStage,
    SectorState,
)
from krishi_karyastan.core.environment import FarmGrid
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase
from krishi_karyastan.protocols.messages import ACLMessage, Performative
from krishi_karyastan.protocols.message_bus import MessageBus


class HarvestingAgent(BaseAgent):
    """Specialized harvesting unit coordinating crop collection based on shared maturity data."""

    def __init__(
        self,
        agent_id: str,
        initial_position: Coordinates,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.HARVESTER,
            initial_position=initial_position,
            env=env,
            knowledge_base=knowledge_base,
            message_bus=message_bus,
            sensor_radius=1.2,
        )
        self.harvest_bin_kg: float = 0.0

    def deliberate(self, current_tick: int) -> None:
        """Checks local sector maturity."""
        percepts = self.perceive(current_tick)
        for coords, state in percepts.items():
            if state.crop_stage == CropStage.MATURE and self.position == coords:
                self.status = AgentStatus.ACTUATING
                state.crop_stage = CropStage.HARVESTED
                self.harvest_bin_kg += 25.0
                self.log_action(
                    tick=current_tick,
                    action_name="HARVEST_CROP",
                    details={"target": coords.to_tuple(), "yield_kg": 25.0},
                )
                break

    def act(self, current_tick: int) -> None:
        """Patrols or moves across sectors."""
        self.navigate_patrol()
