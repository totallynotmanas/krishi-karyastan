"""Tests for physical farm grid, agronomic physics, and partial observability."""

import pytest
from krishi_karyastan.core.models import Coordinates, WeatherState
from krishi_karyastan.core.environment import FarmGrid


def test_farm_grid_initialization():
    grid = FarmGrid(width=6, height=6)
    assert grid.width == 6
    assert grid.height == 6
    assert len(grid.sectors) == 36

    sector = grid.get_sector(Coordinates(x=0, y=0))
    assert 20.0 <= sector.moisture_pct <= 65.0
    assert sector.nutrients.nitrogen_ppm > 50.0


def test_coordinate_distance_and_adjacency():
    c1 = Coordinates(x=1, y=1)
    c2 = Coordinates(x=4, y=5)
    assert c1.manhattan_distance(c2) == 7
    assert c1.euclidean_distance(c2) == 5.0

    adj = Coordinates(x=1, y=2)
    assert c1.is_adjacent(adj)
    assert not c1.is_adjacent(c2)


def test_partial_observability_sensor_radius():
    grid = FarmGrid(width=8, height=8)
    agent_pos = Coordinates(x=3, y=3)

    # With radius 1.5, only immediate Moore neighbors (distance <= 1.414) should be observed
    percepts = grid.observe(agent_pos=agent_pos, sensor_radius=1.5)
    assert len(percepts) == 9  # Center + 8 surrounding cells
    assert agent_pos in percepts

    # Distant sector (0, 0) should NOT be observable
    distant = Coordinates(x=0, y=0)
    assert distant not in percepts


def test_water_application_and_saturation():
    grid = FarmGrid(width=4, height=4)
    target = Coordinates(x=1, y=1)
    sector = grid.get_sector(target)
    sector.moisture_pct = 30.0

    new_m, is_oversat = grid.apply_water(target, volume_liters=5.0)
    assert new_m == 40.0
    assert not is_oversat

    # Apply extreme water to test saturation cap
    new_m, is_oversat = grid.apply_water(target, volume_liters=30.0)
    assert is_oversat
    assert new_m == sector.saturation_limit_pct


def test_nutrient_application_with_carrier():
    grid = FarmGrid(width=4, height=4)
    target = Coordinates(x=2, y=2)
    sector = grid.get_sector(target)
    init_n = sector.nutrients.nitrogen_ppm
    init_m = sector.moisture_pct

    nutrients, new_m, is_oversat = grid.apply_nutrients(
        target,
        nitrogen_g=20.0,
        phosphorus_g=6.0,
        potassium_g=8.0,
        carrier_water_liters=3.0,
    )
    assert nutrients.nitrogen_ppm == pytest.approx(init_n + (20.0 * 2.5), 0.1)
    assert new_m == pytest.approx(init_m + (3.0 * 2.0), 0.1)
    assert not is_oversat


def test_environment_step_evaporation():
    grid = FarmGrid(width=4, height=4)
    target = Coordinates(x=0, y=0)
    init_m = grid.get_sector(target).moisture_pct

    # Step under hot, sunny conditions
    hot_weather = WeatherState(temperature_c=36.0, solar_radiation_w_m2=900.0, rain_mm=0.0)
    grid.step(hot_weather)

    new_m = grid.get_sector(target).moisture_pct
    assert new_m < init_m
