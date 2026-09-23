"""Roster slots for the draft GUI's My Team view.

Pure functions over a list of slot names (e.g. ["PG", "F", ..., "BE"]) and a
parallel list of player ids (None for empty). Eligibility uses ESPN's
per-player eligibleSlots, so "F", "SG/SF", "G/F" etc. need no special casing.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

# ESPN lineup slot order, used when building slots from league settings.
SLOT_ORDER = ["PG", "SG", "SF", "PF", "C", "G", "F", "SG/SF", "G/F", "PF/C", "F/C", "UT", "BE"]
BENCH = "BE"

Slots = List[Optional[int]]


def slots_from_counts(counts: Dict[str, int]) -> List[str]:
    """Expand ESPN lineupSlotCounts (by name) into an ordered slot list. IR is excluded."""
    slots: List[str] = []
    for name in SLOT_ORDER:
        slots += [name] * int(counts.get(name, 0))
    return slots


def slots_from_positions(roster_positions: Sequence[str], team_size: int) -> List[str]:
    """settings.txt rosterPositions (starters) plus bench up to teamSize."""
    slots = list(roster_positions)
    return slots + [BENCH] * max(0, team_size - len(slots))


def eligible(slot: str, eligible_slots: Sequence[str]) -> bool:
    return slot in ("UT", BENCH) or slot in eligible_slots


def auto_slot(slots: Sequence[str], filled: Slots, eligible_slots: Sequence[str], skip: int = -1) -> int:
    """First open eligible slot, starters before bench. -1 if none."""
    for i, slot in enumerate(slots):
        if i != skip and filled[i] is None and slot != BENCH and eligible(slot, eligible_slots):
            return i
    for i, slot in enumerate(slots):
        if i != skip and filled[i] is None and slot == BENCH:
            return i
    return -1


def move(
    slots: Sequence[str],
    filled: Slots,
    player_id: int,
    target: int,
    eligibility: Dict[int, Sequence[str]],
    names: Optional[Dict[int, str]] = None,
) -> Tuple[Slots, Optional[str]]:
    """Put `player_id` in slot `target`.

    Works for new adds and moves. If the target is occupied, the occupant
    swaps into the mover's old slot when eligible, otherwise goes to the next
    open eligible slot. Returns (new filled list, error message or None);
    on error the original list is returned unchanged.
    """
    names = names or {}
    name = names.get(player_id, "This player")
    if not 0 <= target < len(slots):
        return list(filled), "That slot doesn't exist."
    if not eligible(slots[target], eligibility.get(player_id, [])):
        return list(filled), f"{name} can't play {slots[target]}."
    result = list(filled)
    source = result.index(player_id) if player_id in result else -1
    occupant = result[target]
    if occupant == player_id:
        return result, None
    if occupant is not None:
        occ_slots = eligibility.get(occupant, [])
        if source >= 0 and eligible(slots[source], occ_slots):
            result[source] = occupant
            source = -1  # already overwritten by the swap
        else:
            result[target] = None
            if source >= 0:
                result[source] = None
            dest = auto_slot(slots, result, occ_slots, skip=target)
            if dest < 0:
                return list(filled), f"No open slot for {names.get(occupant, 'the current player')}. Remove someone first."
            result[dest] = occupant
            source = -1
    if source >= 0:
        result[source] = None
    result[target] = player_id
    return result, None


def remove(filled: Slots, player_id: int) -> Slots:
    return [None if x == player_id else x for x in filled]
