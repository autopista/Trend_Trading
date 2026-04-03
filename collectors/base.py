"""Base collector abstract class with validation and retry logic."""

from __future__ import annotations

import abc
import logging
import time

import pandas as pd

logger = logging.getLogger(__name__)


class BaseCollector(abc.ABC):
    """Abstract base class for market data collectors."""

    MAX_RETRIES = 3
    BASE_DELAY = 2

    @abc.abstractmethod
    def fetch_ohlcv(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch OHLCV data for a single symbol."""

    @abc.abstractmethod
    def fetch_index(
        self, index_name: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch OHLCV data for a market index."""

    @abc.abstractmethod
    def get_watchlist(self) -> list[str]:
        """Return the list of symbols to track."""

    def validate_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean OHLCV data.

        - Drops rows with any NaN values.
        - Fixes invalid OHLC relationships (low > open, low > close, high < open, high < close).
        - Sets negative volume to 0.
        """
        if df.empty:
            return df

        df = df.dropna().copy()

        if df.empty:
            return df

        # Fix OHLC relationships: ensure low <= min(open, close) and high >= max(open, close)
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                logger.warning("Missing column '%s' in OHLCV data", col)
                return df

        df["low"] = df[["low", "open", "close"]].min(axis=1)
        df["high"] = df[["high", "open", "close"]].max(axis=1)

        # Negative volume -> 0
        if "volume" in df.columns:
            df.loc[df["volume"] < 0, "volume"] = 0

        return df

    def _retry(self, func, *args, **kwargs):
        """Call *func* with exponential backoff retry on failure."""
        last_exc = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.MAX_RETRIES:
                    delay = self.BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s — retrying in %ds",
                        attempt,
                        self.MAX_RETRIES,
                        func.__name__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "All %d attempts failed for %s: %s",
                        self.MAX_RETRIES,
                        func.__name__,
                        exc,
                    )
        raise last_exc  # type: ignore[misc]
