"""Independent Q2 v1.2. Market gates precede causal channel and entry analysis.

The v1.1 selector/config remain untouched. Reuse its robust log fits, confirmed
pivots and partial bucket handling, and pandas' existing market-model estimator.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import math

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict

from radar.features.elasticity import _market_model
from radar.research.candidates import Candidate, fingerprint
from radar.research.parallel_channel import ChannelSettings, _aggregate, _fit, _validate
from radar.research.sessions import calendar

VERSION = "high-beta-liquid-channel-v1.2"


@dataclass(frozen=True)
class Settings:
    beta_minimum: float = 2.0
    adv20_minimum: float = 50_000_000.
    preferred_beta: float = 2.5
    preferred_adv20: float = 100_000_000.
    beta_min_samples_126: int = 105
    beta_min_samples_60: int = 50
    return_outlier_limit: float = .5
    benchmark_outlier_limit: float = .2
    variance_floor: float = 1e-12
    min_daily_bars: int = 205
    weekly_windows: tuple[int, ...] = (12, 16, 20, 26)
    monthly_windows: tuple[int, ...] = (9, 12, 15, 18)
    channel_width_min_log: float = .12
    channel_width_max_log: float = 1.
    drift_reference_sessions: int = 126
    minimum_reference_drift: float = -.10
    maximum_reference_drift: float = .18
    min_full_swings: float = 1.5
    minimum_clarity: float = 62.
    max_band_disagreement: float = .35
    max_position_disagreement: float = .20
    max_drift_disagreement: float = .12
    preferred_position: float = .30
    maximum_watch_position: float = .45
    breakdown_fraction: float = .08
    last_day_extension: float = .08
    five_day_extension: float = .15

    def __post_init__(self):
        if not (1 <= self.beta_min_samples_126 <= 126 and 1 <= self.beta_min_samples_60 <= 60):
            raise ValueError("invalid beta minimum observations")
        if not (0 < self.preferred_position < self.maximum_watch_position < 1):
            raise ValueError("invalid position intervals")
        if self.beta_minimum <= 0 or self.adv20_minimum <= 0 or self.variance_floor <= 0:
            raise ValueError("positive market gates required")
        if self.preferred_beta < self.beta_minimum or self.preferred_adv20 < self.adv20_minimum:
            raise ValueError("preferred tier cannot weaken market gate")
        if not (0 < self.channel_width_min_log < self.channel_width_max_log
                and -.5 < self.minimum_reference_drift <= 0 < self.maximum_reference_drift < 1
                and self.min_full_swings >= 1 and 0 <= self.minimum_clarity <= 100):
            raise ValueError("invalid channel priors")


class MarketEvidence(BaseModel):
    """Explicit caller proof; historical bars need a separate dated certification."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    scope: str
    identity_trusted: bool
    common_stock: bool
    source: str
    feed: str
    adjustment: str
    joint_price_volume_adjustment: bool
    historical_certified: bool = False

    def refusal(self):
        if not self.identity_trusted:return "identity_untrusted"
        if not self.common_stock:return "instrument_not_common_stock"
        if self.scope not in {"current_listing", "historical_verified"}:return "unknown_identity_scope"
        if self.scope == "historical_verified" and not self.historical_certified:
            return "historical_absolute_liquidity_uncertified"
        if self.source != "alpaca" or self.feed != "sip":return "non_sip_or_incompatible_source"
        if self.adjustment not in {"raw", "split"} or not self.joint_price_volume_adjustment:
            return "price_volume_basis_uncertified"
        return None


def settings(root):
    value=yaml.safe_load((Path(root)/"config/high_beta_channel_v1_2.yaml").read_text(encoding="utf-8"))
    if value["version"] != VERSION:raise ValueError("Q2 version/config mismatch")
    return Settings(**value["settings"])


def beta(close, benchmark, window, minimum, cfg):
    """Adjacent exchange-session simple returns, paired OLS with an intercept.

    Outliers are excluded from both members of the pair and counted, not clipped
    into attractive betas. A current stock outlier also quarantines market entry.
    """
    joined=pd.concat([close.rename("stock"),benchmark.rename("market")],axis=1)
    r=joined.pct_change(fill_method=None).tail(window)
    bad=(r.stock.abs()>cfg.return_outlier_limit)|(r.market.abs()>cfg.benchmark_outlier_limit)
    paired=r.where(~bad).dropna()
    count=len(paired);outliers=int(bad.sum())
    if count<minimum:return dict(value=None,samples=count,outliers=outliers,reason="beta_samples_insufficient")
    if float(paired.market.var(ddof=1))<=cfg.variance_floor:
        return dict(value=None,samples=count,outliers=outliers,reason="benchmark_zero_variance")
    stock=r.stock.where(~bad);market=r.market.where(~bad)
    slope,_=_market_model(stock,market,window,minimum,cfg.variance_floor)
    value=float(slope.iloc[-1])
    return dict(value=value if math.isfinite(value) else None,samples=count,outliers=outliers,reason=None)


def market_features(x, spy, qqq, cfg, adjustment='split', source='alpaca'):
    close=x.set_index("date").close.astype(float)
    # Reindex before pct_change: a missing day cannot become a one-session jump.
    days=calendar().sessions_in_range(x.date.iloc[0],x.date.iloc[-1])
    close=close.reindex(days)
    def reference(frame):
        if frame is None or frame.empty:return pd.Series(index=days,dtype=float)
        z=frame.loc[pd.to_datetime(frame.date)<=x.date.iloc[-1]].copy()
        z["date"]=pd.to_datetime(z.date)
        if z.date.duplicated().any():raise ValueError("duplicate_benchmark_sessions")
        if "provider" in z and not z.provider.eq(source).all():raise ValueError("benchmark_source_incompatible")
        if "feed" in z and not z.feed.eq("sip").all():raise ValueError("benchmark_not_sip")
        if "adjustment" in z and not z.adjustment.eq(adjustment).all():raise ValueError("benchmark_basis_incompatible")
        return z.set_index("date").close.astype(float).reindex(days)
    benchmark=reference(spy);tech=reference(qqq)
    if benchmark.iloc[-127:].isna().any():raise ValueError("missing_spy_benchmark")
    if not np.isfinite(benchmark.dropna()).all() or benchmark.dropna().le(0).any():
        raise ValueError("invalid_spy_benchmark")
    betas={name:beta(close,b,w,m,cfg) for name,b,w,m in [
        ("spy_126",benchmark,126,cfg.beta_min_samples_126),("spy_60",benchmark,60,cfg.beta_min_samples_60),
        ("qqq_126",tech,126,cfg.beta_min_samples_126),("qqq_60",tech,60,cfg.beta_min_samples_60)]}
    amount=x.close*x.volume;rets=close.pct_change(fill_method=None)
    prev=x.close.shift();tr=pd.concat([x.high-x.low,(x.high-prev).abs(),(x.low-prev).abs()],axis=1).max(axis=1)
    f={"beta":betas,"adv20_dollar":float(amount.tail(20).mean()),"adv60_dollar":float(amount.tail(60).mean()),
       "amount_definition":"close * SIP volume; both joint split-adjusted; not exact intraday notional"}
    for n in (20,60):
        a=x.tail(n);r=rets.tail(n)
        f[f"atr_pct_{n}"]=float((tr.tail(n)/a.close).mean())
        f[f"realized_volatility_{n}"]=float(r.std(ddof=1)*np.sqrt(252))
        f[f"price_range_{n}"]=float(a.high.max()/a.low.min()-1)
        up=float(amount.tail(n)[r.to_numpy()>0].sum());down=float(amount.tail(n)[r.to_numpy()<0].sum())
        f[f"up_down_dollar_ratio_{n}"]=up/down if down>0 else None
        q=tech.tail(n+1)
        f[f"relative_qqq_return_{n}"]=float((close.iloc[-1]/close.iloc[-n-1])/(q.iloc[-1]/q.iloc[0])-1) if q.notna().all() and (q>0).all() else None
    baseline=float(amount.iloc[-126:-20].mean())
    f["recent_amount_to_baseline"]=f["adv20_dollar"]/baseline if baseline>0 else None
    return f


def _channel(f,tf,cfg):
    # Keep the reusable v1.1 fit; replace version-specific drift/clarity gates.
    fit_cfg=ChannelSettings(width_min_log=cfg.channel_width_min_log,width_max_log=cfg.channel_width_max_log,
        max_negative_drift=100.,max_positive_drift=100.,min_channel_quality=0.)
    c=_fit(f,tf,fit_cfg)
    if "tests" not in c:return c
    span=len(calendar().sessions_in_range(f.date.iloc[0],f.date.iloc[-1]))-1
    normalized=float(np.log1p(c["drift"])*cfg.drift_reference_sessions/max(1,span))
    swings=c["alternations"]/2
    retest=.5*min(1,c["support_touches"]/3)+.5*min(1,c["resistance_touches"]/3)
    parallel=max(0,1-c["parallel_error"]/.6)
    drift_quality=max(0,1-abs(normalized)/math.log1p(cfg.maximum_reference_drift))
    clarity=100*(.25*retest+.25*min(1,swings/2)+.20*parallel+.15*c["coverage"]+.15*drift_quality)
    tests={**c["tests"],"drift":math.log1p(cfg.minimum_reference_drift)<=normalized<=math.log1p(cfg.maximum_reference_drift),
           "alternation":swings>=cfg.min_full_swings,"quality":clarity>=cfg.minimum_clarity,
           "no_major_breakout":c["position"]<1.12}
    loc=((f.close-f.low)/(f.high-f.low).replace(0,np.nan)).iloc[c["completed_pivot_lows"]]
    rejection=float(loc.mean()) if loc.notna().any() else 0.
    return {**c,"tests":tests,"eligible":bool(all(tests.values())),"channel_clarity_score":float(clarity),
            "boundary_retest_quality":float(retest),"full_swing_count":swings,"channel_drift_normalized":normalized,
            "drift_reference_sessions":cfg.drift_reference_sessions,"lower_band_rejection_quality":rejection}


def channel_analysis(x,cfg):
    channels=[]
    for tf,freq,windows in [("weekly","W-FRI",cfg.weekly_windows),("monthly","ME",cfg.monthly_windows)]:
        a=_aggregate(x,freq)
        for n in windows:
            if n<=len(a):channels.append(_channel(a.tail(n).reset_index(drop=True),tf,cfg))
    valid=[c for c in channels if c["eligible"]]
    if not valid:return dict(qualified=False,reason="no_clear_channel",windows=channels)
    lower=np.log([c["lower"] for c in valid]);upper=np.log([c["upper"] for c in valid])
    width=float(np.median(upper-lower));band=float(max(np.ptp(lower),np.ptp(upper))/width)
    pos=float(np.ptp([c["position"] for c in valid]));drift=float(np.ptp([c["channel_drift_normalized"] for c in valid]))
    adjacent=False
    for tf,allowed in [("weekly",cfg.weekly_windows),("monthly",cfg.monthly_windows)]:
        present={c["window"] for c in valid if c["timeframe"]==tf}
        adjacent|=any(a in present and b in present for a,b in zip(allowed,allowed[1:]))
    stable=bool(adjacent and band<=cfg.max_band_disagreement and pos<=cfg.max_position_disagreement and drift<=cfg.max_drift_disagreement)
    stability=max(0.,1-max(band/cfg.max_band_disagreement,pos/cfg.max_position_disagreement,drift/cfg.max_drift_disagreement))
    return dict(qualified=stable,reason="stable_clear_channel" if stable else "channel_windows_disagree",
        lower=float(np.exp(np.median(lower))),upper=float(np.exp(np.median(upper))),
        clarity=float(np.mean([c["channel_clarity_score"] for c in valid])),multi_window_stability=float(stability),
        full_swing_count=float(np.median([c["full_swing_count"] for c in valid])),
        boundary_retest_quality=float(np.mean([c["boundary_retest_quality"] for c in valid])),
        lower_band_rejection_quality=float(np.mean([c["lower_band_rejection_quality"] for c in valid])),
        band_disagreement=band,position_disagreement=pos,drift_disagreement=drift,
        primary_timeframe=max(valid,key=lambda c:c["channel_clarity_score"])["timeframe"],windows=channels)


def daily_state(x,lower,upper,cfg):
    a=x.tail(30);cl=a.close.to_numpy();lo=a.low.to_numpy();hi=a.high.to_numpy();op=a.open.to_numpy()
    position=float(np.log(cl[-1]/lower)/np.log(upper/lower))
    daily_return=float(cl[-1]/cl[-2]-1);five_return=float(cl[-1]/cl[-6]-1)
    new_lows=int(np.sum(lo[-5:]<np.minimum.accumulate(lo[-6:-1])))
    red=np.maximum(op-cl,0)/cl;expanding=bool(np.mean(red[-3:])>1.2*np.mean(red[-8:-3]) and np.mean(red[-3:])>.02)
    falling=bool(cl[-1]<cl[-2]<cl[-3] or five_return<-.06 or new_lows>=3)
    below=bool(position<-cfg.breakdown_fraction or (cl[-2:]<lower*np.exp(-.03*np.log(upper/lower))).all())
    higher_low=bool(lo[-3:].min()>=lo[-8:-3].min()*.995)
    two_rising=bool(cl[-1]>cl[-2]>cl[-3])
    location=(cl[-3:]-lo[-3:])/np.maximum(hi[-3:]-lo[-3:],1e-12)
    close_improving=bool(float(np.mean(location))>=.55)
    above_ma=bool(cl[-1]>=np.mean(cl[-5:]))
    stable=bool(higher_low and two_rising and close_improving and above_ma and not falling and not expanding)
    extended=bool(daily_return>cfg.last_day_extension or five_return>cfg.five_day_extension)
    near=bool(0<=position<=cfg.preferred_position)
    secondary=bool(cfg.preferred_position<position<=cfg.maximum_watch_position)
    stage=("breakdown" if below else "not_near_support" if position>cfg.maximum_watch_position else
           "extended_wait" if extended else "early_reversal" if stable and near else "stabilization_pending")
    distance=max(0.,1-max(position,0)/cfg.maximum_watch_position) if position>=0 else 0.
    return dict(stage=stage,near_support=near,secondary_watch=secondary,channel_position=position,
        position_basis="log(C/L)/log(U/L)",stabilizing=stable,higher_low=higher_low,two_rising_closes=two_rising,
        improving_close_location=close_improving,above_five_day_mean=above_ma,continuous_new_lows=new_lows,
        falling=falling,expanding_red_bodies=expanding,breakdown=below,undercut=position<0,
        extended=extended,last_day_return=daily_return,five_day_return=five_return,
        pullback_from_20day_high=float(cl[-1]/hi[-20:].max()-1),
        rebound_from_recent_low=float(cl[-1]/lo[-20:].min()-1),
        mean_distance=float(cl[-1]/np.mean(cl[-10:])-1),entry_score=float(65*distance+35*stable))


def analyze(frame,asof,spy,qqq,evidence: MarketEvidence,cfg=None):
    cfg=cfg or Settings()
    base=dict(version=VERSION,asof=str(pd.Timestamp(asof).date()),market_qualified=False,
        structure_qualified=False,near_support=False,qualified=False,watch=False,rank_score=0.,
        reason_codes=[],market=None,channel=None,daily=None,preferred_market_tier=False,
        evidence=evidence.model_dump(),config_hash=fingerprint(asdict(cfg)))
    refusal=evidence.refusal()
    if refusal:return {**base,"reason_codes":[refusal]}
    # Future rows are removed before any quality check, return or aggregation.
    prefix=frame.loc[pd.to_datetime(frame.date)<=pd.Timestamp(asof)].copy()
    for column,expected in [("provider",evidence.source),("feed",evidence.feed),("adjustment",evidence.adjustment)]:
        if column in prefix and not prefix[column].eq(expected).all():return {**base,"reason_codes":["mixed_source_or_basis"]}
    try:
        x=_validate(prefix,asof,ChannelSettings(min_daily_bars=cfg.min_daily_bars))
        if list(x.date)!=list(calendar().sessions_in_range(x.date.iloc[0],asof)):
            raise ValueError("missing_exchange_sessions")
        if (x.volume%1!=0).any():raise ValueError("fractional_volume")
        f=market_features(x,spy,qqq,cfg,evidence.adjustment,evidence.source)
    except ValueError as error:return {**base,"reason_codes":[str(error)]}
    reasons=[];b=f["beta"]["spy_126"]
    if b["reason"]:reasons.append(b["reason"])
    if b["outliers"]:reasons.append("extreme_return_quarantine")
    if b["value"] is not None and b["value"]<cfg.beta_minimum:reasons.append("beta_below_minimum")
    if not math.isfinite(f["adv20_dollar"]) or f["adv20_dollar"]<cfg.adv20_minimum:reasons.append("liquidity_below_minimum")
    base.update(market=f)
    if reasons:return {**base,"reason_codes":reasons}
    preferred=bool(b["value"]>=cfg.preferred_beta and f["adv20_dollar"]>=cfg.preferred_adv20)
    channel=channel_analysis(x,cfg);base.update(market_qualified=True,preferred_market_tier=preferred,channel=channel)
    if not channel["qualified"]:return {**base,"reason_codes":[channel["reason"]]}
    daily=daily_state(x,channel["lower"],channel["upper"],cfg)
    watch=bool(daily["stage"] not in {"breakdown","not_near_support"})
    qualified=daily["stage"]=="early_reversal"
    score=.65*channel["clarity"]+.25*daily["entry_score"]+10*preferred
    reasons=[daily["stage"]]
    if daily["falling"]:reasons.append("falling_wait_not_entry")
    if daily["expanding_red_bodies"]:reasons.append("downside_acceleration")
    if daily["undercut"]:reasons.append("below_support_risk")
    return {**base,"structure_qualified":True,"near_support":daily["near_support"],"qualified":qualified,
        "watch":watch,"daily":daily,"rank_score":float(np.clip(score,0,100)),"reason_codes":reasons}


def candidate(result,*,security_id,symbol,name=None,provenance=None):
    state=("qualified" if result["qualified"] else "wait" if result["watch"] else "rejected")
    return Candidate(method="q2_parallel_channel",version=VERSION,decision_date=result["asof"],
        security_id=security_id,symbol=symbol,name=name,status=state,score=result["rank_score"],
        reason_codes=result["reason_codes"],subscores={"channel_clarity":(result["channel"] or {}).get("clarity",0.),
          "entry":(result["daily"] or {}).get("entry_score",0.)},
        window_metadata={"observed_through":result["asof"],"analysis":result},
        data_quality_flags=["CURRENT_LISTING_NOT_HISTORICAL_IDENTITY","SIP_VENDOR_ADJUSTMENT_NOT_EXCHANGE_CERTIFIED"] if result["evidence"]["scope"]=="current_listing" else [],
        provenance=provenance or {})


def rank(rows):
    """Preferred beta/liquidity tier first; a rejected row never enters ranking."""
    ordered=sorted((r for r in rows if r.status!="rejected"),key=lambda r:(
        not r.window_metadata["analysis"]["preferred_market_tier"],r.status!="qualified",-r.score,r.security_id))
    return [r.model_copy(update={"rank":i}) for i,r in enumerate(ordered,1)]
