"""One-off: re-fetch real KRX names for kr watchlist and rewrite settings.yaml.

Root cause: a single `name:` line was accidentally dropped earlier in the file,
which cascaded so every subsequent ticker inherited the *next* ticker's name.
Rather than patch each line manually, rebuild the kr watchlist name field from
pykrx (the same source the collector uses at runtime).

Strategy: scan the YAML line-by-line. Whenever a `- ticker: NNNNNN` line is
followed by a `  name: ...` line, replace the name with
``stock.get_market_ticker_name(NNNNNN)``. Tickers with non-digit characters
(US symbols, KR indices like ``^KS11``) are skipped verbatim, so indices and
the us section are untouched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import FinanceDataReader as fdr
from pykrx import stock


TICKER_RE = re.compile(r"^(?P<indent>\s*)- ticker: (?P<q>'?)(?P<tk>\d{6})(?P=q)\s*$")
NAME_RE = re.compile(r"^(?P<indent>\s*)name: (?P<val>.*?)\s*$")


def _build_etf_map() -> dict[str, str]:
    try:
        df = fdr.StockListing("ETF/KR")
    except Exception:
        return {}
    return {str(row["Symbol"]).zfill(6): str(row["Name"]) for _, row in df.iterrows()}


def main() -> int:
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    lines = cfg_path.read_text(encoding="utf-8").splitlines()

    etf_map = _build_etf_map()

    changes: list[tuple[str, str, str]] = []
    unresolved: list[str] = []

    i = 0
    while i < len(lines) - 1:
        m_ticker = TICKER_RE.match(lines[i])
        if m_ticker:
            m_name = NAME_RE.match(lines[i + 1])
            if m_name:
                ticker = m_ticker.group("tk")
                try:
                    raw = stock.get_market_ticker_name(ticker)
                except Exception as exc:  # pragma: no cover - network/lookup failure
                    unresolved.append(f"{ticker}: {exc}")
                    i += 2
                    continue
                real_name = raw if isinstance(raw, str) and raw else None
                if not real_name:
                    real_name = etf_map.get(ticker)
                if not real_name:
                    unresolved.append(f"{ticker}: no name (got {type(raw).__name__})")
                    i += 2
                    continue
                current = m_name.group("val")
                if current != real_name:
                    changes.append((ticker, current, real_name))
                    lines[i + 1] = f"{m_name.group('indent')}name: {real_name}"
                i += 2
                continue
        i += 1

    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[fix_watchlist_names] updated {len(changes)} entries")
    for ticker, old, new in changes:
        print(f"  {ticker}: {old!r} -> {new!r}")
    if unresolved:
        print(f"[fix_watchlist_names] unresolved ({len(unresolved)}):")
        for line in unresolved:
            print(f"  {line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
