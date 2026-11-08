"""Personal Quant v1: public crypto market data and technical indicators.

Educational research only. This program does not place orders.
"""
from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
INTERVALS = ("15m", "1h", "4h", "1d")
SYMBOLS = ("BTCUSDT", "ETHUSDT")
COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]


def fetch_klines(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """Fetch the latest public spot candles; no API key is required."""
    if symbol not in SYMBOLS:
        raise ValueError(f"Unsupported symbol {symbol!r}. Choose from {', '.join(SYMBOLS)}.")
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported interval {interval!r}. Choose from {', '.join(INTERVALS)}.")
    if not 50 <= limit <= 1000:
        raise ValueError("limit must be between 50 and 1000.")

    query = urllib.parse.urlencode(
        {"symbol": symbol, "interval": interval, "limit": limit}
    )
    request = urllib.request.Request(
        f"{BASE_URL}?{query}",
        headers={"User-Agent": "PersonalQuant/0.1 (educational research)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            import json
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"行情服务返回 HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"无法连接 Binance 公共行情接口：{exc}. 请检查网络或稍后重试。"
        ) from exc

    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"{symbol} {interval} 没有收到有效 K 线数据：{payload!r}")

    frame = pd.DataFrame(payload, columns=COLUMNS)
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    numeric = [
        "open", "high", "low", "close", "volume", "quote_volume",
        "trades", "taker_buy_base", "taker_buy_quote",
    ]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    frame = frame.set_index("open_time").sort_index()
    # Exclude the still-forming candle to avoid using incomplete information.
    now = pd.Timestamp.now(tz="UTC")
    frame = frame.loc[frame["close_time"] < now]
    if frame.empty:
        raise RuntimeError("接口没有返回已收盘的 K 线，请稍后重试。")
    return frame


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Add common technical indicators; values are descriptive, not predictions."""
    result = frame.copy()
    close = result["close"]
    result["MA20"] = close.rolling(20).mean()
    result["MA60"] = close.rolling(60).mean()
    result["EMA12"] = close.ewm(span=12, adjust=False).mean()
    result["EMA26"] = close.ewm(span=26, adjust=False).mean()
    result["MACD"] = result["EMA12"] - result["EMA26"]
    result["MACD_signal"] = result["MACD"].ewm(span=9, adjust=False).mean()
    result["MACD_hist"] = result["MACD"] - result["MACD_signal"]

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result["RSI14"] = (100 - 100 / (1 + rs)).where(avg_loss.ne(0), 100.0)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["ATR14"] = true_range.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    return result


def market_observation(frame: pd.DataFrame) -> str:
    latest = frame.iloc[-1]
    close = float(latest["close"])
    ma20, ma60, rsi = latest["MA20"], latest["MA60"], latest["RSI14"]
    atr = latest["ATR14"]
    if pd.isna(ma20) or pd.isna(ma60):
        trend = "样本不足，暂不能判断均线趋势"
    elif close > ma20 > ma60:
        trend = "均线结构偏强（仅为历史数据描述）"
    elif close < ma20 < ma60:
        trend = "均线结构偏弱（仅为历史数据描述）"
    else:
        trend = "均线结构混合，趋势暂不明确"
    rsi_text = "N/A" if pd.isna(rsi) else f"{float(rsi):.2f}"
    return (
        f"最新已收盘价：{close:.4f}\n"
        f"MA20：{'N/A' if pd.isna(ma20) else f'{float(ma20):.4f}'}\n"
        f"MA60：{'N/A' if pd.isna(ma60) else f'{float(ma60):.4f}'}\n"
        f"RSI14：{rsi_text}\n"
        f"MACD：{float(latest['MACD']):.4f}\n"
        f"ATR14：{'N/A' if pd.isna(atr) else f'{float(atr):.4f}'}\n"
        f"观察：{trend}\n"
        "这不是经过回测的交易信号，也不构成投资建议。"
    )


def analyse_one(symbol: str, interval: str, limit: int) -> Path:
    prices = fetch_klines(symbol, interval, limit)
    analysis = add_indicators(prices)
    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol}_{interval}.csv"
    analysis.to_csv(output_path)

    print(f"\n{'=' * 56}")
    print(f"Personal Quant | {symbol} | {interval}")
    print(f"数据区间（UTC）：{analysis.index.min()} 至 {analysis.index.max()}")
    print(f"已收盘 K 线数量：{len(analysis)}")
    print(market_observation(analysis))
    print(f"CSV 已保存：{output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Personal Quant: BTC/ETH public market data and indicators"
    )
    parser.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    parser.add_argument("--interval", choices=INTERVALS, default="1h")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyse BTC and ETH on 15m, 1h, 4h and 1d (8 public requests).",
    )
    args = parser.parse_args()

    jobs = (
        [(symbol, interval) for symbol in SYMBOLS for interval in INTERVALS]
        if args.all
        else [(args.symbol, args.interval)]
    )
    failures = []
    for index, (symbol, interval) in enumerate(jobs):
        try:
            analyse_one(symbol, interval, args.limit)
        except Exception as exc:
            failures.append((symbol, interval, str(exc)))
            print(f"\n获取 {symbol} {interval} 失败：{exc}")
        if index < len(jobs) - 1:
            time.sleep(0.5)

    if failures:
        print("\n部分任务未完成：")
        for symbol, interval, message in failures:
            print(f"- {symbol} {interval}: {message}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
