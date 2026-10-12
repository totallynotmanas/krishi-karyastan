"""Tests for dynamic spatial knowledge base, belief fusion, and staleness decay."""

import pytest
from krishi_karyastan.core.models import Coordinates, SectorState, SoilNutrientProfile
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase, Belief


def test_initial_belief_creation():
    kb = SharedKnowledgeBase()
    c = Coordinates(x=2, y=3)
    dummy_state = SectorState(
        coords=c,
        moisture_pct=42.0,
        nutrients=SoilNutrientProfile(nitrogen_ppm=110.0, phosphorus_ppm=40.0, potassium_ppm=160.0),
    )

    belief = kb.update_belief(c, dummy_state, confidence=0.85, current_tick=1, agent_id="sma_1")
    assert belief.confidence == 0.85
    assert belief.estimated_state.moisture_pct == 42.0
    assert "sma_1" in belief.contributing_agents


def test_belief_fusion_multiple_agents():
    kb = SharedKnowledgeBase()
    c = Coordinates(x=1, y=1)

    state1 = SectorState(
        coords=c,
        moisture_pct=40.0,
        nutrients=SoilNutrientProfile(nitrogen_ppm=100.0, phosphorus_ppm=40.0, potassium_ppm=150.0),
    )
    kb.update_belief(c, state1, confidence=0.6, current_tick=1, agent_id="agent_1")

    # Second agent observes slightly different value with high confidence
    state2 = SectorState(
        coords=c,
        moisture_pct=50.0,
        nutrients=SoilNutrientProfile(nitrogen_ppm=120.0, phosphorus_ppm=40.0, potassium_ppm=150.0),
    )
    b2 = kb.update_belief(c, state2, confidence=0.8, current_tick=2, agent_id="agent_2")

    # Fused moisture should lie between 40 and 50, weighted towards 50
    assert 44.0 <= b2.estimated_state.moisture_pct <= 48.0
    assert b2.confidence > 0.8
    assert "agent_1" in b2.contributing_agents
    assert "agent_2" in b2.contributing_agents


def test_staleness_uncertainty_decay():
    kb = SharedKnowledgeBase(decay_constant=0.05)
    c = Coordinates(x=0, y=0)
    state = SectorState(
        coords=c,
        moisture_pct=45.0,
        nutrients=SoilNutrientProfile(nitrogen_ppm=100.0, phosphorus_ppm=40.0, potassium_ppm=150.0),
    )
    kb.update_belief(c, state, confidence=0.9, current_tick=0, agent_id="sma_1")

    # Decay after 20 ticks
    kb.decay_all(current_tick=20)
    b = kb.get_belief(c)
    assert b.confidence < 0.5
    assert b.is_stale(current_tick=20, threshold_ticks=15)


def test_find_deficient_patches():
    kb = SharedKnowledgeBase()
    c_healthy = Coordinates(x=0, y=0)
    c_dry = Coordinates(x=3, y=3)

    state_healthy = SectorState(
        coords=c_healthy,
        moisture_pct=50.0,
        nutrients=SoilNutrientProfile(nitrogen_ppm=120.0, phosphorus_ppm=40.0, potassium_ppm=150.0),
    )
    state_dry = SectorState(
        coords=c_dry,
        moisture_pct=19.0,
        nutrients=SoilNutrientProfile(nitrogen_ppm=40.0, phosphorus_ppm=15.0, potassium_ppm=90.0),
    )

    kb.update_belief(c_healthy, state_healthy, 0.9, 1, "sma_1")
    kb.update_belief(c_dry, state_dry, 0.95, 1, "sma_1")

    flagged = kb.find_deficient_patches(moisture_threshold=30.0, nitrogen_threshold=70.0)
    assert len(flagged) == 1
    assert flagged[0][0] == c_dry
