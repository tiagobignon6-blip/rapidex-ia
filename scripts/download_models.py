#!/usr/bin/env python3
"""Idempotent model fetcher — reads scripts/models.manifest.json, downloads
each entry whose SHA256 doesn't match the on-disk file, verifies post-download.

Usage:
    python scripts/download_models.py             # actually download
    python scripts/download_models.py --dry-run   # report status only

Models live under $RAPIDEX_MODELS_DIR (default: ./models). Listed in the
manifest with url + dest_path + sha256 + bytes_expected. Operator fills
real values during the pod swap (see infra/runpod/SWAP-PROCEDURE.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "models.manifest.json"
MODELS_DIR = Path(os.environ.get("RAPIDEX_MODELS_DIR", "./models")).resolve()


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def status(entry: dict) -> tuple[str, Path]:
    dest = MODELS_DIR / entry["dest_path"]
    if entry["url"] == "TODO":
        return ("manifest-incomplete", dest)
    if not dest.exists():
        return ("missing", dest)
    if entry["sha256"] == "TODO":
        return ("present-unverified", dest)
    actual = sha256_of(dest)
    if actual == entry["sha256"]:
        return ("present", dest)
    return ("checksum-mismatch", dest)


def download(entry: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ downloading {entry['name']} from {entry['url']}")
    urllib.request.urlretrieve(entry["url"], dest)
    actual = sha256_of(dest)
    if entry["sha256"] == "TODO":
        print(
            f"  • {entry['name']} fetched (sha256 was TODO; observed: {actual})"
            f"\n    → paste this value into scripts/models.manifest.json to enable verification"
        )
        return
    if actual != entry["sha256"]:
        dest.unlink(missing_ok=True)
        sys.exit(
            f"  ✗ SHA256 mismatch for {entry['name']}: "
            f"expected {entry['sha256']}, got {actual} — aborted"
        )
    print(f"  ✓ {entry['name']} verified ({dest})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Idempotent model fetcher.")
    ap.add_argument("--dry-run", action="store_true", help="Report status, don't download.")
    args = ap.parse_args()

    if not MANIFEST.exists():
        sys.exit(f"manifest not found at {MANIFEST}")
    manifest = json.loads(MANIFEST.read_text())
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"models_dir = {MODELS_DIR}")
    incomplete = 0
    downloaded = 0
    skipped = 0
    failed = 0

    for entry in manifest["models"]:
        st, dest = status(entry)
        prefix = f"  [{st:>20}] {entry['name']}"
        if st == "manifest-incomplete":
            print(f"{prefix} — fill url + sha256 in manifest before downloading")
            incomplete += 1
            continue
        if st == "present":
            print(f"{prefix} → {dest}")
            skipped += 1
            continue
        if args.dry_run:
            print(f"{prefix} → would download to {dest}")
            continue
        try:
            download(entry, dest)
            downloaded += 1
        except SystemExit:
            failed += 1
            raise

    summary = (
        f"\nsummary: present={skipped} downloaded={downloaded} "
        f"incomplete={incomplete} failed={failed}"
    )
    print(summary)
    return 1 if (failed or incomplete) else 0


if __name__ == "__main__":
    raise SystemExit(main())
