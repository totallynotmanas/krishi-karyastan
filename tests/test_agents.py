"""Tests for specialized autonomous agents and BDI operational cycles."""

import pytest
from krishi_karyastan.core.models import Coordinates, AgentStatus
from krishi_karyastan.core.environment import FarmGrid
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase
from krishi_karyastan.protocols.message_bus import MessageBus
from krishi_karyastan.agents.soil_monitoring import SoilMonitoringAgent
from krishi_karyastan.agents.irrigation import IrrigationAgent
from krishi_karyastan.agents.fertilizer import FertilizerAgent
from krishi_karyastan.protocols.schemas import SoilDeficiencyAlert


def test_soil_monitoring_agent_alert_generation():
    grid = FarmGrid(width=6, height=6)
    kb = SharedKnowledgeBase()
    bus = MessageBus()

    # Induce dry patch at (2, 2)
    grid.set_anomalous_patch(Coordinates(x=2, y=2), moisture_pct=17.0, nitrogen_ppm=35.0)

    sma = SoilMonitoringAgent(
        agent_id="sma_test",
        initial_position=Coordinates(x=2, y=2),
        env=grid,
        knowledge_base=kb,
        message_bus=bus,
    )
    bus.subscribe("test_listener", "alerts")

    # Step agent
    sma.step(current_tick=1)

    # Check alert was published to bus
    inbox = bus.receive("test_listener")
    assert len(inbox) == 1
    alert_content = inbox[0].content
    assert alert_content.coords == Coordinates(x=2, y=2)
    assert alert_content.current_moisture_pct == pytest.approx(17.0, abs=1.0)

    # Knowledge base should also have the sector updated
    b = kb.get_belief(Coordinates(x=2, y=2))
    assert b is not None
    assert b.estimated_state.moisture_pct == pytest.approx(17.0, abs=1.0)


def test_irrigation_agent_proposal_formulation():
    grid = FarmGrid(width=6, height=6)
    kb = SharedKnowledgeBase()
    bus = MessageBus()

    ia = IrrigationAgent("irr_test", Coordinates(x=0, y=0), grid, kb, bus)
    alert = SoilDeficiencyAlert.create_from_reading(
        coords=Coordinates(x=4, y=4),
        moisture=20.0,
        nitrogen=110.0,
        phosphorus=30.0,
        potassium=150.0,
        flagged_by="sma",
        tick=1,
    )

    prop = ia.formulate_proposal(alert, current_tick=1, carrier_water_offset_liters=2.0)
    assert prop.target_coords == Coordinates(x=4, y=4)
    # Net water calculation: Gross = (50 - 20)/2 = 15L. Net = 15 - 2 = 13L.
    assert prop.water_volume_liters == 13.0
    assert prop.time_slot.start_tick > 1  # Transit time included


def test_fertilizer_agent_proposal_formulation():
    grid = FarmGrid(width=6, height=6)
    kb = SharedKnowledgeBase()
    bus = MessageBus()

    fa = FertilizerAgent("fert_test", Coordinates(x=5, y=5), grid, kb, bus)
    alert = SoilDeficiencyAlert.create_from_reading(
        coords=Coordinates(x=2, y=2),
        moisture=35.0,
        nitrogen=40.0,
        phosphorus=20.0,
        potassium=120.0,
        flagged_by="sma",
        tick=1,
    )

    prop = fa.formulate_proposal(alert, current_tick=1)
    # Nitrogen deficit = 120 - 40 = 80 ppm. Dose = 80 / 2.5 = 32g.
    assert prop.nitrogen_dose_g == 32.0
    assert prop.carrier_fluid_liters >= 2.0
    assert prop.target_coords == Coordinates(x=2, y=2)
