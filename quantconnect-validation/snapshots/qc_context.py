"""The limited, defensive signal-day view exposed to plugins."""
from __future__ import annotations
import pandas as pd

class StrategyContext:
    __slots__ = ('signal_date', '_frame')

    def __init__(self, signal_date: pd.Timestamp, frame: pd.DataFrame) -> None:
        if not isinstance(frame, pd.DataFrame):
            raise TypeError('StrategyContext.frame must be a pandas DataFrame')
        timestamp = pd.Timestamp(signal_date)
        if pd.isna(timestamp):
            raise ValueError('signal_date must be a valid timestamp')
        object.__setattr__(self, 'signal_date', timestamp)
        object.__setattr__(self, '_frame', frame.copy(deep=True))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError('StrategyContext is read-only')

    @property
    def frame(self) -> pd.DataFrame:
        """Return a fresh copy so plugins cannot mutate the host's frame."""
        return self._frame.copy(deep=True)
