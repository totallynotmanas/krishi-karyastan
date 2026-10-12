"""Fertilizer Agent responsible for precision nutrient dosing and carrier fluid scheduling."""

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
    FertilizerProposal,
    CoordinatedFertigationSchedule,
)


class FertilizerAgent(BaseAgent):
    """Specialized actuator agent delivering precision NPK nutrients.
    
    Coordinates with Irrigation Agent to align timing and ensure carrier water
    does not cause root flooding or nutrient leaching.
    """

    def __init__(
        self,
        agent_id: str,
        initial_position: Coordinates,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
        nitrogen_stock_g: float = 600.0,
        carrier_water_liters: float = 60.0,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.FERTILIZER,
            initial_position=initial_position,
            env=env,
            knowledge_base=knowledge_base,
            message_bus=message_bus,
            sensor_radius=1.0,
        )
        self.nitrogen_stock_g = nitrogen_stock_g
        self.carrier_water_liters = carrier_water_liters
        self.active_schedule: Optional[CoordinatedFertigationSchedule] = None
        self.target_task_coords: Optional[Coordinates] = None
        self.target_nitrogen_g: float = 0.0
        self.target_carrier_liters: float = 0.0

        # Subscribe to deficiency alerts
        self.message_bus.subscribe(self.agent_id, "alerts")

    def deliberate(self, current_tick: int) -> None:
        """Processes incoming confirmed schedules and agreements."""
        messages = self.message_bus.receive(self.agent_id)

        for msg in messages:
            if msg.performative == Performative.CONFIRM and isinstance(msg.content, CoordinatedFertigationSchedule):
                self._handle_confirmed_schedule(msg.content)
            elif msg.performative == Performative.CONFIRM and isinstance(msg.content, dict):
                sched = CoordinatedFertigationSchedule(**msg.content)
                self._handle_confirmed_schedule(sched)

    def _handle_confirmed_schedule(self, schedule: CoordinatedFertigationSchedule) -> None:
        """Adopts confirmed joint fertigation schedule."""
        self.active_schedule = schedule
        self.target_task_coords = schedule.target_coords
        self.target_nitrogen_g = schedule.nitrogen_dose_g
        self.target_carrier_liters = schedule.carrier_fluid_liters
        self.status = AgentStatus.NAVIGATING

    def formulate_proposal(
        self,
        alert: SoilDeficiencyAlert,
        current_tick: int,
    ) -> FertilizerProposal:
        """Calculates nutrient dosing requirements and proposed operational time slot."""
        target_coords = alert.coords
        transit_ticks = self.position.manhattan_distance(target_coords)

        # Nitrogen deficit: 1g N provides ~2.5 ppm in sector
        n_def = alert.nitrogen_deficit_ppm
        n_dose_g = max(5.0, min(150.0, n_def / 2.5))

        # Carrier fluid required for dilution (prevents chemical burn and promotes root uptake)
        carrier_liters = max(2.0, round(n_dose_g * 0.05, 2))
        carrier_moisture_gain = carrier_liters * 2.0

        # Time slot (arrival + application duration)
        actuation_ticks = max(2, int(n_dose_g / 25.0))
        start_tick = current_tick + transit_ticks + 1
        end_tick = start_tick + actuation_ticks

        proposal = FertilizerProposal(
            agent_id=self.agent_id,
            target_coords=target_coords,
            nitrogen_dose_g=round(n_dose_g, 2),
            phosphorus_dose_g=round(n_dose_g * 0.3, 2),
            potassium_dose_g=round(n_dose_g * 0.4, 2),
            carrier_fluid_liters=round(carrier_liters, 2),
            carrier_moisture_gain_pct=round(carrier_moisture_gain, 2),
            time_slot=TimeSlot(start_tick=start_tick, end_tick=end_tick),
            energy_cost=1.2 + (n_dose_g * 0.01),
        )
        return proposal

    def act(self, current_tick: int) -> None:
        """Executes navigation to sector and nutrient dosing actuation."""
        if not self.active_schedule:
            self.status = AgentStatus.IDLE
            return

        slot = self.active_schedule.fertilizer_slot

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
                dose_per_tick = self.target_nitrogen_g / slot.duration()
                carrier_per_tick = self.target_carrier_liters / slot.duration()

                n_to_apply = min(self.nitrogen_stock_g, dose_per_tick)
                c_to_apply = min(self.carrier_water_liters, carrier_per_tick)

                nutrients, new_moist, is_oversat = self.env.apply_nutrients(
                    coords=self.position,
                    nitrogen_g=n_to_apply,
                    phosphorus_g=n_to_apply * 0.3,
                    potassium_g=n_to_apply * 0.4,
                    carrier_water_liters=c_to_apply,
                    agent_id=self.agent_id,
                )

                self.nitrogen_stock_g = max(0.0, round(self.nitrogen_stock_g - n_to_apply, 2))
                self.carrier_water_liters = max(0.0, round(self.carrier_water_liters - c_to_apply, 2))

                self.log_action(
                    tick=current_tick,
                    action_name="APPLY_FERTILIZER",
                    details={
                        "n_applied": round(n_to_apply, 2),
                        "carrier_applied": round(c_to_apply, 2),
                        "new_moisture": new_moist,
                        "oversaturated": is_oversat,
                    },
                )
            else:
                self.navigate_towards(self.target_task_coords)
            return

        # Past scheduled slot
        if current_tick > slot.end_tick:
            self.log_action(
                tick=current_tick,
                action_name="FERTILIZER_TASK_COMPLETED",
                details={"target": self.target_task_coords.to_tuple()},
            )
            self.active_schedule = None
            self.target_task_coords = None
            self.target_nitrogen_g = 0.0
            self.target_carrier_liters = 0.0
            self.status = AgentStatus.IDLE
