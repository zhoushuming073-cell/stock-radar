"""Offline format design fixtures only; never enables or exports PIT execution."""
from datetime import datetime
from decimal import Decimal

LEAN_SOURCE_COMMIT = "82810ea63d5542f05dc58f9d1db0557cf174d0ea"


def mapped_symbol(rows: list[str], day: str) -> str | None:
    """Mirror MapFile.GetMappedSymbol's first row with end-date >= search date."""
    search = datetime.strptime(day, "%Y-%m-%d")
    parsed = sorted((datetime.strptime(r.split(',')[0], "%Y%m%d"),r.split(',')[1]) for r in rows)
    return next((symbol for end,symbol in parsed if end>=search),None)


def factor_row(row: str) -> dict:
    """CorporateFactorRow layout; parser witnesses do not certify adjustment data."""
    parts=row.split(',')
    return {"date":datetime.strptime(parts[0],'%Y%m%d').date().isoformat(),
            "price_factor":Decimal(parts[1]),"split_factor":Decimal(parts[2]),
            "reference_price":Decimal(parts[3]) if len(parts)>3 else Decimal(0)}


def execution_design_status() -> dict:
    return {"origin":"Stock Radar generated evidence / format design, not QuantConnect official data",
            "lean_source_commit":LEAN_SOURCE_COMMIT,"execution_ready":False,
            "terminal_policy":"unresolved; last close is not economic settlement",
            "factor_policy":"general split/dividend normalization and native result reconciliation required"}
