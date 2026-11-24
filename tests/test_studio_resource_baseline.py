import unittest
from unittest.mock import patch

from scripts import studio_resource_baseline as baseline


class StudioResourceBaselineTests(unittest.TestCase):
    def test_boundary_extrema_and_missing_metric_stay_distinct_from_peaks(self):
        result = baseline.summarize({"id": "fixture", "resources": [{
            "operation": "image",
            "before": {"checked_at": "2026-01-01T00:00:00Z", "ram_available": 20, "commit_used": 30},
            "after": {"checked_at": "2026-01-01T00:00:02Z", "ram_available": 16, "commit_used": 34},
        }]})
        self.assertEqual(result["measurement"], "STAGE_BOUNDARY_SNAPSHOTS")
        self.assertEqual(result["operations"]["image"], {
            "sample_count": 2, "paired_measurements": 1, "paired_wall_seconds": 2,
            "min_ram_available_bytes": 16, "max_commit_used_bytes": 34, "min_vram_free_mib": None,
        })

    def test_continuous_sample_preserves_stage_and_missing_vram(self):
        with (patch.object(baseline.time, "monotonic", side_effect=[0, 0, 0, 1, 1]),
              patch.object(baseline.time, "sleep"),
              patch.object(baseline.draft_resources, "snapshot", return_value={"vram_free_mib": None}),
              patch.object(baseline.draft_pipeline, "_read", return_value={
                  "status": "WAITING_RESOURCES", "stage": "MOTION"})):
            self.assertEqual(list(baseline.sample("fixture", 1)), [{"production_id": "fixture",
                "status": "WAITING_RESOURCES", "stage": "MOTION", "vram_free_mib": None}])
