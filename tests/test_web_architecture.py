"""Contracts for the single Web UI and its loopback API."""

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.request import Request, urlopen

import pytest

from radar import local_api


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:4174"


@pytest.fixture
def api(monkeypatch):
    manager = SimpleNamespace(
        store=SimpleNamespace(
            list_scanner_runs=lambda limit: [{"run_id": "scanner-id"}],
            get_run=lambda run_id: {"run_id": run_id, "status": "completed"},
        ),
        launch_queued_scanners=lambda: None,
        queue_scanner=lambda *args, **kwargs: "queued-scanner",
        import_zip=lambda path: SimpleNamespace(
            manifest=SimpleNamespace(id="sample", version="1.0", name="Sample")
        ),
    )
    monkeypatch.setattr(local_api, "lab_manager", lambda: manager)
    monkeypatch.setattr(local_api, "lab_strategies", lambda: [{"id": "sample"}])
    server = ThreadingHTTPServer(("127.0.0.1", 0), local_api.make_handler({ORIGIN}))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(base, path, *, method="GET", data=None, content_type=None):
    headers = {"Origin": ORIGIN}
    if content_type:
        headers["Content-Type"] = content_type
    with urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=3) as response:
        body = response.read()
        return response.status, response.headers, json.loads(body) if body else None


def test_api_health_and_cors(api):
    status, headers, body = request(api, "/health")
    assert status == 200
    assert body["service"] == "stock-radar-api"
    assert headers["Access-Control-Allow-Origin"] == ORIGIN
    status, headers, _ = request(api, "/api/lab/run", method="OPTIONS")
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == ORIGIN


def test_research_and_strategy_routes_remain_available(api):
    assert request(api, "/api/lab/strategies")[2] == [{"id": "sample"}]
    assert request(api, "/api/lab/scanner/runs")[2] == [{"run_id": "scanner-id"}]
    run_id = "00000000-0000-0000-0000-000000000001"
    assert request(api, f"/api/lab/run?id={run_id}")[2]["run_id"] == run_id
    payload = json.dumps({"strategy_id": "sample", "split": "validation"}).encode()
    assert request(api, "/api/lab/scanner/run", method="POST", data=payload,
                   content_type="application/json")[2] == {"run_id": "queued-scanner"}
    assert request(api, "/api/lab/import", method="POST", data=b"sample ZIP",
                   content_type="application/zip")[2]["id"] == "sample"


def test_data_panel_routes(api, monkeypatch):
    launched = []
    monkeypatch.setattr(local_api, "data_status", lambda: {
        "sync": {"state": "succeeded"}, "coverage": [], "settings": {"provider": "Alpaca"}
    })
    monkeypatch.setattr(local_api, "start_daily_sync", lambda: launched.append(True))
    assert request(api, "/api/data/status")[2]["sync"]["state"] == "succeeded"
    assert request(api, "/api/data/sync", method="POST", data=b"{}",
                   content_type="application/json")[2] == {"ok": True}
    assert launched == [True]


def test_single_web_ui_files_and_no_streamlit_imports():
    for name in ("index.html", "lab.html", "app.js", "lab.js"):
        assert (ROOT / "site" / "dist" / name).is_file()
    assert "sync-data" in (ROOT / "site" / "dist" / "index.html").read_text(encoding="utf-8")
    assert "system-config" in (ROOT / "site" / "dist" / "lab.html").read_text(encoding="utf-8")
    for folder in (ROOT / "src", ROOT / "scripts"):
        for path in folder.rglob("*.py"):
            assert "import streamlit" not in path.read_text(encoding="utf-8").lower(), path
    assert not (ROOT / "src" / "radar" / "dashboard.py").exists()
    assert not (ROOT / "src" / "radar" / "strategy_lab_ui.py").exists()
    assert not list((ROOT / "src" / "radar" / "ui").rglob("*.py"))
