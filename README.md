# 鑫多多

A股/港股/美股实时行情监控面板，支持指数分时走势、资金流向、选股、自选股（SQLite 持久化）、K 线弹窗、融资融券、恐慌/风险指数、技术选股、解禁列表、业绩报告、公司公告、异动中心。

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
│   ├── abnormal_center/               # 异动中心模块
│   │   ├── __init__.py
│   │   └── service.py                 # 异动预测/监控 API 代理 + 股票异动分析
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
│           ├── technical_screen/      # 技术选股前端
│           │   └── page.js            # 市场选择 + 选股按钮 + 结果渲染
│           ├── unlock-list/           # 解禁列表前端
│           │   └── service.js         # 解禁数据获取 + 表格渲染 + 股票筛选
│           ├── announce/               # 公司公告前端
│           │   └── service.js         # 公告获取 + 表格渲染 + 股票筛选 + 颜色标记
│           ├── earnings/              # 业绩报告前端
│           │   └── service.js         # 业绩预告/快报/报表获取 + 渲染 + 股票筛选
│           ├── abnormal/              # 异动中心前端
│           │   └── service.js         # 异动预测/监控 + 异动分析器 + 搜索历史
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

| 页面 | 功能 | 状态 |
|------|------|:--:|
| 资金流向 | 上证/深证指数分时、市场成交额、主力资金净流入、融资融券、**恐慌指数**、**风险指数** | ✅ |
| 自选股 | 自选列表、加/删自选（含价格）、批量行情（PE/PB/市值）、商誉率、量比/委比 | ✅ |
| 选股 | 多市场股票搜索（A股/港股/美股）、实时行情查询 | ✅ |
| 技术选股 | 按市场分段异步加载 K 线、**上升通道**扫描（线性回归评分排序） | ✅ |
| K 线弹窗 | LightweightCharts 蜡烛图、日K/周K/月K、分时图、五日分时、MA/布林线（A股/港股/美股通用） | ✅ |
| 解禁列表 | 限售股解禁信息（近一月），支持股票筛选 | ✅ |
| 业绩报告 | 业绩预告 + 业绩快报 + 业绩报表（近两年），支持年报/半年报/一季报/三季报细分，支持股票筛选 | ✅ |
| 公司公告 | 上市公司公告信息（最近 15 天），按重要性颜色标记，支持股票筛选 | ✅ |
| 异动中心 | 异动预测（接近异常波动阈值的股票）+ 异动监控（已触发交易所监控的股票）+ 异动分析器（单股偏离度/回撤/均线偏离分析） | ✅ |

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

### data/money_flow.db — 资金流向数据快照

```sql
CREATE TABLE market_data (
    key   TEXT PRIMARY KEY,          -- major_indices/sh_minute/fund_flow/turnover_minute/margin_trading/daily_closes/fear_index/risk_index
    value TEXT NOT NULL,             -- JSON 序列化的数据
    meta  TEXT                       -- 时间戳或日期字符串(YYYY-MM-DD)
);
```

| key | 数据 | meta |
|-----|------|------|
| major_indices | 上证/深证实时行情 | 时间戳 |
| sh_minute | 上证分时走势 | 时间戳 |
| market_breadth | 涨跌家数 | 时间戳 |
| fund_flow | 主力资金净流入 | 时间戳 |
| turnover_minute | 成交额分时 | 时间戳 |
| margin_trading | 融资融券 | 日期 |
| daily_closes | 30天日K收盘价 | 日期 |
| fear_index | 恐慌指数 | 时间戳 |
| risk_index | 风险指数 | 时间戳 |

### 市场分段定义

| key | label | 代码前缀 / 来源 |
|-----|-------|---------|
| sh_main | 沪A | 600/601/603/605 |
| sz_main | 深A | 000/001/002/003 |
| gem | 创业板 | 300/301 |
| star | 科创板 | 688 |
| bj | 北交所 | 83/87/88 |
| xsb | 新三板 | 43 |
| sz_etf | 深ETF | 159/16/18 |
| sh_etf | 沪ETF | 5 |
| hk_main | 港股 | 东方财富 API（fs=m:116+t:3） |
| us_main | 美股 | NASDAQ 官方 API |

### 数据同步流程

#### 启动增量同步（全市场）

应用启动 2 秒后自动触发，只更新 `stock_list.db` **已存在**的市场：

```
_startup_worker()
    ↓
_refresh_stock_list()         → 同日不重复拉列表
    ↓
_sync_klines()                → 对比 latest_kline_date，只拉增量
    ↓
_cleanup_delisted()           → 清理 detail 中已退市的股票
    ↓
list_sync_date_set()          → 更新各市场同步日期
```

- 股票列表同日不重复拉取（按 `sync_log.last_sync_date` 判断）
- K 线增量：`max_date >= 最近交易日` 则跳过；差 ≤7 天只拉日线，≤31 天拉日线+周线

#### 手动初始化新市场

前端选择市场 → 点击"加载" → 后台异步执行：

```
init_segment(seg_key)
    ↓
_fetch_stocks_by_segment()    → 拉取完整股票列表（分页）
    ↓
list_replace_market()         → 写入 stock_list.db
    ↓
全量 K 线同步（4 线程）        → 每只股票拉日/周/月线，写入 klines + stock_info
    ↓
_cleanup_delisted()
```

- A 股/ETF 数据来源：腾讯 K 线 API（A股）+ 同花顺 API（成交额/换手率）
- 港股/美股 K 线：Yahoo Finance（query1.finance.yahoo.com，需系统代理）
- 美股股票列表：NASDAQ 官方 screener API
- 支持"终止"操作：取消后自动回滚已写入的列表和 K 线数据

#### 收市后定时增量同步

后台线程每 60 秒检查北京时间，收市 30 分钟后自动触发**已有市场**的增量 K 线同步：

| 市场 | 收市 | 触发 | 候选市场 |
|------|------|------|---------|
| 港股 | 14:00 | 14:30 | hk_main |
| A股 | 15:00 | 15:30 | sh_main, sz_main, gem, star, sz_etf, sh_etf, bj |
| 美股 | 04:00 | 04:30 | us_main |

- **只同步 `stock_list.db` 里已有的市场**，未加载的自动跳过
- 周末跳过，同日不重复触发
- **不同市场可并行**：加载美股时港股定时同步不受影响
- 与手动加载互斥：检测到已有同步任务运行中会自动跳过

#### K 线数据源

| 市场 | 股票列表 | K 线 |
|------|---------|------|
| A 股（沪/深/创业/科创/北交/三板/ETF） | 东方财富 push2delay | 腾讯 K 线 + 同花顺（成交额/换手率） |
| 港股 | 东方财富 push2delay | Yahoo Finance（需代理） |
| 美股 | NASDAQ API | Yahoo Finance（需代理） |

## 前端 localStorage 缓存

### kl_cache — K 线弹窗缓存

```json
{
  "_date": "2026-06-06",
  "000001": {
    "day": [{ "time": "2026-01-01", "open": 10.5, ... }],
    "week": [...],
    "month": [...],
    "minute": { "times": ["09:30",...], "prices": [...], "volumes": [...], "amounts": [...] },
    "fiveday": { "times": [...], "prices": [...], "volumes": [...], "amounts": [...] },
    "extra": { "volume_ratio": 1.2, "bid_ratio": 0.8 },
    "quotes": { "price": "10.50", "pct": "+2.5%", ... }
  }
}
```
| 字段 | 说明 |
|------|------|
| `_date` | 缓存日期，跨天自动清空 |
| `{code}` | 股票代码为 key |
| `day/week/month` | K 线数组 |
| `minute` | 当日分时数据 |
| `fiveday` | 五日分时数据 |
| `extra` | 量比 / 委比 |
| `quotes` | 行情快照（价格/涨跌/PE/PB 等） |

### stockCache — 选股列表缓存

```json
{
  "date": "2026-06-06",
  "stocks": [
    { "code": "000001", "market": "0", "gw": 5.23, "pld": 12.5, "addedDate": "2026-05-01", "addedPrice": "10.50" }
  ]
}
```
| 字段 | 说明 |
|------|------|
| `date` | 缓存日期，跨天商誉/质押数据失效 |
| `stocks[].code` | 股票代码 |
| `stocks[].market` | 市场 |
| `stocks[].gw` | 商誉率 (%) |
| `stocks[].pld` | 质押率 (%) |
| `stocks[].addedDate` | 加入自选日期 |
| `stocks[].addedPrice` | 加入自选时价格 |

### watchlistCache — 自选股列表缓存

结构同 `stockCache`，独立存储自选股列表。SQLite `watchlist.db` 作为跨设备兜底。

### 缓存清理

清除缓存按钮调用 `clearAllCaches()` 清除 `kl_cache` / `stockCache` / `watchlistCache` / `abnormal-calc-history-v1` / `stock-search-history-v1` 五个 key，同时立即刷新页面列表。

## 数据同步流程

### 启动时加载

应用启动时启动两个后台线程：

```
app.run()
  │
  ├─ [立即] 行情轮询线程 _background_poller()
  │   ├─ 首次启动：若当日缓存不存在，一次性全量抓取 7 类数据 → money_flow.db
  │   │     ① major_indices     上证/深证指数实时行情（东方财富 push2delay）
  │   │     ② market_breadth    沪深两市涨跌家数（东方财富 push2delay）
  │   │     ③ sh_minute         上证指数日内分时走势（东方财富 trends2）
  │   │     ④ fund_flow         主力资金净流入分时（东方财富 fflow/kline）
  │   │     ⑤ turnover_minute   全市场成交额分时（同花顺 dq.10jqka.com.cn）
  │   │     ⑥ margin_trading    近 60 天融资融券余额（上交所 + 深交所）
  │   │     ⑦ daily_closes      沪深指数近 30 天日K收盘价（腾讯 ifzq.gtimg.cn）
  │   │
  │   └─ 交易时段循环（周一至五 09:15-11:35, 12:55-15:05）：
  │       ├─ 每 5s：刷新 ①（大盘指数）
  │       └─ 每 60s：刷新 ②③④⑤⑥⑦（当日一次性数据仅首次刷新）
  │
  └─ [延迟 2s] 全市场同步线程 _startup_worker()（4 线程并发）
      │
      ├─ 步骤1 _refresh_stock_list()  →  拉取在市的股票列表 → stock_list.db
      │     只拉取 stock_list.db 中已存在的市场分段（非全部 SEGMENTS）
      │     分页拉取（东方财富 push2delay，每页 1000 条）
      │     通过 f2（价格）字段过滤退市股（价格为 '-' 的排除）
      │     list_replace_market 全量替换：该段旧数据全部删除后重新写入
      │     同日已同步的市场跳过
      │
      ├─ 步骤2 _sync_klines()  →  遍历 stock_list.db → 增量/全量 K 线 → stock_detail_list.db
      │     预加载 stock_info 为内存 map（避免每只查 DB），仅提交需要更新的股票
      │     周末自动推算最近交易日（周六/日回退到周五），非交易时段跳过已同步股票
      │     增量优化：
      │       · 按实际间隔天数请求条数（差 1 天只拉 11 条，而非 800 条）
      │       · 差 ≤7 天只拉日线（周/月线新周期未生成）
      │       · 差 ≤31 天拉日线 + 周线
      │       · >31 天或全新才拉日/周/月全量
      │     写入使用 BEGIN IMMEDIATE 单事务，K 线 + latest_kline_date 原子落盘
      │     SQLite WAL 模式 + PRAGMA synchronous=FULL，中途重启不丢进度
      │
      └─ 步骤3 _cleanup_delisted()  →  detail 里有 list 里没有的 → 删除 K 线和元信息（退市股票）
```

### 按需加载（API 实时拉取）

以下 API 由前端在用户操作时触发，实时从外部数据源拉取（不做服务端持久化缓存）：

| API | 数据 | 数据源 |
|-----|------|--------|
| `GET /api/stock-quotes` | 批量股票实时行情（价/量/额/换手/PE/PB/市值） | 东方财富 push2delay |
| `GET /api/stock-extra` | 单只股票量比/委比 | 东方财富 push2delay |
| `GET /api/stock-minute` | 个股分时走势 | A股：东方财富（单日）/ 新浪（多日）；港股美股：Yahoo Finance |
| `GET /api/stock-kline` | 个股K线（日/周/月） | A股：腾讯（前复权）+ 同花顺（成交额/换手率）；港股美股：Yahoo Finance |
| `GET /api/search-stock` | 股票搜索（名称/代码）+ 实时行情 | 东方财富 searchapi |
| `GET /api/goodwill` | 商誉率 + 质押率（10 线程并发） | 东方财富 财务报表 + 数据中心 |
| `GET /api/stock-concepts` | 单只股票核心概念题材 | 东方财富 CoreConception |
| `GET /api/stock-biz-comp` | 单只股票主营构成（按产品分类） | 东方财富 BusinessAnalysis |
| `GET /api/lifting` | 自选股+选股列表限售股解禁（近一月） | adata 库 |
| `GET /api/announcements` | 自选股+选股列表公司公告（近 15 天） | 东方财富 公告 API |
| `GET /api/earnings` | 自选股+选股列表业绩报告（近两年）：业绩预告 + 业绩快报 + 业绩报表 | 东方财富 数据中心 |
| `GET /api/abnormal/prediction` | 异动预测（接近交易所异常波动阈值的股票，按 今日/次日/未标记 分组） | 悟道数据（stock.quicktiny.cn） |
| `GET /api/abnormal/monitor` | 异动监控（已被交易所重点监控的股票列表，含统计） | 悟道数据（stock.quicktiny.cn） |
| `POST /api/abnormal/analyze` | 异动分析器（单只股票偏离度/回撤/均线偏离/涨跌停价测算） | 腾讯 K 线 API + 本地计算 |

### 聚合计算（基于缓存）

以下 API 从 `money_flow.db` 缓存读取数据后，在服务端加权聚合计算得出指数值（缓存 60s）：

| API | 指标 | 依赖缓存数据 | 分项权重 |
|-----|------|-------------|----------|
| `GET /api/fear-index` | 恐慌指数 0-100 | major_indices + sh_minute + market_breadth + fund_flow | 指数压力(22) + 日内压力(28) + 广度压力(22) + 资金压力(12) + 稳定因子(6) + 基础分(20) |
| `GET /api/risk-index` | 风险指数 0-100 | margin_trading + daily_closes + market_breadth | 融资因子(35) + 趋势因子(30) + 情绪因子(20) + 结构因子(15) |

### 手动操作

```
手动加载新市场：
  POST /api/market-db/init/<seg_key>  →  异步初始化新市场（拉列表 + 全量 K 线）
  GET  /api/market-db/init/status    →  查询进度 {running, total, done, phase}

技术选股（离线扫描，不请求外部数据源）：
  POST /api/technical/ascending-channel      →  读 stock_detail_list.db 扫描上升通道（30 线程并发）
      取最近 120 条日K，线性回归拟合通道，R²>=0.6 且通道宽度<30% 且量比>0.8
  GET  /api/technical/ascending-channel/status →  轮询进度
```

### 前端页面加载与自动刷新

前端页面启动时注册全局 10 秒定时器，按当前页面和交易时段决定刷新粒度。

#### 全局启动

```
页面加载 (index.html)
  ├─ loadAllData()              资金流向页初始加载（7 个 API 并行请求）
  ├─ loadPickedStocks()         选股页列表恢复（从 localStorage stockCache）
  ├─ loadWatchlistStocks()      自选股页列表恢复（GET /api/watchlist 获取权威列表 → 缓存补充商誉/质押 → 缓存中多余的股票自动清理）
  └─ setInterval(refreshRealtimeData, 10000)  全局 10 秒定时器（永不停止）
       └─ 内部判断：isInTradingHours() + currentNavPage 决定刷新哪些数据
```

#### 资金流向页

| 时机 | 触发 | API | 频率 |
|------|------|-----|------|
| 初始加载 / 导航切换 | `loadAllData()` → 并行请求 | 上证/深证指数、成交额分时、资金流向、融资融券、恐慌指数、风险指数、上证分时 | 一次性全量 |
| 交易时段自动刷新（每 10s 触发，60s 粒度） | `refreshRealtimeData()` | `major-indices`（每 10s）+ 其余 6 项（每 60s） + `margin-trading`（每天一次） | 10s/60s/每日 |
| 点击"清理缓存"按钮 | `clearAllCaches()` + `loadAllData()` | 同上初始加载 | 手动 |

#### 选股页（纯前端缓存，后端无持久化）

| 时机 | 触发 | API | 频率 |
|------|------|-----|------|
| 初始加载 | `loadPickedStocks()` | 从 localStorage `stockCache` 恢复列表 → `stock-quotes` + `goodwill` | 一次性 |
| 交易时段自动刷新 | `refreshRealtimeData()` | `stock-quotes`（仅更新价格列，不重建表格） | 每 10s |
| 搜索股票 | 输入框输入（防抖 300ms） | `search-stock` | 每次输入 |
| 添加股票 | 点击搜索结果 | `stock-quotes` + `goodwill` | 事件触发 |
| 删除股票 | 点击 × 按钮 | 无 API（仅操作 localStorage） | 事件触发 |

#### 自选股页（后端 SQLite 持久化 + 前端缓存补充）

| 时机 | 触发 | API | 频率 |
|------|------|-----|------|
| 初始加载 | `loadWatchlistStocks()` | `GET /api/watchlist`（权威列表）→ localStorage 补充商誉/质押 → `stock-quotes` + `goodwill` | 一次性 |
| 交易时段自动刷新 | `refreshRealtimeData()` | `stock-quotes`（仅更新价格列，不重建表格） | 每 10s |
| 添加股票 | 点击搜索结果 | `stock-quotes`（获取加入价格）→ `POST /api/watchlist`（持久化）→ `goodwill` | 事件触发 |
| 删除股票 | 点击 × 按钮 | `DELETE /api/watchlist/{code}`（异步删除） | 事件触发 |

#### K 线弹窗

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 打开弹窗 | 点击股票名称 | `stock-quotes` + `stock-kline(day)` + `goodwill` + `stock-extra` + `stock-biz-comp` | 5 个 API 并行请求；有 localStorage 缓存则跳过 |
| 弹窗头部行情 | `setInterval(_refreshHeaderData, 10000)` | `stock-quotes` + `stock-extra` | 交易时段每 10s |
| 切换到分时图 | `_loadMinuteChart()` | `stock-minute` + `setInterval(_refreshMinuteData, 60000)` | 交易时段每 60s |
| 切换到五日分时 | `_loadFiveDayMinute()` | `stock-minute(days=5)` + `setInterval(_refreshFiveDayData, 60000)` | 交易时段每 60s |
| 切换 K 线周期 | `_switchPeriod()` | `stock-kline(period)` | 有缓存直接用，无缓存才请求 |
| 关闭弹窗 | `close()` | 清除当前股票在 kl_cache 中的行情/分时/K线缓存 + 清除所有定时器 | — |

#### 技术选股页

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 页面加载 | 模块初始化 | `market-db/segments` | 获取市场分段列表 |
| 加载市场数据 | 点击"加载"按钮 | `POST market-db/init/{key}` + `GET init/status`（每 1s 轮询进度） | 手动 |
| 运行选股 | 点击"上升通道"按钮 | `POST ascending-channel` + `GET status`（每 2s 轮询进度） | 手动 |

#### 解禁列表页

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 导航切换 | `loadUnlockList()` | `GET /api/lifting?codes={codes}` | 收集自选+选股代码 → 调 adata 获取近一月解禁 → 表格渲染 |
| 股票筛选 | 下拉框 onchange | 复用已加载数据前端过滤 | 仅显示选中股票 |

#### 业绩报告页

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 导航切换 | `loadEarningsList()` | `GET /api/earnings?codes={codes}` | 收集自选+选股代码 → 并行调三个东方财富数据中心 API → 按股票分组排序渲染 |
| 股票筛选 | 下拉框 onchange | 复用已加载数据前端过滤 | 仅显示选中股票 |

#### 公司公告页

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 导航切换 | `loadAnnounceList()` | `GET /api/announcements?codes={codes}` | 收集自选+选股代码 → 调东方财富公告 API（近 15 天）→ 按公告类型颜色标记渲染 |
| 股票筛选 | 下拉框 onchange | 复用已加载数据前端过滤 | 仅显示选中股票 |

#### 异动中心

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 导航切换 | `loadAbnormalCenter()` | 按当前 Tab 调用对应 API | 三个 Tab 懒加载：切换 Tab 时才请求数据 |
| 切换 Tab | `switchAbnormalTab(tab)` | 按需调用 | 预测/监控 Tab 每次切换重新拉取最新数据 |
| 分析器搜索 | 输入框 oninput（防抖） | `search-stock` | 实时搜索股票名称/代码 |
| 分析器执行 | 点击"分析"按钮 | `POST abnormal/analyze` | 调腾讯 K 线 → 计算偏离度/回撤/均线等指标 → 渲染分析卡片 |
| 分析器历史 | 每次分析自动保存 | localStorage | 上限 10 条，重复去重，点击历史标签快捷重新分析 |

#### 前端定时器汇总

| 定时器 | 间隔 | 作用域 | 条件 |
|--------|------|--------|------|
| `refreshRealtimeData` | 10s | 全局 | 交易时段 + 当前页面判断 |
| `_headerTimer` | 10s | K线弹窗 | 交易时段 |
| `_minuteTimer` | 60s | K线弹窗（分时模式） | 交易时段 |
| `_fiveDayTimer` | 60s | K线弹窗（五日模式） | 交易时段 |
| `_initPollTimer` | 1s | 技术选股（市场初始化中） | 任务完成清除 |
| `_techPollTimer` | 2s | 技术选股（选股扫描中） | 任务完成清除 |

#### localStorage 缓存

| Key | 使用页面 | 内容 | 持久化 | 跨天策略 |
|-----|----------|------|--------|----------|
| `kl_cache` | K线弹窗 | K线/分时/五日/行情/商誉/量比委比 | 纯缓存 | 跨天全删；交易时段关闭弹窗清除非商誉缓存 |
| `stockCache` | 选股页 | 已选股票列表 + 商誉/质押 | 纯缓存，后端无持久化 | 跨天商誉失效，列表保留 |
| `watchlistCache` | 自选股页 | 自选股数据补充（商誉/质押） | API 为权威来源（`watchlist.db`），缓存仅作补充 | 跨天商誉失效；API 返回的列表覆盖缓存中多余条目 |
| `abnormal-calc-history-v1` | 异动中心（分析器） | 搜索历史 [{code, name, market}] | 纯前端持久化，上限 10 条 | 跨天保留 |
| `stock-search-history-v1` | 选股页 | 搜索历史 [{code, name, market}] | 纯前端持久化，上限 10 条 | 跨天保留 |

手动清理：点击"清理缓存"按钮 → 删除全部五个 key → 重新加载列表。

## 数据源

### 东方财富

| 数据 | 接口 |
|------|------|
| 大盘指数实时行情 | `push2delay.eastmoney.com/api/qt/ulist.np/get` |
| 股票批量实时行情（价/量/额/换手/PE/PB/市值） | `push2delay.eastmoney.com/api/qt/ulist.np/get` |
| 单只股票量比/委比 | `push2delay.eastmoney.com/api/qt/stock/get` |
| 上证指数日内分时 | `push2delay.eastmoney.com/api/qt/stock/trends2/get` |
| 个股单日分时 | `push2delay.eastmoney.com/api/qt/stock/trends2/get` |
| 主力资金净流入分时 | `push2delay.eastmoney.com/api/qt/stock/fflow/kline/get` |
| 沪深涨跌家数 | `push2delay.eastmoney.com/api/qt/ulist.np/get` |
| 股票列表（分市场分页拉取） | `push2delay.eastmoney.com/api/qt/clist/get` |
| 股票搜索 | `searchapi.eastmoney.com/api/suggest/get` |
| 商誉率 | `emweb.securities.eastmoney.com/PC_HSF10/FinanceAnalysis/FinanceAnalysis` + `NewFinanceAnalysis/ZYZWNewFinanceAnalysis` |
| 质押率 | `datacenter-web.eastmoney.com/api/data/v1/get` |
| 股票核心概念题材 | `emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax` |
| 主营构成（按产品分类） | `emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/PageAjax` |
| 公司公告 | `np-anotice-stock.eastmoney.com/api/security/ann` |
| 业绩预告 | `datacenter-web.eastmoney.com/api/data/v1/get`（reportName: RPT_PUBLIC_OP_NEWPREDICT） |
| 业绩快报 | `datacenter-web.eastmoney.com/api/data/v1/get`（reportName: RPT_FCI_PERFORMANCEE） |
| 业绩报表 | `datacenter-web.eastmoney.com/api/data/v1/get`（reportName: RPT_LICO_FN_CPD） |

### 腾讯证券

| 数据 | 接口 |
|------|------|
| A 股 K 线（日/周/月，前复权） | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` |
| 沪深指数近 30 天日K收盘价 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` |

### 同花顺

| 数据 | 接口 |
|------|------|
| A 股 K 线成交额 / 换手率（补充腾讯接口缺少的字段） | `d.10jqka.com.cn/v2/line/stock_zh_a_hist` |
| 全市场成交额分时 | `dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data` |

### 新浪财经

| 数据 | 接口 |
|------|------|
| A 股多日分时走势（5 分钟K线） | `money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData` |

### Yahoo Finance

| 数据 | 接口 |
|------|------|
| 港股 / 美股 K 线（日/周/月） | `query1.finance.yahoo.com/v8/finance/chart/{symbol}` |
| 港股 / 美股多日分时 | `query1.finance.yahoo.com/v8/finance/chart/{symbol}` |

### adata（Python 库）

| 数据 | 接口 |
|------|------|
| 限售股解禁（近一月） | `adata.sentiment.stock_lifting_last_month()` |

### 悟道数据（Wudao Ashare）

| 数据 | 接口 |
|------|------|
| 异动预测（接近交易所异常波动阈值） | `stock.quicktiny.cn/api/ladder/exchange-monitor/prediction` |
| 异动监控（已触发交易所监控） | `stock.quicktiny.cn/api/ladder/exchange-monitor/list?type=all` |

> 开源项目：[github.com/jcdreamjc/wudao-ashare](https://github.com/jcdreamjc/wudao-ashare)，专为 AI Agent 设计的 A 股实时数据套件（26 个 API），本项目仅代理其中异动相关接口。

### 交易所

| 数据 | 接口 |
|------|------|
| 融资融券余额（沪市） | `query.sse.com.cn/marketdata/tradedata/queryMargin.do` |
| 融资融券余额（深市） | `www.szse.cn/api/report/ShowReport/data` |

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
