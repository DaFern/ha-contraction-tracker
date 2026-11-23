"""Build a reproducible, explicitly scoped local alpha archive; never publishes."""

from pathlib import Path
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "contraction_tracker"
ALLOWED = {".py", ".json", ".yaml", ".js", ".css", ".png", ".svg"}


def build():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    destination = ROOT / "dist" / f"contraction_tracker-{manifest['version']}.zip"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(COMPONENT.rglob("*")):
            if source.is_symlink():
                raise ValueError("Release source must not contain symlinks.")
            if not source.is_file() or source.suffix not in ALLOWED or "__pycache__" in source.parts:
                continue
            relative = source.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())
    print(destination)
    return destination


if __name__ == "__main__":
    build()
