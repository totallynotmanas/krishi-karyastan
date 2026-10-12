"""4D Spatio-Temporal Reservation Grid for hardware collision avoidance."""

from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple
from krishi_karyastan.core.models import Coordinates, TimeSlot


class CollisionAvoidanceTable:
    """Maintains a space-time reservation matrix R(x, y, t) -> agent_id.
    
    Guarantees physical safety by ensuring no two autonomous rovers occupy the same
    physical coordinates or active spraying zones during overlapping time intervals.
    """

    def __init__(self):
        # Key: (x, y, tick) -> agent_id
        self._reservations: Dict[Tuple[int, int, int], str] = {}
        self._reservation_log: List[dict] = []

    def is_slot_available(
        self,
        coords: Coordinates,
        slot: TimeSlot,
        agent_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """Checks if all discrete ticks in the time slot at target sector are free.
        
        Returns:
            Tuple of (is_available, conflicting_agent_id)
        """
        for tick in range(slot.start_tick, slot.end_tick + 1):
            key = (coords.x, coords.y, tick)
            occupant = self._reservations.get(key)
            if occupant is not None and occupant != agent_id:
                return False, occupant
        return True, None

    def reserve(
        self,
        coords: Coordinates,
        slot: TimeSlot,
        agent_id: str,
        reason: str = "Field Operation",
    ) -> bool:
        """Attempts to reserve a space-time block.
        
        Returns:
            True if reserved successfully; False if collision conflict exists.
        """
        available, conflict = self.is_slot_available(coords, slot, agent_id)
        if not available:
            return False

        for tick in range(slot.start_tick, slot.end_tick + 1):
            key = (coords.x, coords.y, tick)
            self._reservations[key] = agent_id

        self._reservation_log.append({
            "coords": coords.to_tuple(),
            "start_tick": slot.start_tick,
            "end_tick": slot.end_tick,
            "agent_id": agent_id,
            "reason": reason,
        })
        return True

    def release(
        self,
        coords: Coordinates,
        slot: TimeSlot,
        agent_id: str,
    ) -> None:
        """Releases a reserved space-time block."""
        for tick in range(slot.start_tick, slot.end_tick + 1):
            key = (coords.x, coords.y, tick)
            if self._reservations.get(key) == agent_id:
                del self._reservations[key]

    def find_first_available_slot(
        self,
        coords: Coordinates,
        duration: int,
        earliest_start: int,
        agent_id: str,
        max_search_ticks: int = 100,
    ) -> TimeSlot:
        """Searches ahead in time to find the earliest non-conflicting operational window."""
        start = earliest_start
        while start < (earliest_start + max_search_ticks):
            candidate_slot = TimeSlot(start_tick=start, end_tick=start + duration - 1)
            available, _ = self.is_slot_available(coords, candidate_slot, agent_id)
            if available:
                return candidate_slot
            start += 1

        # Fallback to far future slot if dense
        return TimeSlot(start_tick=earliest_start + max_search_ticks, end_tick=earliest_start + max_search_ticks + duration - 1)

    def get_active_reservations_at_tick(self, tick: int) -> Dict[Coordinates, str]:
        """Returns map of sectors currently reserved at a specific tick."""
        active: Dict[Coordinates, str] = {}
        for (x, y, t), agent_id in self._reservations.items():
            if t == tick:
                active[Coordinates(x=x, y=y)] = agent_id
        return active

    def clear(self) -> None:
        """Resets all reservations."""
        self._reservations.clear()
        self._reservation_log.clear()
