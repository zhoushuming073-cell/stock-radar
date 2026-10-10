"""Build the exact five-file Q2 v1.3 Strategy Lab import ZIP."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from radar.lab.data import available_features
from radar.lab.research_backend import FEATURES
from radar.strategy.loader import install_strategy_zip, load_strategy_directory


FILES = ("manifest.yaml", "strategy.yaml", "strategy.py", "README.md",
         "tests/test_strategy.py")


def build(root: Path) -> Path:
    folder = root / "templates/q2_relaxed_channel_v1_3"
    features = available_features(root / "data/phase2-research.duckdb") | FEATURES
    registration = load_strategy_directory(folder, features, run_tests=True)
    if (registration.manifest.id, registration.manifest.version) != (
            "q2_relaxed_channel_v1_3", "1.3.0"):
        raise ValueError("unexpected Q2 plugin identity/version")
    target = root / "data/exports/q2_v13_relaxed_channel_plugin.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        for relative in FILES:
            info = zipfile.ZipInfo(f"{registration.manifest.id}/{relative}",
                                   (2026, 10, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (folder / relative).read_bytes())
    with TemporaryDirectory(prefix="q2-v13-zip-") as temporary:
        installed = install_strategy_zip(target, Path(temporary), features,
                                         run_tests=True)
        if installed.manifest != registration.manifest:
            raise ValueError("installed ZIP manifest differs from reviewed source")
    return target


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(build(root))
