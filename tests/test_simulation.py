"""Tests for end-to-end simulation engine and benchmark scenarios."""

import pytest
from krishi_karyastan.core.models import Coordinates
from krishi_karyastan.simulation.scenarios import build_case_study_scenario


def test_case_study_end_to_end_remediation():
    engine = build_case_study_scenario(
        target_patch=Coordinates(x=3, y=4),
        initial_moisture=18.0,
        initial_nitrogen=38.0,
    )

    target_c = Coordinates(x=3, y=4)
    init_state = engine.env.get_sector(target_c)
    assert init_state.moisture_pct == 18.0
    assert init_state.nutrients.nitrogen_ppm == 38.0

    # Run for 22 ticks
    engine.run(ticks=22)

    final_state = engine.env.get_sector(target_c)

    # 1. Verification of alert trigger & negotiation
    assert len(engine.negotiated_schedules) >= 1
    sched = engine.negotiated_schedules[0]
    assert sched.target_coords == target_c
    assert sched.is_safe_non_saturated
    assert sched.is_collision_free

    # 2. Verification of physical remediation in the field
    assert final_state.moisture_pct > 35.0  # Successfully rehydrated
    assert final_state.nutrients.nitrogen_ppm > 80.0  # Successfully fertilized

    # 3. Verification of knowledge base coverage
    assert len(engine.knowledge_base.beliefs) > 20
