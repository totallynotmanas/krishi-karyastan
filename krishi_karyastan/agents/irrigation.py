"""Irrigation Agent responsible for water discharge, moisture regulation, and coordinated response."""

from __future__ import annotations
from typing import Dict, List, Optional
from krishi_karyastan.agents.base import BaseAgent
from krishi_karyastan.core.models import (
    Coordinates,
    AgentType,
    AgentStatus,
    TimeSlot,
)
from krishi_karyastan.core.environment import FarmGrid
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase
from krishi_karyastan.protocols.messages import ACLMessage, Performative
from krishi_karyastan.protocols.message_bus import MessageBus
from krishi_karyastan.protocols.schemas import (
    SoilDeficiencyAlert,
    IrrigationProposal,
    CoordinatedFertigationSchedule,
)


class IrrigationAgent(BaseAgent):
    """Specialized actuator agent delivering precision irrigation water.
    
    Participates in Contract Net Protocol and bilateral negotiation with Fertilizer Agent
    to guarantee soil is not over-saturated beyond field capacity.
    """

    def __init__(
        self,
        agent_id: str,
        initial_position: Coordinates,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
        water_tank_liters: float = 120.0,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.IRRIGATION,
            initial_position=initial_position,
            env=env,
            knowledge_base=knowledge_base,
            message_bus=message_bus,
            sensor_radius=1.0,
        )
        self.water_tank_liters = water_tank_liters
        self.max_tank_liters = water_tank_liters
        self.active_schedule: Optional[CoordinatedFertigationSchedule] = None
        self.target_task_coords: Optional[Coordinates] = None
        self.target_water_volume: float = 0.0

        # Subscribe to deficiency alerts
        self.message_bus.subscribe(self.agent_id, "alerts")

    def deliberate(self, current_tick: int) -> None:
        """Processes incoming alerts, CFPs, and confirmed schedules."""
        messages = self.message_bus.receive(self.agent_id)

        for msg in messages:
            if msg.performative == Performative.CONFIRM and isinstance(msg.content, CoordinatedFertigationSchedule):
                self._handle_confirmed_schedule(msg.content)
            elif msg.performative == Performative.CONFIRM and isinstance(msg.content, dict):
                sched = CoordinatedFertigationSchedule(**msg.content)
                self._handle_confirmed_schedule(sched)

    def _handle_confirmed_schedule(self, schedule: CoordinatedFertigationSchedule) -> None:
        """Adopts a negotiated fertigation plan."""
        self.active_schedule = schedule
        self.target_task_coords = schedule.target_coords
        self.target_water_volume = schedule.irrigation_volume_liters
        self.status = AgentStatus.NAVIGATING

    def formulate_proposal(
        self,
        alert: SoilDeficiencyAlert,
        current_tick: int,
        carrier_water_offset_liters: float = 0.0,
    ) -> IrrigationProposal:
        """Computes water requirements and time window for intervention proposal."""
        target_coords = alert.coords
        transit_ticks = self.position.manhattan_distance(target_coords)

        # Gross moisture deficit
        moisture_def = alert.moisture_deficit_pct
        gross_water_liters = max(2.0, moisture_def / 2.0)

        # Net water deducting carrier fluid contributed by fertilizer agent
        net_water_liters = max(0.0, gross_water_liters - carrier_water_offset_liters)
        estimated_gain = net_water_liters * 2.0

        # Time slot calculation (allow arrival + actuation ticks)
        actuation_ticks = max(2, int(net_water_liters / 4.0))
        start_tick = current_tick + transit_ticks + 1
        end_tick = start_tick + actuation_ticks

        proposal = IrrigationProposal(
            agent_id=self.agent_id,
            target_coords=target_coords,
            water_volume_liters=round(net_water_liters, 2),
            estimated_moisture_gain_pct=round(estimated_gain, 2),
            time_slot=TimeSlot(start_tick=start_tick, end_tick=end_tick),
            water_flow_rate_lpm=5.0,
            energy_cost=1.0 + (net_water_liters * 0.1),
        )
        return proposal

    def act(self, current_tick: int) -> None:
        """Executes navigation to target sector and controlled irrigation actuation."""
        if not self.active_schedule:
            self.status = AgentStatus.IDLE
            return

        slot = self.active_schedule.irrigation_slot

        # If before scheduled slot, navigate towards sector
        if current_tick < slot.start_tick:
            arrived = self.navigate_towards(self.target_task_coords)
            if arrived:
                self.status = AgentStatus.IDLE
            return

        # If inside scheduled time window and at target sector
        if slot.start_tick <= current_tick <= slot.end_tick:
            if self.position == self.target_task_coords:
                self.status = AgentStatus.ACTUATING
                vol_per_tick = self.target_water_volume / slot.duration()
                vol_to_apply = min(self.water_tank_liters, vol_per_tick)

                new_moisture, is_oversaturated = self.env.apply_water(
                    coords=self.position,
                    volume_liters=vol_to_apply,
                    agent_id=self.agent_id,
                )
                self.water_tank_liters = max(0.0, round(self.water_tank_liters - vol_to_apply, 2))

                self.log_action(
                    tick=current_tick,
                    action_name="IRRIGATE_SECTOR",
                    details={
                        "volume_applied": round(vol_to_apply, 2),
                        "new_moisture": new_moisture,
                        "oversaturated": is_oversaturated,
                    },
                )
            else:
                # Still navigating to coordinate
                self.navigate_towards(self.target_task_coords)
            return

        # Past scheduled slot: task completed
        if current_tick > slot.end_tick:
            self.log_action(
                tick=current_tick,
                action_name="IRRIGATION_TASK_COMPLETED",
                details={"target": self.target_task_coords.to_tuple()},
            )
            self.active_schedule = None
            self.target_task_coords = None
            self.target_water_volume = 0.0
            self.status = AgentStatus.IDLE
