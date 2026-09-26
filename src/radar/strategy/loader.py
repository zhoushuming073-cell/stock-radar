"""Validate and load a strategy directory or a single-strategy ZIP.

Source and archive checks happen before import or test execution. These checks
do not sandbox Python: only load code from a trusted author.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from types import MappingProxyType, ModuleType
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from radar.strategy.registry import StrategyRegistration, StrategyRegistry
from radar.strategy.validation import (
    StrategyManifest,
    StrategyValidationError,
    inspect_plugin_source,
    validate_available_features,
    validate_plugin_identity,
)


_FILES = frozenset({
    "manifest.yaml", "strategy.yaml", "strategy.py", "README.md",
    "tests/test_strategy.py",
})
_MAX_FILE_BYTES = 1_000_000
_MAX_ARCHIVE_BYTES = 5_000_000
_MAX_ARCHIVE_MEMBERS = 20


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise StrategyValidationError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(document, dict) or not all(isinstance(k, str) for k in document):
        raise StrategyValidationError(f"{path.name} must be a YAML mapping with string keys")
    return document


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _check_directory(path: Path) -> None:
    if not path.is_dir() or path.is_symlink():
        raise StrategyValidationError(f"strategy directory does not exist: {path}")
    found: set[str] = set()
    for child in path.rglob("*"):
        if child.is_symlink():
            raise StrategyValidationError(f"symbolic links are not allowed: {child}")
        relative = child.relative_to(path).as_posix()
        if any(part in {"__pycache__", ".pytest_cache"} for part in child.relative_to(path).parts):
            continue
        if child.is_file():
            if relative not in _FILES:
                raise StrategyValidationError(f"unexpected strategy file: {relative}")
            if child.stat().st_size > _MAX_FILE_BYTES:
                raise StrategyValidationError(f"strategy file exceeds size limit: {relative}")
            found.add(relative)
        elif child.is_dir() and relative != "tests":
            raise StrategyValidationError(f"unexpected strategy directory: {relative}")
    if found != _FILES:
        raise StrategyValidationError(f"missing strategy files: {', '.join(sorted(_FILES - found))}")


def _run_plugin_tests(path: Path) -> None:
    env = os.environ.copy()
    package_src = Path(__file__).resolve().parents[2]
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Only copy the inspected source set. Existing bytecode and pytest caches
    # in an installed directory cannot influence the test import.
    with tempfile.TemporaryDirectory(prefix="stock-radar-plugin-test-") as temp_name:
        clean = Path(temp_name)
        for relative in _FILES:
            target = clean / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path / relative, target)
        env["PYTHONPATH"] = os.pathsep.join((str(clean), str(package_src)))
        try:
            result = subprocess.run(
                [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_strategy.py"],
                cwd=clean,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StrategyValidationError(f"plugin tests could not finish: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stdout + "\n" + result.stderr)[-4000:]
        raise StrategyValidationError(f"plugin tests failed:\n{detail}")


def _import_plugin(path: Path, manifest: StrategyManifest, *, reported_path: Path):
    source = path / "strategy.py"
    source_bytes = source.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()[:16]
    module_name = f"radar_user_strategy_{manifest.id}_{digest}"
    # Compile the inspected source, never a pre-existing __pycache__ payload.
    module = ModuleType(module_name)
    module.__file__ = str(reported_path)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        exec(compile(source_bytes, str(reported_path), "exec"), module.__dict__)
        return validate_plugin_identity(getattr(module, "PLUGIN", None), manifest)
    except Exception:
        sys.modules.pop(module_name, None)
        raise


def load_strategy_directory(
    path: str | Path,
    available_features: set[str] | frozenset[str],
    *,
    registry: StrategyRegistry | None = None,
    run_tests: bool = True,
) -> StrategyRegistration:
    """Validate and import one installed strategy directory.

    ``available_features`` must be the installed causal feature-version's names.
    Static checks precede both plugin tests and import. Python is not sandboxed.
    """
    candidate = Path(path)
    if candidate.is_symlink():
        raise StrategyValidationError(f"strategy directory symlink is not allowed: {candidate}")
    directory = candidate.resolve()
    _check_directory(directory)
    # Freeze the exact five source files before inspection, tests and import.
    # This prevents a concurrent edit from changing the code after inspection.
    with tempfile.TemporaryDirectory(prefix="stock-radar-plugin-load-") as temp_name:
        snapshot = Path(temp_name)
        for relative in _FILES:
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(directory / relative, target)
        try:
            manifest = StrategyManifest.model_validate(_read_yaml_mapping(snapshot / "manifest.yaml"))
        except ValidationError as exc:
            raise StrategyValidationError(f"invalid manifest.yaml: {exc}") from exc
        config: Mapping[str, Any] = _freeze(_read_yaml_mapping(snapshot / "strategy.yaml"))
        validate_available_features(manifest, available_features)
        inspect_plugin_source(snapshot)
        if run_tests:
            _run_plugin_tests(snapshot)
        plugin = _import_plugin(
            snapshot, manifest, reported_path=directory / "strategy.py"
        )
    registration = StrategyRegistration(manifest, config, plugin, directory)
    if registry is not None:
        registry.register(registration)
    return registration


def _validated_archive_members(archive: zipfile.ZipFile) -> tuple[str, list[zipfile.ZipInfo]]:
    infos = archive.infolist()
    if not infos or len(infos) > _MAX_ARCHIVE_MEMBERS:
        raise StrategyValidationError("ZIP is empty or contains too many members")
    top: set[str] = set()
    files: set[str] = set()
    seen: set[str] = set()
    size = 0
    for info in infos:
        name = info.filename
        if "\\" in name or "\x00" in name or ":" in name:
            raise StrategyValidationError(f"unsafe ZIP member name: {name!r}")
        relative = PurePosixPath(name)
        parts = relative.parts
        if not parts or relative.is_absolute() or any(part in {".", "..", ""} for part in parts):
            raise StrategyValidationError(f"unsafe ZIP member path: {name!r}")
        if name.rstrip("/") != "/".join(parts):
            raise StrategyValidationError(f"noncanonical ZIP member path: {name!r}")
        normalized = "/".join(parts).casefold()
        if normalized in seen:
            raise StrategyValidationError(f"duplicate ZIP path: {name!r}")
        seen.add(normalized)
        top.add(parts[0])
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise StrategyValidationError(f"ZIP symlink is not allowed: {name}")
        if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise StrategyValidationError(f"ZIP special file is not allowed: {name}")
        if info.flag_bits & 0x1:
            raise StrategyValidationError("encrypted ZIP members are not allowed")
        if info.file_size > _MAX_FILE_BYTES:
            raise StrategyValidationError(f"ZIP member exceeds size limit: {name}")
        size += info.file_size
        if size > _MAX_ARCHIVE_BYTES:
            raise StrategyValidationError("ZIP exceeds uncompressed size limit")
        if not info.is_dir():
            if len(parts) != 2 and len(parts) != 3:
                raise StrategyValidationError(f"unexpected ZIP member: {name}")
            relative_file = "/".join(parts[1:])
            if relative_file not in _FILES:
                raise StrategyValidationError(f"unexpected ZIP member: {name}")
            files.add(relative_file)
    if len(top) != 1:
        raise StrategyValidationError("ZIP must contain exactly one strategy directory")
    strategy_id = next(iter(top))
    if not strategy_id or not strategy_id.isascii():
        raise StrategyValidationError("ZIP top-level directory must be an ASCII strategy ID")
    if files != _FILES:
        raise StrategyValidationError(f"ZIP missing files: {', '.join(sorted(_FILES - files))}")
    return strategy_id, infos


def install_strategy_zip(
    zip_path: str | Path,
    strategies_root: str | Path,
    available_features: set[str] | frozenset[str],
    *,
    registry: StrategyRegistry | None = None,
    run_tests: bool = True,
) -> StrategyRegistration:
    """Safely unpack, validate, test and install one strategy ZIP.

    Static inspection happens before Python execution. This is not an OS
    sandbox; only install ZIPs from trusted authors.
    """
    root = Path(strategies_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            folder, members = _validated_archive_members(archive)
            with tempfile.TemporaryDirectory(prefix=".strategy-stage-", dir=root) as stage_name:
                stage = Path(stage_name)
                for info in members:
                    target = stage.joinpath(*PurePosixPath(info.filename).parts)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("xb") as output:
                        copied = 0
                        while chunk := source.read(64 * 1024):
                            copied += len(chunk)
                            if copied > _MAX_FILE_BYTES or copied > info.file_size:
                                raise StrategyValidationError(
                                    f"ZIP member expanded beyond size limit: {info.filename}"
                                )
                            output.write(chunk)
                staged = stage / folder
                registration = load_strategy_directory(
                    staged, available_features, run_tests=run_tests
                )
                if registration.manifest.id != folder:
                    raise StrategyValidationError(
                        "ZIP directory must match manifest strategy ID"
                    )
                destination = root / f"{folder}@{registration.manifest.version}"
                if destination.exists():
                    raise StrategyValidationError(f"strategy directory already exists: {destination}")
                if registry is not None:
                    try:
                        registry.get(folder, registration.manifest.version)
                    except KeyError:
                        pass
                    else:
                        raise StrategyValidationError(
                            f"strategy ID/version already registered: "
                            f"{folder} {registration.manifest.version}"
                        )
                staged.rename(destination)
                installed = StrategyRegistration(
                    registration.manifest, registration.config,
                    registration.plugin, destination,
                )
                if registry is not None:
                    registry.register(installed)
                return installed
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise StrategyValidationError(f"invalid strategy ZIP: {exc}") from exc
