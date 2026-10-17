"""Write FAKE_synthetic_prices.csv: made-up prices for every configured ticker, for tests and demos.

    python tests/fixtures/make_fake_prices.py
"""
from __future__ import annotations

import csv
import random
from datetime import date
from pathlib import Path

from ingestion.config import expected_tickers
from ingestion.contracts import PRICE_COLUMNS
from ingestion.trading_calendar import sessions

OUT = Path(__file__).parent / "FAKE_synthetic_prices.csv"


def main() -> None:
    rng = random.Random(20261017)
    days = sessions("2026-09-21", date(2026, 10, 16))["session_date"]
    with OUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(PRICE_COLUMNS)
        for ticker in expected_tickers():
            is_index = ticker == "XJO"
            close = 9000.0 if is_index else rng.uniform(5, 150)
            for day in days:
                open_ = close * rng.uniform(0.99, 1.01)
                close = open_ * rng.uniform(0.98, 1.02)
                high = max(open_, close) * rng.uniform(1.0, 1.01)
                low = min(open_, close) * rng.uniform(0.99, 1.0)
                # The index has no traded volume or dividend adjustment.
                adj_close = "" if is_index else round(close * 0.97, 4)
                volume = "" if is_index else rng.randint(100_000, 5_000_000)
                writer.writerow([ticker, day.isoformat(), round(open_, 4), round(high, 4), round(low, 4),
                                 round(close, 4), adj_close, volume])


if __name__ == "__main__":
    main()
