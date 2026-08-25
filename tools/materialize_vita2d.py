#!/usr/bin/env python3
"""Materialize the exact historical libvita2d source required by Adrenaline."""

from __future__ import annotations

import argparse
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integration/libvita2d-fbo"
REPOSITORY = (INTEGRATION / "REPOSITORY").read_text(encoding="ascii").strip()
COMMIT = (INTEGRATION / "COMMIT").read_text(encoding="ascii").strip()
TREE = (INTEGRATION / "TREE").read_text(encoding="ascii").strip()


def git(source: Path, *arguments: str, capture: bool = False) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else b""


def verify_source(source: Path) -> None:
    if not (source / ".git").exists():
        raise ValueError(f"not a Git checkout: {source}")
    git(source, "cat-file", "-e", f"{COMMIT}^{{commit}}")
    actual_tree = git(source, "rev-parse", f"{COMMIT}^{{tree}}", capture=True)
    if actual_tree.decode("ascii").strip() != TREE:
        raise RuntimeError("pinned libvita2d commit has an unexpected tree")


def materialize(source: Path, output: Path) -> None:
    verify_source(source)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    archive = git(source, "archive", "--format=tar", COMMIT, capture=True)
    output.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        bundle.extractall(output, filter="data")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.source is not None:
        materialize(args.source.resolve(), args.output.resolve())
        return

    with tempfile.TemporaryDirectory(prefix="adrbubble-vita2d-") as temp:
        checkout = Path(temp) / "vita2dlib"
        subprocess.run(
            ["git", "clone", "--filter=blob:none", REPOSITORY, str(checkout)],
            check=True,
        )
        materialize(checkout, args.output.resolve())


if __name__ == "__main__":
    main()

