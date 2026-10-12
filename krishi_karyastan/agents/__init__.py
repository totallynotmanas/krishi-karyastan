"""Specialized autonomous agents for cooperative precision agriculture."""

from krishi_karyastan.agents.base import BaseAgent
from krishi_karyastan.agents.soil_monitoring import SoilMonitoringAgent
from krishi_karyastan.agents.irrigation import IrrigationAgent
from krishi_karyastan.agents.fertilizer import FertilizerAgent
from krishi_karyastan.agents.pest_detection import PestDetectionAgent
from krishi_karyastan.agents.harvesting import HarvestingAgent

__all__ = [
    "BaseAgent",
    "SoilMonitoringAgent",
    "IrrigationAgent",
    "FertilizerAgent",
    "PestDetectionAgent",
    "HarvestingAgent",
]
