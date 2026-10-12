"""Agronomic Saturation Governor preventing root drowning and nutrient leaching."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class SaturationEvaluationResult(BaseModel):
    """Result of saturation and agronomic safety analysis."""
    is_safe: bool
    initial_moisture_pct: float
    carrier_moisture_gain_pct: float
    irrigation_moisture_gain_pct: float
    projected_final_moisture_pct: float
    field_capacity_pct: float
    saturation_limit_pct: float
    max_safe_irrigation_liters: float
    adjusted_irrigation_liters: float
    warnings: List[str] = Field(default_factory=list)


class SaturationGovernor:
    """Mathematical governor enforcing soil saturation boundaries during multi-agent fertigation.
    
    Governing Equation:
        M_final = M_current + ΔM_carrier + ΔM_irrigation <= M_field_capacity - safety_margin
        
    Where:
        ΔM_carrier = carrier_water_liters * 2.0%
        ΔM_irrigation = irrigation_water_liters * 2.0%
    """

    def __init__(
        self,
        safety_buffer_pct: float = 5.0,
        moisture_gain_per_liter: float = 2.0,
    ):
        self.safety_buffer_pct = safety_buffer_pct
        self.moisture_gain_per_liter = moisture_gain_per_liter

    def evaluate_fertigation_plan(
        self,
        current_moisture_pct: float,
        carrier_water_liters: float,
        proposed_irrigation_liters: float,
        field_capacity_pct: float = 65.0,
        saturation_limit_pct: float = 75.0,
    ) -> SaturationEvaluationResult:
        """Validates joint water additions against field capacity and soil saturation limits.
        
        Args:
            current_moisture_pct: Current volumetric moisture of target sector.
            carrier_water_liters: Water required as liquid carrier for fertilizer.
            proposed_irrigation_liters: Water proposed by Irrigation Agent.
            field_capacity_pct: Limit where gravitational drainage/leaching begins.
            saturation_limit_pct: Absolute limit where anaerobic root suffocation occurs.
        """
        safe_max_moisture = field_capacity_pct - self.safety_buffer_pct
        warnings = []

        # Carrier water contribution
        carrier_moist_gain = carrier_water_liters * self.moisture_gain_per_liter
        moist_after_carrier = current_moisture_pct + carrier_moist_gain

        # Calculate maximum allowable irrigation water before exceeding safe threshold
        allowable_moist_headroom = max(0.0, safe_max_moisture - moist_after_carrier)
        max_allowed_irr_liters = allowable_moist_headroom / self.moisture_gain_per_liter

        # Proposed moisture contribution
        irr_moist_gain = proposed_irrigation_liters * self.moisture_gain_per_liter
        projected_final = moist_after_carrier + irr_moist_gain

        is_safe = True
        adjusted_irr_liters = proposed_irrigation_liters

        # Check for saturation violation
        if projected_final > saturation_limit_pct:
            is_safe = False
            adjusted_irr_liters = round(max_allowed_irr_liters, 2)
            warnings.append(
                f"CRITICAL OVER-SATURATION: Combined moisture ({projected_final:.1f}%) exceeds "
                f"absolute saturation limit ({saturation_limit_pct:.1f}%). Root suffocation imminent!"
            )
        elif projected_final > safe_max_moisture:
            # Within saturation limit but exceeds safe field capacity: adjust down
            adjusted_irr_liters = round(max_allowed_irr_liters, 2)
            warnings.append(
                f"FIELD CAPACITY WARNING: Combined moisture ({projected_final:.1f}%) exceeds "
                f"safe capacity ({safe_max_moisture:.1f}%). Scaled irrigation down from "
                f"{proposed_irrigation_liters:.1f}L to {adjusted_irr_liters:.1f}L to prevent nutrient leaching."
            )

        return SaturationEvaluationResult(
            is_safe=is_safe,
            initial_moisture_pct=round(current_moisture_pct, 2),
            carrier_moisture_gain_pct=round(carrier_moist_gain, 2),
            irrigation_moisture_gain_pct=round(adjusted_irr_liters * self.moisture_gain_per_liter, 2),
            projected_final_moisture_pct=round(moist_after_carrier + (adjusted_irr_liters * self.moisture_gain_per_liter), 2),
            field_capacity_pct=field_capacity_pct,
            saturation_limit_pct=saturation_limit_pct,
            max_safe_irrigation_liters=round(max_allowed_irr_liters, 2),
            adjusted_irrigation_liters=adjusted_irr_liters,
            warnings=warnings,
        )
