"""Locate and invoke the independent LEAN installation, without a paid CLI."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import yaml


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def settings(root: Path) -> dict:
    path = root / 'config/lean.yaml'
    config = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
    config = dict(config or {})
    override = os.environ.get('STOCK_RADAR_LEAN_ROOT')
    if override:
        config['installation_root'] = override
    return config


def installation(root: Path) -> tuple[Path, dict]:
    config = settings(root)
    if not config.get('installation_root'):
        raise ValueError('Set installation_root in config/lean.yaml or STOCK_RADAR_LEAN_ROOT')
    home = Path(config['installation_root']).resolve()
    files = {
        'launcher': home / 'engine/Launcher/bin/Release/QuantConnect.Lean.Launcher.dll',
        'engine': home / 'engine/Launcher/bin/Release/QuantConnect.Lean.Engine.dll',
        'dotnet': home / 'runtime/dotnet/dotnet.exe',
        'python': home / 'runtime/python-package/tools/python311.dll',
        'base_config': home / 'config/demo-python.json',
    }
    for name, path in files.items():
        if not path.is_file():
            raise FileNotFoundError(f'Local LEAN {name} is missing: {path}')
    revision = subprocess.run(['git', '-C', str(home / 'engine'), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    patch = home / 'patches/python-shutdown.diff'
    return home, {'engine': 'lean', 'commit': revision,
                  'launcher_sha256': digest(files['launcher']),
                  'engine_sha256': digest(files['engine']),
                  'python_sha256': digest(files['python']),
                  'local_patch_sha256': digest(patch) if patch.exists() else None,
                  'installation_root': str(home)}


def verify_bundle(output: Path, expected_manifest_hash: str) -> None:
    """Prove the frozen execution configuration and consumed data stayed intact."""
    manifest_path = output / 'manifest.json'
    if digest(manifest_path) != expected_manifest_hash:
        raise ValueError('Frozen LEAN manifest changed')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for filename, key in (('algorithm.py', 'algorithm_sha256'), ('signals.json', 'signal_snapshot'),
                          ('source-prices.csv', 'source_prices_sha256'), ('data-index.json', 'data_snapshot')):
        if digest(output / filename) != manifest[key]:
            raise ValueError(f'Frozen LEAN input changed: {filename}')
    data = (output / 'data').resolve()
    index = json.loads((output / 'data-index.json').read_text(encoding='utf-8'))
    for relative, expected in index.items():
        path = (data / relative).resolve()
        if not path.is_relative_to(data) or digest(path) != expected:
            raise ValueError(f'Frozen LEAN data changed: {relative}')


def invoke(root: Path, output: Path, manifest: Path, run_id: str,
           on_progress, cancelled, expected_identity: dict | None = None,
           expected_manifest_hash: str | None = None) -> Path:
    """Stream native daily portfolio observations; kill child on cancellation/error."""
    from radar.backtest.engine import BacktestCancelled

    home, identity = installation(root)
    if expected_identity is not None and identity != expected_identity:
        raise ValueError('LEAN build changed after this run was queued')
    manifest_hash = expected_manifest_hash or digest(manifest)
    verify_bundle(output, manifest_hash)
    config = json.loads((home / 'config/demo-python.json').read_text(encoding='utf-8-sig'))
    config.update({'environment': 'backtesting', 'live-mode': False,
                   'algorithm-type-name': 'StockRadarExecution', 'algorithm-language': 'Python',
                   'algorithm-location': str(output / 'algorithm.py'),
                   'data-folder': str(output / 'data'), 'results-destination-folder': str(output),
                   'algorithm-id': run_id, 'backtest-name': run_id,
                   'object-store-root': str(output / 'storage'), 'close-automatically': True,
                   'transaction-log': str(output / 'transactions.csv'),
                   'parameters': {'stock-radar-manifest': str(manifest),
                                  'stock-radar-manifest-hash': manifest_hash},
                   'python-additional-paths': [], 'show-missing-data-logs': True})
    if config['environments']['backtesting'].get('live-mode'):
        raise ValueError('LEAN integration only permits backtesting')
    config_path = output / 'lean-config.json'
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    binary = home / 'engine/Launcher/bin/Release'
    dotnet = home / 'runtime/dotnet/dotnet.exe'
    python = home / 'runtime/python-package/tools'
    env = os.environ.copy()
    # Do not leak the host venv into the independent embedded Python runtime.
    env.pop('VIRTUAL_ENV', None)
    env.update({'DOTNET_ROOT': str(dotnet.parent),
                'DOTNET_CLI_HOME': str(home / 'runtime/dotnet-home'),
                'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'PYTHONNET_PYDLL': str(python / 'python311.dll'),
                'PYTHONHOME': str(python), 'PYTHONPATH': os.pathsep.join([
                    str(python / 'Lib/site-packages'), str(binary)]),
                'PYTHONNOUSERSITE': '1', 'PYTHONUTF8': '1'})
    env['PATH'] = os.pathsep.join([str(dotnet.parent), str(python), env.get('PATH', '')])
    progress_path = output / 'daily.jsonl'
    cursor = 0

    def drain():
        nonlocal cursor
        if not progress_path.exists():
            return
        with progress_path.open('rb') as stream:
            stream.seek(cursor)
            while True:
                line = stream.readline()
                if not line.endswith(b'\n'):
                    break
                cursor = stream.tell()
                on_progress(json.loads(line))

    timeout = int(settings(root).get('timeout_seconds', 7200))
    started = time.monotonic()
    with (output / 'console.log').open('w', encoding='utf-8') as log:
        child = subprocess.Popen([str(dotnet), str(binary / 'QuantConnect.Lean.Launcher.dll'),
                                  '--config', str(config_path)], cwd=binary, env=env,
                                 stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while child.poll() is None:
                if cancelled():
                    raise BacktestCancelled('LEAN cancelled')
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f'LEAN exceeded {timeout} seconds')
                drain()
                time.sleep(.15)
            drain()
            if cancelled():
                raise BacktestCancelled('LEAN cancelled')
            if child.returncode:
                raise RuntimeError(f'LEAN exited {child.returncode}; see {output / "console.log"}')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    result = output / f'{run_id}.json'
    if not result.exists() or not (output / 'completed.json').exists():
        raise RuntimeError(f'LEAN did not complete; see {output / "console.log"}')
    verify_bundle(output, manifest_hash)
    return result
