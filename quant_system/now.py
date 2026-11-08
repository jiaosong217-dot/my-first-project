"""Concise BTC/ETH rule signals; public data only, no orders or profit claims.

Run: python -m quant_system.now
This entry point reuses signals.py's indicator formulae and fixed trading rules.
It is NOT a performance-validated strategy or the old spot backtest's result.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

DURATIONS = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1d"}
SYMBOLS = ("BTCUSDT", "ETHUSDT")


@dataclass(frozen=True)
class Decision:
    symbol: str
    state: str
    reason: str
    closed_at: pd.Timestamp | None = None
    expires_at: pd.Timestamp | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None


def validate_frame(frame: pd.DataFrame, interval: str, as_of: pd.Timestamp) -> pd.DataFrame:
    """Reject missing, stale, malformed or gapped bars; exclude unfinished bars."""
    delta = pd.Timedelta(DURATIONS[interval])
    required = ["open", "high", "low", "close", "volume", "close_time"]
    if not set(required).issubset(frame.columns):
        raise ValueError(f"{interval} 行情缺少字段")
    x = frame.loc[frame["close_time"] < as_of].sort_index().copy()
    if len(x) < 250 or not x.index.is_unique or x.index.tz is None:
        raise ValueError(f"{interval} 历史数据不足或时间戳异常")
    if x.index[-1] != as_of.floor(DURATIONS[interval]) - delta:
        raise ValueError(f"{interval} 数据不是最新已收盘K线")
    if not (x.index.to_series().diff().iloc[1:] == delta).all():
        raise ValueError(f"{interval} K线有缺口")
    ends = pd.DatetimeIndex(x["close_time"])
    if not (ends == x.index + delta - pd.Timedelta(milliseconds=1)).all():
        raise ValueError(f"{interval} 开盘和收盘时间不匹配")
    values = x[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise ValueError(f"{interval} 价格或成交量无效")
    if (x["high"] < x[["open", "close", "low"]].max(axis=1)).any() or (x["low"] > x[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError(f"{interval} K线价格结构无效")
    return x


def evaluate(symbol: str, frames: Mapping[str, pd.DataFrame]) -> Decision:
    """Same hypothesis as signals.py, with concise reasons and no sizing claims."""
    def classify_trend(row: pd.Series) -> str:
        if row["close"] > row["ema50"] > row["ema200"] and row["macd_hist"] > 0:
            return "LONG"
        if row["close"] < row["ema50"] < row["ema200"] and row["macd_hist"] < 0:
            return "SHORT"
        return "NEUTRAL"

    rows = {tf: frames[tf].iloc[-1] for tf in DURATIONS}
    for tf, row in rows.items():
        needed = ["close", "ema50", "ema200", "macd_hist", "rsi", "atr"]
        if tf == "15m":
            needed += ["prior_high20", "prior_low20", "volume", "vol_sma20"]
        if not np.isfinite(row[needed].to_numpy(dtype=float)).all():
            raise ValueError(f"{tf} 指标不足，不能判断")
    trigger, hour = rows["15m"], rows["1h"]
    closed = pd.Timestamp(trigger["close_time"]) + pd.Timedelta(milliseconds=1)
    expiry = closed + pd.Timedelta(minutes=15)

    def wait(reason: str) -> Decision:
        return Decision(symbol, "WAIT", reason, closed, expiry)

    daily, h4 = classify_trend(rows["1d"]), classify_trend(rows["4h"])
    if daily != h4 or daily not in ("LONG", "SHORT"):
        return wait("日线和4小时没有一致方向，不开新仓。")
    is_long = daily == "LONG"
    sign = 1 if is_long else -1
    low, high = (45, 68) if is_long else (32, 55)
    if sign * (hour["close"] - hour["ema50"]) <= 0 or not low <= hour["rsi"] <= high:
        return wait("方向已明确，但1小时入场过滤未通过。")
    level = trigger["prior_high20"] if is_long else trigger["prior_low20"]
    low, high = (50, 75) if is_long else (25, 50)
    checks = [
        (sign * (trigger["close"] - level) > 0, "15分钟尚未确认突破。"),
        (trigger["volume"] > 1.2 * trigger["vol_sma20"], "突破成交量不足。"),
        (sign * trigger["macd_hist"] > 0, "15分钟动量未确认。"),
        (low <= trigger["rsi"] <= high, "15分钟RSI不在规则区间。"),
    ]
    for passed, reason in checks:
        if not passed:
            return wait(reason)
    entry, distance = float(trigger["close"]), 1.5 * float(trigger["atr"])
    stop, target = entry - sign * distance, entry + sign * 2 * distance
    if distance <= 0 or min(stop, target) <= 0:
        return wait("波动或价格异常，不能生成有效参考计划。")
    return Decision(symbol, daily, "大周期同向，1小时过滤及15分钟突破均通过。",
                    closed, expiry, entry, stop, target)


def inspect(symbol: str, as_of: pd.Timestamp | None = None) -> Decision:
    """Fail closed on any data problem. Never substitute spot for futures data."""
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass  # Keep Python's default trusted CA store; never disable TLS checks.
    try:
        from quant_system.signals import get_klines, indicators
        snapshot = pd.Timestamp.now(tz="UTC") if as_of is None else as_of
        frames = {}
        for tf in DURATIONS:
            raw = get_klines(symbol, tf, limit=1000)
            frames[tf] = indicators(validate_frame(raw, tf, snapshot))
        decision = evaluate(symbol, frames)
        if pd.Timestamp.now(tz="UTC") >= decision.expires_at:
            raise ValueError("获取行情期间跨过下一次15分钟收盘，请重新运行")
        return decision
    except Exception as exc:
        detail = " ".join(str(exc).split())[:220]
        return Decision(symbol, "UNAVAILABLE", f"数据未通过检查：{detail}")


def format_decision(d: Decision) -> str:
    labels = {
        "LONG": "做多信号触发；做空条件不成立",
        "SHORT": "做空信号触发；做多条件不成立",
        "WAIT": "观望：现在不开多，也不开空",
        "UNAVAILABLE": "无法判断：数据不可用，暂不开仓",
    }
    text = [f"{d.symbol} | {labels[d.state]}", f"原因：{d.reason}"]
    if d.closed_at is not None:
        text.append(f"依据K线收盘：{d.closed_at.isoformat()} | 下次重算：{d.expires_at.isoformat()}")
    if d.state in ("LONG", "SHORT"):
        text.append(f"收盘参考价 {d.entry:,.4f} | 止损参考 {d.stop:,.4f} | 2R目标参考 {d.target:,.4f}")
        text.append("参考价不是实时成交价；信号不是保证获利或已验证的入场建议。")
    return "\n".join(text)


def main() -> None:
    print("BTC / ETH 当前规则信号 | Binance USDT永续 | 仅研究，不下单", flush=True)
    print("正在读取最新已收盘K线；接口失败不会编造方向。", flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(inspect, SYMBOLS))
    for decision in decisions:
        print("\n" + format_decision(decision))
    print("\n未验证收益；未计完整交易成本。这是一次查询，不会在关闭后继续监控。")
    if any(d.state == "UNAVAILABLE" for d in decisions):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
