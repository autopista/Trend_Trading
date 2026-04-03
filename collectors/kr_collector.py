"""Korean market data collector using pykrx."""

from __future__ import annotations

import logging

import pandas as pd

from .base import BaseCollector

logger = logging.getLogger(__name__)

# pykrx column name mapping (Korean -> English)
_OHLCV_COLUMNS = {
    "날짜": "date",
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
}

_INDEX_COLUMNS = {
    "날짜": "date",
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
}


def _to_yyyymmdd(d) -> str:
    """Convert date/str to YYYYMMDD format expected by pykrx."""
    if hasattr(d, "strftime"):
        return d.strftime("%Y%m%d")
    return str(d).replace("-", "")


class KRCollector(BaseCollector):
    """Collect Korean market OHLCV data via pykrx."""

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
        """Fetch OHLCV from pykrx with retry and validation."""

        def _fetch() -> pd.DataFrame:
            from pykrx import stock  # lazy import

            sd = _to_yyyymmdd(start_date)
            ed = _to_yyyymmdd(end_date)
            df = stock.get_market_ohlcv_by_date(sd, ed, symbol)
            if df.empty:
                logger.warning("No data returned for %s", symbol)
                return pd.DataFrame()
            df = df.rename(columns=_OHLCV_COLUMNS)
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
            return df[cols]

        df = self._retry(_fetch)
        return self.validate_ohlcv(df)

    def fetch_index(
        self, index_ticker: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch index OHLCV from pykrx with retry and validation.

        Args:
            index_ticker: KRX index ticker code (e.g. ``"1001"`` for KOSPI).
        """

        def _fetch() -> pd.DataFrame:
            from pykrx import stock  # lazy import

            sd = _to_yyyymmdd(start_date)
            ed = _to_yyyymmdd(end_date)
            df = stock.get_index_ohlcv_by_date(sd, ed, index_ticker)
            if df.empty:
                logger.warning("No index data returned for %s", index_ticker)
                return pd.DataFrame()
            # pykrx index OHLCV columns: 시가, 고가, 저가, 종가, 거래량
            # The index is already a DatetimeIndex (날짜).
            df = df.rename(columns=_INDEX_COLUMNS)
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
            return df[cols]

        df = self._retry(_fetch)
        return self.validate_ohlcv(df)
