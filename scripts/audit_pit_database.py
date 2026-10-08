"""Reproducible database scorecard and seeded survivorship audit.

All percentages expose denominators. Scope is observed historical intervals;
unobserved securities and missing legal delisting evidence are not invented.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from radar.lab.universe import LocalSecurityMaster
from radar.pit.builder import digest
from radar.pit.database import HistoricalDatabase, fixed_sample
from radar.pit.features import file_hash


def ratio(numerator, denominator):
    return {"numerator": int(numerator), "denominator": int(denominator),
            "pct": round(100 * numerator / denominator, 4) if denominator else None}


def audit(root, directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    rules = json.loads((directory / "rules.json").read_text(encoding="utf-8"))
    with HistoricalDatabase(directory) as db:
        c = db.connection
        scalar = lambda query: c.execute(query).fetchone()[0]
        common = "security_type='common'"
        ids = c.execute("SELECT * FROM identity_quality").df()
        common_ids = ids.loc[ids.security_type == "common"]
        stats = {"source_version": manifest["source_version"], "database_sha256": manifest["database_sha256"],
                 "scope": manifest["scope"], "coverage": [manifest["coverage_start"], manifest["coverage_end"]],
                 "counts": manifest["counts"], "sessions": manifest["sessions"], "rules_sha256": file_hash(directory / "rules.json")}
        stats["identity"] = {"all_ids": len(ids), "common_ids": len(common_ids),
            "all_levels": ids.level.value_counts().to_dict(), "common_levels": common_ids.level.value_counts().to_dict(),
            "common_tier2_pass": ratio(sum(common_ids.level == "A"), len(common_ids)),
            "common_unresolved": ratio(sum(common_ids.level != "A"), len(common_ids)),
            "ordinary_current_stable": ratio(sum((common_ids.level == "A") & ~common_ids.disappeared), sum(~common_ids.disappeared))}
        totals = c.execute("""SELECT count(*),count(*) FILTER(WHERE membership_status='confirmed_member'),
            count(*) FILTER(WHERE membership_status='probable_member'),count(*) FILTER(WHERE membership_status='unknown'),
            count(*) FILTER(WHERE evidence_conflict),count(*) FILTER(WHERE membership_status='confirmed_non_member')
            FROM daily_population WHERE security_type='common'""").fetchone()
        stats["membership"] = {name: ratio(n, totals[0]) for name, n in zip(
            ["confirmed", "probable", "unknown", "conflict", "confirmed_non_member"], totals[1:])}
        stats["membership"]["supported"] = ratio(totals[1] + totals[2], totals[0])
        stats["membership"]["denominator_scope"] = "observed common candidate member-days; absent candidates unknown, not counted as nonmembers"
        daily = c.execute("SELECT * FROM daily_scorecard").df()
        stats["population"] = {"minimum": int(daily.observed_population.min()), "maximum": int(daily.observed_population.max()),
                               "median": float(daily.observed_population.median()), "common_minimum": int(daily.common_population.min()),
                               "common_maximum": int(daily.common_population.max()), "sessions_with_rows": len(daily)}
        daily["change"] = daily.observed_population.diff()
        stats["population"]["large_daily_changes"] = daily.loc[daily.change.abs() > 500,
            ["date", "observed_population", "change"]].astype(str).to_dict("records")
        # Fixed hash sampling from sessions, not hand-selected dates.
        replay = []
        days = [str(v)[:10] for v in daily.date]
        for year in range(2021, 2027):
            selected = fixed_sample([v for v in days if v.startswith(str(year))], 2, rules["audit_seed"] + "|replay")
            for day in selected:
                f = db.population_on(day)
                uncertainty=db.uncertainty_on(day)
                later = set(ids.loc[ids.disappeared, "security_id"])
                replay.append({"date": day, "population": len(f), "common": int(sum(f.security_type == "common")),
                               "membership_unknown": int(sum(f.membership_status == "unknown")),
                               "later_disappeared": int(f.security_id.isin(later).sum()), "exchange": f.exchange.value_counts().to_dict(),
                               "absent_prior_observed_unknown_ids":len(uncertainty),
                               "absent_common_unknown_ids":int(sum(uncertainty.security_type=='common'))})
        stats["replay"] = replay
        future_rows = scalar("""SELECT count(*) FROM daily_population p JOIN ticker_episode m USING(interval_id)
            WHERE p.date<m.valid_from OR p.date>m.valid_to OR (m.listing_date IS NOT NULL AND p.date<m.listing_date)""")
        reuse_rows = scalar("""SELECT count(*) FROM accepted_price p LEFT JOIN ticker_episode m
            ON p.security_id=m.security_id AND p.symbol=m.symbol AND p.date BETWEEN m.valid_from AND m.valid_to
            WHERE m.security_id IS NULL""")
        stats["causality"] = {"future_listing_or_interval_leakage_rows": future_rows, "accepted_price_cross_identity_rows": reuse_rows,
            "limitations": "Zero detected against installed boundaries only; missing IPO/class evidence cannot certify zero real-world leakage",
            "reused_or_fragmented_tickers": scalar("SELECT count(*) FROM (SELECT symbol FROM ticker_episode GROUP BY symbol HAVING count(DISTINCT security_id)>1)"),
            "common_ids_with_reuse_or_fragmentation": int(sum(common_ids.ticker_episode_count > 1))}
        gone = common_ids.loc[common_ids.disappeared]
        retained = scalar("""SELECT count(DISTINCT q.security_id) FROM identity_quality q JOIN daily_population p USING(security_id)
            WHERE q.disappeared AND q.security_type='common'""")
        stats["disappeared"] = {"common_ids": len(gone), "history_retained": ratio(retained, len(gone)),
                                "unexplained_end_ids": int(sum(gone.official_terminal == False)),
                                "verified_terminal_ids": int(sum(ids.official_terminal))}
        required = totals[0]
        prices = {}
        for label, table in (("raw_ticker_date_availability", "raw_price_hit"), ("legacy_bounded_availability", "observed_price"),
                             ("accepted_raw", "accepted_price"), ("feature_presence", "feature_presence")):
            n = scalar(f"""SELECT count(*) FROM daily_population p WHERE p.security_type='common' AND EXISTS
                (SELECT 1 FROM {table} a WHERE a.security_id=p.security_id AND a.symbol=p.symbol AND a.date=p.date)""")
            prices[label] = ratio(n, required)
        conflict_ids = scalar("SELECT count(DISTINCT security_id) FROM price_conflict")
        prices["comparison_conflict_ids"] = conflict_ids
        prices['any_bounded_basis_availability']=ratio(scalar("""SELECT count(*) FROM daily_population p
            WHERE p.security_type='common' AND (EXISTS(SELECT 1 FROM observed_price a
            WHERE a.security_id=p.security_id AND a.symbol=p.symbol AND a.date=p.date)
            OR EXISTS(SELECT 1 FROM accepted_price a WHERE a.security_id=p.security_id AND a.symbol=p.symbol AND a.date=p.date))"""),required)
        prices["accepted_rows_with_comparison_conflict"] = scalar("SELECT count(*) FROM accepted_price WHERE conflict_state LIKE 'comparison_conflict%'")
        prices["conflict_free_accepted_raw"] = ratio(scalar("""SELECT count(*) FROM daily_population p WHERE p.security_type='common' AND EXISTS
            (SELECT 1 FROM accepted_price a WHERE a.security_id=p.security_id AND a.symbol=p.symbol AND a.date=p.date
                AND a.conflict_state NOT LIKE 'comparison_conflict%')"""), required)
        prices["denominator_scope"] = "all observed common member-days across 2021-2026; no liquidity/strategy filter"
        stats["price"] = prices
        dn = scalar("""SELECT count(*) FROM daily_population p JOIN identity_quality q USING(security_id)
            WHERE q.disappeared AND p.security_type='common'""")
        stats["delisted_price"] = {}
        for label, table in (("disappeared_legacy_bounded", "observed_price"), ("disappeared_accepted_raw", "accepted_price")):
            n = scalar(f"""SELECT count(*) FROM daily_population p JOIN identity_quality q USING(security_id)
                WHERE q.disappeared AND p.security_type='common' AND EXISTS
                (SELECT 1 FROM {table} a WHERE a.security_id=p.security_id AND a.symbol=p.symbol AND a.date=p.date)""")
            stats["delisted_price"][label] = ratio(n, dn)
        event_scope = "FROM lifecycle_event e JOIN identity_quality q USING(security_id) WHERE q.security_type='common'"
        events = c.execute("SELECT event_type,confidence,count(*) AS n " + event_scope + " GROUP BY 1,2").df()
        material = scalar("SELECT count(*) " + event_scope + " AND event_type NOT IN ('listing','new_observation')")
        resolved = scalar("SELECT count(*) " + event_scope + " AND confidence='verified' AND event_type NOT IN ('listing','new_observation')")
        stats["lifecycle"] = {"detected_material_event_records": material, "resolved": ratio(resolved, material),
            "unresolved": material - resolved, "by_type": events.to_dict("records"),
            "terminal_economics_enabled": scalar("SELECT count(*) FROM lifecycle_event WHERE economics_enabled"),
            "notes": "common-candidate event records include observation-end suspicions; not legal delisting counts; verified event != verified cash settlement"}
        # Verified exchange-listed cessation (including completed M&A) is a
        # research definition, not a claim of parsed legal Form-25 effect.
        # Unexplained directory ends cannot pad this stratum.
        strata = {
            "active_common": list(common_ids.loc[~common_ids.disappeared, "security_id"]),
            "verified_listing_cessation": [r[0] for r in c.execute("SELECT DISTINCT security_id FROM lifecycle_event WHERE confidence='verified' AND event_type IN ('trading_suspension','delisting','termination','equity_cancellation','merger')").fetchall()],
            "verified_rename": [r[0] for r in c.execute("SELECT DISTINCT security_id FROM lifecycle_event WHERE confidence='verified' AND event_type='ticker_change'").fetchall()],
            "verified_merger_acquisition": [r[0] for r in c.execute("SELECT DISTINCT security_id FROM lifecycle_event WHERE confidence='verified' AND event_type IN ('merger','acquisition','cash_acquisition','stock_conversion')").fetchall()],
            "common_reuse_identity_risk": list(common_ids.loc[common_ids.level == "C", "security_id"]),
        }
        samples = []
        stratum_report = {}
        for name, population in strata.items():
            selected = fixed_sample(population, rules["sample_per_stratum"], rules["audit_seed"] + "|" + name)
            stratum_report[name] = {"eligible": len(set(population)), "selected": len(selected),
                                   "shortfall": max(0, rules["sample_per_stratum"] - len(selected)), "ids_sha256": digest(selected)}
            for sid in selected:
                q = ids.loc[ids.security_id == sid].iloc[0]
                r = c.execute("""SELECT min(date),max(date),count(*),count(*) FILTER(WHERE eligible) FROM daily_population WHERE security_id=?""", [sid]).fetchone()
                p = c.execute("SELECT count(DISTINCT date) FROM (SELECT date FROM observed_price WHERE security_id=? UNION SELECT date FROM accepted_price WHERE security_id=?)", [sid,sid]).fetchone()[0]
                a = c.execute("SELECT count(*) FROM accepted_price WHERE security_id=?", [sid]).fetchone()[0]
                f = c.execute("SELECT count(*),count(*) FILTER(WHERE tradability_pass) FROM feature_presence WHERE security_id=?", [sid]).fetchone()
                ev = c.execute("SELECT event_type,effective_date,confidence FROM lifecycle_event WHERE security_id=? ORDER BY effective_date", [sid]).fetchall()
                intervals = c.execute("SELECT symbol,valid_from,valid_to,exchange,security_type FROM ticker_episode WHERE security_id=? ORDER BY valid_from", [sid]).fetchall()
                samples.append({"stratum": name, "security_id": sid, "first_appearance": str(r[0]), "last_appearance": str(r[1]),
                    "population_days": r[2], "scanner_eligible_days": r[3], "issuer_ciks": q.ciks,
                    "historical_price_rows": p, "accepted_raw_rows": a, "feature_rows": f[0], "tradability_pass_rows": f[1],
                    "intervals": [[str(v) for v in row] for row in intervals], "events": [[str(v) for v in row] for row in ev],
                    "level": q.level, "history_retention_pass": bool(r[2] > 0),
                    "research_complete": bool(r[2] > 0 and a > 0 and f[0] > 0 and q.level == "A")})
        stats["survivorship_audit"] = {"seed": rules["audit_seed"], "strata": stratum_report,
            "sample_records": len(samples), "history_retention_pass": ratio(sum(v["history_retention_pass"] for v in samples), len(samples)),
            "research_complete": ratio(sum(v["research_complete"] for v in samples), len(samples)),
            "rows_sha256": digest(samples), "shortfalls_are_not_fabricated": True}
        terminal_ids = [r[0] for r in c.execute("SELECT DISTINCT security_id FROM lifecycle_event WHERE confidence='verified' AND event_type IN ('trading_suspension','delisting','termination','merger')").fetchall()]
        survival = []
        for sid in terminal_ids:
            latest = c.execute("SELECT max(date) FROM daily_population WHERE security_id=? AND eligible", [sid]).fetchone()[0]
            if latest:
                frame = db.population_on(latest)
                original = LocalSecurityMaster(root / "data/security-master.csv", root / "data/security-master-manifest.json")
                old = original.eligible_on(pd.Timestamp(latest))
                native = sid in set(old.security_id)
                price = c.execute("SELECT count(DISTINCT date) FROM (SELECT date FROM observed_price WHERE security_id=? AND date<=? UNION SELECT date FROM accepted_price WHERE security_id=? AND date<=?)", [sid, latest,sid,latest]).fetchone()[0]
                features = c.execute("SELECT count(*) FROM feature_presence WHERE security_id=? AND date<=?", [sid, latest]).fetchone()[0]
                survival.append({"security_id": sid, "last_eligible_session": str(latest), "membership": sid in set(frame.security_id),
                    "native_scanner_mapping": native, "bounded_price_rows": price, "feature_rows": features,
                    "pass": bool(native and price > 0 and features > 0)})
        stats["delisted_survival"] = {"cases": survival, "passed": ratio(sum(v["pass"] for v in survival), len(survival)),
            "scope": "verified cessation/M&A; scanner eligibility is mapping eligibility, not an asserted profitable signal"}
        reasons = c.execute("""SELECT reason,count(DISTINCT security_id) AS ids FROM identity_lifecycle_review_queue
            WHERE scope='common' GROUP BY reason ORDER BY ids DESC""").fetchall()
        stats["review_queue"] = {"common_reason_counts": dict(reasons),
            "common_review_ids": scalar("SELECT count(DISTINCT security_id) FROM identity_lifecycle_review_queue WHERE scope='common'"),
            "other_class_review_ids": scalar("SELECT count(DISTINCT security_id) FROM identity_lifecycle_review_queue WHERE scope='other_class'"),
            "no_manual_whole_market_review": True}
        checks = {
            "membership_supported": stats["membership"]["supported"]["pct"] >= rules["tier2"]["confirmed_or_probable_member_days_pct"],
            "identity": stats["identity"]["common_tier2_pass"]["pct"] >= rules["tier2"]["identity_A_common_episode_pct"],
            "accepted_raw_prices": stats["price"]["accepted_raw"]["pct"] >= rules["tier2"]["accepted_raw_common_member_days_pct"],
            "material_events": (stats["lifecycle"]["resolved"]["pct"] or 0) >= rules["tier2"]["resolved_detected_material_events_pct"],
            "disappeared_retention": stats["disappeared"]["history_retained"]["pct"] == 100,
            "future_leakage": future_rows == 0, "reuse_isolation": reuse_rows == 0,
            "confirmed_terminal_sample": len(strata["verified_listing_cessation"]) >= rules["tier2"]["minimum_confirmed_terminal_sample"],
        }
        stats["tier"] = {"current": "Tier 2 Research-Grade PIT" if all(checks.values()) else "Tier 1 Exploratory PIT",
            "tier2_checks": checks, "criteria_met": ratio(sum(checks.values()), len(checks)),
            "maintenance": all(checks.values()), "architecture_contract_tests_required": 18,
            "composite_completion": "not reported: unlike denominators cannot support a meaningful overall completion percentage"}
        daily.to_csv(directory / "daily-scorecard.csv", index=False)
        pd.DataFrame(samples).to_json(directory / "survivorship-sample.json", orient="records", indent=2, force_ascii=False)
    inputs_unchanged = {}
    for name, record in manifest["inputs"].items():
        path = Path(record["path"])
        inputs_unchanged[name] = file_hash(path) == record["sha256"]
    stats["input_locks_unchanged"] = inputs_unchanged
    # Recheck inherited official documents independently of catalog assertions.
    trust=json.loads((root/'config/pit_trust_evidence.json').read_text(encoding='utf-8'))
    raw_index={p.stem:p for p in (root/'data/pit/raw').rglob('*.raw')}
    official={}
    for name,ev in trust['sources'].items():
        path=raw_index.get(ev['raw_sha256'])
        official[name]=bool(path and file_hash(path)==ev['raw_sha256'])
    stats['inherited_official_raw_hashes_verified']=official
    previous=json.loads((root/'reports/evidence/qc-protected-verification-2026-10-08.json').read_text(encoding='utf-8'))
    stats['protected_artifacts_unchanged_since_previous_receipt']={item['path']:
        file_hash(root/item['path'])==item.get('current_sha256',item['sha256']) for item in previous['files']}
    stats['audit_code_sha256']=file_hash(Path(__file__))
    (directory / "scorecard.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"directory": str(directory), "identity": stats["identity"], "membership": stats["membership"],
                      "price": stats["price"], "tier": stats["tier"]}, ensure_ascii=False, indent=2))
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--directory", type=Path)
    args = p.parse_args()
    root = args.root.resolve()
    directory = args.directory or Path(json.loads((root / "data/pit/construction/current.json").read_text(encoding="utf-8"))["directory"])
    audit(root, directory)
