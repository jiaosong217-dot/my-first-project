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
