# Personal Quant — 个人量化金融研究系统

一个从零开始构建的个人量化研究平台。当前先研究 BTC/ETH 现货公开行情，逐步扩展到其他市场。项目用于学习、研究和模拟分析，不连接账户、不下单，也不保证盈利。

## V1.0：BTC/ETH 多周期行情与技术指标

数据源：Binance 官方公开 Spot Market Data 接口 `https://data-api.binance.vision`。获取公开 K 线不需要 API Key。接口或网络可能因地区、网络策略或服务限制而不可用。

支持标的：
- `BTCUSDT`
- `ETHUSDT`

支持周期：
- `15m`：15 分钟
- `1h`：1 小时
- `4h`：4 小时
- `1d`：日线

当前计算：
- MA20、MA60
- EMA12、EMA26
- MACD、MACD Signal、MACD Histogram
- RSI14
- ATR14

默认每次获取最近 500 根已收盘 K 线（可设置 50–1000 根），并导出到本地 `data/` 目录。注意：15 分钟 500 根只覆盖约 5 天，不能当作长期历史样本。

## 安装

建议 Python 3.11+。在项目根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 运行

先测试 BTC 1 小时：

```bash
python -m quant_system.main --symbol BTCUSDT --interval 1h --limit 500
```

测试 ETH 4 小时：

```bash
python -m quant_system.main --symbol ETHUSDT --interval 4h --limit 500
```

一次运行 BTC、ETH 的四个周期（共 8 个公开请求）：

```bash
python -m quant_system.main --all --limit 500
```

结果保存为 `data/BTCUSDT_1h.csv` 等 CSV 文件。该目录已加入 `.gitignore`，不会把本地行情文件提交到 GitHub。

## 策略回测实验室（初版）

运行 BTC 1 小时策略比较：

```bash
python -m quant_system.backtest --symbol BTCUSDT --interval 1h --limit 1000
```

可将 `BTCUSDT` 换成 `ETHUSDT`，周期可选 `15m`、`1h`、`4h`、`1d`。

初版比较四种规则策略与买入持有基准：
- MA 趋势
- MACD 趋势
- RSI 均值回归
- Donchian 突破

默认假设每边手续费 0.10%、每边滑点 0.05%，可通过 `--fee` 和 `--slippage` 调整。结果包括总收益、年化收益、最大回撤、Sharpe、Profit Factor、胜率、交易次数和持仓暴露，并按时间顺序切分训练期与样本外测试期。报告写入本地 `reports/` 目录。

**重要限制：** 这是初步的现货多头/空仓（long/flat）研究基线，不做杠杆、不做空、不包含合约资金费率、借币成本、冲击成本或真实成交模拟。当前最多 1000 根 K 线，尤其不足以证明策略长期有效。不要根据这份小样本报告直接实盘。

## 下一阶段

1. 增加历史分页下载，建立足够长的样本
2. 做滚动样本外验证与参数稳定性分析
3. 加入合约多空、资金费率、保证金与强平风险模型
4. 加入模拟交易、信号日志与人工确认流程
5. 再评估是否需要连接交易所执行接口

## 风险与数据纪律

- 指标只是对历史价格的数学描述，不代表预测或买卖建议。
- 历史回测结果不保证未来表现；必须防止未来函数、幸存者偏差、过拟合。
- 不要把 API Key、Secret、密码或个人账户信息提交到仓库。
- 当前程序仅请求公开行情，不含交易权限、账户连接或自动下单功能。

## 多周期做多/做空/观望信号原型

这是一个面向 USDT 永续合约研究的**规则型信号原型**，只读取 Binance USDⓈ-M Futures 公开行情，不需要 API Key，也不会下单。

运行 BTC：
```bash
python -m quant_system.signals --symbol BTCUSDT --equity 1000 --risk-pct 0.005
```

运行 ETH：
```bash
python -m quant_system.signals --symbol ETHUSDT --equity 1000 --risk-pct 0.005
```

初始规则：
- 日线 + 4小时：EMA50/EMA200 排列、收盘价位置及 MACD 柱方向必须同向，定义大级别多空环境。
- 1小时：检查趋势过滤与 RSI 区间，避免在不合适的动量位置追入。
- 15分钟：要求20根已完成 K 线区间突破、成交量放大、MACD 柱同向及 RSI 确认，作为触发条件。
- 任一层级不一致或触发条件不满足，输出 WAIT（观望）。
- 以15分钟 ATR 的1.5倍给出研究用止损参考，目标参考为2R；按账户权益风险预算估算数量。

默认风险预算为账户权益的0.5%，仅为示例参数；手续费参数默认单边0.05%，必须按你实际交易所费率调整。

**非常重要：** 这只是第一版可检验的规则假设，不是已证明能稳定盈利的策略。当前未充分建模真实成交、点差、滑点、资金费率、强平、盘口深度及不同交易所差异；参考入场价是最近一根已收盘15分钟K线的收盘价，不是保证成交价。信号可能长时间为 WAIT，也可能在历史测试中亏损。必须先完成回测、样本外验证和模拟交易，不能直接据此实盘。

## 本地交互式仪表盘

已增加 Streamlit + Plotly 仪表盘。安装依赖后，在项目根目录运行：

```bash
streamlit run app.py
```

浏览器会打开本地仪表盘。页面包含：
- BTC/ETH 研究信号：LONG / SHORT / WAIT 及条件检查理由
- 15m / 1h / 4h / 1d 多周期指标表
- 1小时K线图及 EMA50 / EMA200
- 风险预算与止损参考（仅在规则信号完整时显示）
- 系统边界与后续开发说明

仪表盘读取 Binance USDⓈ-M Futures 公开行情，不需要 API Key；不会连接账户或发送订单。页面中的信号来自当前实验规则，不包含人工编造的信号分数，也不代表策略已盈利。请先进行严谨回测与模拟交易。
