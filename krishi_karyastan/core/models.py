"""Data models for spatial farm coordinates, soil chemistry, and agent states."""

from __future__ import annotations
from enum import Enum
from typing import Optional, List, Tuple
from pydantic import BaseModel, Field, field_validator


class Coordinates(BaseModel):
    """Discrete 2D coordinates on the farm grid."""
    x: int = Field(..., ge=0, description="X coordinate (horizontal column index)")
    y: int = Field(..., ge=0, description="Y coordinate (vertical row index)")

    def manhattan_distance(self, other: Coordinates) -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def euclidean_distance(self, other: Coordinates) -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5

    def is_adjacent(self, other: Coordinates, include_diagonals: bool = False) -> bool:
        dx = abs(self.x - other.x)
        dy = abs(self.y - other.y)
        if include_diagonals:
            return (dx <= 1 and dy <= 1) and not (dx == 0 and dy == 0)
        return (dx + dy) == 1

    def to_tuple(self) -> Tuple[int, int]:
        return (self.x, self.y)

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Coordinates):
            return False
        return self.x == other.x and self.y == other.y

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"


class CropStage(str, Enum):
    """Phenological stage of the planted crop."""
    FALLOW = "FALLOW"
    VEGETATIVE = "VEGETATIVE"
    FLOWERING = "FLOWERING"
    RIPENING = "RIPENING"
    MATURE = "MATURE"
    HARVESTED = "HARVESTED"


class AgentType(str, Enum):
    """Specialized autonomous agent roles in the cooperative."""
    SOIL_MONITOR = "SOIL_MONITOR"
    IRRIGATION = "IRRIGATION"
    FERTILIZER = "FERTILIZER"
    PEST_DETECTOR = "PEST_DETECTOR"
    HARVESTER = "HARVESTER"


class AgentStatus(str, Enum):
    """Operational status of an autonomous node."""
    IDLE = "IDLE"
    NAVIGATING = "NAVIGATING"
    SENSING = "SENSING"
    ACTUATING = "ACTUATING"
    NEGOTIATING = "NEGOTIATING"
    BLOCKED = "BLOCKED"
    CHARGING = "CHARGING"
    MAINTENANCE = "MAINTENANCE"


class ActionType(str, Enum):
    """Actuation categories."""
    SAMPLE_SOIL = "SAMPLE_SOIL"
    IRRIGATE = "IRRIGATE"
    FERTILIZE = "FERTILIZE"
    PEST_TREATMENT = "PEST_TREATMENT"
    HARVEST = "HARVEST"
    RECHARGE = "RECHARGE"


class SoilNutrientProfile(BaseModel):
    """Soil chemical composition representing primary macronutrients."""
    nitrogen_ppm: float = Field(..., ge=0.0, description="Available Nitrogen in ppm/mg-kg-1")
    phosphorus_ppm: float = Field(..., ge=0.0, description="Available Phosphorus in ppm")
    potassium_ppm: float = Field(..., ge=0.0, description="Available Potassium in ppm")
    organic_matter_pct: float = Field(default=3.5, ge=0.0, le=20.0, description="Soil organic matter %")
    ph: float = Field(default=6.8, ge=3.5, le=10.0, description="Soil pH level")


class SectorState(BaseModel):
    """Full ground-truth physical state of an individual farm sector."""
    coords: Coordinates
    moisture_pct: float = Field(..., ge=0.0, le=100.0, description="Volumetric moisture content (%)")
    field_capacity_pct: float = Field(default=65.0, description="Field capacity limit (%) before runoff/percolation")
    saturation_limit_pct: float = Field(default=75.0, description="Absolute saturation limit (%) risking anaerobic suffocation")
    wilting_point_pct: float = Field(default=20.0, description="Permanent wilting point (%)")
    nutrients: SoilNutrientProfile
    crop_type: str = Field(default="Wheat")
    crop_stage: CropStage = Field(default=CropStage.VEGETATIVE)
    pest_index: float = Field(default=0.0, ge=0.0, le=1.0, description="0.0 healthy, 1.0 severe pest infestation")
    last_updated_tick: int = Field(default=0)
    last_serviced_by: Optional[str] = Field(default=None)

    @property
    def is_dry(self) -> bool:
        """Returns True if moisture is below safe vegetative buffer."""
        return self.moisture_pct < (self.wilting_point_pct + 12.0)

    @property
    def is_nutrient_poor(self) -> bool:
        """Returns True if any primary macronutrient (especially N) is below baseline."""
        return self.nutrients.nitrogen_ppm < 70.0 or self.nutrients.phosphorus_ppm < 20.0


class WeatherState(BaseModel):
    """Ambient environmental variables driving dynamic evaporation & crop uptake."""
    temperature_c: float = Field(default=28.0, description="Air temperature in Celsius")
    solar_radiation_w_m2: float = Field(default=600.0, description="Solar irradiance W/m^2")
    rain_mm: float = Field(default=0.0, description="Rainfall precipitation in mm/tick")
    humidity_pct: float = Field(default=55.0, description="Relative ambient humidity %")


class TimeSlot(BaseModel):
    """Temporal reservation window for 4D collision-free path/task scheduling."""
    start_tick: int = Field(..., ge=0)
    end_tick: int = Field(..., ge=0)

    @field_validator("end_tick")
    @classmethod
    def validate_order(cls, v: int, info) -> int:
        start = info.data.get("start_tick")
        if start is not None and v < start:
            raise ValueError(f"end_tick ({v}) cannot precede start_tick ({start})")
        return v

    def overlaps_with(self, other: TimeSlot) -> bool:
        """Returns True if two time intervals intersect."""
        return max(self.start_tick, other.start_tick) <= min(self.end_tick, other.end_tick)

    def duration(self) -> int:
        return self.end_tick - self.start_tick + 1
