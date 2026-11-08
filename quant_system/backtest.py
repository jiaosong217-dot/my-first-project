"""Strategy comparison backtester for Personal Quant.

Long-only spot baseline. Signals are formed from completed candle closes and
executed at the next candle open. Fees and slippage are charged on position
changes. No live orders are sent. Funding, borrow costs, taxes and market impact
beyond the configured slippage are not modelled.
"""
from __future__ import annotations

import argparse
import math
from typing import Callable

import numpy as np
import pandas as pd

from quant_system.main import add_indicators, fetch_klines, INTERVALS, SYMBOLS


BARS_PER_YEAR = {
    "15m": 365 * 24 * 4,
    "1h": 365 * 24,
    "4h": 365 * 6,
    "1d": 365,
}


def build_target_positions(frame: pd.DataFrame, strategy: str) -> pd.Series:
    """Create close-time target positions (0 or 1), without using future data."""
    close = frame["close"]
    if strategy == "ma_trend":
        enter = (close > frame["MA20"]) & (frame["MA20"] > frame["MA60"])
        exit_ = close < frame["MA20"]
    elif strategy == "macd_trend":
        enter = (frame["MACD"] > frame["MACD_signal"]) & (close > frame["MA60"])
        exit_ = (frame["MACD"] < frame["MACD_signal"]) | (close < frame["MA60"])
    elif strategy == "rsi_reversion":
        enter = (frame["RSI14"] < 30) & (close < frame["MA20"])
        exit_ = frame["RSI14"] > 50
    elif strategy == "donchian_breakout":
        prior_high = close.shift(1).rolling(20).max()
        prior_low = close.shift(1).rolling(10).min()
        enter = close > prior_high
        exit_ = close < prior_low
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    positions = []
    holding = 0
    for i in range(len(frame)):
        if pd.isna(enter.iloc[i]) or pd.isna(exit_.iloc[i]):
            positions.append(0)
            continue
        if holding == 0 and bool(enter.iloc[i]):
            holding = 1
        elif holding == 1 and bool(exit_.iloc[i]):
            holding = 0
        positions.append(holding)
    return pd.Series(positions, index=frame.index, dtype=float, name=strategy)


def make_returns(
    frame: pd.DataFrame,
    close_time_positions: pd.Series,
    fee: float,
    slippage: float,
) -> pd.Series:
    """Apply prior-close signal at current open; measure current-open to next-open."""
    held = close_time_positions.shift(1).fillna(0.0)
    next_open_return = frame["open"].shift(-1).div(frame["open"]).sub(1.0)
    turnover = held.diff().abs()
    if len(turnover):
        turnover.iloc[0] = abs(float(held.iloc[0]))
    costs = turnover.fillna(0.0) * (fee + slippage)
    returns = (held * next_open_return) - costs
    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def trade_returns(strategy_returns: pd.Series, held_positions: pd.Series) -> list[float]:
    """Compound net bar returns into completed/ongoing long trades."""
    trades: list[float] = []
    active = False
    value = 1.0
    aligned_positions = held_positions.reindex(strategy_returns.index).fillna(0.0)
    for timestamp, ret in strategy_returns.items():
        position = float(aligned_positions.loc[timestamp])
        if position > 0 and not active:
            active, value = True, 1.0
        if active:
            value *= 1.0 + float(ret)
        if active and position == 0:
            trades.append(value - 1.0)
            active = False
    if active:
        trades.append(value - 1.0)
    return trades


def calculate_metrics(
    returns: pd.Series,
    positions: pd.Series,
    interval: str,
) -> dict[str, float | int]:
    if returns.empty:
        return {
            "total_return_pct": 0.0, "annualized_return_pct": 0.0,
            "max_drawdown_pct": 0.0, "sharpe": 0.0, "profit_factor": 0.0,
            "win_rate_pct": 0.0, "trades": 0, "exposure_pct": 0.0,
        }

    equity = (1.0 + returns).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    years = max(len(returns) / BARS_PER_YEAR[interval], 1.0 / BARS_PER_YEAR[interval])
    annualized = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if equity.iloc[-1] > 0 else -1.0
    drawdown = equity / equity.cummax() - 1.0
    volatility = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    sharpe = (
        float(returns.mean() / volatility * math.sqrt(BARS_PER_YEAR[interval]))
        if volatility > 0 else 0.0
    )
    trades = trade_returns(returns, positions)
    winners = [x for x in trades if x > 0]
    losers = [x for x in trades if x < 0]
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    return {
        "total_return_pct": total_return * 100,
        "annualized_return_pct": annualized * 100,
        "max_drawdown_pct": float(drawdown.min()) * 100,
        "sharpe": sharpe,
        "profit_factor": profit_factor,
        "win_rate_pct": (len(winners) / len(trades) * 100) if trades else 0.0,
        "trades": len(trades),
        "exposure_pct": float((positions > 0).mean()) * 100,
    }


def run_backtest(
    raw: pd.DataFrame,
    interval: str,
    fee: float,
    slippage: float,
    split: float,
) -> pd.DataFrame:
    """Compare strategies in-sample and chronologically held-out out-of-sample."""
    frame = add_indicators(raw)
    strategies = ("ma_trend", "macd_trend", "rsi_reversion", "donchian_breakout")
    split_at = int(len(frame) * split)
    rows = []

    for strategy in strategies:
        target = build_target_positions(frame, strategy)
        held = target.shift(1).fillna(0.0)
        returns = make_returns(frame, target, fee, slippage)
        # Keep the chronological split. The first held-out bar is flat so no
        # position opened in training is carried into the test period.
        is_returns = returns.iloc[: max(0, split_at - 1)]
        is_positions = held.reindex(is_returns.index).fillna(0.0)
        oos_returns = returns.iloc[max(0, split_at - 1):]
        oos_positions = held.reindex(oos_returns.index).fillna(0.0).copy()
        if len(oos_positions):
            first = oos_positions.index[0]
            oos_positions.loc[first] = 0.0
            oos_returns = make_returns(
                frame.loc[oos_returns.index[0]:],
                target.loc[oos_returns.index[0]:].where(
                    target.index >= oos_returns.index[0], 0.0
                ),
                fee,
                slippage,
            )
            oos_positions = target.reindex(oos_returns.index).shift(1).fillna(0.0)

        for sample, sample_returns, sample_positions in (
            ("in_sample", is_returns, is_positions),
            ("out_of_sample", oos_returns, oos_positions),
        ):
            metrics = calculate_metrics(sample_returns, sample_positions, interval)
            rows.append({"strategy": strategy, "sample": sample, **metrics})

    # Buy-and-hold is a benchmark, with entry and exit transaction costs.
    benchmark_target = pd.Series(1.0, index=frame.index)
    benchmark_returns = make_returns(frame, benchmark_target, fee, slippage)
    for sample, sample_returns in (
        ("in_sample", benchmark_returns.iloc[: max(0, split_at - 1)]),
        ("out_of_sample", benchmark_returns.iloc[max(0, split_at - 1):]),
    ):
        sample_positions = pd.Series(1.0, index=sample_returns.index)
        metrics = calculate_metrics(sample_returns, sample_positions, interval)
        rows.append({"strategy": "buy_and_hold", "sample": sample, **metrics})

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare simple crypto strategies after costs")
    parser.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    parser.add_argument("--interval", choices=INTERVALS, default="1h")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--fee", type=float, default=0.001, help="Fee per side, e.g. 0.001 = 0.10%%")
    parser.add_argument("--slippage", type=float, default=0.0005, help="Slippage per side, e.g. 0.0005 = 0.05%%")
    parser.add_argument("--split", type=float, default=0.7, help="Chronological in-sample fraction")
    args = parser.parse_args()

    if not 0.5 <= args.split <= 0.9:
        parser.error("--split must be between 0.5 and 0.9")
    if args.fee < 0 or args.slippage < 0:
        parser.error("--fee and --slippage must be non-negative")

    raw = fetch_klines(args.symbol, args.interval, args.limit)
    report = run_backtest(raw, args.interval, args.fee, args.slippage, args.split)
    output_dir = "reports"
    import os
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/{args.symbol}_{args.interval}_backtest.csv"
    report.to_csv(output_path, index=False)

    print(f"\nPersonal Quant Strategy Lab | {args.symbol} | {args.interval}")
    print(f"Bars: {len(raw)} | Fee/side: {args.fee:.4%} | Slippage/side: {args.slippage:.4%}")
    print(f"Chronological split: {args.split:.0%} in-sample / {1 - args.split:.0%} out-of-sample")
    print(report.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"\nReport saved: {output_path}")
    print("\nImportant: preliminary backtest only; not a profit guarantee. Spot long-only baseline; funding/borrow costs are not modelled.")


if __name__ == "__main__":
    main()
