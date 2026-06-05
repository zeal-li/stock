# 鑫多多

A股/港股/美股实时行情监控面板，支持指数分时走势、资金流向、选股、自选股（SQLite 持久化）、K 线弹窗、融资融券、恐慌/风险指数等。

## 目录结构

```
stock/
├── back_end/                        # 🔧 后端（Flask）
│   ├── app.py                       # 路由注册 + 启动
│   ├── common/                      # 公共模块
│   │   ├── __init__.py              # 代理配置
│   │   ├── utils.py                 # 格式化函数（fmt/is_etf 等）
│   │   └── finance.py              # 财务数据（商誉率/质押率）
│   ├── money_flow/                  # 资金流向
│   │   ├── cache.py                 # 内存缓存 + 后台轮询线程
│   │   ├── market.py               # 大盘指数行情 + 分时走势 + 涨跌家数
│   │   ├── fund_flow.py            # 大盘资金净流入
│   │   ├── turnover.py             # 成交额分时
│   │   ├── margin.py               # 融资融券
│   │   ├── fear_index.py           # 市场恐慌指数
│   │   └── risk_index.py           # 市场风险指数
│   ├── stock_pick/                  # 选股
│   │   └── service.py              # 股票搜索 + 行情查询
│   ├── watchlist/                   # 自选股
│   │   └── service.py              # SQLite 持久化 + CRUD API
│   ├── technical_screen/            # 技术选股
│   │   └── service.py              # 上升通道扫描
│   ├── data/                        # 数据文件（.gitignore 排除）
│   │   └── watchlist.db            # 自选股 SQLite 数据库
│   ├── requirements.txt
│   ├── start.bat / stop.bat / restart.bat
├── front_end/                       # 🎨 前端
│   ├── templates/
│   │   └── index.html              # 页面骨架 + 导航 + 初始化
│   └── static/
│       ├── style.css               # 全局样式
│       └── js/
│           ├── common.js           # 公共函数（交易时间判断/缓存清理）
│           ├── money_flow/
│           │   ├── charts.js       # 图表渲染（分时/资金流/融资融券）
│           │   └── refresh.js      # 自动刷新（10s 定时器）
│           ├── stock_pick/
│           │   └── service.js      # 选股列表（搜索/缓存/渲染）
│           ├── watchlist/
│           │   └── service.js      # 自选股列表（增删/行情/缓存）
│           └── kline/
│               └── popup.js        # K 线弹窗（日K/周K/月K/分时/五日）
├── .gitignore
└── README.md
```

## 功能模块

| 页面 | 功能 |
|------|------|
| 资金流向 | 上证指数分时走势、大盘资金净流入、融资融券、市场恐慌/风险指数 |
| 选股 | 股票搜索、自选列表（价格/涨跌/PE/PB/市值/商誉/质押） |
| 自选股 | 独立自选列表、SQLite 跨设备持久化、加自选/删自选 |
| K 线弹窗 | LightweightCharts 蜡烛图、日K/周K/月K/分时/五日、均线/布林线 |

### K 线弹窗

- 标题栏：实时价格、涨跌、⭐加自选/🗑删自选
- 参数行：今开/高/低/昨收、成交量/成交额、换手/振幅、量比/委比、PE/PB、总市值/流通市值、商誉率/质押率
- 十字线提示：日期、高/低、开/收、涨跌额/涨跌幅、成交量/成交额/换手率
- 指标切换：MA5/10/20/30/60/120、布林线（UP/MID/LOW）

### 缓存策略

| 数据 | 存储 | 生命周期 |
|------|------|----------|
| K 线/分时数据 | localStorage `kl_cache` | 跨天自动清 + 手动清 |
| 选股列表 | localStorage `stockCache` | 跨天清商誉 + 手动清 |
| 自选股列表 | localStorage `watchlistCache` + SQLite | localStorage 优先，SQLite 兜底 |
| 内存缓存 | Python `_cache` 字典 | 后端进程级，5~60s TTL |

## 数据源

### 行情 + K 线

| 数据 | 市场 | 来源 |
|------|------|------|
| 实时行情 | A/港/美 | 东方财富 `push2delay.eastmoney.com` |
| 日K线 | A 股 | 腾讯 `ifzq.gtimg.cn` + 同花顺 `d.10jqka.com.cn` |
| 日K线 | 港股/美股 | Yahoo Finance `query1.finance.yahoo.com` |
| 分时走势 | A 股 | 东方财富 `trends2`（5s 缓存，仅交易时段） |

### 大盘指标

| 数据 | 来源 | 刷新频率 |
|------|------|----------|
| 大盘资金净流入 | 东方财富 `fflow/kline` | 60s |
| 成交额 | 同花顺 `dq.10jqka.com.cn` | 60s |
| 恐慌/风险指数 | 多因子加权 | 60s |
| 融资融券 | akshare | 每天一次 |

### 财务数据

| 数据 | 来源 |
|------|------|
| 商誉率 | 东方财富 F10 资产负债表 |
| 质押率 | 东方财富 `RPT_CSDC_LIST` |
| 股票搜索 | 东方财富 `searchapi.eastmoney.com` |

## 环境要求

- Python 3.9+
- 依赖见 `back_end/requirements.txt`

## 快速开始

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r back_end\requirements.txt
cd back_end
python app.py
# 浏览器访问 http://localhost:5000
```

或直接双击 `back_end\start.bat`。

## 开发指南

### 加新功能模块

1. 在 `back_end/<功能名>/` 下新建模块
2. 在 `back_end/app.py` 中 import 并注册路由
3. 前端 JS 放入 `front_end/static/js/<功能名>/`
4. 在 `index.html` 中加 `<script>` 引用和页面容器

```python
# 后端示例
from new_feature.service import get_data

@app.route('/api/new-endpoint')
def new_endpoint():
    return jsonify(get_data())
```
