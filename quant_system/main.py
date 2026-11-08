"""First Personal Quant prototype: fetch daily prices and calculate indicators.

This is an educational research tool. It does not place orders or provide investment advice.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder-style exponential smoothing."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    relative_strength = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative_strength))
    return rsi.where(avg_loss.ne(0), 100.0)


def load_prices(ticker: str, period: str) -> pd.DataFrame:
    """Download daily market data from Yahoo Finance via yfinance."""
    frame = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if frame.empty:
        raise RuntimeError(
            f"No price data returned for {ticker!r}. Check the symbol, network, "
            "and data-source availability."
        )

    # yfinance may return MultiIndex columns even for a single ticker.
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)

    required = {"Close"}
    if not required.issubset(frame.columns):
        raise RuntimeError(f"Downloaded data is missing required columns: {required}")

    frame = frame.copy()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame = frame.dropna(subset=["Close"])
    return frame


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Add basic trend and momentum indicators."""
    result = frame.copy()
    result["MA20"] = result["Close"].rolling(20).mean()
    result["MA60"] = result["Close"].rolling(60).mean()
    result["RSI14"] = calculate_rsi(result["Close"], 14)
    return result


def describe_market(frame: pd.DataFrame) -> str:
    """Return a descriptive observation, not an executable trade instruction."""
    latest = frame.iloc[-1]
    close = float(latest["Close"])
    ma20 = latest["MA20"]
    ma60 = latest["MA60"]
    rsi = latest["RSI14"]

    if pd.isna(ma20) or pd.isna(ma60):
        trend = "数据长度不足，暂不能判断 MA20/MA60 趋势"
    elif close > ma20 and ma20 > ma60:
        trend = "价格高于 MA20，且 MA20 高于 MA60：偏强趋势观察"
    elif close < ma20 and ma20 < ma60:
        trend = "价格低于 MA20，且 MA20 低于 MA60：偏弱趋势观察"
    else:
        trend = "均线关系不一致：暂列为震荡或趋势不明确"

    rsi_text = "暂不可用" if pd.isna(rsi) else f"{float(rsi):.2f}"
    return (
        f"最新收盘价：{close:.4f}\n"
        f"MA20：{'N/A' if pd.isna(ma20) else f'{float(ma20):.4f}'}\n"
        f"MA60：{'N/A' if pd.isna(ma60) else f'{float(ma60):.4f}'}\n"
        f"RSI14：{rsi_text}\n"
        f"市场观察：{trend}\n"
        "注意：这是基于历史日线的描述性指标，不是买卖建议或经过验证的策略信号。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal Quant - first research prototype")
    parser.add_argument("--ticker", default="SPY", help="Market symbol, e.g. SPY, AAPL, BTC-USD")
    parser.add_argument("--period", default="1y", help="History period supported by the data source, e.g. 6mo, 1y, 2y, 5y")
    args = parser.parse_args()

    prices = load_prices(args.ticker, args.period)
    analysis = add_indicators(prices)

    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_ticker = args.ticker.replace("/", "_").replace("=", "_")
    output_path = output_dir / f"{safe_ticker}_daily.csv"
    analysis.to_csv(output_path)

    print(f"\nPersonal Quant | {args.ticker} | {args.period}")
    print(f"数据区间：{analysis.index.min()} 至 {analysis.index.max()}")
    print(f"记录数量：{len(analysis)}")
    print("\n最新市场观察")
    print(describe_market(analysis))
    print(f"\n数据已保存至：{output_path}")


if __name__ == "__main__":
    main()
