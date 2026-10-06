"""Pinned Git history, not mutable latest lists or GitHub API pagination.

Raw repositories stay local. Commit time is availability evidence, not an
exchange-certified listing timestamp. Nothing in this module licenses data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

REPOSITORIES = {
    "symbols": "https://github.com/rreichel3/US-Stock-Symbols.git",
    "delisted": "https://github.com/YLiu95/delisted-equity-data.git",
    "reference": "https://github.com/Quant-Lodge/ticker-reference-data.git",
}


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", f"--git-dir={repo.resolve()}", *args], check=True,
        capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout


def download(cache: Path, name: str, *, update: bool = False) -> Path:
    """Explicit network operation. Never update a cache during a build."""
    repo = cache / f"{name}.git"
    cache.mkdir(parents=True, exist_ok=True)
    if not repo.exists():
        subprocess.run(["git", "clone", "--bare", REPOSITORIES[name], str(repo)],
                       check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif update:
        git(repo, "fetch", "origin", "+refs/heads/*:refs/heads/*")
    return repo


def pin(repo: Path, end: date) -> str:
    """Pin a commit no later than the requested New York calendar cutoff."""
    refs = git(repo, "log", "--first-parent", "--format=%H %cI").decode().splitlines()
    for line in refs:
        sha, timestamp = line.split(" ", 1)
        if datetime.fromisoformat(timestamp).astimezone(ZoneInfo("America/New_York")).date() <= end:
            return sha
    raise ValueError(f"no source commit available by {end}")


def effective_day(timestamp: str) -> date:
    """A commit after signal close cannot enter that day's Scanner universe."""
    local = datetime.fromisoformat(timestamp).astimezone(ZoneInfo("America/New_York"))
    return local.date() + timedelta(days=local.hour >= 16)


@dataclass(frozen=True)
class Snapshot:
    day: date
    commit: str
    available_at: str
    records: tuple[dict, ...]
    hashes: dict[str, str]
    errors: tuple[str, ...] = ()


class GitObjects:
    """One cat-file process avoids thousands of Windows process launches."""
    def __init__(self, repo: Path):
        self.process = subprocess.Popen(
            ["git", f"--git-dir={repo.resolve()}", "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def read(self, expression: str) -> bytes | None:
        self.process.stdin.write((expression + "\n").encode())
        self.process.stdin.flush()
        header = self.process.stdout.readline().decode().strip().split()
        if header[-1] == "missing":
            return None
        size = int(header[-1])
        payload = self.process.stdout.read(size)
        self.process.stdout.read(1)
        return payload

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=30)


def history(repo: Path, commit: str, start: date, end: date):
    """Yield full per-exchange snapshots in availability order, with hashes.

    Duplicate same-date commits use the last snapshot available before close.
    A predecessor is retained to establish bounded carry on the first date.
    Missing/invalid exchange files remain observable failed snapshots.
    """
    paths = git(repo, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    exchange_paths = {}
    for exchange in ("nasdaq", "nyse", "amex"):
        choices = [p for p in paths if p.startswith(exchange + "/") and
                   "full" in p and p.endswith(".json")]
        if len(choices) != 1:
            raise ValueError(f"ambiguous full snapshot path for {exchange}: {choices}")
        exchange_paths[exchange.upper()] = choices[0]
    lines = git(repo, "log", "--first-parent", "--format=%H %cI", commit,
                "--", *exchange_paths.values()).decode().splitlines()
    dated = {}
    for line in reversed(lines):
        sha, timestamp = line.split(" ", 1)
        day = effective_day(timestamp)
        if day <= end:
            dated[day] = (sha, timestamp)
    before = [d for d in dated if d < start]
    days = sorted(d for d in dated if d >= start or (before and d == max(before)))
    objects = GitObjects(repo)
    try:
        for day in days:
            sha, timestamp = dated[day]
            records, hashes, errors = [], {}, []
            for exchange, path in exchange_paths.items():
                payload = objects.read(f"{sha}:{path}")
                if payload is None:
                    errors.append(f"missing:{exchange}")
                    continue
                hashes[path] = hashlib.sha256(payload).hexdigest()
                try:
                    raw = json.loads(payload)
                    if isinstance(raw, dict):
                        raw = raw.get("data", {}).get("rows", raw.get("rows"))
                    if not isinstance(raw, list) or not raw:
                        raise ValueError("empty or non-list snapshot")
                    seen = set()
                    for item in raw:
                        symbol = str(item.get("symbol", item.get("Symbol", ""))).strip().upper()
                        if not symbol or symbol in seen:
                            raise ValueError(f"blank/duplicate symbol {symbol}")
                        seen.add(symbol)
                        records.append({**item, "symbol": symbol, "exchange": exchange})
                except (ValueError, TypeError, AttributeError) as error:
                    errors.append(f"invalid:{exchange}:{error}")
            yield Snapshot(day, sha, timestamp, tuple(records), hashes, tuple(errors))
    finally:
        objects.close()
