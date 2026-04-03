"""Korean market data collector using pykrx."""

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


def _to_yyyymmdd(date_str: str) -> str:
    """Convert date string to YYYYMMDD format expected by pykrx.

    Accepts YYYY-MM-DD or YYYYMMDD.
    """
    return date_str.replace("-", "")


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
            cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            return df[cols]

        df = self._retry(_fetch)
        return self.validate_ohlcv(df)

    def fetch_index(
        self, index_name: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch index OHLCV from pykrx with retry and validation."""

        def _fetch() -> pd.DataFrame:
            from pykrx import stock  # lazy import

            sd = _to_yyyymmdd(start_date)
            ed = _to_yyyymmdd(end_date)
            df = stock.get_index_ohlcv_by_date(sd, ed, index_name)
            if df.empty:
                logger.warning("No index data returned for %s", index_name)
                return pd.DataFrame()
            df = df.rename(columns=_INDEX_COLUMNS)
            df.index.name = "date"
            cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            return df[cols]

        df = self._retry(_fetch)
        return self.validate_ohlcv(df)
