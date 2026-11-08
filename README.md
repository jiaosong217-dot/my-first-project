# Personal Quant — 个人量化金融研究系统

一个从零开始构建的个人量化研究平台。目标是逐步覆盖全球金融市场，整合行情数据、技术分析、基本面与宏观研究、策略回测和 AI 辅助研究。

> 当前阶段仅用于学习、研究和模拟分析。程序输出不是投资建议，不会连接交易所下单，也不会自动执行真实交易。

## 当前版本：V1.0 起步

第一步先建立可运行的数据分析原型：

- 从公开行情数据源获取历史日线（当前示例使用 Yahoo Finance 的 `yfinance` 接口）
- 计算 MA20、MA60 和 RSI14
- 输出趋势观察和指标摘要
- 将数据保存为 CSV，便于后续复核

## 环境准备

建议使用 Python 3.11 或更新版本。

```bash
python -m venv .venv
```

macOS / Linux 激活环境：

```bash
source .venv/bin/activate
```

Windows 激活环境：

```powershell
.venv\\Scripts\\Activate.ps1
```

安装依赖：

```bash
python -m pip install -r requirements.txt
```

运行示例（SPY 为美国标普500 ETF，仅作数据演示）：

```bash
python -m quant_system.main --ticker SPY --period 1y
```

也可以尝试：

```bash
python -m quant_system.main --ticker AAPL --period 2y
python -m quant_system.main --ticker BTC-USD --period 1y
python -m quant_system.main --ticker 0700.HK --period 1y
```

行情源的代码、交易时段、复权口径、数据延迟和可用性因市场而异。不同市场接入前必须验证数据质量与使用许可。

## 项目结构

```
.
├── quant_system/
│   ├── __init__.py
│   └── main.py
├── data/                 # 本地导出的 CSV（不会提交）
├── .gitignore
├── requirements.txt
└── README.md
```

## 研究纪律

1. 不把单一指标当作交易决策。
2. 回测必须计入手续费、滑点和合理成交假设。
3. 避免未来函数、幸存者偏差和过拟合。
4. 先做样本外验证和模拟跟踪，再讨论真实资金。
5. 绝不将 API 密钥、密码或账户凭证提交到 GitHub。

## 后续路线

- V1.0：行情获取、清洗、指标计算、CSV 导出
- V1.1：多市场数据标准化与数据库
- V1.2：宏观与基本面数据研究
- V1.3：策略回测和风险指标
- V1.4：AI 辅助研究报告
- V2.0：可解释的模拟交易信号面板（人工确认下单）
