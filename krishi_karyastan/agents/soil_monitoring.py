"""Soil Monitoring Agent implementing localized sensing, belief updating, and anomaly flagging."""

from __future__ import annotations
from typing import Dict, List, Optional, Set
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
from krishi_karyastan.protocols.schemas import SoilDeficiencyAlert, AlertUrgency


class SoilMonitoringAgent(BaseAgent):
    """Specialized distributed mobile sensor node.
    
    Responsibilities:
    1. Patrols assigned sectors under partial observability.
    2. Gathers high-resolution soil moisture and NPK sensor readings.
    3. Fuses observations into Shared Knowledge Base via FIPA-ACL INFORM performatives.
    4. Detects agronomic deficits (dry and/or nutrient-poor patches) and broadcasts alerts.
    """

    def __init__(
        self,
        agent_id: str,
        initial_position: Coordinates,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
        moisture_threshold: float = 35.0,
        nitrogen_threshold: float = 85.0,
        sensor_radius: float = 1.5,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.SOIL_MONITOR,
            initial_position=initial_position,
            env=env,
            knowledge_base=knowledge_base,
            message_bus=message_bus,
            sensor_radius=sensor_radius,
        )
        self.moisture_threshold = moisture_threshold
        self.nitrogen_threshold = nitrogen_threshold
        self.flagged_patches: Dict[Coordinates, int] = {}  # coords -> last_flagged_tick
        self.alert_cooldown_ticks: int = 15

    def deliberate(self, current_tick: int) -> None:
        """Evaluates recent local observations for soil anomalies."""
        self.status = AgentStatus.SENSING
        percepts = self.perceive(current_tick)

        for coords, state in percepts.items():
            # Check if sector suffers from moisture or nitrogen deficiency
            is_dry = state.moisture_pct < self.moisture_threshold
            is_nutrient_poor = state.nutrients.nitrogen_ppm < self.nitrogen_threshold

            if is_dry or is_nutrient_poor:
                last_flagged = self.flagged_patches.get(coords, -999)
                if (current_tick - last_flagged) >= self.alert_cooldown_ticks:
                    self._flag_deficiency(coords, state, current_tick)
                    self.flagged_patches[coords] = current_tick
            elif coords in self.flagged_patches and state.moisture_pct >= 45.0 and state.nutrients.nitrogen_ppm >= 90.0:
                # Patch has successfully recovered!
                del self.flagged_patches[coords]
                self.log_action(
                    tick=current_tick,
                    action_name="PATCH_REMEDIATED",
                    details={
                        "target": coords.to_tuple(),
                        "moisture": state.moisture_pct,
                        "nitrogen": state.nutrients.nitrogen_ppm,
                    },
                )

    def _flag_deficiency(self, coords: Coordinates, state: SectorState, current_tick: int) -> None:
        """Formulates and broadcasts a FIPA-ACL SoilDeficiencyAlert message."""
        alert = SoilDeficiencyAlert.create_from_reading(
            coords=coords,
            moisture=state.moisture_pct,
            nitrogen=state.nutrients.nitrogen_ppm,
            phosphorus=state.nutrients.phosphorus_ppm,
            potassium=state.nutrients.potassium_ppm,
            flagged_by=self.agent_id,
            tick=current_tick,
            target_moisture=50.0,
            target_nitrogen=120.0,
        )

        # 1. Update Knowledge Base explicitly
        self.knowledge_base.update_belief(
            coords=coords,
            observed_state=state,
            confidence=0.98,
            current_tick=current_tick,
            agent_id=self.agent_id,
        )

        # 2. Dispatch INFORM to the 'alerts' topic for actuator agents
        msg = ACLMessage(
            sender=self.agent_id,
            receiver="alerts",
            performative=Performative.INFORM,
            protocol="fipa-request-inform",
            conversation_id=f"alert_patch_{coords.x}_{coords.y}",
            content=alert,
            timestamp=current_tick,
        )
        self.message_bus.publish(msg)

        self.log_action(
            tick=current_tick,
            action_name="FLAG_DEFICIENT_PATCH",
            details={
                "target": coords.to_tuple(),
                "moisture": state.moisture_pct,
                "nitrogen": state.nutrients.nitrogen_ppm,
                "urgency": alert.urgency.value,
            },
        )

    def act(self, current_tick: int) -> None:
        """Advances patrol movement across farm sectors."""
        self.navigate_patrol()
