"""Mean-variance (Markowitz) optimal portfolio over a universe (default DJIA 30).

Estimates the long-only maximum-Sharpe portfolio from the window's hourly
returns, allocates capital by those weights at the start, and holds.

Note: weights are estimated in-sample over the contest window, so this is an
idealized "mean-variance optimal" reference baseline rather than a tradeable
out-of-sample strategy. It is intentionally self-contained (numpy only).
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from dashboard.backend.llm_validator import DJIA_30

from .base import BaselineStrategy
from ._common import (
    build_price_cache,
    equity_curve_from_positions,
    market_timestamps,
    subset_bars,
)


class MeanVarianceStrategy(BaselineStrategy):
    key = "mean_variance"

    def required_symbols(self) -> List[str]:
        symbols = self.config.get("symbols")
        return list(symbols) if symbols else list(DJIA_30)

    def _optimal_weights(self, returns: np.ndarray) -> np.ndarray:
        """Long-only max-Sharpe (tangency) weights with rf=0.

        Uses the pseudo-inverse for numerical stability, clips short positions,
        and renormalizes. Falls back to equal weight when degenerate.
        """
        n = returns.shape[1]
        mu = returns.mean(axis=0)
        cov = np.cov(returns, rowvar=False)
        if cov.ndim == 0:
            cov = cov.reshape(1, 1)

        try:
            raw = np.linalg.pinv(cov) @ mu
        except np.linalg.LinAlgError:
            raw = np.ones(n)

        weights = np.clip(raw, 0.0, None)
        total = weights.sum()
        if not np.isfinite(total) or total <= 0:
            return np.ones(n) / n
        return weights / total

    def run(
        self,
        bars_by_symbol: Dict[str, pd.DataFrame],
        start_date: str,
        end_date: str,
        initial_capital: float,
    ) -> List[Dict[str, Any]]:
        symbols = self.required_symbols()
        bars_subset = subset_bars(bars_by_symbol, symbols)
        if not bars_subset:
            return []

        timestamps = market_timestamps(bars_subset)
        if not timestamps:
            return []

        price_cache = build_price_cache(bars_subset, timestamps)
        active_symbols = sorted(price_cache.keys())
        if not active_symbols:
            return []

        price_matrix = np.array(
            [[price_cache[sym][ts] for sym in active_symbols] for ts in timestamps],
            dtype=float,
        )
        if price_matrix.shape[0] < 3:
            return []

        returns = price_matrix[1:] / price_matrix[:-1] - 1.0
        weights = self._optimal_weights(returns)

        first_prices = price_matrix[0]
        positions: Dict[str, int] = {}
        cash = float(initial_capital)
        for idx, symbol in enumerate(active_symbols):
            price = first_prices[idx]
            if price <= 0:
                continue
            allocation = initial_capital * weights[idx]
            shares = int(allocation / price)
            if shares > 0:
                positions[symbol] = shares
                cash -= shares * price

        if not positions:
            return []

        self._num_positions = len(positions)
        print(
            f"\n   📋 Mean-variance baseline: {len(positions)} positions, "
            f"top weight {weights.max():.1%}"
        )
        return equity_curve_from_positions(positions, cash, price_cache, timestamps)

    def num_trades(self) -> int:
        return getattr(self, "_num_positions", 0)
