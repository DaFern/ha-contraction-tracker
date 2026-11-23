"""Check local package structure; --publish also rejects undecided public metadata."""

import argparse
import ast
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "contraction_tracker"


def check(publish=False):
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    for key in ("domain", "name", "version", "documentation", "issue_tracker",
                "codeowners", "config_flow", "dependencies", "requirements", "iot_class"):
        assert key in manifest, key
    assert manifest["domain"] == "contraction_tracker"
    assert manifest["version"] == runpy.run_path(str(COMPONENT / "const.py"))["VERSION"]
    for path in COMPONENT.rglob("*.py"):
        ast.parse(path.read_text(), filename=str(path))
    for path in ROOT.rglob("*.json"):
        if ".git" not in path.parts:
            json.loads(path.read_text())
    assert json.loads((COMPONENT / "strings.json").read_text()) == json.loads(
        (COMPONENT / "translations" / "en.json").read_text())
    for path in (COMPONENT / "brand" / "icon.png", COMPONENT / "frontend" / "icon.png"):
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), path
    assert len(list((ROOT / "custom_components").iterdir())) == 1
    for path in COMPONENT.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".js", ".css", ".json", ".yaml"}:
            text = path.read_text()
            for forbidden in ("duckdns.org", "input_text.meg_", "notify.mobile_app_megan", "notify.daniel"):
                assert forbidden not in text, f"Household reference in {path.name}"
    if publish:
        blockers = []
        if "OWNER" in manifest["documentation"] or "OWNER" in manifest["issue_tracker"]:
            blockers.append("Set the approved public repository and issue URLs.")
        if not manifest["codeowners"]:
            blockers.append("Set an agreed maintainer/code owner.")
        if "NOT SELECTED" in (ROOT / "LICENSE").read_text():
            blockers.append("Choose a redistribution licence with the owner.")
        if blockers:
            print("\n".join(f"BLOCKED: {item}" for item in blockers))
            return 1
    print("Local alpha structure, Python syntax, JSON, translations, assets and household-isolation checks passed.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    sys.exit(check(parser.parse_args().publish))
