"""Versioned boundary contracts. Unknown/future fields are rejected on signals."""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Signal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    signal_date: date
    available_at: datetime
    symbol: str = Field(pattern=r'^[A-Z][A-Z0-9.\-]{0,14}$')
    rank: int = Field(ge=1)
    strategy_score: float
    strategy_id: str
    strategy_version: str
    reference_close: float = Field(gt=0)
    avg_dollar_volume_20: float = Field(ge=0)
    allocation_weight: float = Field(ge=0)

    @field_validator('strategy_score', 'reference_close', 'avg_dollar_volume_20', 'allocation_weight')
    @classmethod
    def finite(cls, value):
        if not isfinite(value):
            raise ValueError('signal numbers must be finite')
        return value

    @model_validator(mode='after')
    def availability(self):
        if self.available_at.tzinfo is None or self.available_at.date() != self.signal_date:
            raise ValueError('signal must be stamped with its timezone-aware session close')
        return self


class PortfolioPoint(BaseModel):
    timestamp: datetime
    date: date
    equity: float
    cash: float
    holdings_value: float
    benchmark: float | None
    drawdown: float

    @model_validator(mode='after')
    def reconcile(self):
        values = [self.equity, self.cash, self.holdings_value, self.drawdown]
        if not all(isfinite(v) for v in values) or abs(self.equity - self.cash - self.holdings_value) > .02:
            raise ValueError('native portfolio cash/holdings do not reconcile')
        return self


RESULT_SCHEMA_VERSION = 'stock-radar-backtest-v1'
SIGNAL_SCHEMA_VERSION = 'stock-radar-signals-v1'
