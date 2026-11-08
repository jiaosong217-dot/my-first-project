"""Personal Quant local dashboard: concise BTC/ETH long/short/wait decisions.

Runs locally with public Binance USD-M Futures data. No account connection,
no API secrets, and no order execution. Signals are experimental rules.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_system.now import inspect, SYMBOLS
from quant_system.signals import FRAMES, get_klines, indicators, classify_trend

st.set_page_config(
    page_title="Personal Quant | 多空信号",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1500px;}
[data-testid="stMetric"] {background: #111827; border: 1px solid #293548;
    padding: 12px 16px; border-radius: 12px;}
.signal {padding: 20px; border-radius: 14px; border: 1px solid #334155;
    background: #111827; margin-bottom: 10px;}
.signal h1 {margin: 0.15rem 0 0.4rem 0; font-size: 2rem;}
.muted {color: #94a3b8; font-size: .86rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60, show_spinner=False)
def get_decision(symbol: str):
    return inspect(symbol)


@st.cache_data(ttl=60, show_spinner=False)
def get_chart_frame(symbol: str, interval: str):
    return indicators(get_klines(symbol, interval, limit=500))


def fmt(value):
    return "—" if value is None else f"{value:,.2f}"


st.title("📊 Personal Quant")
st.caption("BTC / ETH · USDT 永续 · 多周期技术分析 · 做多 / 做空 / 观望")
with st.sidebar:
    st.header("研究设置")
    selected = st.multiselect("交易标的", list(SYMBOLS), default=list(SYMBOLS))
    st.divider()
    equity = st.number_input("模拟账户权益（USDT）", min_value=10.0, value=1000.0, step=100.0)
    risk_percent = st.slider("单笔风险预算（%）", 0.1, 2.0, 0.5, 0.1)
    st.caption("仓位估算只按止损距离计算，不包含杠杆、强平、资金费和滑点。")
    if st.button("↻ 重新检查行情", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("每次打开或刷新时重新读取已收盘K线；不是后台持续监控。")

st.warning("这是实验性规则信号，不是已证明盈利的策略。数据失败或不完整时会显示“无法判断”，不会猜测方向。")

if not selected:
    st.info("请在左侧选择 BTCUSDT 或 ETHUSDT。")
    st.stop()

decisions = {}
with st.spinner("正在检查 BTC / ETH 四个周期的最新已收盘K线…"):
    for symbol in selected:
        decisions[symbol] = get_decision(symbol)

st.subheader("当前判断")
cols = st.columns(len(selected))
labels = {
    "LONG": ("🟢 做多", "success"),
    "SHORT": ("🔴 做空", "error"),
    "WAIT": ("🟡 观望", "warning"),
    "UNAVAILABLE": ("⚪ 无法判断", "secondary"),
}
for col, symbol in zip(cols, selected):
    d = decisions[symbol]
    label, color = labels[d.state]
    with col:
        st.markdown(
            f'<div class="signal"><div class="muted">{symbol} · USDT 永续</div>'
            f'<h1>{label}</h1><div>{d.reason}</div></div>',
            unsafe_allow_html=True,
        )
        if d.closed_at is not None:
            st.caption(f"信号依据：已收盘15分钟K线 {d.closed_at.strftime('%Y-%m-%d %H:%M UTC')}")
            st.caption(f"本次信号有效观察至：{d.expires_at.strftime('%Y-%m-%d %H:%M UTC')}，之后应重新计算")
        if d.state in ("LONG", "SHORT"):
            a, b, c = st.columns(3)
            a.metric("参考入场", fmt(d.entry))
            b.metric("止损参考", fmt(d.stop))
            c.metric("2R目标参考", fmt(d.target))
            risk_cash = equity * risk_percent / 100
            distance = abs(d.entry - d.stop)
            quantity = risk_cash / distance if distance > 0 else 0
            st.write(f"按风险预算估算数量：**{quantity:.6f} {symbol.replace('USDT','')}**")
            st.caption(f"风险预算约 {risk_cash:.2f} USDT；未计算杠杆、手续费、滑点、资金费及强平风险。")
        else:
            st.caption("没有经过完整条件确认的入场计划，不提供仓位估算。")

tab_signal, tab_chart, tab_logic = st.tabs(["多空结论", "多周期图表", "判断规则"])
with tab_signal:
    for symbol, d in decisions.items():
        st.markdown(f"**{symbol} — {labels[d.state][0]}**")
        st.write(d.reason)
        if d.state == "UNAVAILABLE":
            st.error("行情或数据质量检查未通过。请刷新，若持续失败请检查网络/交易所接口。")
        st.divider()

with tab_chart:
    interval = st.selectbox("图表周期", ["15m", "1h", "4h", "1d"], index=1)
    for symbol in selected:
        try:
            frame = get_chart_frame(symbol, interval).tail(180)
            latest = frame.iloc[-1]
            trend_rows = []
            for tf in FRAMES:
                # The chart tab requests each timeframe independently for a readable status table.
                dframe = get_chart_frame(symbol, tf)
                row = dframe.iloc[-1]
                trend_rows.append({
                    "周期": tf,
                    "收盘价": float(row["close"]),
                    "EMA50": float(row["ema50"]),
                    "EMA200": float(row["ema200"]),
                    "RSI14": float(row["rsi"]),
                    "MACD柱": float(row["macd_hist"]),
                    "趋势": classify_trend(row),
                })
            st.markdown(f"### {symbol}")
            st.dataframe(pd.DataFrame(trend_rows), use_container_width=True, hide_index=True)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=frame.index, open=frame["open"], high=frame["high"],
                low=frame["low"], close=frame["close"], name="K线"
            ))
            fig.add_trace(go.Scatter(x=frame.index, y=frame["ema50"], name="EMA50"))
            fig.add_trace(go.Scatter(x=frame.index, y=frame["ema200"], name="EMA200"))
            fig.update_layout(
                title=f"{symbol} · {interval} K线与均线",
                height=430, template="plotly_dark", xaxis_rangeslider_visible=False,
                margin=dict(l=10, r=10, t=45, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.error(f"{symbol} 图表读取失败：{exc}")

with tab_logic:
    st.markdown("""
### 当前版本的规则逻辑

1. **日线与4小时**：EMA50 / EMA200 排列、收盘价位置和 MACD 柱方向共同判断大趋势。
2. **1小时**：趋势位置与 RSI 区间过滤，避免大周期方向虽一致但入场位置不理想。
3. **15分钟**：要求突破前20根已收盘K线高点/低点、成交量高于20根均量的1.2倍、MACD动量同向且 RSI 位于指定区间。
4. 所有条件同向才输出 LONG 或 SHORT；否则 WAIT。行情缺失、过期或数据异常则 UNAVAILABLE。
5. ATR(14) 的1.5倍用于止损参考，2R用于目标参考。

### 重要限制

- 这是第一套可检验的规则，不是 AI 已经找到的盈利策略。
- 当前尚未完成足够长的永续合约历史回测、资金费率和滑点建模、样本外验证及模拟交易。
- 不使用本界面的信号直接进行真实杠杆交易。
- 页面不会自动下单，也不会持续后台监控。
""")
st.caption("Personal Quant · 本地研究工具 · 不构成投资建议")
