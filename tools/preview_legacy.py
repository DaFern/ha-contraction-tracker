"""Offline preview only; private snapshots must stay outside this project."""

import argparse
import importlib
import json
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    path = args.source.resolve()
    if path.is_relative_to(ROOT):
        parser.error("Keep personal source snapshots outside the portable project.")
    package = types.ModuleType("_contraction_tracker_preview")
    package.__path__ = [str(ROOT / "custom_components" / "contraction_tracker")]
    sys.modules[package.__name__] = package
    legacy = importlib.import_module(f"{package.__name__}.legacy")
    try:
        source = json.loads(path.read_text(), object_pairs_hook=legacy._unique_object)
        candidate = legacy.convert(source, int(time.time()))
        print(json.dumps({"status": "offline_preview", "saved": False,
                          "source_sha256": legacy.source_digest(source), **legacy.summary(candidate)}))
    except (ValueError, OSError) as err:
        print(f"Preview refused: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
