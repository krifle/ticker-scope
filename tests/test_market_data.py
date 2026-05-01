from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd

from ticker_scope.data.market_data import MarketDataRequest, load_price_history


class MarketDataTests(unittest.TestCase):
    def test_load_price_history_normalizes_yfinance_multiindex_response(self) -> None:
        columns = pd.MultiIndex.from_product(
            [["Open", "High", "Low", "Close", "Volume"], ["TSLA"]]
        )
        raw_history = pd.DataFrame(
            [[10.0, 12.0, 9.0, 11.0, 1000], [11.0, 13.0, 10.0, 12.0, 1500]],
            index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
            columns=columns,
        )

        with patch("ticker_scope.data.market_data.yf.download", return_value=raw_history) as download:
            result = load_price_history(
                MarketDataRequest(
                    symbol="tsla",
                    interval="1d",
                    auto_adjust=True,
                    start=date(2024, 1, 2),
                    end=date(2024, 1, 4),
                )
            )

        download.assert_called_once()
        call_kwargs = download.call_args.kwargs
        self.assertEqual(call_kwargs["tickers"], "TSLA")
        self.assertEqual(call_kwargs["start"], date(2024, 1, 2))
        self.assertEqual(call_kwargs["end"], date(2024, 1, 4))
        self.assertNotIn("period", call_kwargs)

        self.assertEqual(list(result.columns), ["Date", "Open", "High", "Low", "Close", "Volume", "Symbol"])
        self.assertEqual(result["Symbol"].tolist(), ["TSLA", "TSLA"])
        self.assertEqual(result["Close"].tolist(), [11.0, 12.0])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["Date"]))

    def test_load_price_history_rejects_empty_response(self) -> None:
        with patch(
            "ticker_scope.data.market_data.yf.download",
            return_value=pd.DataFrame(),
        ):
            with self.assertRaisesRegex(ValueError, "No price history returned"):
                load_price_history(MarketDataRequest(symbol="TSLA"))


if __name__ == "__main__":
    unittest.main()
