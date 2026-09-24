"""Dynamic Spatial Knowledge Base implementing multi-agent belief fusion and uncertainty decay."""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from krishi_karyastan.core.models import (
    Coordinates,
    SectorState,
    SoilNutrientProfile,
    WeatherState,
)


class Belief(BaseModel):
    """Represents the collective agent belief regarding a specific sector."""
    coords: Coordinates
    estimated_state: SectorState
    confidence: float = Field(..., ge=0.0, le=1.0, description="Certainty score (0.0 to 1.0)")
    last_observed_tick: int = Field(..., ge=0)
    contributing_agents: List[str] = Field(default_factory=list)

    def is_stale(self, current_tick: int, threshold_ticks: int = 15) -> bool:
        """Determines if the belief requires fresh re-sensing due to staleness."""
        return (current_tick - self.last_observed_tick) > threshold_ticks or self.confidence < 0.35


class SharedKnowledgeBase:
    """Decentralized/Shared Spatial Knowledge Base constructed from distributed agent observations.
    
    Demonstrates Knowledge Representation under Partial Observability:
    1. Agents transmit localized percepts.
    2. Knowledge base fuses observations with Bayesian-inspired weighted averaging.
    3. Unobserved sectors decay in confidence over time via exponential decay.
    """

    def __init__(
        self,
        decay_constant: float = 0.05,
        default_confidence: float = 0.5,
    ):
        self.decay_constant = decay_constant
        self.default_confidence = default_confidence
        self.beliefs: Dict[Coordinates, Belief] = {}
        self.last_sync_tick: int = 0
        self.update_history: List[dict] = []

    def update_belief(
        self,
        coords: Coordinates,
        observed_state: SectorState,
        confidence: float,
        current_tick: int,
        agent_id: str,
    ) -> Belief:
        """Fuses a newly arrived agent percept into the dynamic knowledge base."""
        self.last_sync_tick = current_tick

        if coords not in self.beliefs:
            # First time observing this sector
            belief = Belief(
                coords=coords,
                estimated_state=observed_state.model_copy(deep=True),
                confidence=min(1.0, max(0.0, confidence)),
                last_observed_tick=current_tick,
                contributing_agents=[agent_id],
            )
            self.beliefs[coords] = belief
            return belief

        existing = self.beliefs[coords]
        # Current decayed confidence of prior belief
        prior_c = self._compute_decayed_confidence(existing, current_tick)
        new_c = min(1.0, max(0.0, confidence))

        # Weighted belief fusion
        total_weight = prior_c + new_c
        if total_weight > 0:
            w_prior = prior_c / total_weight
            w_new = new_c / total_weight

            fused_moisture = (existing.estimated_state.moisture_pct * w_prior) + (observed_state.moisture_pct * w_new)
            fused_n = (existing.estimated_state.nutrients.nitrogen_ppm * w_prior) + (observed_state.nutrients.nitrogen_ppm * w_new)
            fused_p = (existing.estimated_state.nutrients.phosphorus_ppm * w_prior) + (observed_state.nutrients.phosphorus_ppm * w_new)
            fused_k = (existing.estimated_state.nutrients.potassium_ppm * w_prior) + (observed_state.nutrients.potassium_ppm * w_new)

            fused_nutrients = SoilNutrientProfile(
                nitrogen_ppm=round(fused_n, 2),
                phosphorus_ppm=round(fused_p, 2),
                potassium_ppm=round(fused_k, 2),
                organic_matter_pct=observed_state.nutrients.organic_matter_pct,
                ph=observed_state.nutrients.ph,
            )

            existing.estimated_state.moisture_pct = round(fused_moisture, 2)
            existing.estimated_state.nutrients = fused_nutrients
            existing.estimated_state.crop_stage = observed_state.crop_stage
            existing.estimated_state.pest_index = observed_state.pest_index

        # Confidence increases with corroborating observation
        fused_confidence = min(1.0, prior_c + new_c * (1.0 - prior_c))
        existing.confidence = round(fused_confidence, 3)
        existing.last_observed_tick = current_tick
        if agent_id not in existing.contributing_agents:
            existing.contributing_agents.append(agent_id)

        self.update_history.append({
            "tick": current_tick,
            "coords": coords.to_tuple(),
            "agent_id": agent_id,
            "moisture": existing.estimated_state.moisture_pct,
            "nitrogen": existing.estimated_state.nutrients.nitrogen_ppm,
            "confidence": existing.confidence,
        })
        return existing

    def _compute_decayed_confidence(self, belief: Belief, current_tick: int) -> float:
        """Applies exponential staleness decay: c(t) = c_0 * exp(-lambda * dt)."""
        dt = max(0, current_tick - belief.last_observed_tick)
        decayed = belief.confidence * math.exp(-self.decay_constant * dt)
        return max(0.05, min(1.0, decayed))

    def decay_all(self, current_tick: int) -> None:
        """Applies temporal staleness decay across all registered beliefs."""
        self.last_sync_tick = current_tick
        for belief in self.beliefs.values():
            belief.confidence = round(self._compute_decayed_confidence(belief, current_tick), 3)

    def get_belief(self, coords: Coordinates, current_tick: Optional[int] = None) -> Optional[Belief]:
        """Retrieves belief for a coordinate, optionally updating decayed confidence."""
        belief = self.beliefs.get(coords)
        if belief and current_tick is not None:
            belief.confidence = round(self._compute_decayed_confidence(belief, current_tick), 3)
        return belief

    def find_deficient_patches(
        self,
        moisture_threshold: float = 32.0,
        nitrogen_threshold: float = 80.0,
        min_confidence: float = 0.25,
    ) -> List[Tuple[Coordinates, Belief]]:
        """Identifies sectors believed to be dry and/or nutrient-poor with sufficient certainty."""
        flagged: List[Tuple[Coordinates, Belief]] = []
        for coords, belief in self.beliefs.items():
            if belief.confidence >= min_confidence:
                state = belief.estimated_state
                if state.moisture_pct < moisture_threshold or state.nutrients.nitrogen_ppm < nitrogen_threshold:
                    flagged.append((coords, belief))
        return flagged

    def get_coverage_ratio(self, total_sectors: int) -> float:
        """Calculates proportion of farm sectors currently mapped in the knowledge base."""
        if total_sectors == 0:
            return 0.0
        return len(self.beliefs) / total_sectors

    def get_summary_statistics(self) -> dict:
        """Computes aggregate health metrics from the knowledge base."""
        if not self.beliefs:
            return {"sectors_known": 0, "avg_moisture": 0.0, "avg_nitrogen": 0.0, "avg_confidence": 0.0}

        total_m = sum(b.estimated_state.moisture_pct for b in self.beliefs.values())
        total_n = sum(b.estimated_state.nutrients.nitrogen_ppm for b in self.beliefs.values())
        total_c = sum(b.confidence for b in self.beliefs.values())
        count = len(self.beliefs)

        return {
            "sectors_known": count,
            "avg_moisture": round(total_m / count, 2),
            "avg_nitrogen": round(total_n / count, 2),
            "avg_confidence": round(total_c / count, 3),
        }
