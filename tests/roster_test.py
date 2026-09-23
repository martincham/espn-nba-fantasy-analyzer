import unittest

from library import roster

SLOTS = ["PG", "C", "F", "F", "SG/SF", "SG/SF", "UT", "BE", "BE"]
ELIG = {
    1: ["C", "PF/C", "F/C", "UT", "BE"],  # center
    2: ["SF", "PF", "F", "SG/SF", "G/F", "UT", "BE"],  # forward
    3: ["PG", "SG", "G", "SG/SF", "UT", "BE"],  # guard
    4: ["C", "PF/C", "UT", "BE"],  # second center
}
NAMES = {1: "Center", 2: "Forward", 3: "Guard", 4: "Backup"}


def empty():
    return [None] * len(SLOTS)


class RosterTest(unittest.TestCase):
    def test_slots_from_counts_orders_and_skips_ir(self):
        counts = {"PG": 1, "C": 1, "F": 2, "SG/SF": 2, "UT": 1, "BE": 5, "IR": 2}
        self.assertEqual(
            roster.slots_from_counts(counts),
            ["PG", "C", "F", "F", "SG/SF", "SG/SF", "UT", "BE", "BE", "BE", "BE", "BE"],
        )

    def test_slots_from_positions_pads_bench(self):
        self.assertEqual(roster.slots_from_positions(["PG", "UT"], 4), ["PG", "UT", "BE", "BE"])

    def test_auto_slot_prefers_starters(self):
        self.assertEqual(roster.auto_slot(SLOTS, empty(), ELIG[1]), 1)
        filled = empty()
        filled[1] = 1
        self.assertEqual(roster.auto_slot(SLOTS, filled, ELIG[4]), 6)  # UT before bench

    def test_rejects_ineligible_slot(self):
        filled, error = roster.move(SLOTS, empty(), 2, 1, ELIG, NAMES)
        self.assertEqual(error, "Forward can't play C.")
        self.assertEqual(filled, empty())

    def test_add_and_swap(self):
        filled, _ = roster.move(SLOTS, empty(), 2, 4, ELIG, NAMES)  # forward to SG/SF
        filled, _ = roster.move(SLOTS, filled, 3, 0, ELIG, NAMES)  # guard to PG
        # Swap forward and guard: guard can play SG/SF, forward can't play PG.
        filled, error = roster.move(SLOTS, filled, 3, 4, ELIG, NAMES)
        self.assertIsNone(error)
        self.assertEqual(filled[4], 3)
        self.assertEqual(filled[0], None)  # forward can't take PG...
        self.assertIn(2, filled)  # ...so it moved to the next open eligible slot
        self.assertEqual(filled.count(2), 1)

    def test_eligible_swap_is_direct(self):
        filled, _ = roster.move(SLOTS, empty(), 1, 1, ELIG, NAMES)
        filled, _ = roster.move(SLOTS, filled, 4, 6, ELIG, NAMES)
        filled, error = roster.move(SLOTS, filled, 4, 1, ELIG, NAMES)
        self.assertIsNone(error)
        self.assertEqual((filled[1], filled[6]), (4, 1))

    def test_bumped_player_needs_room(self):
        filled = [9, 1, 9, 9, 9, 9, 9, 9, 9]
        elig = {**ELIG, 9: ["UT", "BE"]}
        # New center into the C slot: the old center has nowhere to go.
        result, error = roster.move(SLOTS, filled, 4, 1, elig, NAMES)
        self.assertEqual(error, "No open slot for Center. Remove someone first.")
        self.assertEqual(result, filled)

    def test_remove(self):
        self.assertEqual(roster.remove([1, None, 2], 2), [1, None, None])


if __name__ == "__main__":
    unittest.main()
