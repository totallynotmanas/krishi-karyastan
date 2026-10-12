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
    FertilizerProposal,
    CoordinatedFertigationSchedule,
)
from krishi_karyastan.negotiation.saturation_governor import SaturationGovernor
from krishi_karyastan.negotiation.collision_avoidance import CollisionAvoidanceTable


class IrrigationAgent(BaseAgent):
    """Specialized actuator agent delivering precision irrigation water.
    
    Participates in Contract Net Protocol and bilateral negotiation with Fertilizer Agent
    to guarantee soil is not over-saturated beyond field capacity and vacates sectors to prevent collisions.
    """

    def __init__(
        self,
        agent_id: str,
        initial_position: Coordinates,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
        water_tank_liters: float = 120.0,
        saturation_governor: Optional[SaturationGovernor] = None,
        collision_table: Optional[CollisionAvoidanceTable] = None,
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

        self.saturation_governor = saturation_governor or SaturationGovernor()
        self.collision_table = collision_table or CollisionAvoidanceTable()

        # Subscribe to deficiency alerts
        self.message_bus.subscribe(self.agent_id, "alerts")

    def deliberate(self, current_tick: int) -> None:
        """Processes incoming alerts, CFPs, and confirmed schedules."""
        messages = self.message_bus.receive(self.agent_id)

        for msg in messages:
            # 1. Direct confirmation
            if msg.performative == Performative.CONFIRM:
                sched = msg.content if isinstance(msg.content, CoordinatedFertigationSchedule) else CoordinatedFertigationSchedule(**msg.content)
                self._handle_confirmed_schedule(sched)

            # 2. Received CFP from Fertilizer Agent to negotiate joint intervention
            elif msg.performative == Performative.CFP and isinstance(msg.content, dict):
                self._handle_cfp_from_fertilizer(msg, current_tick)

    def _handle_cfp_from_fertilizer(self, msg: ACLMessage, current_tick: int) -> None:
        """Evaluates fertilizer proposal, checks saturation bounds, deconflicts slots, and accepts."""
        raw_alert = msg.content.get("alert")
        raw_fert_prop = msg.content.get("fert_proposal")
        if not raw_alert or not raw_fert_prop:
            return

        alert = SoilDeficiencyAlert(**raw_alert)
        fert_prop = FertilizerProposal(**raw_fert_prop)

        # Gross water demand
        gross_water = max(2.0, alert.moisture_deficit_pct / 2.0)
        carrier_water = fert_prop.carrier_fluid_liters

        # Net water deducting carrier fluid
        net_water = max(0.0, gross_water - carrier_water)

        # Validate with Saturation Governor
        eval_res = self.saturation_governor.evaluate_fertigation_plan(
            current_moisture_pct=alert.current_moisture_pct,
            carrier_water_liters=carrier_water,
            proposed_irrigation_liters=net_water,
            field_capacity_pct=alert.field_capacity_pct,
            saturation_limit_pct=alert.saturation_limit_pct,
        )
        final_water = eval_res.adjusted_irrigation_liters

        # Reserve Fertilizer slot
        self.collision_table.reserve(
            coords=alert.coords,
            slot=fert_prop.time_slot,
            agent_id=fert_prop.agent_id,
            reason="Fertilizer Application",
        )

        # Deconflict Irrigation Slot (start AFTER fertilizer finishes + 1 tick buffer to vacate sector!)
        irr_duration = max(2, int(final_water / 4.0))
        earliest_irr_start = max(
            fert_prop.time_slot.end_tick + 2,
            self.position.manhattan_distance(alert.coords) + current_tick + 1,
        )
        irr_slot = self.collision_table.find_first_available_slot(
            coords=alert.coords,
            duration=irr_duration,
            earliest_start=earliest_irr_start,
            agent_id=self.agent_id,
        )
        self.collision_table.reserve(
            coords=alert.coords,
            slot=irr_slot,
            agent_id=self.agent_id,
            reason="Irrigation Application",
        )

        # Build coordinated schedule
        schedule = CoordinatedFertigationSchedule(
            target_coords=alert.coords,
            fertilizer_agent_id=fert_prop.agent_id,
            fertilizer_slot=fert_prop.time_slot,
            nitrogen_dose_g=fert_prop.nitrogen_dose_g,
            carrier_fluid_liters=carrier_water,
            carrier_moisture_gain_pct=fert_prop.carrier_moisture_gain_pct,
            irrigation_agent_id=self.agent_id,
            irrigation_slot=irr_slot,
            irrigation_volume_liters=final_water,
            irrigation_moisture_gain_pct=round(final_water * 2.0, 2),
            initial_moisture_pct=alert.current_moisture_pct,
            projected_final_moisture_pct=eval_res.projected_final_moisture_pct,
            saturation_threshold_pct=alert.field_capacity_pct,
            is_safe_non_saturated=eval_res.is_safe,
            is_collision_free=True,
            negotiation_notes=[f"Bilateral FIPA-ACL negotiation agreed for {alert.coords}"],
        )

        # Reply with ACCEPT_PROPOSAL
        self.send_message(
            receiver=msg.sender,
            performative=Performative.ACCEPT_PROPOSAL,
            content=schedule,
            current_tick=current_tick,
            conversation_id=msg.conversation_id,
            in_reply_to=msg.message_id,
        )

        # Adopt schedule for self
        self._handle_confirmed_schedule(schedule)

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
        """Executes navigation to target sector, controlled water discharge, and automatic vacating."""
        # Case A: Active schedule underway
        if self.active_schedule:
            slot = self.active_schedule.irrigation_slot

            dist = self.position.manhattan_distance(self.target_task_coords)
            # 1. Before scheduled slot: hold outside until exactly time to enter
            if current_tick < slot.start_tick:
                ticks_until_start = slot.start_tick - current_tick
                if ticks_until_start > dist and dist <= 1:
                    self.status = AgentStatus.IDLE
                    return
                self.navigate_towards(self.target_task_coords)
                return

            # 2. Inside scheduled slot: actuate water application
            if slot.start_tick <= current_tick <= slot.end_tick:
                if self.position == self.target_task_coords:
                    self.status = AgentStatus.ACTUATING
                    vol_per_tick = self.target_water_volume / max(1, slot.duration())
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
                    self.navigate_towards(self.target_task_coords)
                return

            # 3. Scheduled slot ended: task complete, immediately vacate sector
            if current_tick > slot.end_tick:
                self.log_action(
                    tick=current_tick,
                    action_name="IRRIGATION_TASK_COMPLETED",
                    details={"target": self.target_task_coords.to_tuple()},
                )
                self.active_schedule = None
                self.target_task_coords = None
                self.target_water_volume = 0.0
                # Begin vacating back towards home station
                self.navigate_towards(self.home_station)
                return

        # Case B: No active schedule - return to home station to refill water and recharge
        if self.position != self.home_station:
            self.navigate_towards(self.home_station)
        else:
            # At home station: refill water & recharge
            if self.water_tank_liters < self.max_tank_liters or self.battery_pct < 95.0:
                self.status = AgentStatus.CHARGING
                self.water_tank_liters = min(self.max_tank_liters, round(self.water_tank_liters + 20.0, 2))
            else:
                self.status = AgentStatus.IDLE
