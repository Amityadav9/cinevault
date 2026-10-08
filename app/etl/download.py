"""Download the IMDb non-commercial datasets into data/raw/.

Usage:
    uv run python -m app.etl.download            # skip files that already exist
    uv run python -m app.etl.download --force    # re-download everything

Docs: https://developer.imdb.com/non-commercial-datasets/
"""

import argparse
import sys
from pathlib import Path

import httpx

from app.core.config import get_settings

BASE_URL = "https://datasets.imdbws.com"
FILES = ["title.basics.tsv.gz", "title.ratings.tsv.gz"]
CHUNK_SIZE = 1024 * 1024  # 1 MB


def download(name: str, dest_dir: Path, force: bool = False) -> Path:
    dest = dest_dir / name
    if dest.exists() and not force:
        print(f"✓ {name} already exists ({dest.stat().st_size / 1e6:.1f} MB), skipping")
        return dest

    # Write to .part first, rename at the end: a crashed download never looks complete.
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", f"{BASE_URL}/{name}", timeout=60, follow_redirects=True) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as f:
            for chunk in resp.iter_bytes(CHUNK_SIZE):
                f.write(chunk)
                done += len(chunk)
                pct = f"{done / total:6.1%}" if total else ""
                print(f"\r↓ {name}: {done / 1e6:7.1f} MB {pct}", end="", flush=True)
    tmp.replace(dest)
    print(f"\n✓ saved {dest}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    raw_dir = get_settings().data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        for name in FILES:
            download(name, raw_dir, force=args.force)
    except httpx.HTTPError as exc:
        sys.exit(f"\n✗ download failed: {exc}")


if __name__ == "__main__":
    main()
