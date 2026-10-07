"""Frozen run dependency closure, separate from global database readiness.

The population includes unpriced members and every feature/rank participant.
Declarations are evidence claims, never independent proof of source completeness.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.pit.actions import corporate_actions, TERMINALS
from radar.pit.builder import digest
from radar.pit.features import file_hash

POLICY = "pit-run-closure-v1"
PREFLIGHT = ("Identity", "Membership", "Price", "CorporateAction", "Terminal", "LEAN Input")


def iso(value) -> str:
    return str(pd.Timestamp(value).date())


def freeze_file(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": file_hash(path)}


def verify_dependencies(manifest: dict, expected: str | None = None) -> None:
    payload = {k: v for k, v in manifest.items() if k != "dependency_sha256"}
    actual = digest(payload)
    if actual != manifest.get("dependency_sha256") or (expected is not None and actual != expected):
        raise ValueError("PIT run dependency hash changed")
    for item in manifest["files"].values():
        if file_hash(Path(item["path"])) != item["sha256"]:
            raise ValueError("PIT run dependency source changed: " + item["path"])


def save_dependency(root: Path, manifest: dict) -> dict:
    """Content-addressed artifact; no overwriting a prior certification."""
    verify_dependencies(manifest)
    path = root / "data/pit/run-dependencies" / (manifest["dependency_sha256"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False)
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError("dependency artifact collision")
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return {"path": str(path.resolve()), "sha256": file_hash(path),
            "dependency_sha256": manifest["dependency_sha256"]}


def load_dependency(reference: dict) -> dict:
    path = Path(reference["path"])
    if file_hash(path) != reference["sha256"]:
        raise ValueError("queued PIT dependency manifest changed")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    verify_dependencies(manifest, reference["dependency_sha256"])
    return manifest


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def build_dependency(master, database: Path, sessions, frame: pd.DataFrame,
                     signals: list[dict], metadata: dict, *, catalog: dict | None = None,
                     certificates: dict | None = None, files: dict | None = None,
                     warmup_sessions: int = 126, open_positions: list[dict] | None = None) -> dict:
    """Compute full closure before any native orders; no outcome-based pruning.

    Execution ranges conservatively include every possible position up to its
    maximum exit session. Shorter realized lifetimes do not relax frozen inputs.
    """
    days = [iso(d) for d in sessions]
    if not days or days != sorted(set(days)) or warmup_sessions < 1:
        raise ValueError("invalid dependency calendar/warm-up")
    start, end, evaluation = metadata["window"]
    if not start <= end <= evaluation or not all(x in days for x in (start, end, evaluation)):
        raise ValueError("dependency interval outside calendar")
    covered = [d for d in days if start <= d <= evaluation]
    signal_days = [d for d in covered if d <= end]
    master.validate_coverage(pd.to_datetime(signal_days))
    for day in covered:
        master.observed_on(day)  # Evaluation can legitimately have no remaining stock members.
    certificates = certificates or {}
    files = dict(files or {})
    for path in (Path(database), master.csv_path, master.manifest_path):
        key = str(path.resolve())
        frozen = freeze_file(path)
        if key in files and files[key] != frozen:
            raise ValueError('dependency source changed before closure')
        files[key] = frozen
    actions = corporate_actions(catalog or {"events": [], "sources": {}}, certificates.get("actions"))
    by_id, population = {}, []
    participant = {}
    for row in frame.reset_index(drop=True).to_dict("records"):
        if start <= iso(row["date"]) <= end:
            participant.setdefault(iso(row["date"]), set()).add(str(row["security_id"]))
    # Entire eligible population, not selected or priced securities alone.
    for day in signal_days:
        members = master.eligible_on(day)
        ids = sorted(set(members.security_id.astype(str)))
        population.append({"date": day, "security_ids": ids,
                           "feature_evaluation_ids": sorted(participant.get(day, set()))})
        for identity in ids:
            by_id.setdefault(identity, {"membership": set(), "required": set(), "execution": set()})["membership"].add(day)
    signals = [dict(row) for row in signals]
    for signal in signals:
        day, symbol = signal["signal_date"], signal["symbol"]
        mapping = master.eligible_on(day)
        match = mapping.loc[mapping.symbol.eq(symbol)]
        if len(match) != 1 or day not in signal_days:
            raise ValueError("signal is not an unambiguous PIT member")
        identity = str(match.iloc[0].security_id)
        if signal.get("security_id", identity) != identity:
            raise ValueError("signal security identity mismatch")
        signal["security_id"] = identity
        index = covered.index(day)
        hold = metadata["resolved_config"]["values"]["execution"]["exit"]["max_holding_sessions"]
        through = len(covered) if hold is None else min(len(covered), index + hold + 2)
        by_id[identity]["execution"].update(covered[index + 1:through])
    for position in open_positions or []:
        identity = position["security_id"]
        by_id.setdefault(identity, {"membership": set(), "required": set(), "execution": set()})[
            "execution"].update(d for d in covered if d >= position["entry_date"])
    dependencies = []
    mapping_groups = dict(tuple(master.frame.groupby("security_id", sort=False)))
    day_index = {day: i for i, day in enumerate(days)}
    for identity, dependency in sorted(by_id.items()):
        mappings = mapping_groups[identity]
        listings = mappings.listing_date.dropna()
        listing = iso(listings.min()) if len(listings) else None
        for day in dependency["membership"]:
            index = day_index[day]
            dependency["required"].update(d for d in days[max(0, index - warmup_sessions + 1):index + 1]
                                          if listing is None or d >= listing)
        dependency["required"].update(dependency["execution"])
        relevant = [a for a in actions if a["security_id"] == identity
                    and min(dependency["required"]) <= a["effective_date"] <= max(dependency["required"])]
        # Only an economic terminal with approved terms may remove nonexistent
        # post-cessation market sessions. A snapshot end never removes them.
        terminal = [a for a in relevant if a["handling_mode"] == "native_cash_entitlement"]
        if terminal:
            if len(terminal) != 1:
                raise ValueError("ambiguous terminal settlement")
            last = terminal[0]["review"]["last_tradable_session"]
            dependency["required"] = {d for d in dependency["required"] if d <= last}
        required = sorted(dependency["required"])
        mappings = mappings.loc[mappings.valid_from.le(pd.Timestamp(max(required)))
                                & (mappings.valid_to.isna() | mappings.valid_to.ge(pd.Timestamp(min(required))))]
        record = {"security_id": identity, "symbols": sorted(set(mappings.symbol)),
                  "membership_sessions": sorted(dependency["membership"]),
                  "execution_sessions": sorted(dependency["execution"]), "required_sessions": required,
                  "mappings": _records(mappings), "actions": relevant,
                  "listing_date": listing,
                  "warmup_calendar_shortfall": (max(0, warmup_sessions - (days.index(min(dependency["membership"])) + 1))
                                                if dependency["membership"] and listing is None else 0),
                  "certificate": certificates.get("securities", {}).get(identity, {})}
        dependencies.append(record)
    benchmark_days = days[max(0, days.index(start) - 200):days.index(evaluation) + 1]
    with duckdb.connect(str(database), read_only=True) as connection:
        bars = connection.execute("""SELECT date,symbol,security_id,open,high,low,close,volume,
            provider,feed,adjustment FROM daily_bars WHERE date BETWEEN ? AND ?""",
            [min([benchmark_days[0], *[d for r in dependencies for d in r["required_sessions"]]]), evaluation]).df()
    bars["date"] = pd.to_datetime(bars.date).dt.strftime("%Y-%m-%d")
    invalid = (~np.isfinite(bars[["open", "high", "low", "close", "volume"]].astype(float)).all(axis=1)
               | bars.low.le(0) | bars.volume.lt(0) | bars.volume.ne(np.floor(bars.volume))
               | ~bars.open.between(bars.low, bars.high) | ~bars.close.between(bars.low, bars.high))
    invalid_pairs = set(zip(bars.loc[invalid, "date"], bars.loc[invalid, "security_id"]))
    duplicate_pairs = set(zip(bars.loc[bars.duplicated(["security_id", "date"], keep=False)
                                      & bars.security_id.notna(), "date"],
                              bars.loc[bars.duplicated(["security_id", "date"], keep=False)
                                      & bars.security_id.notna(), "security_id"]))
    observed = set(zip(bars.date, bars.security_id)) - invalid_pairs - duplicate_pairs
    bar_groups = dict(tuple(bars.loc[bars.security_id.notna()].groupby("security_id", sort=False)))
    for record in dependencies:
        identity = record["security_id"]
        required = record["required_sessions"]
        record["missing_sessions"] = [d for d in required if (d, identity) not in observed]
        group = bar_groups.get(identity, bars.iloc[0:0])
        subset = group.loc[group.date.isin(required)]
        record["price_rows_sha256"] = digest(_records(subset.sort_values(["date", "symbol"])))
        record["price_sources"] = _records(subset[["provider", "feed", "adjustment"]].drop_duplicates())
        mismatch = []
        for bar in subset.itertuples(index=False):
            mapped = [m for m in record["mappings"] if m["symbol"] == bar.symbol
                      and iso(m["valid_from"]) <= bar.date <= (iso(m["valid_to"]) if m["valid_to"] else "9999-12-31")]
            if len(mapped) != 1:
                mismatch.append(bar.date)
        record["price_mapping_mismatch"] = mismatch
    benchmark = []
    # SPY/QQQ causal context and SPY MA200 guard require independent history.
    for symbol in ("SPY", "QQQ"):
        subset = bars.loc[bars.symbol.eq(symbol) & bars.date.isin(benchmark_days)]
        bad_days = set(subset.loc[invalid.loc[subset.index], 'date'])
        bad_days.update(subset.loc[subset.duplicated('date', keep=False), 'date'])
        benchmark.append({"symbol": symbol, "required_sessions": benchmark_days,
                          "missing_sessions": sorted(set(benchmark_days) - (set(subset.date) - bad_days)),
                          "price_sources": _records(subset[["provider", "feed", "adjustment"]].drop_duplicates()),
                          "price_rows_sha256": digest(_records(subset.sort_values("date"))),
                          "certificate": certificates.get("benchmarks", {}).get(symbol, {})})
    manifest = {"policy": POLICY, "universe_version": master.manifest["source_version"],
                "universe_fingerprint": master.fingerprint, "window": [start, end, evaluation],
                "sessions": covered, "calendar": days, "warmup_sessions": warmup_sessions,
                "strategy_id": metadata["strategy_id"], "strategy_version": metadata["strategy_version"],
                "config_hash": metadata["config_hash"], "resolved_config_hash": metadata["resolved_config_hash"],
                "signal_source_scanner": metadata.get("source_scanner_run_id"),
                "signals": signals, "signal_sha256": digest(signals), "population": population,
                "dependencies": dependencies, "benchmarks": benchmark,
                "population_attestation": certificates.get("population", {}),
                "source_attested_membership": master.manifest.get("coverage_complete") is True,
                "files": files, "prior_open_positions": open_positions or [],
                "data_origin": "Stock Radar generated PIT execution dataset"}
    manifest["dependency_sha256"] = digest(manifest)
    return manifest


def readiness(manifest: dict) -> dict:
    """All preflight gates must PASS; execution/reconciliation remain NOT_RUN."""
    verify_dependencies(manifest)
    reasons = {key: [] for key in PREFLIGHT}
    frozen_hashes = {value["sha256"] for value in manifest["files"].values()}
    def bound_claim(claim):
        hashes = claim.get("source_hashes", [])
        return bool(hashes) and set(hashes) <= frozen_hashes
    certificate = manifest["population_attestation"]
    if not (manifest["source_attested_membership"] or (
            certificate.get("verified") is True and certificate.get("start", "9999") <= manifest["window"][0]
            and certificate.get("end", "0000") >= manifest["window"][2] and bound_claim(certificate))):
        reasons["Membership"].append("full run population lacks source-attested historical completeness")
    total, missing = 0, 0
    native_roots = set()
    selected_ids = {s['security_id'] for s in manifest['signals']}
    if manifest['prior_open_positions']:
        reasons['LEAN Input'].append('native prior-holdings import is unsupported; a fresh cash-funded portfolio is required')
    for row in manifest["dependencies"]:
        identity = row["security_id"]
        mappings = row["mappings"]
        if identity in selected_ids:
            root = sorted(mappings,key=lambda m:m['valid_from'])[0]['symbol']
            if root in native_roots or root in {'SPY','QQQ'}:
                reasons['LEAN Input'].append(identity + ': native map root collision needs a validated SID alias adapter')
            native_roots.add(root)
        if not all(m.get("resolution_status") == "verified" and m.get("classification_confidence") == "verified"
                   and m.get("issuer_id") and m.get("share_class") and m.get("identity_evidence_hash")
                   and m.get("identity_evidence_hash") in frozen_hashes
                   and m.get("exchange") in {"NASDAQ", "NYSE", "AMEX"} and m.get("security_type") == "common"
                   for m in mappings):
            reasons["Identity"].append(identity + ": unresolved issuer/class/exchange/type or reuse")
        cert = row["certificate"]
        if not (cert.get("verified") is True and cert.get("identity_bound") is True
                and cert.get("price_basis") == "raw" and cert.get("feature_basis") == "causal_split_only"
                and cert.get("source_version") and cert.get("license") and bound_claim(cert)
                and cert.get("start", "9999") <= min(row["required_sessions"])
                and cert.get("end", "0000") >= max(row["required_sessions"])):
            reasons["Price"].append(identity + ": raw/source/license/feature basis not certified for required scope")
        if row["missing_sessions"]:
            reasons["Price"].append(f"{identity}: {len(row['missing_sessions'])} required sessions missing (first {row['missing_sessions'][0]})")
        if row["price_mapping_mismatch"]:
            reasons["Identity"].append(identity + ": price dated mapping mismatch")
        adjustments = {s['adjustment'] for s in row['price_sources']}
        raw_equivalent = (cert.get('raw_equivalent_no_splits') is True
                          and not any(a['event_type'] in {'split', 'reverse_split'} for a in row['actions']))
        if not adjustments <= {'raw', 'none', 'unadjusted'} and not (adjustments <= {'split'} and raw_equivalent):
            reasons['Price'].append(identity + ': stored adjusted prices are not certified raw execution inputs')
        if row["warmup_calendar_shortfall"]:
            reasons["Price"].append(identity + ": unknown pre-calendar warm-up")
        if cert.get("action_coverage_verified") is not True:
            reasons["CorporateAction"].append(identity + ": complete action coverage not attested for required scope")
        for action in row["actions"]:
            if action["confidence"] != "verified" or action["handling_mode"] == "blocked":
                gate = "Terminal" if action["event_type"] in TERMINALS else "CorporateAction"
                reasons[gate].append(action["event_id"] + ": unsupported handling/economics")
            # Dividend cash return is not certified by a split-only source.
        total += len(row["required_sessions"])
        missing += len(row["missing_sessions"])
    for benchmark in manifest["benchmarks"]:
        cert = benchmark["certificate"]
        if benchmark["missing_sessions"] or not (cert.get("verified") is True and bound_claim(cert)
                                                  and cert.get("identity_bound") is True and cert.get("source_version")
                                                  and cert.get("license") and cert.get("price_basis") == "raw"
                                                  and cert.get("feature_basis") == "causal_split_only"
                                                  and cert.get("start", "9999") <= min(benchmark['required_sessions'])
                                                  and cert.get("end", "0000") >= max(benchmark['required_sessions'])
                                                  and cert.get("action_coverage_verified") is True
                                                  and {s['adjustment'] for s in benchmark['price_sources']}
                                                      <= {'raw', 'none', 'unadjusted'}):
            reasons["Price"].append(benchmark["symbol"] + ": benchmark/calendar provenance or sessions incomplete")
        total += len(benchmark["required_sessions"])
        missing += len(benchmark["missing_sessions"])
    if reasons["Identity"] or reasons["Price"] or reasons["CorporateAction"] or reasons["Terminal"]:
        reasons["LEAN Input"].append("map/factor/raw-price/action inputs cannot be safely generated")
    gates = {key: "FAIL" if reasons[key] else "PASS" for key in PREFLIGHT}
    ready = all(x == "PASS" for x in gates.values())
    return {"scope": "run", "policy": POLICY, "dependency_sha256": manifest["dependency_sha256"],
            "formal_pit_ready": ready, "preflight_ready": ready,
            "research_validity": "formal_pit_source_dependent" if ready else "retrospective_pit_blocked",
            "scorecard": {**gates, "LEAN Native Execution": "NOT_RUN", "Result Reconciliation": "NOT_RUN"},
            "reasons_by_gate": reasons, "required_prices": total, "missing_prices": missing,
            "price_coverage": (total - missing) / total if total else None,
            "security_count": len(manifest["dependencies"]), "signals": len(manifest["signals"])}


def require_ready(manifest: dict) -> dict:
    report = readiness(manifest)
    if not report["preflight_ready"]:
        failures = {key: len(value) for key, value in report["reasons_by_gate"].items() if value}
        raise ValueError("LEAN PIT run BLOCKED: " + json.dumps(failures, sort_keys=True))
    return report


def local_dependency(root: Path, master, metadata: dict, frame, sessions, signals) -> dict:
    """Bind physical DBs, review declarations and every referenced raw evidence file."""
    from radar.lab.data import pit_database_for
    from radar.pit.trust import load_catalog
    root = Path(root)
    source = root / "data/phase2-research.duckdb"
    database = pit_database_for(source, master)
    paths = [master.csv_path, master.manifest_path, master.csv_path.with_name("security-master-feature-store.json"),
             source, database, root / "config/research.yaml"]
    external = master.feature_store.get("external_prices")
    if external:
        paths.extend([Path(external["database"]), Path(external["database"]).with_suffix(".manifest.json")])
    catalog_path = root / "config/pit_trust_evidence.json"
    catalog = load_catalog(catalog_path, root / "data/pit/raw/official-evidence") if catalog_path.exists() else {"events": [], "sources": {}}
    if catalog_path.exists():
        paths.append(catalog_path)
        paths.extend(root / "data/pit/raw/official-evidence" / (s["raw_sha256"] + ".raw") for s in catalog["sources"].values())
    review = root / "data/pit/run-certification.json"
    certificates = json.loads(review.read_text(encoding="utf-8")) if review.exists() else {}
    action_reviews = root / 'config/pit_execution_action_reviews.json'
    if action_reviews.exists():
        declarations = json.loads(action_reviews.read_text(encoding='utf-8'))
        for key, value in certificates.get('actions', {}).items():
            if key in declarations and declarations[key] != value:
                raise ValueError('conflicting run/global action review')
            declarations[key] = value
        certificates['actions'] = declarations
        paths.append(action_reviews)
    if review.exists():
        paths.append(review)
        for item in certificates.get("artifacts", []):
            path = Path(item["path"])
            path = path if path.is_absolute() else root / path
            if file_hash(path) != item["sha256"]:
                raise ValueError("run certification raw evidence changed")
            paths.append(path)
    # Recheck the external licensed acceptance inputs, even though the feature
    # store's physical byte lock is independent of raw evidence/license locks.
    price_review = root / "config/pit_public_price_review.json"
    if price_review.exists():
        declaration = json.loads(price_review.read_text(encoding="utf-8"))
        paths.append(price_review)
        raw = root / "data/pit/raw/public-prices"
        license_path = raw / (declaration['license_raw_sha256'] + '.raw')
        adjustment_path = raw / declaration['adjustment_evidence_file']
        if (file_hash(license_path) != declaration['license_raw_sha256']
                or file_hash(adjustment_path) != declaration['adjustment_evidence_sha256']):
            raise ValueError('external accepted license/adjustment evidence changed')
        paths.extend([license_path, adjustment_path])
        for item in declaration["series"]:
            path = raw / item["file"]
            paths.append(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            if digest(payload) != item["payload_sha256"]:
                raise ValueError("external accepted payload changed")
            for query in payload['queries']:
                path = raw / (query['raw_sha256'] + '.raw')
                if file_hash(path) != query['raw_sha256']:
                    raise ValueError('external accepted SQL response changed')
                paths.append(path)
    files = {str(path.resolve()): freeze_file(path) for path in paths}
    for key, source_doc in catalog["sources"].items():
        path = root / "data/pit/raw/official-evidence" / (source_doc["raw_sha256"] + ".raw")
        if files[str(path.resolve())]["sha256"] != source_doc["raw_sha256"]:
            raise ValueError("official action evidence changed: " + key)
    return build_dependency(master, database, sessions, frame, signals, metadata,
                            catalog=catalog, certificates=certificates, files=files)
