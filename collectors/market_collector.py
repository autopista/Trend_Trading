"""MarketCollector facade — orchestrates KR and US data collection."""

import logging

import pandas as pd

from .kr_collector import KRCollector
from .us_collector import USCollector
from .base import BaseCollector

logger = logging.getLogger(__name__)


class MarketCollector:
    """High-level facade that drives both KR and US collectors."""

    def __init__(self, config: dict):
        kr_cfg = config.get("markets", {}).get("kr", {})
        us_cfg = config.get("markets", {}).get("us", {})

        self.kr_collector = KRCollector(
            watchlist=kr_cfg.get("watchlist", []),
            indices=kr_cfg.get("indices", []),
        )
        self.us_collector = USCollector(
            watchlist=us_cfg.get("watchlist", []),
            indices=us_cfg.get("indices", []),
        )

    def collect_all(
        self,
        start_date: str,
        end_date: str,
        market: str | None = None,
    ) -> dict:
        """Collect data for specified market(s).

        Args:
            start_date: Start date (YYYY-MM-DD or YYYYMMDD).
            end_date: End date (YYYY-MM-DD or YYYYMMDD).
            market: "kr", "us", or None for both.

        Returns:
            Dict with keys "kr" and/or "us", each containing
            {"stocks": {symbol: df}, "indices": {name: df}, "failed": [symbols]}.
        """
        results: dict = {}

        if market is None or market == "kr":
            logger.info("Collecting KR market data...")
            results["kr"] = self._collect_market(
                self.kr_collector, "kr", start_date, end_date
            )

        if market is None or market == "us":
            logger.info("Collecting US market data...")
            results["us"] = self._collect_market(
                self.us_collector, "us", start_date, end_date
            )

        return results

    def _collect_market(
        self,
        collector: BaseCollector,
        market_name: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        """Collect all stocks and indices for a single market.

        Returns:
            {"stocks": {symbol: df}, "indices": {name: df}, "failed": [symbols]}
        """
        stocks: dict[str, pd.DataFrame] = {}
        indices: dict[str, pd.DataFrame] = {}
        failed: list[str] = []

        watchlist = collector.get_watchlist()
        total = len(watchlist)
        for i, symbol in enumerate(watchlist, 1):
            logger.info(
                "[%s] Fetching stock %d/%d: %s", market_name, i, total, symbol
            )
            try:
                df = collector.fetch_ohlcv(symbol, start_date, end_date)
                if df.empty:
                    logger.warning("[%s] Empty data for %s", market_name, symbol)
                    failed.append(symbol)
                else:
                    stocks[symbol] = df
            except Exception:
                logger.exception("[%s] Failed to fetch %s", market_name, symbol)
                failed.append(symbol)

        # Determine index list from the collector
        index_list: list[str] = getattr(collector, "indices", [])
        for idx_name in index_list:
            logger.info("[%s] Fetching index: %s", market_name, idx_name)
            try:
                df = collector.fetch_index(idx_name, start_date, end_date)
                if df.empty:
                    logger.warning(
                        "[%s] Empty index data for %s", market_name, idx_name
                    )
                    failed.append(idx_name)
                else:
                    indices[idx_name] = df
            except Exception:
                logger.exception(
                    "[%s] Failed to fetch index %s", market_name, idx_name
                )
                failed.append(idx_name)

        logger.info(
            "[%s] Collection complete — %d stocks, %d indices, %d failed",
            market_name,
            len(stocks),
            len(indices),
            len(failed),
        )

        return {"stocks": stocks, "indices": indices, "failed": failed}
