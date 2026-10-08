"""Measured candle/window readiness, no returns, model fitting or QC matching."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from radar.pit.shape import ShapeResearchDatabase, render_svg, tensor
from radar.pit.features import file_hash


def metric(n,d):
    return {"numerator":int(n),"denominator":int(d),"pct":round(100*n/d,4) if d else None}


def audit(root):
    root=Path(root).resolve()
    with ShapeResearchDatabase.current(root) as db:
        c=db.connection
        scalar=lambda q:c.execute(q).fetchone()[0]
        inputs=db.manifest["inputs"]
        c.execute("ATTACH '"+inputs["historical_database"]["path"].replace("'","''")+"' AS hist (READ_ONLY)")
        total=scalar("SELECT count(*) FROM session_assessment")
        available=scalar("SELECT count(*) FROM session_assessment WHERE shape_research_status<>'MISSING'")
        ready=scalar("SELECT count(*) FROM session_assessment WHERE shape_research_ready")
        supported=scalar("SELECT count(*) FROM session_assessment WHERE shape_research_ready AND membership_status IN ('confirmed_member','probable_member')")
        statuses={k:metric(v,total) for k,v in c.execute("SELECT shape_research_status,count(*) FROM session_assessment GROUP BY ALL").fetchall()}
        status={"total_observed_common_member_days":total,"available":metric(available,total),"ready":metric(ready,total),
                "ready_of_available":metric(ready,available),"default_supported_ready":metric(supported,total),"status":statuses}
        security={"total_observed_common_ids":scalar("SELECT count(DISTINCT security_id) FROM population"),
                  "any_available":scalar("SELECT count(DISTINCT security_id) FROM session_assessment WHERE shape_research_status<>'MISSING'"),
                  "any_ready_candle":scalar("SELECT count(DISTINCT security_id) FROM session_assessment WHERE shape_research_ready"),
                  "ready_complete_windows":{},"quarantined_any":scalar("SELECT count(DISTINCT security_id) FROM session_assessment WHERE shape_research_status='QUARANTINED'"),
                  "entirely_missing":scalar("SELECT count(*) FROM (SELECT security_id FROM session_assessment GROUP BY security_id HAVING bool_and(shape_research_status='MISSING'))")}
        for length in db.manifest["rules"]["windows"]:
            security["ready_complete_windows"][str(length)]={"supported":scalar(f"SELECT count(DISTINCT security_id) FROM universe_window_index WHERE length={length} AND supported_membership"),
                                                        "including_unknown":scalar(f"SELECT count(DISTINCT security_id) FROM universe_window_index WHERE length={length}")}
        windows=c.execute("""SELECT length,split_assignment,count(*) AS including_unknown,
                            count(*) FILTER(WHERE supported_membership) AS supported FROM visual_window_index GROUP BY ALL ORDER BY length,split_assignment""").df().to_dict("records")
        for length in db.manifest["rules"]["windows"]:
            for split in db.manifest["split_assignments"]:
                if not any(r["length"]==length and r["split_assignment"]==split for r in windows):
                    windows.append({"length":length,"split_assignment":split,"including_unknown":0,"supported":0})
        membership={k:metric(v,total) for k,v in c.execute("SELECT membership_status,count(*) FROM population GROUP BY ALL").fetchall()}
        daily=c.execute("""SELECT decision_date,length,count(*) FILTER(WHERE supported_membership) AS exclude_unknown,
                          count(*) AS include_unknown,count(*)-count(*) FILTER(WHERE supported_membership) AS additional_unknown
                          FROM universe_window_index GROUP BY ALL ORDER BY decision_date,length""").df()
        sensitivity={"candle_addition":metric(ready-supported,supported),
                     "windows_by_length":{},"daily_maximum_addition":int(daily.additional_unknown.max()),
                     "interpretation":"Actual eligible candle/window/count sensitivity only; no strategy returns were run. Includes priced observed unknowns, not fictitious unobserved candidates."}
        for length in db.manifest["rules"]["windows"]:
            rows=[r for r in windows if r["length"]==length]
            inc=sum(r["including_unknown"] for r in rows);ex=sum(r["supported"] for r in rows)
            sensitivity["windows_by_length"][str(length)]={"exclude_unknown":ex,"include_unknown":inc,"addition":metric(inc-ex,ex)}
        reasons=c.execute("""SELECT reason,count(*) AS source_findings,count(DISTINCT security_id) AS ids,
                    count(DISTINCT security_id||'|'||CAST(date AS VARCHAR)) AS sessions
                    FROM shape_review_queue,unnest(string_split(shape_research_reason,'|')) AS t(reason)
                    WHERE reason<>'noncritical_uncertainty' GROUP BY reason ORDER BY sessions DESC""").df().to_dict("records")
        safety={"detected_future_boundary_rows":scalar("SELECT count(DISTINCT security_id||'|'||CAST(date AS VARCHAR)) FROM shape_price WHERE future_leakage"),
                "ready_future_boundary_rows":scalar("SELECT count(*) FROM shape_price WHERE shape_research_ready AND future_leakage"),
                "issuer_or_reviewed_reuse_ids":scalar("SELECT count(DISTINCT security_id) FROM shape_price WHERE identity_conflict"),
                "issuer_or_reviewed_reuse_sessions":scalar("SELECT count(DISTINCT security_id||'|'||CAST(date AS VARCHAR)) FROM shape_price WHERE identity_conflict"),
                "ready_identity_conflict_rows":scalar("SELECT count(*) FROM shape_price WHERE shape_research_ready AND identity_conflict"),
                "no_identity_conflict":metric(scalar("SELECT count(*) FROM session_assessment a WHERE a.shape_research_status<>'MISSING' AND NOT EXISTS(SELECT 1 FROM shape_price b WHERE b.security_id=a.security_id AND b.date=a.date AND b.identity_conflict)"),available),
                "source_conflict_ids":scalar("SELECT count(DISTINCT security_id) FROM shape_price WHERE source_conflict"),
                "suspected_split_sessions":scalar("SELECT count(DISTINCT security_id||'|'||CAST(date AS VARCHAR)) FROM shape_price WHERE suspected_split"),
                "known_split_events":scalar("SELECT count(*) FROM split_action"),
                "known_split_events_with_candles":scalar("SELECT count(DISTINCT security_id||'|'||CAST(date AS VARCHAR)) FROM shape_price WHERE known_split"),
                "known_split_events_with_sane_series":scalar("SELECT count(DISTINCT security_id||'|'||CAST(date AS VARCHAR)) FROM shape_price WHERE known_split AND shape_research_ready"),
                "known_split_official_evidence":scalar("SELECT count(*) FROM split_action WHERE confidence='verified'"),
                "invalid_action_records":scalar("SELECT count(*) FROM invalid_split_action"),
                "ready_unresolved_split_rows":scalar("SELECT count(*) FROM shape_price WHERE shape_research_ready AND (suspected_split OR invalid_split_action)"),
                "visual_nonready_start_or_end":scalar("SELECT count(*) FROM visual_window_index WHERE NOT shape_research_ready OR NOT start_ready"),
                "window_duplicates":scalar("SELECT count(*) FROM (SELECT security_id,decision_date,length,count(*) n FROM visual_window_index GROUP BY ALL HAVING n>1)"),
                "split_boundary_violations":0,
                "limits":"Zero detected against installed boundaries is not complete real-world IPO/class attestation; no company outcome enters tensors."}
        for split,(start,end) in db.manifest["split_assignments"].items():
            safety["split_boundary_violations"]+=c.execute("SELECT count(*) FROM visual_window_index WHERE split_assignment=? AND (window_start<? OR decision_date>?)",[split,start,end]).fetchone()[0]
        survivorship={}
        cohorts={"later_disappeared":"q.disappeared AND q.security_type='common'",
                 "verified_listing_cessation":"q.security_type='common' AND q.security_id IN (SELECT security_id FROM hist.lifecycle_event WHERE event_type='trading_suspension' AND confidence='verified')",
                 "verified_acquired":"q.security_type='common' AND q.security_id IN (SELECT security_id FROM hist.lifecycle_event WHERE event_type='merger' AND confidence='verified')"}
        for name,condition in cohorts.items():
            denom=scalar("SELECT count(*) FROM hist.identity_quality q WHERE "+condition)
            for_ready=scalar("SELECT count(*) FROM hist.identity_quality q WHERE "+condition+" AND EXISTS(SELECT 1 FROM session_assessment s WHERE s.security_id=q.security_id AND s.shape_research_ready)")
            historical=scalar("SELECT count(*) FROM hist.identity_quality q WHERE "+condition+" AND EXISTS(SELECT 1 FROM population s WHERE s.security_id=q.security_id)")
            fullwindow=scalar("SELECT count(*) FROM hist.identity_quality q WHERE "+condition+" AND EXISTS(SELECT 1 FROM universe_window_index w WHERE w.security_id=q.security_id AND w.length=20 AND supported_membership)")
            memberdays=scalar("SELECT count(*) FROM population p JOIN hist.identity_quality q USING(security_id) WHERE "+condition)
            days_ready=scalar("SELECT count(*) FROM session_assessment p JOIN hist.identity_quality q USING(security_id) WHERE "+condition+" AND p.shape_research_ready")
            survivorship[name]={"population_retained":metric(historical,denom),"any_ready_candle":metric(for_ready,denom),
                                "supported_20_session_window":metric(fullwindow,denom),"ready_sessions":metric(days_ready,memberdays)}
        # Four documented cessation cases, also include raw BBBY and adjusted NVDA.
        samples=[]
        out=root/"reports/evidence/shape-samples-2026-10-08";out.mkdir(parents=True,exist_ok=True)
        for sid in ("SEC-0000886158-COMMON","SEC-0000718877-COMMON","SEC-0001418091-COMMON","SEC-0001353283-COMMON","SEC-0001045810-COMMON"):
            choices=c.execute("SELECT decision_date,length,split_assignment FROM visual_window_index WHERE security_id=? AND supported_membership ORDER BY length DESC,decision_date DESC LIMIT 1",[sid]).fetchall()
            if not choices:
                samples.append({"security_id":sid,"sample_available":False});continue
            decision,length,split=choices[0];w=db.window(sid,decision,int(length))
            svg=render_svg(w.normalized);again=render_svg(w.normalized)
            name=sid+".svg";(out/name).write_bytes(svg)
            samples.append({"security_id":sid,"sample_available":True,"metadata":w.metadata,
                            "image":str((out/name).relative_to(root)),"svg_sha256":sha256(svg).hexdigest(),
                            "tensor_sha256":sha256(tensor(w.normalized).tobytes()).hexdigest(),"repeat_identical":svg==again})
        r= db.manifest["rules"]["readiness"]
        window_count=lambda split,length:next(x["supported"] for x in windows if x["split_assignment"]==split and x["length"]==length)
        checks={"ohlcv_coverage":status["available"]["pct"]>=r["minimum_available_pct"],
                "majority_available_ready":status["ready_of_available"]["pct"]>=r["minimum_ready_of_available_pct"],
                "substantive_disappeared_coverage":survivorship["later_disappeared"]["any_ready_candle"]["numerator"]>=r["minimum_ready_disappeared_ids"],
                "documented_cessation_cases":survivorship["verified_listing_cessation"]["any_ready_candle"]["numerator"]>=r["minimum_cessation_samples_retained"],
                "train_window_scale":window_count("train",126)>=r["minimum_train_windows_126"],
                "validation_window_scale":window_count("validation",126)>=r["minimum_validation_windows_126"],
                "test_window_scale":window_count("test",126)>=r["minimum_test_windows_126"],
                "no_leaking_or_conflicted_ready_inputs":all(safety[k]==0 for k in ("ready_future_boundary_rows","ready_identity_conflict_rows","ready_unresolved_split_rows","split_boundary_violations","window_duplicates","visual_nonready_start_or_end"))}
        locks={k:file_hash(Path(v["path"]))==v["sha256"] for k,v in inputs.items()}
        checks["locked_sources_and_code_unchanged"]=all(locks.values())
        result={"source_version":db.fingerprint,"database_sha256":db.manifest["database_sha256"],"scope":db.manifest["scope"],
                "coverage":c.execute("SELECT min(date)::VARCHAR,max(date)::VARCHAR,count(*) FROM sessions").fetchone(),
                "price":status,"security":security,"membership":membership,"windows":sorted(windows,key=lambda x:(x["length"],x["split_assignment"])),
                "unknown_sensitivity":sensitivity,"safety":safety,"survivorship":survivorship,"material_review_reasons":reasons,
                "review_queue":{"source_findings":scalar("SELECT count(*) FROM shape_review_queue"),"distinct_ids":scalar("SELECT count(DISTINCT security_id) FROM shape_review_queue")},
                "split_assignments":db.manifest["split_assignments"],"rules":db.manifest["rules"],"readiness_checks":checks,
                "shape_research_state":"SHAPE_RESEARCH_READY" if all(checks.values()) else "PARTIAL",
                "general_pit_tier":"Tier 1 (strict unchanged)","source_locks_unchanged":locks,"samples":samples,
                "strict_accepted_raw_rows":scalar("SELECT count(*) FROM hist.accepted_price"),
                "no_strategy_or_training_run":True,"qc_exports_or_runs":False,
                "audit_code_sha256":file_hash(Path(__file__)),
                "newly_assessed_raw_member_days":scalar("SELECT count(*) FROM session_assessment a WHERE a.shape_research_status<>'MISSING' AND NOT EXISTS(SELECT 1 FROM hist.observed_price o WHERE o.security_id=a.security_id AND o.date=a.date) AND NOT EXISTS(SELECT 1 FROM hist.accepted_price o WHERE o.security_id=a.security_id AND o.date=a.date)")}
        evidence=root/"reports/evidence/shape-research-scorecard-2026-10-08.json"
        evidence.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        daily.to_csv(db.directory/"unknown-sensitivity-daily.csv",index=False)
        print(json.dumps({"state":result["shape_research_state"],"price":status,"security":security,"survivorship":survivorship,"windows":windows,"checks":checks},ensure_ascii=False),flush=True)
        return result


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path.cwd());audit(p.parse_args().root)
