"""Local Streamlit dashboard for Personal Quant.

Research interface only. No order execution. Signals are experimental rules,
not proven profitable recommendations.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_system.signals import (
    FRAMES, SYMBOLS, get_klines, indicators, classify_trend
)

st.set_page_config(
    page_title="Personal Quant | Crypto Research",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {background: #111827; border: 1px solid #263244;
    padding: 12px 16px; border-radius: 12px;}
.signal-card {padding: 18px; border-radius: 14px; border: 1px solid #334155;
    background: #111827; min-height: 150px;}
.small-muted {color: #94a3b8; font-size: 0.85rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60, show_spinner=False)
def load_frame(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    return indicators(get_klines(symbol, interval, limit))


def signal_for(symbol: str, equity: float, risk_fraction: float, fee_percent: float):
    frames = {tf: load_frame(symbol, tf, 300) for tf in FRAMES}
    latest = {tf: data.iloc[-1] for tf, data in frames.items()}
    regime_1d = classify_trend(latest["1d"])
    regime_4h = classify_trend(latest["4h"])
    hourly = latest["1h"]
    trigger = latest["15m"]
    direction = regime_1d if regime_1d == regime_4h and regime_1d != "NEUTRAL" else "WAIT"
    reasons = [
        f"日线趋势：{regime_1d}",
        f"4小时趋势：{regime_4h}",
    ]
    if direction == "LONG":
        h_ok = hourly["close"] > hourly["ema50"] and 45 <= hourly["rsi"] <= 68
        t_ok = (
            trigger["close"] > trigger["prior_high20"]
            and trigger["volume"] > 1.2 * trigger["vol_sma20"]
            and trigger["macd_hist"] > 0
            and 50 <= trigger["rsi"] <= 75
        )
        reasons += [f"1小时趋势过滤：{'通过' if h_ok else '未通过'}",
                    f"15分钟向上突破与成交量确认：{'通过' if t_ok else '未通过'}"]
        if not (h_ok and t_ok):
            direction = "WAIT"
    elif direction == "SHORT":
        h_ok = hourly["close"] < hourly["ema50"] and 32 <= hourly["rsi"] <= 55
        t_ok = (
            trigger["close"] < trigger["prior_low20"]
            and trigger["volume"] > 1.2 * trigger["vol_sma20"]
            and trigger["macd_hist"] < 0
            and 25 <= trigger["rsi"] <= 50
        )
        reasons += [f"1小时趋势过滤：{'通过' if h_ok else '未通过'}",
                    f"15分钟向下跌破与成交量确认：{'通过' if t_ok else '未通过'}"]
        if not (h_ok and t_ok):
            direction = "WAIT"
    else:
        reasons.append("日线与4小时方向未一致，暂不产生方向信号")

    entry = float(trigger["close"])
    atr = float(trigger["atr"])
    stop_distance = 1.5 * atr if pd.notna(atr) and atr > 0 else None
    plan = None
    if direction in ("LONG", "SHORT") and stop_distance:
        stop = entry - stop_distance if direction == "LONG" else entry + stop_distance
        target = entry + 2 * stop_distance if direction == "LONG" else entry - 2 * stop_distance
        risk_cash = equity * risk_fraction
        qty = risk_cash / stop_distance
        notional = qty * entry
        fee_est = notional * (fee_percent / 100) * 2
        plan = {
            "entry": entry, "stop": stop, "target": target, "risk_cash": risk_cash,
            "qty": qty, "notional": notional, "fee": fee_est,
        }
    return direction, reasons, frames, plan


def fmt_price(value):
    return "—" if value is None else f"{value:,.4f}"


st.title("📈 Personal Quant")
st.caption("AI 加密货币量化研究系统 · BTC / ETH · 多周期信号 · 本地运行")
with st.sidebar:
    st.header("研究设置")
    symbols = st.multiselect("交易标的", list(SYMBOLS), default=list(SYMBOLS))
    equity = st.number_input("模拟账户权益（USDT）", min_value=10.0, value=1000.0, step=100.0)
    risk_pct = st.slider("单笔风险预算（权益比例）", min_value=0.1, max_value=2.0, value=0.5, step=0.1) / 100
    fee_pct = st.number_input("单边手续费假设（%）", min_value=0.0, value=0.05, step=0.01, format="%.3f")
    st.caption("费率请按你实际交易所等级修改。当前只展示研究结果，不会下单。")
    refresh = st.button("↻ 刷新行情", use_container_width=True)
    if refresh:
        st.cache_data.clear()

st.info("研究提示：这里的 LONG / SHORT / WAIT 是一组待验证的规则输出，不代表已证明盈利。所有数据来自公开永续合约行情；未连接交易账户。")

tabs = st.tabs(["交易信号", "多周期分析", "风险计划", "系统说明"])
if not symbols:
    st.warning("请在左侧至少选择 BTCUSDT 或 ETHUSDT。")
else:
    results = {}
    with st.spinner("正在获取公开行情并计算多周期条件…"):
        for symbol in symbols:
            try:
                results[symbol] = signal_for(symbol, equity, risk_pct, fee_pct)
            except Exception as exc:
                st.error(f"{symbol} 数据获取失败：{exc}")

    with tabs[0]:
        st.subheader("当前研究信号")
        cols = st.columns(len(symbols))
        for col, symbol in zip(cols, symbols):
            if symbol not in results:
                continue
            direction, reasons, frames, plan = results[symbol]
            with col:
                label = {"LONG": "🟢 做多 LONG", "SHORT": "🔴 做空 SHORT", "WAIT": "🟡 观望 WAIT"}[direction]
                st.markdown(f'<div class="signal-card"><h3>{symbol} 永续</h3><h2>{label}</h2><p class="small-muted">最近已收盘 15 分钟 K 线：{frames["15m"].index[-1]}</p></div>', unsafe_allow_html=True)
                st.metric("参考价格", fmt_price(float(frames["15m"].iloc[-1]["close"])))
                st.markdown("**信号条件检查**")
                for reason in reasons:
                    st.write("• " + reason)
                if plan:
                    st.markdown("**风险参考（不是下单指令）**")
                    st.write(f"止损参考：{fmt_price(plan['stop'])}")
                    st.write(f"2R 目标参考：{fmt_price(plan['target'])}")
                else:
                    st.caption("当前规则没有产生完整入场条件，因此不提供仓位建议。")

    with tabs[1]:
        st.subheader("多周期趋势与指标")
        for symbol in symbols:
            if symbol not in results:
                continue
            direction, reasons, frames, plan = results[symbol]
            st.markdown(f"### {symbol}")
            rows = []
            for tf in FRAMES:
                row = frames[tf].iloc[-1]
                rows.append({
                    "周期": tf,
                    "最新收盘价": row["close"],
                    "EMA50": row["ema50"],
                    "EMA200": row["ema200"],
                    "RSI14": row["rsi"],
                    "MACD柱": row["macd_hist"],
                    "趋势分类": classify_trend(row),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            chart_data = frames["1h"].tail(120)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=chart_data.index, open=chart_data["open"], high=chart_data["high"],
                low=chart_data["low"], close=chart_data["close"], name="K线"
            ))
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data["ema50"], name="EMA50"))
            fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data["ema200"], name="EMA200"))
            fig.update_layout(
                title=f"{symbol} · 1小时K线（最近120根）",
                height=430, template="plotly_dark", xaxis_rangeslider_visible=False,
                margin=dict(l=10, r=10, t=45, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tabs[2]:
        st.subheader("风险计划")
        st.caption("仓位估算仅基于止损距离和风险预算；尚未校验交易所最小下单量、杠杆、保证金、强平价、滑点及资金费率。")
        for symbol in symbols:
            if symbol not in results:
                continue
            direction, reasons, frames, plan = results[symbol]
            st.markdown(f"### {symbol} · {direction}")
            if not plan:
                st.write("没有完整信号，不建议根据本模块计算仓位。")
                continue
            a, b, c = st.columns(3)
            a.metric("风险预算", f"{plan['risk_cash']:.2f} USDT")
            b.metric("止损距离", fmt_price(abs(plan["entry"] - plan["stop"])))
            c.metric("估算名义仓位", f"{plan['notional']:.2f} USDT")
            st.write(f"估算数量：{plan['qty']:.8f} {symbol.replace('USDT', '')}")
            st.write(f"往返手续费估算：{plan['fee']:.4f} USDT（不含滑点）")

    with tabs[3]:
        st.subheader("系统边界与开发路线")
        st.markdown("""
- **已具备：** 公开永续合约K线、多周期 EMA/MACD/RSI/ATR 计算、规则信号原型。
- **尚未具备：** 经过充分验证的盈利策略、真实成交模拟、资金费率完整建模、强平模型、自动下单。
- **下一步：** 长历史数据分页、逐笔/盘口成本近似、样本外与滚动回测、模拟交易日志。
- **安全：** 不需要交易所密钥，不连接资金账户，不执行订单。
        """)
        st.warning("不要把本界面的研究信号当成投资建议或保证盈利的买卖指令。")
