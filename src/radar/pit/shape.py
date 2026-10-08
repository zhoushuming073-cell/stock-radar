"""Independent, opt-in historical shape windows; never promotes strict PIT data.

Only normalized OHLCV enters model/chart inputs. Metadata and labels are kept
outside inputs. Raw split factors effective after the decision are never used.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import duckdb
import numpy as np
import pandas as pd

from radar.pit.features import file_hash
from radar.pit.database import membership_truth

OHLCV = ["open", "high", "low", "close", "volume"]
READY = ("READY", "READY_WITH_MINOR_UNCERTAINTY")


def canonical_hash(frame):
    values = [[str(r.date)[:10], *[float(getattr(r, col)).hex() for col in OHLCV]]
              for r in frame.itertuples()]
    return sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def classify_bar(row):
    """Shared pure classifier used by the bulk SQL pipeline and fixtures."""
    if not row.get("available", True):
        return "MISSING", "no_ohlcv"
    for key in ("future_leakage", "identity_conflict", "invalid_ohlcv", "split_conflict",
                "source_conflict", "mixed_basis", "suspicious_gap"):
        if row.get(key, False):
            return "QUARANTINED", key
    if row.get("minor_uncertainty", False) or membership_truth(row.get("membership_status", "unknown")) is None:
        return "READY_WITH_MINOR_UNCERTAINTY", "membership_or_noncritical_provenance_uncertainty"
    return "READY", "automatic_sanity_pass"


def normalize_window(frame, decision_date, actions=()):
    """Normalize on information in the window, without future price anchors.

    Historical split-only vendor series may use a later constant price/volume
    multiplier. Window normalization cancels those constants independently.
    This does not make absolute legacy prices suitable for PIT tradability.
    """
    f = frame.copy()
    f["date"] = pd.to_datetime(f.date).dt.normalize()
    decision = pd.Timestamp(decision_date).normalize()
    if f.empty or not f.date.is_monotonic_increasing or f.date.duplicated().any() or (f.date > decision).any():
        raise ValueError("unordered, duplicate, empty or future window")
    if f.basis.nunique() != 1 or f.source.nunique() != 1:
        raise ValueError("mixed source/adjustment basis")
    if f.basis.iloc[0] not in ("raw", "split"):
        raise ValueError("unsupported adjustment basis")
    a = f[OHLCV].to_numpy(dtype=float)
    if (not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4] < 0).any()
            or (f.high < f[["open", "close", "low"]].max(axis=1)).any()
            or (f.low > f[["open", "close"]].min(axis=1)).any()):
        raise ValueError("invalid OHLCV")
    if f.basis.iloc[0] == "raw":
        for action in actions:
            effective = pd.Timestamp(action["date"]).normalize()
            factor = float(action["factor"])
            if not np.isfinite(factor) or factor <= 0:
                raise ValueError("invalid split factor")
            if effective <= decision:
                before = f.date < effective
                f.loc[before, OHLCV[:4]] /= factor
                f.loc[before, "volume"] = f.loc[before, "volume"].astype(float) * factor
    base = float(f.close.iloc[0])
    vol_base = float(f.volume.max()) or 1.0
    f[OHLCV[:4]] /= base
    f["volume"] = f.volume.astype(float) / vol_base
    return f[["date", *OHLCV]]


def tensor(window):
    """Five channels only, no labels, company names or current ticker fields."""
    return np.ascontiguousarray(window[OHLCV].to_numpy(dtype="<f8"))


def render_svg(window, path=None):
    """Deterministic candlestick + volume plot from canonical numeric inputs.

    Fixed coordinates and colors, no text/axes containing identity or outcomes.
    SVG avoids font, GPU and platform-dependent rasterization in dataset hashes.
    """
    a = tensor(window)
    if len(a) < 1 or not np.isfinite(a).all():
        raise ValueError("empty or nonfinite plot")
    w, h = 640, 480
    root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(w), height=str(h), viewBox=f"0 0 {w} {h}")
    ET.SubElement(root, "rect", width=str(w), height=str(h), fill="#ffffff")
    low, high = float(a[:, 2].min()), float(a[:, 1].max())
    span = max(high - low, 1e-12)
    y = lambda p: 20 + (high - p) / span * 320
    step = 600 / len(a)
    fmt = lambda x: f"{x:.6f}"
    for i, (o, hi, lo, cl, vol) in enumerate(a):
        x = 20 + (i + .5) * step
        color = "#168c58" if cl >= o else "#c84545"
        ET.SubElement(root, "line", x1=fmt(x), x2=fmt(x), y1=fmt(y(hi)), y2=fmt(y(lo)), stroke=color, **{"stroke-width": "1"})
        ET.SubElement(root, "rect", x=fmt(x-step*.32), y=fmt(min(y(o), y(cl))), width=fmt(step*.64), height=fmt(max(abs(y(o)-y(cl)), .5)), fill=color)
        ET.SubElement(root, "rect", x=fmt(x-step*.32), y=fmt(460-vol*90), width=fmt(step*.64), height=fmt(vol*90), fill=color)
    result = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if path is not None:
        Path(path).write_bytes(result)
    return result


def split_for_window(start, decision, splits):
    """Input must be wholly in one split, not merely its decision date."""
    start, decision = pd.Timestamp(start), pd.Timestamp(decision)
    if start > decision:
        raise ValueError("reversed window")
    for name, bounds in splits.items():
        if pd.Timestamp(bounds[0]) <= start <= decision <= pd.Timestamp(bounds[1]):
            return name
    return None


def assert_training_split(assignment):
    if assignment != "train":
        raise ValueError("only Train may fit model parameters; Fresh OOS is protected")


@dataclass
class ShapeWindow:
    metadata: dict
    ohlcv: pd.DataFrame
    normalized: pd.DataFrame

    def training_tensor(self):
        assert_training_split(self.metadata["split_assignment"])
        return tensor(self.normalized)


class ShapeResearchDatabase:
    """Read-only, hash-verified dataset; no production provider substitution."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        path = self.directory / "shape.duckdb"
        if file_hash(path) != self.manifest["database_sha256"]:
            raise ValueError("shape database bytes changed")
        self.connection = duckdb.connect(str(path), read_only=True)
        self.fingerprint = self.manifest["source_version"]

    @classmethod
    def current(cls, root):
        pointer = json.loads((Path(root) / "data/pit/shape-research/current.json").read_text(encoding="utf-8"))
        return cls(pointer["directory"])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def window(self, security_id, decision_date, length=60, *, include_unknown=False, source=None, dataset=True):
        if length not in self.manifest["rules"]["windows"]:
            raise ValueError("unconfigured window length")
        table = "visual_window_index" if dataset else "universe_window_index"
        sql = f"""SELECT * FROM {table} WHERE security_id=? AND decision_date=? AND length=?
                 AND (supported_membership OR ?)"""
        args = [security_id, pd.Timestamp(decision_date).date(), length, include_unknown]
        if source is not None:
            sql += " AND source=?"
            args.append(source)
        # The frozen index chooses a source using prefix-only quality/availability.
        row = self.connection.execute(sql + " ORDER BY priority LIMIT 1", args).df()
        if row.empty:
            raise ValueError("no complete safe window in one frozen split")
        m = row.iloc[0].to_dict()
        if not dataset:
            m["split_assignment"] = split_for_window(m["window_start"], m["decision_date"], self.manifest["split_assignments"])
        f = self.connection.execute("""SELECT * FROM shape_price WHERE series_id=? AND date BETWEEN ? AND ? ORDER BY date""",
                                    [m["series_id"], m["window_start"], m["decision_date"]]).df()
        if len(f) != length or not f.shape_research_ready.all():
            raise ValueError("unsafe/incomplete indexed window")
        actions = self.connection.execute("SELECT date,factor FROM split_action WHERE security_id=? AND date<=? ORDER BY date",
                                          [security_id, m["decision_date"]]).df().to_dict("records")
        normalized = normalize_window(f, decision_date, actions)
        m["historical_ticker"] = f.symbol.iloc[-1]
        m["window_end"] = m["decision_date"]
        m["ohlcv_hash"] = canonical_hash(f)
        m["normalized_hash"] = canonical_hash(normalized)
        m["membership_status"] = f.membership_status.iloc[-1]
        m["shape_readiness_status"] = "READY_WITH_MINOR_UNCERTAINTY" if (f.shape_research_status != "READY").any() else "READY"
        m["adjustment_mode"] = f.basis.iloc[0]
        m["source_hash"] = f.source_hash.iloc[0]
        m["dataset_version"] = self.fingerprint
        return ShapeWindow(m, f[["date", "symbol", *OHLCV, "basis", "source"]].copy(), normalized)

    def universe_on(self, day, length=126, *, include_unknown=False):
        return self.connection.execute("""SELECT security_id,historical_ticker AS symbol,membership_status,
            shape_research_status,source,basis FROM universe_window_index
            WHERE decision_date=? AND length=? AND (supported_membership OR ?) ORDER BY security_id""",
            [pd.Timestamp(day).date(), length, include_unknown]).df()

    def feature_window(self, security_id, decision_date, length=126, **kwargs):
        """Causal scale-free adapter. Absolute tradability/execution stays strict.

        Native Strategy 2 can consume these OHLCV/ratio inputs in its exploratory
        adapter; this API does not reuse postdated names, future labels or ranks.
        """
        window = self.window(security_id, decision_date, length, dataset=False, **kwargs)
        f = window.normalized.set_index("date")
        out = f.copy()
        out["return_1"] = f.close.pct_change(fill_method=None)
        out["range_fraction"] = (f.high-f.low) / f.close
        out["volume_relative_20"] = f.volume / f.volume.rolling(20, min_periods=20).mean()
        out.index.name = "date"
        return out

    def strategy2_feature_window(self, security_id, decision_date, spy_close, qqq_close, length=126, **kwargs):
        """Reuse unchanged native base/Strategy 2 formulas for shape research.

        Returns scale-free factors on a native (date,symbol) index. Absolute
        tradability and elasticity cross-sectional ranks are deliberately left
        to their existing dated adapters, rather than invented from one stock.
        """
        from radar.features.base import compute_base_features
        from radar.features.strategy2 import compute_strategy2_features
        window = self.window(security_id, decision_date, length, dataset=False, **kwargs)
        bars = window.normalized.set_index("date")
        decision = pd.Timestamp(decision_date)
        def benchmark(series):
            if not isinstance(series.index, pd.DatetimeIndex) or series.index.has_duplicates or not series.index.is_monotonic_increasing:
                raise ValueError("benchmark must have unique ordered dates")
            return series.loc[series.index <= decision].reindex(bars.index)
        base = compute_base_features(bars)
        absolute = {"avg_volume_20", "avg_dollar_volume_20"}
        absolute.update(c for c in base if c.startswith(("ma_", "atr_", "high_", "low_"))
                        and not c.startswith(("atr_pct_", "atr_contraction")))
        result = pd.concat([base.drop(columns=sorted(absolute)),
                            compute_strategy2_features(bars, benchmark(spy_close), benchmark(qqq_close))], axis=1)
        result["symbol"] = window.ohlcv.symbol.to_numpy()
        result["security_id"] = security_id
        result = result.reset_index().set_index(["date", "symbol"])
        result.attrs.update({"scope": "shape factors only; not a native portfolio acceptance",
                             "shape_dataset_version": self.fingerprint, "ohlcv_hash": window.metadata["ohlcv_hash"]})
        return result
