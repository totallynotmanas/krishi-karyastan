"""Physical 2D Farm Grid Environment simulating soil dynamics, weather, and partial observability."""

from __future__ import annotations
import math
import random
from typing import Dict, List, Optional, Tuple
from krishi_karyastan.core.models import (
    Coordinates,
    SectorState,
    SoilNutrientProfile,
    WeatherState,
    CropStage,
)


class FarmGrid:
    """Simulates physical farm sectors, agronomic soil physics, and localized sensing."""

    def __init__(
        self,
        width: int = 8,
        height: int = 8,
        default_moisture: float = 48.0,
        default_nitrogen: float = 120.0,
        default_phosphorus: float = 45.0,
        default_potassium: float = 180.0,
        crop_type: str = "Wheat",
        seed: Optional[int] = 42,
    ):
        self.width = width
        self.height = height
        self.crop_type = crop_type
        if seed is not None:
            random.seed(seed)

        self.sectors: Dict[Coordinates, SectorState] = {}
        self.current_tick: int = 0
        self.weather: WeatherState = WeatherState()

        # Initialize uniform healthy sectors with slight natural variance
        for x in range(width):
            for y in range(height):
                coords = Coordinates(x=x, y=y)
                moisture = max(25.0, min(60.0, default_moisture + random.uniform(-3.0, 3.0)))
                nitrogen = max(60.0, default_nitrogen + random.uniform(-8.0, 8.0))
                phosphorus = max(25.0, default_phosphorus + random.uniform(-4.0, 4.0))
                potassium = max(100.0, default_potassium + random.uniform(-10.0, 10.0))

                nutrients = SoilNutrientProfile(
                    nitrogen_ppm=round(nitrogen, 2),
                    phosphorus_ppm=round(phosphorus, 2),
                    potassium_ppm=round(potassium, 2),
                    organic_matter_pct=3.8,
                    ph=6.8,
                )
                self.sectors[coords] = SectorState(
                    coords=coords,
                    moisture_pct=round(moisture, 2),
                    field_capacity_pct=65.0,
                    saturation_limit_pct=75.0,
                    wilting_point_pct=22.0,
                    nutrients=nutrients,
                    crop_type=crop_type,
                    crop_stage=CropStage.VEGETATIVE,
                    pest_index=0.0,
                    last_updated_tick=0,
                )

    def is_valid_coordinate(self, coords: Coordinates) -> bool:
        """Checks if coordinate falls inside farm grid boundaries."""
        return 0 <= coords.x < self.width and 0 <= coords.y < self.height

    def get_sector(self, coords: Coordinates) -> SectorState:
        """Retrieves ground truth state of a sector."""
        if not self.is_valid_coordinate(coords):
            raise ValueError(f"Coordinate {coords} is outside farm bounds ({self.width}x{self.height})")
        return self.sectors[coords]

    def set_anomalous_patch(
        self,
        coords: Coordinates,
        moisture_pct: float,
        nitrogen_ppm: float,
        phosphorus_ppm: Optional[float] = None,
        potassium_ppm: Optional[float] = None,
    ) -> None:
        """Artificially induces a dry, nutrient-poor patch for testing and case studies."""
        sector = self.get_sector(coords)
        sector.moisture_pct = round(moisture_pct, 2)
        sector.nutrients.nitrogen_ppm = round(nitrogen_ppm, 2)
        if phosphorus_ppm is not None:
            sector.nutrients.phosphorus_ppm = round(phosphorus_ppm, 2)
        if potassium_ppm is not None:
            sector.nutrients.potassium_ppm = round(potassium_ppm, 2)
        sector.last_updated_tick = self.current_tick

    def observe(
        self,
        agent_pos: Coordinates,
        sensor_radius: float = 1.5,
        noise_std: float = 0.0,
    ) -> Dict[Coordinates, SectorState]:
        """Provides localized partial observability to an agent within its sensor radius.
        
        Args:
            agent_pos: Current physical coordinates of the agent.
            sensor_radius: Sensing range in Euclidean distance.
            noise_std: Standard deviation of Gaussian sensor noise.
            
        Returns:
            Dict mapping observed Coordinates to local SectorState copies.
        """
        local_percepts: Dict[Coordinates, SectorState] = {}
        for coords, sector in self.sectors.items():
            dist = agent_pos.euclidean_distance(coords)
            if dist <= sensor_radius:
                # Create a local percept copy (with optional measurement noise)
                n_noise = random.gauss(0, noise_std) if noise_std > 0 else 0.0
                m_noise = random.gauss(0, noise_std) if noise_std > 0 else 0.0

                observed_moisture = max(0.0, min(100.0, sector.moisture_pct + m_noise))
                observed_nitrogen = max(0.0, sector.nutrients.nitrogen_ppm + n_noise)

                percept = sector.model_copy(deep=True)
                percept.moisture_pct = round(observed_moisture, 2)
                percept.nutrients.nitrogen_ppm = round(observed_nitrogen, 2)
                local_percepts[coords] = percept

        return local_percepts

    def apply_water(
        self,
        coords: Coordinates,
        volume_liters: float,
        agent_id: str = "IrrigationAgent",
    ) -> Tuple[float, bool]:
        """Applies irrigation water to a sector.
        
        Formula: 1 Liter per 1m² sector yields approx +2.0% volumetric moisture.
        
        Returns:
            Tuple of (new_moisture_pct, is_over_saturated_flag)
        """
        sector = self.get_sector(coords)
        delta_moisture = volume_liters * 2.0
        new_moisture = sector.moisture_pct + delta_moisture

        is_oversaturated = False
        if new_moisture > sector.saturation_limit_pct:
            is_oversaturated = True
            # Moisture caps at physical saturation; excess becomes runoff
            excess = new_moisture - sector.saturation_limit_pct
            new_moisture = sector.saturation_limit_pct
            # Leaching penalty: heavy runoff washes out 5% nitrogen per excess percent
            leach_factor = max(0.7, 1.0 - (excess * 0.03))
            sector.nutrients.nitrogen_ppm = round(sector.nutrients.nitrogen_ppm * leach_factor, 2)

        sector.moisture_pct = round(new_moisture, 2)
        sector.last_updated_tick = self.current_tick
        sector.last_serviced_by = agent_id
        return sector.moisture_pct, is_oversaturated

    def apply_nutrients(
        self,
        coords: Coordinates,
        nitrogen_g: float,
        phosphorus_g: float,
        potassium_g: float,
        carrier_water_liters: float = 0.0,
        agent_id: str = "FertilizerAgent",
    ) -> Tuple[SoilNutrientProfile, float, bool]:
        """Applies fertilizer dosing with liquid carrier water.
        
        Formula:
            - Nitrogen: +1.0g per m² topsoil adds approx +2.5 ppm.
            - Carrier fluid adds +2.0% moisture per liter.
            
        Returns:
            Tuple of (updated_nutrients, new_moisture, is_oversaturated)
        """
        sector = self.get_sector(coords)
        # Apply nutrients
        sector.nutrients.nitrogen_ppm = round(sector.nutrients.nitrogen_ppm + (nitrogen_g * 2.5), 2)
        sector.nutrients.phosphorus_ppm = round(sector.nutrients.phosphorus_ppm + (phosphorus_g * 2.0), 2)
        sector.nutrients.potassium_ppm = round(sector.nutrients.potassium_ppm + (potassium_g * 2.0), 2)

        # Apply carrier moisture
        new_moisture, is_oversaturated = self.apply_water(
            coords=coords,
            volume_liters=carrier_water_liters,
            agent_id=agent_id,
        )
        return sector.nutrients, new_moisture, is_oversaturated

    def step(self, weather: Optional[WeatherState] = None) -> None:
        """Advances physical environment dynamics by one discrete simulation tick."""
        self.current_tick += 1
        if weather is not None:
            self.weather = weather

        # Physics coefficients
        # Evaporation proportional to solar radiation and ambient temperature
        evap_rate = (self.weather.temperature_c / 30.0) * (self.weather.solar_radiation_w_m2 / 800.0) * 0.15
        rain_gain = self.weather.rain_mm * 2.0

        for coords, sector in self.sectors.items():
            # Update moisture
            current_m = sector.moisture_pct
            updated_m = max(sector.wilting_point_pct * 0.5, current_m - evap_rate + rain_gain)
            sector.moisture_pct = round(updated_m, 2)

            # Crop uptake of nitrogen during active vegetative growth
            if sector.crop_stage == CropStage.VEGETATIVE:
                uptake = 0.08
                sector.nutrients.nitrogen_ppm = round(max(10.0, sector.nutrients.nitrogen_ppm - uptake), 2)
                sector.nutrients.phosphorus_ppm = round(max(5.0, sector.nutrients.phosphorus_ppm - (uptake * 0.3)), 2)

            sector.last_updated_tick = self.current_tick
