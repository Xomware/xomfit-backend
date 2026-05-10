"""Unit tests for the reports aggregator.

These run without AWS — pure-python module under test.

Run:
    python -m unittest tests.test_reports_aggregator
"""

import unittest

from lambdas.common.reports_aggregator import aggregate, baseline_one_rm


def _set(weight, reps, completed_at=None):
    s = {"weight": weight, "reps": reps}
    if completed_at:
        s["completed_at"] = completed_at
    return s


def _ex(ex_id, name, sets):
    return {"exercise_id": ex_id, "exercise_name": name, "sets": sets}


def _w(started, ended, exercises):
    return {"started_at": started, "ended_at": ended, "exercises": exercises}


class AggregateHappyPath(unittest.TestCase):
    def test_totals_top_exercises_and_pr_detection(self):
        prior = [
            _w(
                "2026-04-25T16:00:00Z", "2026-04-25T17:00:00Z",
                [_ex("bench", "Bench", [_set(185, 5)])],  # baseline e1RM ~ 215.83
            )
        ]

        period = [
            _w(
                "2026-04-28T15:00:00Z",  # Mon
                "2026-04-28T16:00:00Z",  # 60 min
                [
                    _ex("bench", "Bench", [
                        _set(185, 5),                       # 925 vol, e1RM 215.83 (no PR — equals baseline)
                        _set(225, 3, "2026-04-28T15:30:00Z"),  # 675 vol, e1RM 247.5 (PR)
                    ]),
                    _ex("squat", "Squat", [
                        _set(225, 5),                       # 1125 vol, e1RM 262.5 (PR — no prior)
                        _set(225, 5),                       # 1125 vol
                    ]),
                ],
            ),
            _w(
                "2026-04-30T15:00:00Z",
                "2026-04-30T15:30:00Z",                     # 30 min
                [
                    _ex("bench", "Bench", [_set(135, 10)]),  # 1350 vol, e1RM 180 (no PR)
                ],
            ),
        ]

        out = aggregate(period, prior_workouts=prior)

        # Totals: 925 + 675 + 1125 + 1125 + 1350 = 5200
        self.assertEqual(out["total_volume"], 5200.0)
        self.assertEqual(out["sessions"], 2)
        self.assertEqual(out["total_sets"], 5)
        self.assertEqual(out["total_reps"], 5 + 3 + 5 + 5 + 10)

        # avg session secs = (3600 + 1800) / 2 = 2700
        self.assertEqual(out["avg_session_seconds"], 2700)

        # Top exercises by volume: squat (2250) > bench (2950? recalc) -> bench is 925+675+1350=2950
        # So bench (2950) > squat (2250)
        names = [e["exercise_name"] for e in out["top_exercises"]]
        self.assertEqual(names[:2], ["Bench", "Squat"])
        self.assertEqual(out["top_exercises"][0]["volume"], 2950.0)
        self.assertEqual(out["top_exercises"][1]["volume"], 2250.0)

        # PRs: bench beat baseline (215.83 -> 247.5), squat had no baseline so 262.5 is a PR.
        prs_by_id = {p["exercise_id"]: p for p in out["prs"]}
        self.assertIn("bench", prs_by_id)
        self.assertIn("squat", prs_by_id)
        self.assertAlmostEqual(prs_by_id["bench"]["estimated_1rm"], 247.5, places=2)
        self.assertAlmostEqual(prs_by_id["bench"]["previous_estimated_1rm"], 215.83, places=2)
        self.assertAlmostEqual(prs_by_id["squat"]["estimated_1rm"], 262.5, places=2)


class AggregateEdgeCases(unittest.TestCase):
    def test_empty_period_returns_zero_stats(self):
        out = aggregate([], prior_workouts=[])
        self.assertEqual(out["sessions"], 0)
        self.assertEqual(out["total_volume"], 0.0)
        self.assertEqual(out["total_sets"], 0)
        self.assertEqual(out["total_reps"], 0)
        self.assertEqual(out["avg_session_seconds"], 0)
        self.assertEqual(out["top_exercises"], [])
        self.assertEqual(out["prs"], [])

    def test_no_prior_baseline_means_no_prs_reported(self):
        """If prior_workouts is None we cannot establish a baseline,
        so prs[] must be empty (every set would otherwise be a PR)."""
        period = [
            _w(
                "2026-05-04T08:00:00Z", "2026-05-04T09:00:00Z",
                [_ex("bench", "Bench", [_set(225, 1)])],
            )
        ]
        out = aggregate(period, prior_workouts=None)
        self.assertEqual(out["prs"], [])
        self.assertEqual(out["sessions"], 1)
        self.assertEqual(out["total_volume"], 225.0)

    def test_malformed_sets_are_treated_as_zero(self):
        period = [
            _w(
                "2026-05-04T08:00:00Z", "2026-05-04T08:30:00Z",
                [_ex("bench", "Bench", [
                    _set(None, "five"),     # garbage
                    _set("100", "3"),       # stringly typed but valid
                    _set(0, 0),
                ])],
            )
        ]
        out = aggregate(period, prior_workouts=[])
        self.assertEqual(out["total_volume"], 300.0)  # 100 * 3
        self.assertEqual(out["total_sets"], 3)
        self.assertEqual(out["total_reps"], 3)

    def test_baseline_one_rm_uses_best_set(self):
        prior = [
            _w("2026-04-01T00:00:00Z", "2026-04-01T01:00:00Z", [
                _ex("dead", "Deadlift", [_set(315, 5), _set(225, 10), _set(405, 1)]),
            ])
        ]
        baseline = baseline_one_rm(prior)
        # 315*(1+5/30) = 367.5; 225*(1+10/30) = 300; 405 (1 rep) = 405. Best = 405.
        self.assertAlmostEqual(baseline["dead"], 405.0, places=2)


if __name__ == "__main__":
    unittest.main()
