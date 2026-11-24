import unittest

from scripts.studio_resource_baseline import summarize


class StudioResourceBaselineTests(unittest.TestCase):
    def test_boundary_extrema_and_missing_metric_stay_distinct_from_peaks(self):
        result = summarize({"id": "fixture", "resources": [{
            "operation": "image",
            "before": {"checked_at": "2026-01-01T00:00:00Z", "ram_available": 20, "commit_used": 30},
            "after": {"checked_at": "2026-01-01T00:00:02Z", "ram_available": 16, "commit_used": 34},
        }]})
        self.assertEqual(result["measurement"], "STAGE_BOUNDARY_SNAPSHOTS")
        self.assertEqual(result["operations"]["image"], {
            "sample_count": 2, "paired_measurements": 1, "paired_wall_seconds": 2,
            "min_ram_available_bytes": 16, "max_commit_used_bytes": 34, "min_vram_free_mib": None,
        })
