"""Pre-configured benchmark scenarios highlighting the multi-agent problem statement."""

from __future__ import annotations
from krishi_karyastan.core.models import Coordinates
from krishi_karyastan.core.environment import FarmGrid
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase
from krishi_karyastan.protocols.message_bus import MessageBus
from krishi_karyastan.agents.soil_monitoring import SoilMonitoringAgent
from krishi_karyastan.agents.irrigation import IrrigationAgent
from krishi_karyastan.agents.fertilizer import FertilizerAgent
from krishi_karyastan.agents.pest_detection import PestDetectionAgent
from krishi_karyastan.agents.harvesting import HarvestingAgent
from krishi_karyastan.negotiation.saturation_governor import SaturationGovernor
from krishi_karyastan.negotiation.collision_avoidance import CollisionAvoidanceTable
from krishi_karyastan.negotiation.coordination_engine import FertigationCoordinator
from krishi_karyastan.simulation.engine import SimulationEngine


def build_case_study_scenario(
    target_patch: Coordinates = Coordinates(x=3, y=4),
    initial_moisture: float = 18.0,
    initial_nitrogen: float = 38.0,
) -> SimulationEngine:
    """Builds canonical benchmark scenario matching the course case study.
    
    Setup:
    - 8x8 Farm Grid.
    - Sector (3, 4) starts severely dry (18%) and nitrogen-deficient (38 ppm).
    - Soil Monitoring Agent patrols a designated zone that covers (3, 4).
    - Irrigation Agent begins at station (0, 0).
    - Fertilizer Agent begins at station (7, 7).
    - Pest Detection & Harvesting agents operate in their assigned sectors.
    """
    grid = FarmGrid(width=8, height=8, seed=42)
    grid.set_anomalous_patch(
        coords=target_patch,
        moisture_pct=initial_moisture,
        nitrogen_ppm=initial_nitrogen,
    )

    kb = SharedKnowledgeBase(decay_constant=0.03)
    bus = MessageBus()

    collision_table = CollisionAvoidanceTable()
    saturation_gov = SaturationGovernor(safety_buffer_pct=5.0)
    coordinator = FertigationCoordinator(
        saturation_governor=saturation_gov,
        collision_table=collision_table,
        message_bus=bus,
    )

    engine = SimulationEngine(
        env=grid,
        knowledge_base=kb,
        message_bus=bus,
        coordinator=coordinator,
    )

    # 1. Soil Monitoring Agent (Patrol path directly passing through target patch)
    sma = SoilMonitoringAgent(
        agent_id="SoilMonitor_Alpha",
        initial_position=Coordinates(x=1, y=2),
        env=grid,
        knowledge_base=kb,
        message_bus=bus,
        sensor_radius=1.8,
    )
    sma.patrol_route = [
        Coordinates(x=1, y=2),
        Coordinates(x=2, y=3),
        Coordinates(x=3, y=4),
        Coordinates(x=4, y=5),
        Coordinates(x=1, y=2),
    ]

    # 2. Irrigation Agent
    ia = IrrigationAgent(
        agent_id="Irrigator_Unit_1",
        initial_position=Coordinates(x=0, y=0),
        env=grid,
        knowledge_base=kb,
        message_bus=bus,
        water_tank_liters=150.0,
        saturation_governor=saturation_gov,
        collision_table=collision_table,
    )

    # 3. Fertilizer Agent
    fa = FertilizerAgent(
        agent_id="Fertilizer_Unit_1",
        initial_position=Coordinates(x=7, y=7),
        env=grid,
        knowledge_base=kb,
        message_bus=bus,
        nitrogen_stock_g=800.0,
        carrier_water_liters=80.0,
    )

    # 4. Pest Detection Agent
    pa = PestDetectionAgent(
        agent_id="PestScout_Beta",
        initial_position=Coordinates(x=0, y=7),
        env=grid,
        knowledge_base=kb,
        message_bus=bus,
        sensor_radius=2.0,
    )
    pa.patrol_route = [
        Coordinates(x=0, y=7),
        Coordinates(x=2, y=7),
        Coordinates(x=2, y=5),
        Coordinates(x=0, y=7),
    ]

    # 5. Harvesting Agent
    ha = HarvestingAgent(
        agent_id="Harvester_Gamma",
        initial_position=Coordinates(x=7, y=0),
        env=grid,
        knowledge_base=kb,
        message_bus=bus,
    )
    ha.patrol_route = [
        Coordinates(x=7, y=0),
        Coordinates(x=5, y=0),
        Coordinates(x=5, y=2),
        Coordinates(x=7, y=0),
    ]

    engine.add_agent(sma)
    engine.add_agent(ia)
    engine.add_agent(fa)
    engine.add_agent(pa)
    engine.add_agent(ha)

    return engine


def build_multi_sector_contention_scenario() -> SimulationEngine:
    """Builds multi-patch scenario testing contention resolution and scheduling queues."""
    engine = build_case_study_scenario(
        target_patch=Coordinates(x=2, y=2),
        initial_moisture=15.0,
        initial_nitrogen=30.0,
    )
    # Add second deficiency
    engine.env.set_anomalous_patch(
        coords=Coordinates(x=5, y=5),
        moisture_pct=20.0,
        nitrogen_ppm=45.0,
    )
    return engine
