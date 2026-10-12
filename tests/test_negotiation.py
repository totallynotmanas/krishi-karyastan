"""Tests for negotiation logic, agronomic saturation governor, and collision avoidance."""

import pytest
from krishi_karyastan.core.models import Coordinates, TimeSlot
from krishi_karyastan.core.environment import FarmGrid
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase
from krishi_karyastan.protocols.message_bus import MessageBus
from krishi_karyastan.protocols.schemas import SoilDeficiencyAlert
from krishi_karyastan.agents.irrigation import IrrigationAgent
from krishi_karyastan.agents.fertilizer import FertilizerAgent
from krishi_karyastan.negotiation.saturation_governor import SaturationGovernor
from krishi_karyastan.negotiation.collision_avoidance import CollisionAvoidanceTable
from krishi_karyastan.negotiation.coordination_engine import FertigationCoordinator


def test_saturation_governor_safe_case():
    gov = SaturationGovernor(safety_buffer_pct=5.0)
    # 25% moisture + 2L carrier (+4%) + 10L irrigation (+20%) = 49% (Safe below 60% safe field capacity)
    res = gov.evaluate_fertigation_plan(
        current_moisture_pct=25.0,
        carrier_water_liters=2.0,
        proposed_irrigation_liters=10.0,
        field_capacity_pct=65.0,
        saturation_limit_pct=75.0,
    )
    assert res.is_safe
    assert res.adjusted_irrigation_liters == 10.0
    assert res.projected_final_moisture_pct == 49.0
    assert len(res.warnings) == 0


def test_saturation_governor_prevents_oversaturation():
    gov = SaturationGovernor(safety_buffer_pct=5.0)
    # High initial moisture (55%) + 3L carrier (+6%) + 15L irrigation (+30%) = 91% (Exceeds 75% saturation limit)
    res = gov.evaluate_fertigation_plan(
        current_moisture_pct=55.0,
        carrier_water_liters=3.0,
        proposed_irrigation_liters=15.0,
        field_capacity_pct=65.0,
        saturation_limit_pct=75.0,
    )
    # Governor must detect danger and trim irrigation down to 0 or safe headroom
    assert not res.is_safe or res.adjusted_irrigation_liters < 15.0
    assert len(res.warnings) > 0


def test_collision_avoidance_table_conflicts():
    table = CollisionAvoidanceTable()
    coords = Coordinates(x=3, y=3)
    slot1 = TimeSlot(start_tick=5, end_tick=10)
    slot2_conflicting = TimeSlot(start_tick=8, end_tick=12)
    slot3_disjoint = TimeSlot(start_tick=11, end_tick=15)

    # Reserve for Agent A
    assert table.reserve(coords, slot1, "AgentA")

    # Conflict check
    avail, conflicting_agent = table.is_slot_available(coords, slot2_conflicting, "AgentB")
    assert not avail
    assert conflicting_agent == "AgentA"

    # Reservation for conflicting agent should fail
    assert not table.reserve(coords, slot2_conflicting, "AgentB")

    # Disjoint slot should succeed
    avail3, _ = table.is_slot_available(coords, slot3_disjoint, "AgentB")
    assert avail3
    assert table.reserve(coords, slot3_disjoint, "AgentB")


def test_full_bilateral_negotiation():
    grid = FarmGrid(width=8, height=8)
    kb = SharedKnowledgeBase()
    bus = MessageBus()

    ia = IrrigationAgent("irr_node", Coordinates(x=0, y=0), grid, kb, bus)
    fa = FertilizerAgent("fert_node", Coordinates(x=7, y=7), grid, kb, bus)

    coordinator = FertigationCoordinator(
        saturation_governor=SaturationGovernor(),
        collision_table=CollisionAvoidanceTable(),
        message_bus=bus,
    )

    alert = SoilDeficiencyAlert.create_from_reading(
        coords=Coordinates(x=3, y=4),
        moisture=18.0,
        nitrogen=35.0,
        phosphorus=20.0,
        potassium=110.0,
        flagged_by="sma_node",
        tick=1,
    )

    sched = coordinator.negotiate_response(alert, fa, ia, current_tick=1)

    # 1. Non-saturation guaranteed
    assert sched.is_safe_non_saturated
    assert sched.projected_final_moisture_pct <= sched.saturation_threshold_pct

    # 2. Collision avoidance guaranteed (No overlapping time slots)
    assert sched.is_collision_free
    assert not sched.fertilizer_slot.overlaps_with(sched.irrigation_slot)

    # 3. Sequencing: Fertilizer scheduled before Irrigation
    assert sched.fertilizer_slot.end_tick < sched.irrigation_slot.start_tick
