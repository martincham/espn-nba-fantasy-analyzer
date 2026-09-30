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


def day_lineup(
    slots: Sequence[str],
    players: Sequence[int],
    eligibility: Dict[int, Sequence[str]],
    prefer: Optional[Dict[int, int]] = None,
) -> Tuple[Slots, List[int]]:
    """One day's starting lineup from the players with a game, best first.

    Each player starts if the players ahead of him can be moved around to make
    a slot for him, so the most players start and the better ones never sit
    for worse ones. `prefer` is a slot to try first for each player (where he
    started the day before), so players stay put from day to day, except that
    UT is left open when someone in it fits an open slot. Returns
    (a player or None for each slot in `slots`, bench slots left empty; the
    players who sit).
    """
    prefer = prefer or {}
    filled: Slots = [None] * len(slots)
    starting = [i for i, slot in enumerate(slots) if slot != BENCH]

    def fits(pid: int, seen: set) -> bool:
        options = [i for i in starting if eligible(slots[i], eligibility.get(pid, []))]
        options.sort(key=lambda i: i != prefer.get(pid))
        for i in options:
            if i in seen:
                continue
            seen.add(i)
            if filled[i] is None or fits(filled[i], seen):
                filled[i] = pid
                return True
        return False

    sits = [pid for pid in players if not fits(pid, set())]
    # Leave UT open rather than a position slot: any streamer fits UT.
    for i in starting:
        if slots[i] == "UT" and filled[i] is not None:
            to = next((j for j in starting if filled[j] is None and slots[j] != "UT"
                       and eligible(slots[j], eligibility.get(filled[i], []))), None)
            if to is not None:
                filled[to], filled[i] = filled[i], None
    return filled, sits
