"""Tests for the selection rules in cleanup_ghcr.py.

The package versions here are made up: small, hand-written examples of each case the rules
must handle, not a copy of what is on GHCR.
"""

import unittest
from datetime import datetime, timezone

from cleanup_ghcr import closed_pr_versions, deletable, is_stale_staging

SHA = "a" * 40
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
OLD = "2026-09-01T00:00:00Z"   # well past 48 hours
NEW = "2026-09-30T23:00:00Z"   # one hour before NOW


def version(digest, tag_list=(), created=OLD):
    return {"id": digest, "name": digest, "created_at": created,
            "metadata": {"container": {"tags": list(tag_list)}}}


def names(versions):
    return sorted(v["name"] for v in versions)


class ClosedPr(unittest.TestCase):
    def test_only_versions_tagged_solely_for_this_pr(self):
        versions = [
            version("own", ["env-pr-12", "env-pr-12-x86_64"]),
            version("shared", ["env", "env-pr-12"]),  # also main's: keep
            version("other", ["env-pr-123"]),         # 123 is not 12
            version("untagged"),
        ]
        self.assertEqual(names(closed_pr_versions(versions, 12)), ["own"])


class StaleStaging(unittest.TestCase):
    def test_needs_a_staging_tag_and_only_ci_tags(self):
        self.assertTrue(is_stale_staging(version("d", [f"env-mg-{SHA}"])))
        self.assertTrue(is_stale_staging(version("d", [f"env-mg-{SHA}-aarch64", "env-pr-7"])))
        self.assertFalse(is_stale_staging(version("d", ["env-pr-7"])))        # open PR
        self.assertFalse(is_stale_staging(version("d", [f"env-mg-{SHA}", "env"])))  # published
        self.assertFalse(is_stale_staging(version("d", ["env-mg-abc123"])))   # not a full sha
        self.assertFalse(is_stale_staging(version("d")))


class Deletable(unittest.TestCase):
    def test_keeps_what_tagged_versions_reference(self):
        versions = [
            version("index", ["env"]),
            version("amd64"), version("arm64"), version("attestation"),  # children of index
            version("orphan"),
        ]
        refs = {"index": ["amd64", "arm64", "attestation"]}
        self.assertEqual(names(deletable(versions, refs, NOW, 48)), ["orphan"])

    def test_age_threshold(self):
        versions = [version("old"), version("new", created=NEW)]
        self.assertEqual(names(deletable(versions, {}, NOW, 48)), ["old"])
        self.assertEqual(names(deletable(versions, {}, NOW, 0.5)), ["new", "old"])

    def test_stale_staging_goes_but_its_children_wait_a_run(self):
        # The children are still referenced this run; once the index is gone they are
        # untagged and unreferenced, and go on the next one.
        versions = [version("mg", [f"env-mg-{SHA}"]), version("child")]
        self.assertEqual(names(deletable(versions, {"mg": ["child"]}, NOW, 48)), ["mg"])

    def test_live_cache_tag_is_kept_at_any_age(self):
        versions = [version("cache", ["env-x86_64"]), version("blob"), version("superseded")]
        self.assertEqual(names(deletable(versions, {"cache": ["blob"]}, NOW, 48)), ["superseded"])

    def test_unreadable_manifest_deletes_nothing(self):
        versions = [version("index", ["env"]), version("orphan")]
        self.assertIsNone(deletable(versions, {}, NOW, 48))


if __name__ == "__main__":
    unittest.main()
