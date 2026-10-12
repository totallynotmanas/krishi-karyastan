"""Discrete-tick simulation engine orchestrating agents, physics, and multi-agent coordination."""

from __future__ import annotations
from typing import Dict, List, Optional
from krishi_karyastan.core.models import Coordinates, WeatherState
from krishi_karyastan.core.environment import FarmGrid
from krishi_karyastan.core.knowledge_base import SharedKnowledgeBase
from krishi_karyastan.protocols.messages import ACLMessage, Performative
from krishi_karyastan.protocols.message_bus import MessageBus
from krishi_karyastan.protocols.schemas import SoilDeficiencyAlert, CoordinatedFertigationSchedule
from krishi_karyastan.agents.base import BaseAgent
from krishi_karyastan.agents.irrigation import IrrigationAgent
from krishi_karyastan.agents.fertilizer import FertilizerAgent
from krishi_karyastan.negotiation.coordination_engine import FertigationCoordinator


class SimulationEngine:
    """Manages the lifecycle loop of the multi-agent precision farming ecosystem."""

    def __init__(
        self,
        env: FarmGrid,
        knowledge_base: SharedKnowledgeBase,
        message_bus: MessageBus,
        coordinator: FertigationCoordinator,
    ):
        self.env = env
        self.knowledge_base = knowledge_base
        self.message_bus = message_bus
        self.coordinator = coordinator
        self.agents: Dict[str, BaseAgent] = {}
        self.current_tick: int = 0
        self.event_log: List[dict] = []
        self.negotiated_schedules: List[CoordinatedFertigationSchedule] = []
        self._handled_alerts: set = set()

    def add_agent(self, agent: BaseAgent) -> None:
        """Registers an agent into the simulation."""
        self.agents[agent.agent_id] = agent
        agent._engine_ref = self

    def step(self, weather: Optional[WeatherState] = None) -> dict:
        """Executes a single discrete simulation tick across the entire farm."""
        self.current_tick += 1

        # 1. Physical environment updates (evaporation, plant uptake)
        self.env.step(weather)

        # 2. Knowledge base temporal staleness decay
        self.knowledge_base.decay_all(self.current_tick)

        # 3. Agent execution cycles
        for agent in self.agents.values():
            agent.step(self.current_tick)

        # 4. Record any schedules agreed during decentralized agent negotiation
        for agent in self.agents.values():
            if hasattr(agent, "active_schedule") and agent.active_schedule:
                if agent.active_schedule not in self.negotiated_schedules:
                    self.negotiated_schedules.append(agent.active_schedule)

        # 5. Capture tick telemetry
        telemetry = self.get_telemetry()
        return telemetry

    def run(self, ticks: int) -> List[dict]:
        """Runs the simulation for a predetermined number of ticks."""
        snapshots = []
        for _ in range(ticks):
            telemetry = self.step()
            snapshots.append(telemetry)
        return snapshots

    def get_telemetry(self) -> dict:
        """Packages real-time state for CLI and Web dashboards."""
        agent_positions = {
            a.agent_id: {
                "type": a.agent_type.value,
                "position": a.position.to_tuple(),
                "status": a.status.value,
                "battery": a.battery_pct,
            }
            for a in self.agents.values()
        }

        # Check for any physical hardware collisions (two agents sharing coordinates)
        positions_seen = {}
        collision_events = []
        for a_id, a in self.agents.items():
            pos = a.position.to_tuple()
            if pos in positions_seen:
                collision_events.append({
                    "agent1": a_id,
                    "agent2": positions_seen[pos],
                    "coords": pos,
                })
            else:
                positions_seen[pos] = a_id

        sector_heatmaps = []
        for y in range(self.env.height):
            row = []
            for x in range(self.env.width):
                s = self.env.get_sector(Coordinates(x=x, y=y))
                row.append({
                    "coords": (x, y),
                    "moisture": s.moisture_pct,
                    "nitrogen": s.nutrients.nitrogen_ppm,
                    "crop_stage": s.crop_stage.value,
                    "is_dry": s.is_dry,
                    "is_nutrient_poor": s.is_nutrient_poor,
                })
            sector_heatmaps.append(row)

        return {
            "tick": self.current_tick,
            "agents": agent_positions,
            "sectors": sector_heatmaps,
            "collision_count": len(collision_events),
            "collision_events": collision_events,
            "kb_stats": self.knowledge_base.get_summary_statistics(),
            "recent_messages": [
                {
                    "id": m.message_id,
                    "sender": m.sender,
                    "receiver": m.receiver,
                    "performative": m.performative.value,
                    "conversation_id": m.conversation_id,
                    "tick": m.timestamp,
                }
                for m in self.message_bus.get_history(limit=15)
            ],
            "negotiated_schedules_count": len(self.negotiated_schedules),
        }
