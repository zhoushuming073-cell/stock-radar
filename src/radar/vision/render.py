"""Standardized, blind candlestick rendering using mplfinance."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

RENDERER_VERSION = "mplfinance-blind-v1"


def _deps():
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        import mplfinance as mpf
    except ImportError as exc:
        raise RuntimeError(
            'Vision rendering requires optional dependencies. '
            'Install with: pip install -e ".[vision]"'
        ) from exc
    return plt, mpf


def _prepare(window: pd.DataFrame) -> pd.DataFrame:
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in window]
    if missing:
        raise ValueError("missing OHLCV columns: " + ",".join(missing))
    frame = window[required].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if frame.empty or frame["date"].duplicated().any() or not frame["date"].is_monotonic_increasing:
        raise ValueError("ordered unique non-empty window required")
    values = frame[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise ValueError("invalid OHLCV")
    frame = frame.set_index("date").rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    return frame


def render_blind_png(window: pd.DataFrame, path: str | Path | None = None) -> tuple[bytes, str]:
    """Render price + volume only; no ticker, date labels, axes, title or outcome.

    The canonical OHLCV hash remains the research truth.  The PNG hash is bound
    to the recorded renderer/dependency environment and is used to detect local
    task drift, not to claim cross-platform pixel identity forever.
    """
    plt, mpf = _deps()
    frame = _prepare(window)
    market = mpf.make_marketcolors(
        up="#168c58", down="#c84545", edge="inherit", wick="inherit", volume="inherit"
    )
    style = mpf.make_mpf_style(
        base_mpf_style="classic",
        marketcolors=market,
        facecolor="white",
        figcolor="white",
        gridstyle="",
        y_on_right=False,
    )
    fig, axes = mpf.plot(
        frame,
        type="candle",
        volume=True,
        style=style,
        axisoff=True,
        returnfig=True,
        figsize=(8, 6),
        tight_layout=True,
        warn_too_much_data=10000,
    )
    for ax in axes:
        ax.set_axis_off()
    buf = BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=120,
        bbox_inches="tight",
        pad_inches=0,
        metadata={"Software": "Stock Radar", "Renderer": RENDERER_VERSION},
    )
    plt.close(fig)
    data = buf.getvalue()
    digest = sha256(data).hexdigest()
    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return data, digest
