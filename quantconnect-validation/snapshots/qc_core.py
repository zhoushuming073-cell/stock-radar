import numpy as np
import pandas as pd
def core_membership(day, members, bars, calendar, rules):
    """Past-only liquidity ranking, independent of later data and strategy P&L.

    Returns admitted IDs plus unresolved competitors. Even a single unresolved
    competitor can displace a rank; native readiness must bound this effect.
    """
    settings = rules['core']
    prior = [d for d in calendar if d < day]
    lookback = prior[-settings['minimum_history_sessions']:]
    ranked, unknown, rejected = ([], [], {})
    groups = dict(tuple(bars.loc[bars.date.astype(str).str[:10].isin(lookback)].groupby('security_id')))
    for member in members:
        sid = member['security_id']
        if member.get('listing_date') and member['listing_date'][:10] > day:
            rejected[sid] = 'future_listing'
            continue
        if member.get('security_type') != 'common':
            rejected[sid] = 'not_common'
            continue
        if member.get('listing_date') and len([d for d in lookback if d >= member['listing_date'][:10]]) < settings['minimum_history_sessions']:
            rejected[sid] = 'known_short_trading_history'
            continue
        group = groups.get(sid)
        if group is None or group.empty:
            unknown.append(sid)
            continue
        part = group.sort_values('date')
        last = part.iloc[-1]
        if str(last.date)[:10] == prior[-1] and float(last.close) < settings['price_floor']:
            rejected[sid] = 'known_prior_price_below_floor'
            continue
        recent_known = part.loc[part.date.astype(str).str[:10].isin(prior[-settings['dollar_volume_lookback']:])]
        dollars_known = recent_known.close.astype(float) * recent_known.volume.astype(float)
        if len(dollars_known) and np.isfinite(dollars_known).all() and (float(dollars_known.min()) < settings['minimum_daily_dollar_volume']):
            rejected[sid] = 'known_insufficient_daily_liquidity'
            continue
        if len(recent_known) == settings['dollar_volume_lookback'] and float(dollars_known.mean()) < settings['minimum_avg_dollar_volume']:
            rejected[sid] = 'known_insufficient_average_liquidity'
            continue
        if len(lookback) < settings['minimum_history_sessions'] or len(part) != len(lookback) or set(part.date.astype(str).str[:10]) != set(lookback) or part.date.duplicated().any():
            unknown.append(sid)
            continue
        v = part[['open', 'high', 'low', 'close', 'volume']].astype(float)
        if not np.isfinite(v).all().all() or (v.low <= 0).any() or (v.volume < 0).any() or (not v.open.between(v.low, v.high).all()) or (not v.close.between(v.low, v.high).all()):
            unknown.append(sid)
            continue
        recent = part.tail(settings['dollar_volume_lookback'])
        dollars = recent.close.astype(float) * recent.volume.astype(float)
        if float(dollars.mean()) < settings['minimum_avg_dollar_volume'] or float(dollars.min()) < settings['minimum_daily_dollar_volume']:
            rejected[sid] = 'known_insufficient_liquidity'
            continue
        ranked.append((sid, float(dollars.mean())))
    ranked.sort(key=lambda r: (-r[1], r[0]))
    return {'date': day, 'security_ids': [r[0] for r in ranked[:settings['target_size']]], 'unknown_security_ids': sorted(unknown), 'rejected': rejected, 'eligible_before_cap': len(ranked), 'possible_rank_displacement': min(len(unknown), settings['target_size']), 'causal_cutoff': prior[-1] if prior else None, 'definitive': not unknown}
