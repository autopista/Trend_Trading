"""Main pipeline — 4-phase execution for Trend Trading system.

Phases:
    1. Data collection via MarketCollector → upsert to DB
    2. Livermore analysis (MarketKey, PivotDetector, VolumeAnalyzer) → upsert states
    3. Signal generation → save signals, send Telegram alerts
    4. Portfolio update (track open trades)

Usage:
    python update_all.py --market kr --days 90
    python update_all.py --market us --phase 2
    python update_all.py --phase 1 --days 180
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv

from collectors.market_collector import MarketCollector, _parse_symbol_list
from db.database import get_engine, get_session, init_db
from db.models import Signal, Trade
from db.repository import (
    get_all_symbols,
    get_open_trades,
    get_prices,
    get_signals_by_date,
    save_signal,
    upsert_livermore_state,
    upsert_market_index,
    upsert_prices,
)
from livermore_engine.market_key import MarketKey
from livermore_engine.pivot_points import PivotDetector
from livermore_engine.trend_analyzer import TrendAnalyzer
from livermore_engine.volume_analysis import VolumeAnalyzer
from signals.signal_generator import SignalGenerator
from signals.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load settings from config/settings.yaml."""
    config_path = Path(__file__).parent / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _configure_logging() -> None:
    """Set up root logger with timestamps."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Phase 1 — Data Collection
# ---------------------------------------------------------------------------

def run_phase1(config: dict, market: str, start_date: str, end_date: str) -> dict:
    """Collect market data and upsert into DB.

    Returns:
        Collection results dict from MarketCollector.
    """
    logger.info("═══ Phase 1: Data Collection (%s) ═══", market)

    collector = MarketCollector(config)
    results = collector.collect_all(start_date, end_date, market=market)

    session = get_session()
    try:
        for mkt, data in results.items():
            # Upsert stock prices
            for symbol, df in data.get("stocks", {}).items():
                upsert_prices(session, df, symbol, mkt)
                logger.info("Upserted %d rows for %s (%s)", len(df), symbol, mkt)

            # Upsert index data — store OHLCV in Price table (for TrendAnalyzer)
            # and daily close value in MarketIndex (for dashboard summary cards).
            for idx_ticker, df in data.get("indices", {}).items():
                display_name = collector.index_name_map.get(idx_ticker, idx_ticker)
                upsert_prices(session, df, idx_ticker, mkt)
                for _, row in df.iterrows():
                    upsert_market_index(
                        session,
                        index_name=display_name,
                        market=mkt,
                        dt=row["date"],
                        value=float(row["close"]),
                        change_pct=float(row.get("change_pct", 0)) if "change_pct" in row.index else None,
                    )
                logger.info("Upserted %d index rows for %s (%s)", len(df), display_name, idx_ticker)

            if data.get("failed"):
                logger.warning("[%s] Failed symbols: %s", mkt, data["failed"])
    finally:
        session.close()

    return results


# ---------------------------------------------------------------------------
# Phase 2 — Livermore Analysis
# ---------------------------------------------------------------------------

def run_phase2(config: dict, market: str, start_date: str, end_date: str) -> None:
    """Run Livermore Market Key analysis and upsert states."""
    logger.info("═══ Phase 2: Livermore Analysis (%s) ═══", market)

    livermore_cfg = config.get("livermore", {})
    mk = MarketKey(pivot_threshold_pct=livermore_cfg.get("pivot_threshold_pct", 5.0))

    session = get_session()
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)

        # Analyze ALL symbols in DB for this market (not just watchlist)
        all_symbols = get_all_symbols(session, market)
        logger.info("Found %d symbols in DB for %s", len(all_symbols), market)

        for symbol in all_symbols:
            prices = get_prices(session, symbol, sd, ed)
            if len(prices) < 5:
                logger.warning("Insufficient data for %s — skipping", symbol)
                continue

            ohlcv = pd.DataFrame([
                {
                    "date": p.date,
                    "open": p.open,
                    "high": p.high,
                    "low": p.low,
                    "close": p.close,
                    "volume": p.volume,
                }
                for p in prices
            ])

            result = mk.analyze(ohlcv)

            for _, row in result.iterrows():
                upsert_livermore_state(
                    session,
                    symbol=symbol,
                    market=market,
                    dt=row["date"],
                    column_state=row["column_state"],
                    reference_pivot_price=float(row["reference_pivot_price"]),
                    trend_direction=row["trend_direction"],
                    trend_strength=float(row["trend_strength"]),
                    trend_duration_days=int(row["trend_duration_days"]),
                )

            logger.info("Analyzed %s — %d states saved", symbol, len(result))
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Phase 3 — Signal Generation
# ---------------------------------------------------------------------------

def run_phase3(
    config: dict,
    market: str,
    start_date: str,
    end_date: str,
    notifier: TelegramNotifier,
) -> list[dict]:
    """Generate signals and send Telegram alerts.

    Returns:
        List of signal dicts produced.
    """
    logger.info("═══ Phase 3: Signal Generation (%s) ═══", market)

    livermore_cfg = config.get("livermore", {})
    signals_cfg = config.get("signals", {})

    mk = MarketKey(pivot_threshold_pct=livermore_cfg.get("pivot_threshold_pct", 5.0))
    pivot_detector = PivotDetector(
        lookback_days=livermore_cfg.get("lookback_days", 20),
        volume_surge_ratio=livermore_cfg.get("volume_surge_ratio", 1.5),
        confirm_days=livermore_cfg.get("false_breakout_confirm_days", 2),
    )
    volume_analyzer = VolumeAnalyzer(
        lookback_days=livermore_cfg.get("lookback_days", 20),
        surge_ratio=livermore_cfg.get("volume_surge_ratio", 1.5),
    )
    trend_analyzer = TrendAnalyzer(
        pivot_threshold_pct=livermore_cfg.get("pivot_threshold_pct", 5.0),
    )
    signal_gen = SignalGenerator(
        min_confidence=signals_cfg.get("min_confidence", 60),
        confirm_days=livermore_cfg.get("false_breakout_confirm_days", 2),
    )

    market_cfg = config.get("markets", {}).get(market, {})
    indices = _parse_symbol_list(market_cfg.get("indices", []))

    session = get_session()
    all_signals: list[dict] = []

    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)

        # Determine market direction from the first index
        market_direction = "neutral"
        if indices:
            idx_prices = get_prices(session, indices[0], sd, ed)
            if len(idx_prices) >= 5:
                idx_ohlcv = pd.DataFrame([
                    {
                        "date": p.date,
                        "open": p.open,
                        "high": p.high,
                        "low": p.low,
                        "close": p.close,
                        "volume": p.volume,
                    }
                    for p in idx_prices
                ])
                ctx = trend_analyzer.analyze_market(idx_ohlcv)
                market_direction = ctx.trend_direction

        logger.info("Market direction: %s", market_direction)

        # Generate signals for ALL symbols in DB (not just watchlist),
        # but exclude market indices — they're analyzed only for direction.
        index_set = set(indices)
        all_symbols = [s for s in get_all_symbols(session, market) if s not in index_set]
        logger.info("Generating signals for %d symbols", len(all_symbols))

        for symbol in all_symbols:
            prices = get_prices(session, symbol, sd, ed)
            if len(prices) < 25:
                logger.warning("Insufficient data for %s — skipping signal gen", symbol)
                continue

            ohlcv = pd.DataFrame([
                {
                    "date": p.date,
                    "open": p.open,
                    "high": p.high,
                    "low": p.low,
                    "close": p.close,
                    "volume": p.volume,
                }
                for p in prices
            ])

            mk_result = mk.analyze(ohlcv)
            pivots = pivot_detector.detect(ohlcv)
            vol = volume_analyzer.analyze(ohlcv)

            if mk_result.empty or pivots.empty or vol.empty:
                continue

            # RSI (simple 14-period)
            deltas = ohlcv["close"].diff()
            gain = deltas.clip(lower=0).rolling(14).mean()
            loss = (-deltas.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, float("nan"))
            rsi_series = 100 - (100 / (1 + rs))
            rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

            results = {
                "market_key": mk_result,
                "pivots": pivots,
                "volume": vol,
                "price": float(ohlcv["close"].iloc[-1]),
                "rsi": rsi,
            }

            signals = signal_gen.generate(symbol, results, market_direction)

            for sig in signals:
                # Persist to DB
                signal_obj = Signal(
                    symbol=sig["symbol"],
                    market=market,
                    date=ed,
                    signal_type=sig["signal_type"],
                    price=sig["price"],
                    target_price=sig.get("target_price"),
                    stop_price=sig.get("stop_price"),
                    reason=sig["reason"],
                    confidence=sig["confidence"],
                    notified=False,
                )
                try:
                    save_signal(session, signal_obj)
                except Exception:
                    logger.exception("Failed to save signal for %s", symbol)
                    session.rollback()

                # Telegram notification for buy/sell signals
                if sig["signal_type"] in ("buy", "sell"):
                    try:
                        asyncio.get_event_loop().run_until_complete(
                            notifier.send_signal(sig, market)
                        )
                    except RuntimeError:
                        asyncio.run(notifier.send_signal(sig, market))
                    except Exception:
                        logger.exception("Telegram notification failed for %s", symbol)

            all_signals.extend(signals)
            logger.info(
                "Generated %d signal(s) for %s", len(signals), symbol
            )

    finally:
        session.close()

    all_signals = signal_gen.prioritize(all_signals)
    logger.info("Phase 3 complete — %d total signals", len(all_signals))

    # Daily heartbeat — confirm pipeline ran end-to-end even when no buy/sell.
    try:
        asyncio.get_event_loop().run_until_complete(
            notifier.notify_pipeline_complete(market, all_signals)
        )
    except RuntimeError:
        asyncio.run(notifier.notify_pipeline_complete(market, all_signals))
    except Exception:
        logger.exception("Telegram pipeline-complete notification failed")

    return all_signals


# ---------------------------------------------------------------------------
# Phase 4 — Portfolio Update
# ---------------------------------------------------------------------------

def run_phase4(config: dict, market: str) -> None:
    """Update portfolio by checking open trades against current prices."""
    logger.info("═══ Phase 4: Portfolio Update (%s) ═══", market)

    session = get_session()
    try:
        open_trades: list[Trade] = list(get_open_trades(session, market=market))

        if not open_trades:
            logger.info("No open trades for %s", market)
            return

        today = date.today()
        for trade in open_trades:
            prices = get_prices(session, trade.symbol, today, today)
            if not prices:
                logger.warning("No price data today for %s", trade.symbol)
                continue

            current_price = prices[-1].close

            # Check stop-loss
            if trade.signal and trade.signal.stop_price:
                if current_price <= trade.signal.stop_price:
                    trade.status = "closed"
                    trade.exit_date = today
                    trade.exit_price = current_price
                    trade.pnl = (current_price - trade.entry_price) * trade.quantity
                    trade.pnl_pct = (
                        (current_price - trade.entry_price) / trade.entry_price * 100
                    )
                    logger.info(
                        "Stop-loss triggered for %s — PnL: %.2f%%",
                        trade.symbol, trade.pnl_pct,
                    )

            # Check target
            if trade.signal and trade.signal.target_price:
                if current_price >= trade.signal.target_price:
                    trade.status = "closed"
                    trade.exit_date = today
                    trade.exit_price = current_price
                    trade.pnl = (current_price - trade.entry_price) * trade.quantity
                    trade.pnl_pct = (
                        (current_price - trade.entry_price) / trade.entry_price * 100
                    )
                    logger.info(
                        "Target reached for %s — PnL: %.2f%%",
                        trade.symbol, trade.pnl_pct,
                    )

        session.commit()
        logger.info("Portfolio update complete — %d trades reviewed", len(open_trades))
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and run the pipeline."""
    _configure_logging()

    # Load .env from config/
    env_path = Path(__file__).parent / "config" / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info("Loaded environment from %s", env_path)

    parser = argparse.ArgumentParser(description="Trend Trading — 4-phase pipeline")
    parser.add_argument(
        "--market",
        choices=["kr", "us"],
        default=None,
        help="Market to process (default: both)",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="Run only this phase (default: all)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days of history to collect (default: 365)",
    )
    args = parser.parse_args()

    config = _load_config()
    init_db()

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=args.days)).isoformat()

    markets = [args.market] if args.market else ["kr", "us"]
    notifier = TelegramNotifier()

    for mkt in markets:
        logger.info("━━━━ Processing market: %s ━━━━", mkt.upper())

        phases_to_run = [args.phase] if args.phase else [1, 2, 3, 4]

        # Phase 1
        if 1 in phases_to_run:
            try:
                run_phase1(config, mkt, start_date, end_date)
            except Exception:
                logger.exception("Phase 1 failed for %s — skipping remaining phases", mkt)
                try:
                    asyncio.run(
                        notifier.send_error(f"Phase 1 ({mkt.upper()}) 데이터 수집 실패")
                    )
                except Exception:
                    logger.exception("Failed to send error notification")
                continue  # skip remaining phases for this market

        # Phase 2
        if 2 in phases_to_run:
            try:
                run_phase2(config, mkt, start_date, end_date)
            except Exception:
                logger.exception("Phase 2 failed for %s", mkt)

        # Phase 3
        if 3 in phases_to_run:
            try:
                run_phase3(config, mkt, start_date, end_date, notifier)
            except Exception:
                logger.exception("Phase 3 failed for %s", mkt)

        # Phase 4
        if 4 in phases_to_run:
            try:
                run_phase4(config, mkt)
            except Exception:
                logger.exception("Phase 4 failed for %s", mkt)

    logger.info("═══ Pipeline complete ═══")


if __name__ == "__main__":
    main()
