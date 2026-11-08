"""Multi-timeframe BTC/ETH perpetual-futures signal research prototype.

Uses public Binance USD-M Futures market data only. It never places orders.
The rules are an initial testable hypothesis, not a proven profitable strategy.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

BASE = "https://fapi.binance.com/fapi/v1/klines"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
FRAMES = ("15m", "1h", "4h", "1d")
COLS = ["open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"]


def get_klines(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    request = urllib.request.Request(
        f"{BASE}?{query}", headers={"User-Agent": "PersonalQuant/0.1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Binance Futures HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Futures market data unavailable: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"No candles returned for {symbol} {interval}: {payload!r}")
    df = pd.DataFrame(payload, columns=COLS)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    nums = ["open", "high", "low", "close", "volume", "quote_volume",
            "trades", "taker_buy_base", "taker_buy_quote"]
    df[nums] = df[nums].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df = df.set_index("open_time").sort_index()
    # Never make a decision from a still-forming candle.
    return df.loc[df["close_time"] < pd.Timestamp.now(tz="UTC")].copy()


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    c = x["close"]
    x["ema20"] = c.ewm(span=20, adjust=False).mean()
    x["ema50"] = c.ewm(span=50, adjust=False).mean()
    x["ema200"] = c.ewm(span=200, adjust=False).mean()
    x["macd"] = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False).mean()
    x["macd_hist"] = x["macd"] - x["macd_signal"]
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    x["rsi"] = (100 - 100/(1+rs)).where(loss.ne(0), 100.0)
    prev = c.shift(1)
    tr = pd.concat([x["high"]-x["low"], (x["high"]-prev).abs(),
                    (x["low"]-prev).abs()], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    x["vol_sma20"] = x["volume"].rolling(20).mean()
    x["prior_high20"] = x["high"].shift(1).rolling(20).max()
    x["prior_low20"] = x["low"].shift(1).rolling(20).min()
    return x


def classify_trend(row: pd.Series) -> str:
    vals = [row.get("ema50"), row.get("ema200"), row.get("macd_hist")]
    if any(pd.isna(v) for v in vals):
        return "NEUTRAL"
    if row["close"] > row["ema50"] > row["ema200"] and row["macd_hist"] > 0:
        return "LONG"
    if row["close"] < row["ema50"] < row["ema200"] and row["macd_hist"] < 0:
        return "SHORT"
    return "NEUTRAL"


def analyse(symbol: str, equity: float, risk_pct: float, fee_pct: float) -> dict:
    data = {tf: indicators(get_klines(symbol, tf)) for tf in FRAMES}
    rows = {tf: frame.iloc[-1] for tf, frame in data.items()}
    daily = classify_trend(rows["1d"])
    four_hour = classify_trend(rows["4h"])
    hourly = rows["1h"]
    trigger = rows["15m"]

    # Higher-timeframe regime must agree. Conflicts and sideways markets mean WAIT.
    direction = daily if daily == four_hour and daily != "NEUTRAL" else "WAIT"
    reasons = [f"1d regime={daily}", f"4h regime={four_hour}"]

    if direction == "LONG":
        hourly_ok = hourly["close"] > hourly["ema50"] and 45 <= hourly["rsi"] <= 68
        trigger_ok = (
            trigger["close"] > trigger["prior_high20"]
            and trigger["volume"] > 1.2 * trigger["vol_sma20"]
            and trigger["macd_hist"] > 0
            and 50 <= trigger["rsi"] <= 75
        )
        reasons += [f"1h pullback/trend filter={'pass' if hourly_ok else 'fail'}",
                    f"15m upside breakout/volume trigger={'pass' if trigger_ok else 'fail'}"]
        if not (hourly_ok and trigger_ok):
            direction = "WAIT"
    elif direction == "SHORT":
        hourly_ok = hourly["close"] < hourly["ema50"] and 32 <= hourly["rsi"] <= 55
        trigger_ok = (
            trigger["close"] < trigger["prior_low20"]
            and trigger["volume"] > 1.2 * trigger["vol_sma20"]
            and trigger["macd_hist"] < 0
            and 25 <= trigger["rsi"] <= 50
        )
        reasons += [f"1h pullback/trend filter={'pass' if hourly_ok else 'fail'}",
                    f"15m downside breakout/volume trigger={'pass' if trigger_ok else 'fail'}"]
        if not (hourly_ok and trigger_ok):
            direction = "WAIT"
    else:
        reasons.append("1d and 4h trend are not aligned; stand aside")

    entry = float(trigger["close"])
    atr = float(trigger["atr"])
    stop_distance = 1.5 * atr if np.isfinite(atr) and atr > 0 else None
    if direction in ("LONG", "SHORT") and stop_distance:
        stop = entry - stop_distance if direction == "LONG" else entry + stop_distance
        target = entry + 2 * stop_distance if direction == "LONG" else entry - 2 * stop_distance
        risk_cash = equity * risk_pct
        qty = risk_cash / stop_distance
        notional = qty * entry
        cost_estimate = notional * (fee_pct / 100) * 2
    else:
        stop = target = qty = notional = cost_estimate = None

    return {
        "symbol": symbol,
        "decision": direction,
        "as_of_utc": str(data["15m"].index[-1]),
        "reference_entry": round(entry, 6),
        "stop_reference": None if stop is None else round(stop, 6),
        "target_reference_2R": None if target is None else round(target, 6),
        "risk_budget_usdt": round(equity * risk_pct, 4),
        "estimated_quantity": None if qty is None else round(qty, 8),
        "estimated_notional_usdt": None if notional is None else round(notional, 4),
        "round_trip_fee_estimate_usdt": None if cost_estimate is None else round(cost_estimate, 4),
        "reasons": reasons,
        "timeframes": {
            tf: {
                "close": round(float(rows[tf]["close"]), 6),
                "ema50": round(float(rows[tf]["ema50"]), 6),
                "ema200": round(float(rows[tf]["ema200"]), 6),
                "rsi": round(float(rows[tf]["rsi"]), 2),
                "macd_hist": round(float(rows[tf]["macd_hist"]), 6),
            } for tf in FRAMES
        },
        "warning": (
            "Research signal only, not a proven profitable strategy or an order. "
            "Reference entry is the last closed 15m candle close; actual execution "
            "price may differ. Fees, slippage, funding, liquidation and spread are "
            "not fully modelled. Validate with historical and paper trading first."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Multi-timeframe crypto long/short signal research")
    p.add_argument("--symbol", choices=SYMBOLS, default="BTCUSDT")
    p.add_argument("--equity", type=float, default=1000.0, help="Illustrative account equity in USDT")
    p.add_argument("--risk-pct", type=float, default=0.005, help="Risk budget fraction per idea; default 0.5%%")
    p.add_argument("--fee-pct", type=float, default=0.05, help="Illustrative one-way fee percent; set to your actual tier")
    args = p.parse_args()
    if args.equity <= 0 or not 0 < args.risk_pct <= 0.02 or args.fee_pct < 0:
        p.error("equity must be positive; risk-pct must be >0 and <=0.02; fee-pct must be non-negative")
    result = analyse(args.symbol, args.equity, args.risk_pct, args.fee_pct)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
