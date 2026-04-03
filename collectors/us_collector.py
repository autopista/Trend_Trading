"""US market data collector using yfinance."""

import logging

import pandas as pd
import yfinance as yf

from .base import BaseCollector

logger = logging.getLogger(__name__)


class USCollector(BaseCollector):
    """Collect US market OHLCV data via yfinance."""

    def __init__(
        self,
        watchlist: list[str] | None = None,
        indices: list[str] | None = None,
    ):
        self.watchlist = watchlist or []
        self.indices = indices or []

    def get_watchlist(self) -> list[str]:
        return list(self.watchlist)

    def fetch_ohlcv(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch OHLCV from yfinance with retry and validation."""

        def _fetch() -> pd.DataFrame:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date)
            if df.empty:
                logger.warning("No data returned for %s", symbol)
                return pd.DataFrame()
            # Rename columns to lowercase standard names
            df = df.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            df.index.name = "date"
            # Keep only standard OHLCV columns
            cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            return df[cols]

        df = self._retry(_fetch)
        return self.validate_ohlcv(df)

    def fetch_index(
        self, index_name: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch index data — yfinance uses the same API for indices."""
        return self.fetch_ohlcv(index_name, start_date, end_date)
