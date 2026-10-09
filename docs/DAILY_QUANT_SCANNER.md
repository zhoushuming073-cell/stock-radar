# Latest-session Q1/Q2 Daily Scanner

Use the existing site: **http://127.0.0.1:4174/lab.html#scanner**. The Daily Quant Watchlist card sits above historical Scanner Research. It requires the existing local API on8765; that API is not a second website. Start the normal local-site launcher.

1. Update local Market data when it is stale.
2. Click **Run Daily Scanner**. Work runs in a silent subprocess; the browser polls only job status. No terminal window or broker order is created.
3. View Q1, Q2 or both. Display defaults to20, with10/50/100 options. A shorter valid list is not padded.
4. Expand a row for subscores, reasons and data-quality warnings. **Open** goes to that symbol in the existing market chart.
5. Overlap includes Watch/Wait memberships. It is not a list where both methods necessarily say Qualified.

CLI from repository root (existing virtual environment):

```powershell
.venv/Scripts/python.exe scripts/scan_quant_daily.py --method all --top 20
```

Optional `--asof YYYY-MM-DD` must be a completed exchange session; `--out data/research/watchlist.json` or `.csv` exports privately. Method `q1` or `q2` is supported. No future-outcome labels are needed. Successful daily Market ingestion now invokes the same scanner; `daily_update.py --skip-watchlist` opts out. Scanner failure records its own status and does not falsely mark Market ingestion failed. Existing missed-run scheduling behavior is retained.

GET `/api/research/daily?method=all&top=20` reads the latest persisted snapshot; it does not start a scan. GET `/api/research/daily/status` reports the silent worker. POST `/api/research/daily/run` starts a bounded worker with the existing loopback origin/write checks.

Snapshots: `data/research/daily-quant/<asof>-<content-hash>.json`; latest pointer, worker log and status remain ignored local data. Unchanged inputs reproduce the same snapshot hash. Freshness is evaluated against the exchange calendar each time the snapshot is read; weekends/holidays do not falsely create a new missing session. An unavailable newest session is reported as stale, with its actual last available date.

This is a research watchlist. Qualified is a shape workflow state, not a buy order. Current asset membership, mixed equity classes and uncertified corporate-action coverage are explicitly different from the frozen historical universe.
