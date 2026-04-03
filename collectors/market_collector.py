"""MarketCollector facade — orchestrates KR and US data collection."""

from __future__ import annotations

import logging

import pandas as pd

from .kr_collector import KRCollector
from .us_collector import USCollector
from .base import BaseCollector

logger = logging.getLogger(__name__)


def _parse_symbol_list(items: list) -> list[str]:
    """Extract ticker strings from a list that may contain dicts or plain strings.

    Supports both old format (``["AAPL", "MSFT"]``) and new format
    (``[{"ticker": "AAPL", "name": "Apple"}, ...]``).
    """
    result: list[str] = []
    for item in items:
        if isinstance(item, dict):
            result.append(item["ticker"])
        else:
            result.append(str(item))
    return result


def _parse_name_map(items: list) -> dict[str, str]:
    """Build a {ticker: display_name} mapping from a symbol/index list.

    For plain strings the ticker is used as the display name.
    """
    mapping: dict[str, str] = {}
    for item in items:
        if isinstance(item, dict):
            mapping[item["ticker"]] = item.get("name", item["ticker"])
        else:
            mapping[str(item)] = str(item)
    return mapping


class MarketCollector:
    """High-level facade that drives both KR and US collectors."""

    def __init__(self, config: dict):
        kr_cfg = config.get("markets", {}).get("kr", {})
        us_cfg = config.get("markets", {}).get("us", {})

        kr_watchlist = _parse_symbol_list(kr_cfg.get("watchlist", []))
        kr_indices = _parse_symbol_list(kr_cfg.get("indices", []))
        us_watchlist = _parse_symbol_list(us_cfg.get("watchlist", []))
        us_indices = _parse_symbol_list(us_cfg.get("indices", []))

        self.kr_collector = KRCollector(
            watchlist=kr_watchlist,
            indices=kr_indices,
        )
        self.us_collector = USCollector(
            watchlist=us_watchlist,
            indices=us_indices,
        )

        # Display-name mappings for indices (used when upserting to DB)
        self.index_name_map: dict[str, str] = {}
        self.index_name_map.update(_parse_name_map(kr_cfg.get("indices", [])))
        self.index_name_map.update(_parse_name_map(us_cfg.get("indices", [])))

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
        for idx_ticker in index_list:
            display_name = self.index_name_map.get(idx_ticker, idx_ticker)
            logger.info("[%s] Fetching index: %s (%s)", market_name, display_name, idx_ticker)
            try:
                df = collector.fetch_index(idx_ticker, start_date, end_date)
                if df.empty:
                    logger.warning(
                        "[%s] Empty index data for %s", market_name, display_name
                    )
                    failed.append(idx_ticker)
                else:
                    # Store under the display name so DB gets human-readable names
                    indices[display_name] = df
            except Exception:
                logger.exception(
                    "[%s] Failed to fetch index %s", market_name, display_name
                )
                failed.append(idx_ticker)

        logger.info(
            "[%s] Collection complete — %d stocks, %d indices, %d failed",
            market_name,
            len(stocks),
            len(indices),
            len(failed),
        )

        return {"stocks": stocks, "indices": indices, "failed": failed}
