"""Shared exchange calendar; completed sessions, never calendar-day guesses."""
from functools import lru_cache
import pandas as pd
import exchange_calendars as xc


@lru_cache(maxsize=1)
def calendar():
    return xc.get_calendar('XNYS', start='2020-01-01', end='2028-12-31')


def completed_session(now=None):
    now = pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError('timezone-aware clock required')
    cal = calendar()
    schedule = cal.schedule
    eligible = schedule.index[schedule['close'] <= now]
    if len(eligible) == 0:
        raise ValueError('no completed exchange session')
    return eligible[-1].date().isoformat()


def require_session(day, *, now=None):
    stamp = pd.Timestamp(day)
    if stamp.tzinfo is not None or stamp != stamp.normalize() or not calendar().is_session(stamp):
        raise ValueError('a date of a real exchange session is required')
    if str(stamp.date()) > completed_session(now):
        raise ValueError('in-progress/future session is not allowed')
    return str(stamp.date())
