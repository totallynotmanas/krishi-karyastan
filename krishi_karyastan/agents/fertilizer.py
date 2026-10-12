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
    
    Coordinates with Irrigation Agent via FIPA-ACL to align timing and ensure carrier water
    does not cause root flooding or nutrient leaching, and vacates sectors to prevent collisions.
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
        self.max_nitrogen_stock_g = nitrogen_stock_g
        self.carrier_water_liters = carrier_water_liters
        self.max_carrier_liters = carrier_water_liters

        self.active_schedule: Optional[CoordinatedFertigationSchedule] = None
        self.target_task_coords: Optional[Coordinates] = None
        self.target_nitrogen_g: float = 0.0
        self.target_carrier_liters: float = 0.0
        self.is_negotiating: bool = False
        self._handled_alerts: set = set()

        # Subscribe to deficiency alerts
        self.message_bus.subscribe(self.agent_id, "alerts")

    def deliberate(self, current_tick: int) -> None:
        """Processes incoming alerts, negotiation dialogs, and confirmed schedules."""
        messages = self.message_bus.receive(self.agent_id)

        for msg in messages:
            # 1. Received confirmed schedule (from Coordinator or direct agreement)
            if msg.performative == Performative.CONFIRM:
                sched = msg.content if isinstance(msg.content, CoordinatedFertigationSchedule) else CoordinatedFertigationSchedule(**msg.content)
                self._handle_confirmed_schedule(sched)
                self.is_negotiating = False

            # 2. Received proposal acceptance from Irrigation Agent
            elif msg.performative == Performative.ACCEPT_PROPOSAL:
                sched = msg.content if isinstance(msg.content, CoordinatedFertigationSchedule) else CoordinatedFertigationSchedule(**msg.content)
                self._handle_confirmed_schedule(sched)
                self.is_negotiating = False
                # Send confirmation acknowledgement
                self.send_message(
                    receiver=msg.sender,
                    performative=Performative.CONFIRM,
                    content=sched,
                    current_tick=current_tick,
                    conversation_id=msg.conversation_id,
                    in_reply_to=msg.message_id,
                )

            # 3. Received soil deficiency alert: initiate bilateral negotiation with Irrigation Agent
            elif msg.performative == Performative.INFORM and "alert" in msg.conversation_id.lower():
                if self.active_schedule is None and not self.is_negotiating:
                    content = msg.content
                    alert = content if isinstance(content, SoilDeficiencyAlert) else SoilDeficiencyAlert(**content)
                    if alert.alert_id not in self._handled_alerts:
                        self._handled_alerts.add(alert.alert_id)
                        self._initiate_negotiation_with_irrigation(alert, current_tick)

    def _initiate_negotiation_with_irrigation(self, alert: SoilDeficiencyAlert, current_tick: int) -> None:
        """Dispatches FIPA-ACL CFP to Irrigation Agent proposing joint response."""
        fert_proposal = self.formulate_proposal(alert, current_tick)
        self.is_negotiating = True
        self.status = AgentStatus.NEGOTIATING

        self.send_message(
            receiver="Irrigator_Unit_1",
            performative=Performative.CFP,
            content={
                "alert": alert.model_dump(),
                "fert_proposal": fert_proposal.model_dump(),
            },
            current_tick=current_tick,
            conversation_id=f"fertigation_neg_{alert.coords.x}_{alert.coords.y}_{current_tick}",
        )

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
        """Executes navigation to sector, nutrient dosing, and automatic vacating to prevent collisions."""
        # Case A: Active schedule underway
        if self.active_schedule:
            slot = self.active_schedule.fertilizer_slot

            dist = self.position.manhattan_distance(self.target_task_coords)
            # 1. Before scheduled slot: hold outside until exactly time to enter
            if current_tick < slot.start_tick:
                ticks_until_start = slot.start_tick - current_tick
                if ticks_until_start > dist and dist <= 1:
                    self.status = AgentStatus.IDLE
                    return
                self.navigate_towards(self.target_task_coords)
                return

            # 2. Inside scheduled slot: actuate dosing at target
            if slot.start_tick <= current_tick <= slot.end_tick:
                if self.position == self.target_task_coords:
                    self.status = AgentStatus.ACTUATING
                    dose_per_tick = self.target_nitrogen_g / max(1, slot.duration())
                    carrier_per_tick = self.target_carrier_liters / max(1, slot.duration())

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

            # 3. Scheduled slot ended: task completed, immediately vacate sector
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
                # Begin vacating back towards home station
                self.navigate_towards(self.home_station)
                return

        # Case B: No active schedule - return to home station to resupply and charge
        if self.position != self.home_station:
            self.navigate_towards(self.home_station)
        else:
            # At home station: resupply nutrients & recharge
            if self.nitrogen_stock_g < self.max_nitrogen_stock_g or self.battery_pct < 95.0:
                self.status = AgentStatus.CHARGING
                self.nitrogen_stock_g = min(self.max_nitrogen_stock_g, round(self.nitrogen_stock_g + 50.0, 2))
                self.carrier_water_liters = min(self.max_carrier_liters, round(self.carrier_water_liters + 10.0, 2))
            else:
                self.status = AgentStatus.IDLE
