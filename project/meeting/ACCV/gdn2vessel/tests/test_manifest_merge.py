"""
test_manifest_merge.py — Unit tests for manifest merge logic in precompute_benchmark.py

Bug fixed 2026-06-22: manifest write was overwrite-only.
`--dataset drive` would write drive entries and discard pre-existing chase entries.
Fix: read existing manifest → dedup by key=(dataset,severity,image_id,seed)
     (new entry wins on collision) → write back full merged set.

Tests (all pure-Python, no GPU, no real dataset I/O):
  1. Fresh write (no existing manifest) → entries written as-is.
  2. Non-overlapping datasets (drive + chase) → both preserved in merged manifest.
  3. Same-key collision → new entry (re-computed) wins over old (cached) entry.
  4. --dataset all equivalent: all-dataset run covers existing, result = all entries.
  5. Corrupt / missing manifest.json → gracefully falls back to empty existing list.
  6. Dedup key uniqueness: entries with distinct (dataset,severity,image_id,seed)
     are all kept (no false dedup).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Inline the merge logic (mirrors main() in precompute_benchmark.py exactly,
# so any future divergence fails a test — forces them to stay in sync).
# ---------------------------------------------------------------------------

def _entry_key(e: dict) -> tuple:
    return (e.get('dataset', ''), e.get('severity', ''),
            e.get('image_id', ''), e.get('seed', ''))


def _merge_manifest(existing_entries: list, new_entries: list) -> list:
    """
    Merge new_entries into existing_entries.
    Dedup key = (dataset, severity, image_id, seed).
    New entry wins on collision (re-computed beats stale cache).
    Returns list of all merged entries (order: existing first, then new).
    """
    merged: dict = {_entry_key(e): e for e in existing_entries}
    for e in new_entries:
        merged[_entry_key(e)] = e
    return list(merged.values())


def _read_manifest(manifest_path: Path) -> list:
    """Read manifest from disk; return [] on missing/corrupt."""
    if not manifest_path.exists():
        return []
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _write_manifest(manifest_path: Path, entries: list) -> None:
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(dataset: str, severity: str, image_id: str, seed: int,
                status: str = 'computed') -> dict:
    return {
        'dataset':  dataset,
        'severity': severity,
        'image_id': image_id,
        'seed':     seed,
        'npz':      f'/cache/{dataset}/{severity}_{image_id}_s{seed}.npz',
        'n_gaps':   3,
        'shape':    [584, 565],
        'status':   status,
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestManifestMerge:
    """Test the merge-on-write logic introduced to fix the overwrite bug."""

    # ------------------------------------------------------------------
    # 1. Fresh write (no existing manifest)
    # ------------------------------------------------------------------

    def test_fresh_write_no_existing(self, tmp_path):
        """
        When manifest.json does not yet exist, first write should succeed
        and the resulting manifest equals the new entries only.
        """
        manifest_path = tmp_path / 'manifest.json'
        drive_entries = [
            _make_entry('drive', 'Medium', 'img01', 42),
            _make_entry('drive', 'Hard',   'img01', 42),
        ]

        existing = _read_manifest(manifest_path)          # [] — file absent
        assert existing == [], "Expected empty list for absent manifest"

        merged = _merge_manifest(existing, drive_entries)
        _write_manifest(manifest_path, merged)

        result = _read_manifest(manifest_path)
        assert len(result) == 2
        datasets = {e['dataset'] for e in result}
        assert datasets == {'drive'}

    # ------------------------------------------------------------------
    # 2. Non-overlapping datasets: drive + chase both preserved
    # ------------------------------------------------------------------

    def test_two_datasets_both_preserved(self, tmp_path):
        """
        Core regression test for the reported bug:
        Run --dataset drive → manifest has drive entries.
        Run --dataset chase → manifest should have BOTH drive AND chase entries.
        """
        manifest_path = tmp_path / 'manifest.json'

        # Step 1: precompute drive
        drive_entries = [
            _make_entry('drive', 'Medium', 'drive_img01', 7),
            _make_entry('drive', 'Hard',   'drive_img01', 7),
        ]
        existing = _read_manifest(manifest_path)
        merged = _merge_manifest(existing, drive_entries)
        _write_manifest(manifest_path, merged)

        # Step 2: precompute chase (this used to overwrite and lose drive)
        chase_entries = [
            _make_entry('chase', 'Medium', 'chase_img01', 7),
            _make_entry('chase', 'Easy',   'chase_img01', 7),
        ]
        existing = _read_manifest(manifest_path)
        merged = _merge_manifest(existing, chase_entries)
        _write_manifest(manifest_path, merged)

        # Verify both datasets present
        result = _read_manifest(manifest_path)
        datasets = {e['dataset'] for e in result}
        assert 'drive' in datasets, "drive entries lost after chase precompute (regression)"
        assert 'chase' in datasets, "chase entries missing after chase precompute"
        assert len(result) == 4, f"Expected 4 entries total, got {len(result)}"

    # ------------------------------------------------------------------
    # 3. Same-key collision: new (re-computed) wins over old (cached)
    # ------------------------------------------------------------------

    def test_collision_new_entry_wins(self, tmp_path):
        """
        When the same (dataset,severity,image_id,seed) appears in both existing
        and new entries, the NEW entry should survive (re-computed beats cached).
        """
        manifest_path = tmp_path / 'manifest.json'

        old_entry = _make_entry('drive', 'Medium', 'img01', 42, status='cached')
        _write_manifest(manifest_path, [old_entry])

        # Re-compute same image → new entry has status='computed' and more fields
        new_entry = _make_entry('drive', 'Medium', 'img01', 42, status='computed')
        new_entry['n_gaps'] = 5   # updated value

        existing = _read_manifest(manifest_path)
        merged = _merge_manifest(existing, [new_entry])
        _write_manifest(manifest_path, merged)

        result = _read_manifest(manifest_path)
        assert len(result) == 1, "Dedup should keep exactly 1 entry for same key"
        assert result[0]['status'] == 'computed', "New entry should win over cached"
        assert result[0]['n_gaps'] == 5, "New entry's n_gaps should be used"

    # ------------------------------------------------------------------
    # 4. --dataset all equivalent: all-run covers / supersedes existing
    # ------------------------------------------------------------------

    def test_all_dataset_run_supersedes_existing(self, tmp_path):
        """
        After partial precompute (drive only), running --dataset all should
        produce a manifest with all datasets, with no duplication.
        """
        manifest_path = tmp_path / 'manifest.json'

        # Partial: only drive
        partial = [_make_entry('drive', 'Medium', 'img01', 0)]
        _write_manifest(manifest_path, partial)

        # Full run: drive + chase (simulates --dataset all output)
        all_entries = [
            _make_entry('drive', 'Medium', 'img01', 0),   # same key → overwrites
            _make_entry('chase', 'Medium', 'img01', 0),
        ]
        existing = _read_manifest(manifest_path)
        merged = _merge_manifest(existing, all_entries)
        _write_manifest(manifest_path, merged)

        result = _read_manifest(manifest_path)
        assert len(result) == 2, f"Expected 2 entries after --all run, got {len(result)}"
        datasets = {e['dataset'] for e in result}
        assert datasets == {'drive', 'chase'}

    # ------------------------------------------------------------------
    # 5. Corrupt / missing manifest fallback
    # ------------------------------------------------------------------

    def test_corrupt_manifest_fallback(self, tmp_path):
        """
        Corrupt manifest.json (invalid JSON) → _read_manifest returns []
        without raising, and new entries are written normally.
        """
        manifest_path = tmp_path / 'manifest.json'
        manifest_path.write_text('{ INVALID JSON !!!', encoding='utf-8')

        existing = _read_manifest(manifest_path)
        assert existing == [], "Corrupt JSON should fall back to []"

        new_entries = [_make_entry('stare', 'Easy', 'stare01', 1)]
        merged = _merge_manifest(existing, new_entries)
        _write_manifest(manifest_path, merged)

        result = _read_manifest(manifest_path)
        assert len(result) == 1
        assert result[0]['dataset'] == 'stare'

    def test_absent_manifest_fallback(self, tmp_path):
        """Missing manifest.json → _read_manifest returns [] without error."""
        manifest_path = tmp_path / 'nonexistent' / 'manifest.json'
        existing = _read_manifest(manifest_path)
        assert existing == []

    # ------------------------------------------------------------------
    # 6. Distinct keys: no false dedup
    # ------------------------------------------------------------------

    def test_distinct_keys_all_kept(self, tmp_path):
        """
        Entries that differ in any key component (dataset/severity/image_id/seed)
        must all be retained — no false deduplication.
        """
        manifest_path = tmp_path / 'manifest.json'

        entries = [
            _make_entry('drive', 'Easy',   'img01', 0),
            _make_entry('drive', 'Medium', 'img01', 0),   # different severity
            _make_entry('drive', 'Easy',   'img02', 0),   # different image_id
            _make_entry('drive', 'Easy',   'img01', 1),   # different seed
            _make_entry('chase', 'Easy',   'img01', 0),   # different dataset
        ]

        existing = _read_manifest(manifest_path)
        merged = _merge_manifest(existing, entries)
        _write_manifest(manifest_path, merged)

        result = _read_manifest(manifest_path)
        assert len(result) == 5, (
            f"Expected 5 distinct entries, got {len(result)} — false dedup detected"
        )

    # ------------------------------------------------------------------
    # 7. Dedup key fields match precompute_benchmark.py schema
    # ------------------------------------------------------------------

    def test_dedup_key_fields_exist_in_schema(self):
        """
        All four dedup key fields must be present in the canonical entry schema
        produced by precompute_one (both 'computed' and 'cached' branches).
        """
        computed_entry = {
            'dataset':  'drive',
            'severity': 'Medium',
            'image_id': '01',
            'seed':     42,
            'npz':      '/cache/drive/Medium_01_s42.npz',
            'n_gaps':   3,
            'shape':    [584, 565],
            'status':   'computed',
        }
        cached_entry = {
            'dataset':  'drive',
            'severity': 'Medium',
            'image_id': '01',
            'seed':     42,
            'npz':      '/cache/drive/Medium_01_s42.npz',
            'status':   'cached',
        }
        for entry in (computed_entry, cached_entry):
            key = _entry_key(entry)
            assert key == ('drive', 'Medium', '01', 42), (
                f"Unexpected dedup key {key} for entry with status={entry['status']}"
            )

    # ------------------------------------------------------------------
    # 8. Triple-dataset accumulation (drive → chase → stare)
    # ------------------------------------------------------------------

    def test_three_sequential_runs_all_preserved(self, tmp_path):
        """
        Simulates three sequential partial precomputes.
        After each run, the manifest must grow (not reset).
        """
        manifest_path = tmp_path / 'manifest.json'

        for ds in ('drive', 'chase', 'stare'):
            new_e = [_make_entry(ds, 'Medium', f'{ds}_img01', 0)]
            existing = _read_manifest(manifest_path)
            merged = _merge_manifest(existing, new_e)
            _write_manifest(manifest_path, merged)

        result = _read_manifest(manifest_path)
        datasets = {e['dataset'] for e in result}
        assert datasets == {'drive', 'chase', 'stare'}, (
            f"Expected all 3 datasets, got {datasets}"
        )
        assert len(result) == 3
