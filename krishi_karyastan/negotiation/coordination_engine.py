"""Negotiation engine orchestrating bilateral fertigation coordination and conflict deconfliction."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from krishi_karyastan.core.models import Coordinates, TimeSlot
from krishi_karyastan.agents.irrigation import IrrigationAgent
from krishi_karyastan.agents.fertilizer import FertilizerAgent
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


class FertigationCoordinator:
    """Orchestrates multi-agent negotiation between Irrigation and Fertilizer agents.
    
    Resolves:
    1. Agronomic Over-Saturation: Compensates for carrier water fluid; caps joint volume below field capacity.
    2. Physical Hardware Collisions: Schedules non-overlapping sequential time slots in the 4D reservation grid.
    """

    def __init__(
        self,
        saturation_governor: Optional[SaturationGovernor] = None,
        collision_table: Optional[CollisionAvoidanceTable] = None,
        message_bus: Optional[MessageBus] = None,
    ):
        self.saturation_governor = saturation_governor or SaturationGovernor()
        self.collision_table = collision_table or CollisionAvoidanceTable()
        self.message_bus = message_bus
        self.negotiation_history: List[CoordinatedFertigationSchedule] = []

    def negotiate_response(
        self,
        alert: SoilDeficiencyAlert,
        fertilizer_agent: FertilizerAgent,
        irrigation_agent: IrrigationAgent,
        current_tick: int,
    ) -> CoordinatedFertigationSchedule:
        """Executes full bilateral negotiation cycle between Fertilizer and Irrigation agents.
        
        Negotiation Protocol:
        1. Fertilizer Agent submits proposal (nutrient dose + required carrier liquid).
        2. Saturation Governor adjusts irrigation gross volume down to account for carrier water.
        3. Irrigation Agent submits adjusted proposal.
        4. Collision Table assigns sequential collision-free time windows [Fertilizer -> Irrigation].
        5. Both agents commit reservations and receive CONFIRM performatives.
        """
        conversation_id = f"fertigation_neg_{alert.coords.x}_{alert.coords.y}_{current_tick}"
        notes: List[str] = []

        # Step 1: Fertilizer Agent formulates proposal
        fert_proposal: FertilizerProposal = fertilizer_agent.formulate_proposal(
            alert=alert,
            current_tick=current_tick,
        )
        notes.append(
            f"Fertilizer Proposal: {fert_proposal.nitrogen_dose_g:.1f}g N with "
            f"{fert_proposal.carrier_fluid_liters:.1f}L carrier water"
        )

        # Step 2: Irrigation Agent formulates proposal with carrier offset
        irr_proposal: IrrigationProposal = irrigation_agent.formulate_proposal(
            alert=alert,
            current_tick=current_tick,
            carrier_water_offset_liters=fert_proposal.carrier_fluid_liters,
        )
        notes.append(
            f"Irrigation Proposal: {irr_proposal.water_volume_liters:.1f}L net water "
            f"(deducted {fert_proposal.carrier_fluid_liters:.1f}L carrier water)"
        )

        # Step 3: Saturation Governor evaluates joint contribution
        eval_result = self.saturation_governor.evaluate_fertigation_plan(
            current_moisture_pct=alert.current_moisture_pct,
            carrier_water_liters=fert_proposal.carrier_fluid_liters,
            proposed_irrigation_liters=irr_proposal.water_volume_liters,
            field_capacity_pct=alert.field_capacity_pct,
            saturation_limit_pct=alert.saturation_limit_pct,
        )

        # If governor adjusted irrigation water downwards to prevent leaching/saturation
        if eval_result.adjusted_irrigation_liters < irr_proposal.water_volume_liters:
            irr_proposal.water_volume_liters = eval_result.adjusted_irrigation_liters
            notes.extend(eval_result.warnings)

        # Step 4: Deconflict Spatio-Temporal Hardware Collisions
        # Agronomic best practice: Fertilizer application first, followed immediately by irrigation
        fert_duration = fert_proposal.time_slot.duration()
        irr_duration = max(2, int(irr_proposal.water_volume_liters / 4.0))

        # 4a. Find collision-free slot for Fertilizer Agent
        earliest_fert_start = max(
            current_tick + 1,
            fertilizer_agent.position.manhattan_distance(alert.coords) + current_tick + 1,
        )
        fert_slot = self.collision_table.find_first_available_slot(
            coords=alert.coords,
            duration=fert_duration,
            earliest_start=earliest_fert_start,
            agent_id=fertilizer_agent.agent_id,
        )
        self.collision_table.reserve(
            coords=alert.coords,
            slot=fert_slot,
            agent_id=fertilizer_agent.agent_id,
            reason="Fertilizer Application",
        )
        notes.append(f"Reserved {fertilizer_agent.agent_id} for slot [{fert_slot.start_tick}, {fert_slot.end_tick}]")

        # 4b. Find collision-free slot for Irrigation Agent (strictly after fertilizer finishes)
        earliest_irr_start = max(
            fert_slot.end_tick + 1,
            irrigation_agent.position.manhattan_distance(alert.coords) + current_tick + 1,
        )
        irr_slot = self.collision_table.find_first_available_slot(
            coords=alert.coords,
            duration=irr_duration,
            earliest_start=earliest_irr_start,
            agent_id=irrigation_agent.agent_id,
        )
        self.collision_table.reserve(
            coords=alert.coords,
            slot=irr_slot,
            agent_id=irrigation_agent.agent_id,
            reason="Complementary Irrigation",
        )
        notes.append(f"Reserved {irrigation_agent.agent_id} for slot [{irr_slot.start_tick}, {irr_slot.end_tick}]")

        # Step 5: Synthesize Final Coordinated Schedule
        schedule = CoordinatedFertigationSchedule(
            target_coords=alert.coords,
            fertilizer_agent_id=fertilizer_agent.agent_id,
            fertilizer_slot=fert_slot,
            nitrogen_dose_g=fert_proposal.nitrogen_dose_g,
            carrier_fluid_liters=fert_proposal.carrier_fluid_liters,
            carrier_moisture_gain_pct=fert_proposal.carrier_moisture_gain_pct,
            irrigation_agent_id=irrigation_agent.agent_id,
            irrigation_slot=irr_slot,
            irrigation_volume_liters=irr_proposal.water_volume_liters,
            irrigation_moisture_gain_pct=round(irr_proposal.water_volume_liters * 2.0, 2),
            initial_moisture_pct=alert.current_moisture_pct,
            projected_final_moisture_pct=eval_result.projected_final_moisture_pct,
            saturation_threshold_pct=alert.field_capacity_pct,
            is_safe_non_saturated=eval_result.is_safe,
            is_collision_free=True,
            negotiation_notes=notes,
        )
        self.negotiation_history.append(schedule)

        # Step 6: Transmit FIPA-ACL CONFIRM performatives to both agents
        if self.message_bus:
            # Confirm to Fertilizer Agent
            confirm_fa = ACLMessage(
                sender="FertigationCoordinator",
                receiver=fertilizer_agent.agent_id,
                performative=Performative.CONFIRM,
                protocol="fipa-contract-net",
                conversation_id=conversation_id,
                content=schedule,
                timestamp=current_tick,
            )
            self.message_bus.publish(confirm_fa)

            # Confirm to Irrigation Agent
            confirm_ia = ACLMessage(
                sender="FertigationCoordinator",
                receiver=irrigation_agent.agent_id,
                performative=Performative.CONFIRM,
                protocol="fipa-contract-net",
                conversation_id=conversation_id,
                content=schedule,
                timestamp=current_tick,
            )
            self.message_bus.publish(confirm_ia)

        # Notify agents directly of agreed schedule
        fertilizer_agent._handle_confirmed_schedule(schedule)
        irrigation_agent._handle_confirmed_schedule(schedule)

        return schedule
