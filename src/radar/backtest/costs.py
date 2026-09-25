"""Auditable per-order US-equity fee breakdown for backtests.

The fee schedule is the illustrative uSMART plan in ``config/research.yaml``
(``illustrative_costs``); it is unconfirmed and must not be treated as the
user's real broker contract. Every component is returned separately so a
backtest can show exactly which fees were charged on each side.

Rules applied, in order, per component:
  * commission / platform / settlement: ``max(shares * per_share, min)`` then
    capped at ``notional * cap_notional_fraction`` (the cap wins over the min,
    matching the existing research-side helper).
  * SEC fee: sell side only, ``max(notional * fraction, sec_sell_min)``.
  * FINRA TAF: sell side only, ``min(max(shares * per_share, min), max)``.
  * CAT fee: both sides, ``max(shares * per_share, cat_min)``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_SECTION = "illustrative_costs"

_FEE_KEYS = (
    "commission_per_share",
    "commission_min",
    "commission_cap_notional_fraction",
    "platform_per_share",
    "platform_min",
    "platform_cap_notional_fraction",
    "settlement_per_share",
    "settlement_min",
    "settlement_cap_notional_fraction",
    "sec_sell_notional_fraction",
    "sec_sell_min",
    "finra_sell_per_share",
    "finra_sell_min",
    "finra_sell_max",
    "cat_per_share",
    "cat_min",
)


@dataclass(frozen=True)
class FeeConfig:
    """Fee schedule loaded from the ``illustrative_costs`` config section."""

    profile: str
    order_notional_usd: float
    commission_per_share: float
    commission_min: float
    commission_cap_notional_fraction: float
    platform_per_share: float
    platform_min: float
    platform_cap_notional_fraction: float
    settlement_per_share: float
    settlement_min: float
    settlement_cap_notional_fraction: float
    sec_sell_notional_fraction: float
    sec_sell_min: float
    finra_sell_per_share: float
    finra_sell_min: float
    finra_sell_max: float
    cat_per_share: float
    cat_min: float
    slippage_bps_per_side: tuple[float, ...]


@dataclass(frozen=True)
class FeeBreakdown:
    """One side of one order, with each fee kept separately for audit."""

    side: str
    price: float
    quantity: float
    notional: float
    commission: float
    platform: float
    settlement: float
    sec: float
    finra: float
    cat: float
    total: float

    @property
    def total_bps(self) -> float:
        """Total fees in basis points of the order notional."""
        if self.notional <= 0:
            return 0.0
        return self.total / self.notional * 10_000


def _money(value: float) -> float:
    return round(float(value), 6)


def _capped_per_share(
    quantity: float, notional: float, per_share: float, minimum: float, cap_fraction: float,
) -> float:
    return min(max(quantity * per_share, minimum), notional * cap_fraction)


def _number(raw: dict, key: str) -> float:
    if key not in raw:
        raise ValueError(f"illustrative_costs.{key} is required")
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"illustrative_costs.{key} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"illustrative_costs.{key} must be a finite non-negative number")
    return value


def load_fee_config(path: str | Path) -> FeeConfig:
    """Load the illustrative fee schedule from a research YAML file."""
    config_file = Path(path)
    if not config_file.is_file():
        raise ValueError(f"fee config file does not exist: {config_file}")
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or CONFIG_SECTION not in raw:
        raise ValueError(f"config must contain a {CONFIG_SECTION} section")
    section = raw[CONFIG_SECTION]
    if not isinstance(section, dict):
        raise ValueError(f"{CONFIG_SECTION} must be a mapping")
    profile = section.get("profile")
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("illustrative_costs.profile is required")
    notional = _number(section, "order_notional_usd")
    if notional <= 0:
        raise ValueError("illustrative_costs.order_notional_usd must be positive")
    bps = section.get("slippage_bps_per_side")
    if not isinstance(bps, list) or not bps:
        raise ValueError("illustrative_costs.slippage_bps_per_side must be a non-empty list")
    return FeeConfig(
        profile=profile.strip(),
        order_notional_usd=notional,
        **{key: _number(section, key) for key in _FEE_KEYS},
        slippage_bps_per_side=tuple(_number({"value": item}, "value") for item in bps),
    )


def _build(side: str, price: float, quantity: float, cfg: FeeConfig) -> FeeBreakdown:
    price = float(price)
    quantity = float(quantity)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("price must be a finite positive number")
    if not math.isfinite(quantity) or quantity <= 0:
        raise ValueError("quantity must be a finite positive number")
    notional = price * quantity
    commission = _capped_per_share(quantity, notional, cfg.commission_per_share,
                                   cfg.commission_min, cfg.commission_cap_notional_fraction)
    platform = _capped_per_share(quantity, notional, cfg.platform_per_share,
                                 cfg.platform_min, cfg.platform_cap_notional_fraction)
    settlement = _capped_per_share(quantity, notional, cfg.settlement_per_share,
                                   cfg.settlement_min, cfg.settlement_cap_notional_fraction)
    if side == "sell":
        sec = max(notional * cfg.sec_sell_notional_fraction, cfg.sec_sell_min)
        finra = min(max(quantity * cfg.finra_sell_per_share, cfg.finra_sell_min),
                    cfg.finra_sell_max)
    else:
        sec = 0.0
        finra = 0.0
    cat = max(quantity * cfg.cat_per_share, cfg.cat_min)
    fees = (_money(commission), _money(platform), _money(settlement),
            _money(sec), _money(finra), _money(cat))
    return FeeBreakdown(
        side=side,
        price=price,
        quantity=quantity,
        notional=_money(notional),
        commission=fees[0],
        platform=fees[1],
        settlement=fees[2],
        sec=fees[3],
        finra=fees[4],
        cat=fees[5],
        total=_money(sum(fees)),
    )


def buy_cost(price: float, quantity: float, cfg: FeeConfig) -> FeeBreakdown:
    """Fees charged on a single buy of ``quantity`` shares at ``price``."""
    return _build("buy", price, quantity, cfg)


def sell_cost(price: float, quantity: float, cfg: FeeConfig) -> FeeBreakdown:
    """Fees charged on a single sell of ``quantity`` shares at ``price``."""
    return _build("sell", price, quantity, cfg)
