"""Evidence-backed actions and explicit price bases for generated PIT inputs.

An observed disappearance is never a terminal event. Cash terms are insufficient
without an independently reviewed settlement date and accounting convention.
"""
from __future__ import annotations

from decimal import Decimal
import math

import pandas as pd

TERMINALS = {"cash_acquisition", "stock_merger", "merger", "bankruptcy",
             "delisting", "trading_suspension", "equity_cancellation", "liquidation"}
NONTERMINALS = {"listing", "symbol_change", "exchange_transfer", "split", "reverse_split", "dividend"}


def validate_no_material_action(review: dict, security_id: str, sessions: list[str],
                                known_actions: list[dict], frozen_hashes: set[str]) -> bool:
    """A negative result requires positive, complete source coverage evidence.

    Source silence, an empty event table, and a split-only endpoint are insufficient.
    This validates the declaration's scope and locks, not the truth of a publisher.
    """
    needed = {'split','reverse_split','symbol_change','merger','cash_acquisition',
              'delisting','exchange_transfer','dividend','bankruptcy','equity_cancellation'}
    if not sessions or review.get('result') != 'reviewed_no_material_action':
        return False
    if (review.get('security_id') != security_id or not review.get('reviewer_logic_version')
            or review.get('review_start','9999') > min(sessions)
            or review.get('review_end','0000') < max(sessions)):
        return False
    sources = review.get('sources_checked', [])
    covered = set()
    for source in sources:
        if (not source.get('url','').startswith('https://') or not source.get('source_version')
                or source.get('raw_sha256') not in frozen_hashes
                or source.get('identity_bound') is not True or source.get('coverage_complete') is not True
                or source.get('start','9999') > min(sessions) or source.get('end','0000') < max(sessions)):
            return False
        covered.update(source.get('event_types_checked',[]))
    if not needed <= covered or not needed <= set(review.get('event_types_checked',[])):
        return False
    return not any(a['security_id']==security_id and min(sessions)<=a['effective_date']<=max(sessions)
                   and a['event_type'] in needed for a in known_actions)


def corporate_actions(catalog: dict, reviews: dict | None = None) -> list[dict]:
    """Normalize without upgrading the original evidence's confidence."""
    reviews = reviews or {}
    result = []
    for event in catalog.get("events", []):
        source = catalog["sources"][event["source"]]
        key = f"{event['security_id']}:{event['event_type']}:{event['effective_date']}"
        review = reviews.get(key, {})
        kind = event["event_type"]
        if kind == 'merger' and review.get('event_type') == 'cash_acquisition' and event.get('documented_cash_consideration'):
            kind = 'cash_acquisition'
        ratio = (float(event["to_factor"]) / float(event["for_factor"])
                 if kind in {"split", "reverse_split"} else None)
        mode = {"symbol_change": "same_identity_map", "exchange_transfer": "same_identity_us_route",
                "listing": "membership_boundary"}.get(kind, "blocked")
        if kind in {"split", "reverse_split"} and review.get("factor_verified") is True:
            mode = "native_raw_split"
        # A dividend implementation needs its native cash/factor golden. Until
        # that exists, even a documented dividend keeps this run blocked.
        if kind in TERMINALS and review.get("settlement_verified") is True:
            if (review.get("settlement_policy") == "cash_entitlement_at_effective_date"
                    and review.get("currency") == "USD"
                    and review.get("settlement_date") and review.get("last_tradable_session")
                    and pd.Timestamp(review["settlement_date"]) > pd.Timestamp(review["last_tradable_session"])
                    and isinstance(review.get("cash_per_share"), (int, float))
                    and math.isfinite(review["cash_per_share"]) and review["cash_per_share"] > 0
                    and review.get("settlement_fee") == 0
                    and kind == "cash_acquisition"
                    and review['cash_per_share'] == event.get('documented_cash_consideration')):
                mode = "native_cash_entitlement"
        result.append({"event_id": key, "security_id": event["security_id"], "event_type": kind,
                       "effective_date": event["effective_date"], "old_symbol": event.get("old_symbol"),
                       "new_symbol": event.get("new_symbol"), "old_exchange": event.get("old_exchange"),
                       "new_exchange": event.get("new_exchange"), "ratio": ratio,
                       "consideration": event.get("documented_cash_consideration"),
                       "source": source, "confidence": event["confidence"], "handling_mode": mode,
                       "review": review, "last_tradable_session": event.get("last_tradable_session")})
    by_event = {row['event_id']: row for row in result}
    for row in result:
        if row['event_type'] == 'trading_suspension' and row['review'].get('covered_by'):
            covered = by_event.get(row['review']['covered_by'], {})
            if (covered.get('handling_mode') == 'native_cash_entitlement'
                    and covered.get('security_id') == row['security_id']
                    and row['confidence'] == 'verified'
                    and row['last_tradable_session'] == covered['review']['last_tradable_session']):
                row['handling_mode'] = 'cash_quote_cessation'
    return sorted(result, key=lambda x: (x["effective_date"], x["event_id"]))


def write_action_store(catalog: dict, reviews: dict, output) -> dict:
    """New evidence table only. Never writes a research or market database."""
    from pathlib import Path
    import json
    import duckdb
    from radar.pit.builder import digest
    from radar.pit.features import file_hash
    output = Path(output)
    if output.exists():
        raise ValueError('corporate action destination already exists')
    rows = corporate_actions(catalog, reviews)
    output.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(output)) as c:
        c.execute('''CREATE TABLE corporate_action_event (
            event_id VARCHAR PRIMARY KEY, security_id VARCHAR, event_type VARCHAR, effective_date DATE,
            old_symbol VARCHAR, new_symbol VARCHAR, ratio DOUBLE, consideration DOUBLE,
            source JSON, confidence VARCHAR, handling_mode VARCHAR, evidence JSON)''')
        c.executemany('INSERT INTO corporate_action_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            [(r['event_id'], r['security_id'], r['event_type'], r['effective_date'], r['old_symbol'],
              r['new_symbol'], r['ratio'], r['consideration'], json.dumps(r['source']), r['confidence'],
              r['handling_mode'], json.dumps(r)) for r in rows])
        c.execute('CHECKPOINT')
    receipt = {'database':str(output.resolve()), 'database_sha256':file_hash(output),
               'events_sha256':digest(rows), 'events':len(rows), 'coverage_complete':False,
               'policy':'reviewed events only; absent events are not certified absent'}
    output.with_suffix('.manifest.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt


def split_adjust(raw: pd.DataFrame, actions: list[dict], as_of: str) -> pd.DataFrame:
    """Causal split-only feature prices; volume scales reciprocally to prices.

    Only actions effective by as_of enter features. Execution consumes raw bars,
    letting native LEAN adjust holdings once. Dividend-adjusted inputs rejected.
    """
    frame = raw.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    for action in actions:
        if action["event_type"] not in {"split", "reverse_split"} or action["effective_date"] > as_of:
            continue
        if action["handling_mode"] != "native_raw_split" or action["confidence"] != "verified":
            raise ValueError("unverified split factor")
        ratio = float(action["ratio"])
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError("invalid split ratio")
        mask = (frame.security_id.eq(action["security_id"])
                & frame.date.lt(pd.Timestamp(action["effective_date"])))
        for name in ("open", "high", "low", "close"):
            frame.loc[mask, name] = frame.loc[mask, name].astype(float) / ratio
        frame.loc[mask, "volume"] = frame.loc[mask, "volume"].astype(float) * ratio
    return frame


def factor_lines(actions: list[dict], sessions: list[str], raw_closes: dict[str, float]) -> str:
    """LEAN factors change on the actual prior trading session, including holidays."""
    splits = sorted((x for x in actions if x["event_type"] in {"split", "reverse_split"}),
                    key=lambda x: x["effective_date"])
    rows = []
    cumulative = Decimal(1)
    for action in reversed(splits):
        if action["handling_mode"] != "native_raw_split":
            raise ValueError("split is not approved for raw native execution")
        previous = [day for day in sessions if day < action["effective_date"]]
        if not previous:
            raise ValueError("split needs its previous trading session")
        day = previous[-1]
        reference = raw_closes.get(day)
        if reference is None or not math.isfinite(reference) or reference <= 0:
            raise ValueError("split reference raw close unavailable")
        cumulative /= Decimal(str(action["ratio"]))
        rows.append(f"{day.replace('-', '')},1,{cumulative},{reference}\n")
    # LEAN also derives its minimum data date from the first factor row. Seed
    # it before the research start; event rows still carry prior-session dates.
    return f"19980102,1,{cumulative},1\n" + "".join(reversed(rows)) + "20501231,1,1,1\n"
