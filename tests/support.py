"""Load dependency-free modules without importing Home Assistant."""

import importlib
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
namespace = "_contraction_tracker_test_core"
if namespace not in sys.modules:
    package = types.ModuleType(namespace)
    package.__path__ = [str(ROOT / "custom_components" / "contraction_tracker")]
    sys.modules[namespace] = package

model = importlib.import_module(f"{namespace}.model")
manager = importlib.import_module(f"{namespace}.manager")
notifications = importlib.import_module(f"{namespace}.notifications")
