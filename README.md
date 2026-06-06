# 鑫多多

A股/港股/美股实时行情监控面板，支持指数分时走势、资金流向、选股、自选股（SQLite 持久化）、K 线弹窗、融资融券、恐慌/风险指数、技术选股。

## 目录结构

```
stock/
├── .gitignore
├── README.md
├── note.md
├── note2.md
├── build_exe.py                       # PyInstaller 打包入口
├── gitpush.bat
├── 鑫多多.spec                         # PyInstaller spec 文件
│
├── back_end/                          # 🔧 后端（Flask）
│   ├── app.py                         # 主入口：路由 + 启动 + 后台定时器
│   ├── requirements.txt
│   ├── start.bat / stop.bat / restart.bat
│   │
│   ├── common/                        # 公共模块
│   │   ├── __init__.py
│   │   ├── utils.py                   # 格式化 + is_etf 等
│   │   └── finance.py                 # 商誉率 + 质押率
│   │
│   ├── data/                          # 运行时数据（.gitignore）
│   │   ├── stock_list.db              # 在市的股票列表
│   │   ├── stock_detail_list.db       # K线 + 股票元信息
│   │   ├── money_flow.db              # 资金流、融资融券历史数据
│   │   └── watchlist.db               # 自选股持久化
│   │
│   ├── market_db/                     # 全市场股票数据库
│   │   ├── __init__.py
│   │   ├── db.py                      # SQLite 表结构 + CRUD
│   │   └── sync.py                    # 股票列表同步 + K线增量更新
│   │
│   ├── money_flow/                    # 资金流向模块
│   │   ├── __init__.py
│   │   ├── market.py                  # 大盘行情（上证指数/分时）
│   │   ├── fund_flow.py               # 主力资金净流入
│   │   ├── margin.py                  # 融资融券
│   │   ├── fear_index.py              # 恐慌指数
│   │   ├── risk_index.py              # 风险指数
│   │   ├── turnover.py                # 换手率
│   │   └── storage.py                 # 数据库持久化
│   │
│   ├── stock_pick/                    # 选股模块
│   │   ├── __init__.py
│   │   └── service.py
│   │
│   ├── technical_screen/              # 技术选股模块
│   │   ├── __init__.py
│   │   └── service.py                 # 上升通道扫描（基于本地 K 线缓存）
│   │
│   └── watchlist/                     # 自选股模块
│       ├── __init__.py
│       └── service.py                 # 自选股 SQLite CRUD
│
├── front_end/                         # 🎨 前端（原生 HTML/CSS/JS）
│   ├── templates/
│   │   └── index.html                 # 主页面：导航 + 各模块初始化
│   └── static/
│       ├── style.css
│       └── js/
│           ├── common.js              # 公共工具：交易时间判断 / 缓存清理
│           ├── kline/                 # K线图表模块
│           │   ├── popup.js           # K线弹窗主逻辑
│           │   ├── chart.js           # 日K/周K/月K（Lightweight Charts）
│           │   ├── minute.js          # 分时走势图
│           │   └── fiveday.js         # 五日走势图
│           ├── money_flow/            # 资金流向前端
│           │   ├── charts.js          # 资金流图表渲染（ECharts）
│           │   └── refresh.js         # 数据刷新逻辑
│           ├── stock_pick/            # 选股前端
│           │   └── service.js         # 搜索 + 缓存 + 渲染
│           └── watchlist/             # 自选股前端
│               └── service.js         # 自选列表 + 刷新 + 加选天数
│
├── build/                             # PyInstaller 构建中间产物
├── dist/                              # PyInstaller 分发输出
└── venv/                              # Python 虚拟环境（gitignore）
```

## 功能页面

| 页面 | 功能 |
|------|------|
| 资金流向 | 上证指数分时、大盘资金净流入、融资融券、恐慌/风险指数 |
| 自选股 | 自选列表、加/删自选、行情刷新、加选天数/涨跌幅 |
| 选股 | 股票搜索、自选列表、商誉率/质押率 |
| 技术选股 | 按市场分段加载、上升通道扫描 |
| K 线弹窗 | LightweightCharts 蜡烛图、日K/周K/月K/分时/五日、MA/布林线 |

## SQLite 数据库表结构

### data/stock_list.db — 在市的股票列表

```sql
-- 股票列表
CREATE TABLE stocks (
    code TEXT NOT NULL,          -- 股票代码（6位）
    market TEXT NOT NULL,        -- 市场分段（sh_main/sz_main/gem/star/sz_etf/sh_etf）
    name TEXT,                   -- 股票名称
    PRIMARY KEY (code, market)
);

-- 同步日志
CREATE TABLE sync_log (
    market TEXT PRIMARY KEY,     -- 市场分段
    last_sync_date TEXT           -- 上次同步日期 YYYY-MM-DD
);
```

### data/stock_detail_list.db — K 线数据

```sql
-- K 线数据
CREATE TABLE klines (
    code TEXT NOT NULL,          -- 股票代码
    market TEXT NOT NULL,        -- 市场分段
    period TEXT NOT NULL,        -- 周期（daily/weekly/monthly）
    date TEXT NOT NULL,          -- 日期
    open REAL,                   -- 开盘价
    high REAL,                   -- 最高价
    low REAL,                    -- 最低价
    close REAL,                  -- 收盘价
    volume REAL,                 -- 成交量
    amount REAL,                 -- 成交额
    PRIMARY KEY (code, market, period, date)
);

-- 索引：按市场批量查询
CREATE INDEX idx_klines_market ON klines(market, code, period, date);

-- 股票元信息
CREATE TABLE stock_info (
    code TEXT NOT NULL,          -- 股票代码
    market TEXT NOT NULL,        -- 市场分段
    name TEXT,                   -- 股票名称
    latest_kline_date TEXT,      -- 最新K线日期
    PRIMARY KEY (code, market)
);
```

### data/watchlist.db — 自选股

```sql
CREATE TABLE watchlist (
    code TEXT,                   -- 股票代码
    market TEXT,                 -- 市场
    created_at TEXT,             -- 加入时间
    added_price TEXT,            -- 加入价格
    PRIMARY KEY (code, market)
);
```

### 市场分段定义

| key | label | 代码前缀 |
|-----|-------|---------|
| sh_main | 沪A | 600/601/603/605 |
| sz_main | 深A | 000/001/002/003 |
| gem | 创业板 | 300/301 |
| star | 科创板 | 688 |
| sz_etf | 深ETF | 159/16/18 |
| sh_etf | 沪ETF | 5-（过滤掉 600-605/688） |

## 数据同步流程

```
启动 → _startup_worker（后台线程，4 线程）
  ├─ _refresh_stock_list()    拉取在市的股票列表 → stock_list.db（已有市场才更新，同日跳过）
  ├─ _sync_klines()           遍历 stock_list.db → 增量/全量拉 K 线 → stock_detail_list.db（最近 3 年）
  └─ _cleanup_delisted()      detail 里有 list 里没有的 → 删除（退市）

手动加载市场：
  POST /api/market-db/init/<seg_key>  →  异步初始化新市场（拉列表 + 全量 K 线）
  GET  /api/market-db/init/status    →  查询进度 {running, total, done, phase}

技术选股：
  POST /api/technical/ascending-channel      →  读 stock_detail_list.db 扫描上升通道
  GET  /api/technical/ascending-channel/status →  轮询结果
```

## 缓存策略

| 数据 | 存储 | 生命周期 |
|------|------|---------|
| K 线/分时数据 | localStorage `kl_cache` | 跨天自动清 + 关弹窗清 |
| 选股列表 | localStorage `stockCache` | 跨天清商誉 |
| 自选股列表 | localStorage `watchlistCache` + SQLite | localStorage 优先，SQLite 兜底 |
| 资金流数据 | SQLite `money_flow.db` | 启动时查日期，非当日全量更新 |

## 数据源

| 数据 | 来源 |
|------|------|
| 实时行情 | 东方财富 `push2delay.eastmoney.com` |
| K 线（A 股） | 腾讯 `ifzq.gtimg.cn` + 同花顺 `d.10jqka.com.cn` |
| K 线（港股/美股） | Yahoo Finance `query1.finance.yahoo.com` |
| 分时走势 | 东方财富 `trends2`（5s 缓存，仅交易时段） |
| 股票列表 | 东方财富 `push2delay.eastmoney.com/api/qt/clist/get` |
| K 线同步 | akshare `stock_zh_a_hist`（日/周/月） |
| 大盘资金净流入 | 东方财富 `fflow/kline` |
| 融资融券 | akshare |
| 商誉/质押 | 东方财富 F10 / `RPT_CSDC_LIST` |
| 股票搜索 | 东方财富 `searchapi.eastmoney.com` |

## 快速开始

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r back_end\requirements.txt
cd back_end
python app.py
# 浏览器访问 http://localhost:5000
```

或双击 `back_end\start.bat`。

## 打包

```powershell
# 用 venv python 运行
venv\Scripts\python.exe build_exe.py
# exe 输出到 dist\鑫多多.exe
```
