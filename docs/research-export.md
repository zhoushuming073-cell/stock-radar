# Research export bundles

Open the existing local Strategy Lab at `http://127.0.0.1:4174/lab.html#experiments`.
The **Research Export Bundle** card selects the latest three complete v3
strategy groups by default. Adjust the checkboxes, name the study, and choose
**Export selected runs**. A ZIP is saved under `data/research-exports/`; the
download link and saved bundle history appear in the same card. This does not
publish market data or Run evidence to GitHub or Sites.

Each bundle contains:

- `manifest.json`: exact Run IDs, comparison groups and research warnings.
- `experiment_summary.csv`: one row per selected Run, including failed attempts.
- `runs/<id>/run.json` and `metrics.json`: original Run provenance and results.
- Completed Scanner Runs: all candidate rows in CSV and Parquet, including
  causal features, diagnostics, probabilities, forward labels and censoring.
- Completed Backtest Runs: equity, trades and events in CSV and Parquet.
- `comparisons/`: Top-K event metrics, selected candidate overlap for compatible
  Scanner definitions, regime breakdown and Backtest risk summary.
- `provenance/hashes.json`: SHA-256 for every generated evidence file (excluding
  the hash and environment files themselves).

The exporter uses the project's existing [Apache Arrow/PyArrow](https://github.com/apache/arrow)
dependency for Parquet. It verifies completed Scanner snapshots against the
Run store's artifact hashes before export and checks candidate row counts in
both CSV and Parquet. Run records in SQLite are read only; exported bundles
do not mutate or reinterpret them. A comparison group is defined by feature,
market feature, dataset, universe, split and evaluation or execution settings.
Do not average metrics across groups. Current-snapshot survivorship risk,
uncommitted source states and previously viewed historical Test runs are
recorded as audit warnings.

Research ZIPs and their local history index are ignored by Git. To verify a
download, recompute SHA-256 of each archived path in `provenance/hashes.json`.
The ZIP checksum is also stored in its adjacent local `.json` index.
