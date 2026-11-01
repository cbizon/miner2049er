"""Read KGX JSONL sources, plain or zstd-compressed, and fetch a release.

A Translator KG release is one tar.zst holding nodes.jsonl (~1 GB),
edges.jsonl (~27 GB) and graph-metadata.json. miner-fetch-source splits it
into per-file zstd streams so every reader can stream them without ever
writing the uncompressed graph to disk.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path
from typing import BinaryIO

import httpx
import pyarrow as pa

RELEASE_MEMBERS = {
    "nodes.jsonl": "nodes.jsonl.zst",
    "edges.jsonl": "edges.jsonl.zst",
    "graph-metadata.json": "graph-metadata.json",
}
READ_BUFFER = 8 * 1024 * 1024


def open_source(path: Path) -> BinaryIO:
    """Open a JSONL source for binary line iteration."""
    if path.suffix == ".zst":
        # pyarrow streams don't iterate by line; the buffered wrapper does.
        stream = pa.input_stream(str(path), compression="zstd")
        return io.BufferedReader(stream, buffer_size=READ_BUFFER)
    return path.open("rb")


def download(url: str, destination: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    size = 0
    partial = destination.with_name(destination.name + ".partial")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
        response.raise_for_status()
        with partial.open("wb") as output:
            for chunk in response.iter_bytes(READ_BUFFER):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    partial.replace(destination)
    return {"url": url, "bytes": size, "sha256": digest.hexdigest()}


def split_release(archive: Path, output_dir: Path) -> dict[str, dict[str, int]]:
    written: dict[str, dict[str, int]] = {}
    stream = pa.input_stream(str(archive), compression="zstd", buffer_size=READ_BUFFER)
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            target_name = RELEASE_MEMBERS.get(Path(member.name).name)
            if target_name is None or not member.isfile():
                continue
            source = tar.extractfile(member)
            target = output_dir / target_name
            partial = target.with_name(target.name + ".partial")
            if target_name.endswith(".zst"):
                with pa.output_stream(str(partial), compression="zstd") as output:
                    shutil.copyfileobj(source, output, READ_BUFFER)
            else:
                with partial.open("wb") as output:
                    shutil.copyfileobj(source, output, READ_BUFFER)
            partial.replace(target)
            written[target_name] = {
                "uncompressed_bytes": member.size,
                "stored_bytes": target.stat().st_size,
            }
    missing = set(RELEASE_MEMBERS.values()) - set(written)
    if missing:
        raise ValueError(f"Release archive {archive} lacks {sorted(missing)}")
    return written


def fetch_source(
    *,
    url: str,
    output_dir: Path,
    expected_version: str,
    expected_sha256: str | None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / "release.tar.zst"
    downloaded = download(url, archive)
    if expected_sha256 and downloaded["sha256"] != expected_sha256:
        archive.unlink()
        raise ValueError(
            f"Release checksum mismatch: expected {expected_sha256}, "
            f"found {downloaded['sha256']}"
        )
    files = split_release(archive, output_dir)
    metadata = json.loads((output_dir / "graph-metadata.json").read_text(encoding="utf-8"))
    if metadata.get("version") != expected_version:
        raise ValueError(
            f"Release metadata version {metadata.get('version')!r} does not match "
            f"expected {expected_version!r}"
        )
    archive.unlink()
    record = {"release": downloaded, "graph_version": expected_version, "files": files}
    (output_dir / "source-manifest.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a Translator KG release and split it into zstd JSONL files"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--graph-version", required=True)
    parser.add_argument(
        "--sha256",
        help="Expected SHA-256 of the release archive; recorded either way",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    record = fetch_source(
        url=args.url,
        output_dir=args.output_dir,
        expected_version=args.graph_version,
        expected_sha256=args.sha256,
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
