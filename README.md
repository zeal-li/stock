# 鑫多多

A股/港股/美股实时行情监控面板，支持指数分时走势、资金流向、选股、自选股（SQLite 持久化）、K 线弹窗、融资融券、恐慌/风险指数、技术选股、解禁列表、业绩报告、公司公告、异动中心、龙虎榜、全球行情（指数/大宗商品/外汇）、板块资金流向、ML 训练（XGBoost）。

## 目录结构

```
stock/
├── .gitignore
├── README.md
├── note.md
├── note2.md
├── strategie.md
├── build_exe.py                       # PyInstaller 打包入口
├── gitpush.bat
├── 鑫多多.spec                         # PyInstaller spec 文件
│
├── back_end/                          # 🔧 后端（Flask）
│   ├── app.py                         # 主入口：路由 + 启动 + 后台定时器
│   ├── requirements.txt
│   ├── start.bat / stop.bat / restart.bat / train_ml.bat
│   │
│   ├── common/                        # 公共模块
│   │   ├── __init__.py
│   │   ├── utils.py                   # 格式化 + is_etf 等
│   │   └── finance.py                 # 商誉率 + 质押率
│   │
│   ├── data/                          # 运行时数据（.gitignore）
│   │   ├── stock_lib.db               # 市场 + 股票列表 + K线 + 股票元信息（合并单库）
│   │   ├── money_flow.db              # 资金流、融资融券历史数据
│   │   ├── watchlist.db               # 自选股持久化
│   │   ├── longhu_bang.db             # 龙虎榜每日明细（SQLite 缓存，90 天自动清理）
│   │   └── sector_fund.db             # 板块资金流向缓存（10s TTL）
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
│   ├── longhu_bang/                   # 龙虎榜模块
│   │   ├── __init__.py
│   │   └── service.py                 # 龙虎榜数据爬取（同花顺）+ SQLite 缓存 + 席位解析
│   │
│   ├── global_market/                 # 全球行情模块
│   │   ├── __init__.py
│   │   ├── indices.py                 # 全球指数实时行情（A股8大指数 + 海外7大指数，新浪财经）
│   │   ├── commodities.py             # 大宗商品行情（贵金属/有色金属/能化/黑色系/农产品，新浪财经）
│   │   └── forex.py                   # 外汇汇率行情（离岸/在岸人民币 + 主流货币对，新浪财经）
│   │
│   ├── sector_fund/                   # 板块资金流向模块
│   │   ├── __init__.py
│   │   ├── service.py                 # 行业/概念板块主力流入流出排行 + 成分股（东方财富）
│   │   └── storage.py                 # SQLite 缓存存储（10s TTL）
│   │
│   ├── stock_pick/                    # 选股模块
│   │   ├── __init__.py
│   │   └── service.py
│   │
│   ├── technical_screen/              # 技术选股模块
│   │   ├── __init__.py
│   │   ├── service.py                 # 策略扫描引擎（三上悠亚），支持 pipeline 串联，扫描后自动附加预测评分
│   │   └── strategies/                # 策略实现
│   │       ├── __init__.py
│   │       ├── san_shang_you_ya.py    # 三上悠亚：三周期布林中上轨共振
│   │       └── prediction.py          # 明日涨跌预测：多因子评分模型（不独立显示，附在筛选结果后）
│   │
│   ├── abnormal_center/               # 异动中心模块
│   │   ├── __init__.py
│   │   └── service.py                 # 异动预测/监控 API 代理 + 股票异动分析
│   │
│   ├── ml_train/                      # ML 训练模块（XGBoost）
│   │   ├── __init__.py
│   │   ├── features.py                # 特征工程：45 维技术指标（MA偏离/均线排列/量价/布林/RSI/MACD/动量/波动率/ATR/KDJ/OBV/CCI/WR/MFI/大盘对比等）
│   │   ├── train.py                   # XGBoost 训练脚本：日K线 → 特征+标签 → 训练 → 保存最优模型
│   │   ├── model.pkl                  # 当前最优模型（joblib 序列化）
│   │   ├── feature_names.txt          # 特征名列表
│   │   └── training_history.csv       # 每次训练记录（AUC/样本数/是否最优）
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
│           ├── longhu/               # 龙虎榜前端
│           │   └── service.js         # 交易日历 + 日期选择 + 分类标签（全部/机构/游资/机构+游资）+ 席位明细展开 + 表格渲染
│           ├── global_market/         # 全球行情前端
│           │   ├── indices.js         # 全球指数渲染（A股8指数 + 海外7指数）
│           │   ├── commodities.js     # 大宗商品网格渲染（7行 × 12列）+ 全球指数联动
│           │   └── forex.js           # 外汇汇率网格渲染（2排 × 12列）
│           ├── sector_fund/           # 板块资金前端
│           │   └── sector_fund.js     # 行业/概念切换 + 今日/5日/10日切换 + 流入流出双表 + 成分股弹窗
│           ├── technical_screen/      # 技术选股前端
│           │   └── page.js            # 市场选择 + 选股按钮 + 结果渲染
│           ├── unlock-list/           # 解禁列表前端
│           │   └── service.js         # 解禁数据获取 + 表格渲染 + 股票筛选
│           ├── announce/               # 公司公告前端
│           │   └── service.js         # 公告获取 + 表格渲染 + 股票筛选 + 颜色标记
│           ├── earnings/              # 业绩报告前端
│           │   └─ service.js         # 业绩预告/快报/报表获取 + 渲染 + 股票筛选
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
| 技术选股 | 按市场分段异步加载 K 线、**三上悠亚**布林带三周期共振扫描 + **明日涨跌预测**评分 | ✅ |
| K 线弹窗 | LightweightCharts 蜡烛图、日K/周K/月K、分时图、五日分时、MA/布林线（A股/港股/美股通用） | ✅ |
| 解禁列表 | 限售股解禁信息（近一月），支持股票筛选 | ✅ |
| 业绩报告 | 业绩预告 + 业绩快报 + 业绩报表（近两年），支持年报/半年报/一季报/三季报细分，支持股票筛选 | ✅ |
| 公司公告 | 上市公司公告信息（最近 15 天），按重要性颜色标记，支持股票筛选 | ✅ |
| 异动中心 | 异动预测（接近异常波动阈值的股票）+ 异动监控（已触发交易所监控的股票）+ 异动分析器（单股偏离度/回撤/均线偏离分析） | ✅ |
| 龙虎榜 | 每日龙虎榜明细（同花顺数据源），日期选择器 + 分类标签（全部/机构榜/游资榜/机构+游资）+ 买卖席位明细展开 + 90天自动清理 | ✅ |
| 全球行情 | 全球指数（A股8大 + 海外7大）+ 大宗商品（贵金属/有色/能化/黑色/农产品，7行×12列）+ 外汇汇率（离岸/在岸人民币 + 主流货币对，新浪财经） | ✅ |
| 板块资金 | 行业/概念板块主力资金流入/流出排行（今日/5日/10日），板块成分股弹窗（按涨跌幅排序） | ✅ |

## SQLite 数据库表结构

### data/stock_lib.db — 市场 + 股票列表 + K线 + 股票元信息（合并单库）

```sql
-- 市场元信息（每个市场一条记录）
CREATE TABLE stock_market (
    market       TEXT PRIMARY KEY,  -- 市场分段（hs_main/gem/star/hs_etf/hk_main/us_main）
    sync_ts      TEXT,              -- K线上次同步完成时间（全部个股成功后写入）
    list_sync_ts TEXT               -- 股票列表上次拉取时间
);

-- 股票列表（每个市场 N 条记录）
CREATE TABLE market_stock_list (
    code   TEXT NOT NULL,
    market TEXT NOT NULL,
    name   TEXT,                    -- 股票名称
    PRIMARY KEY (code, market)
);

-- K 线数据
CREATE TABLE stock_klines (
    code   TEXT NOT NULL,
    market TEXT NOT NULL,
    period TEXT NOT NULL,           -- daily / weekly / monthly
    date   TEXT NOT NULL,           -- YYYYMMDD
    open   REAL,
    high   REAL,
    low    REAL,
    close  REAL,
    volume REAL,
    amount REAL,
    PRIMARY KEY (code, market, period, date)
);
CREATE INDEX idx_klines_market ON stock_klines(market, code, period, date);

-- 股票元信息（per-period 独立时间戳）
CREATE TABLE stock_info (
    code       TEXT NOT NULL,
    market     TEXT NOT NULL,
    name       TEXT,                -- 股票名称
    daily_ts   TEXT,                -- 日K最后更新成功时间戳（判断是否需拉取日K）
    weekly_ts  TEXT,                -- 周K最后更新成功时间戳
    monthly_ts TEXT,                -- 月K最后更新成功时间戳
    PRIMARY KEY (code, market)
);
```

> `daily_ts` / `weekly_ts` / `monthly_ts`：三个周期独立记录最后更新时间戳。增量更新时各周期独立判断是否需要拉取——日K落后了就只拉日K，周K月K没落后就跳过。该字段与 K 线数据在 `stock_info_sync_atomic()` 中同一事务原子写入。

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

### data/longhu_bang.db — 龙虎榜数据缓存

```sql
CREATE TABLE longhu_bang (
    trade_date TEXT PRIMARY KEY,  -- 交易日期（YYYY-MM-DD）
    data       TEXT NOT NULL,     -- JSON 序列化的龙虎榜明细（含席位、上榜原因）
    created_at TEXT DEFAULT (datetime('now'))
);
```

> 启动时自动清理 90 天前的数据（`cleanup_old_data()`）。首次请求某日数据时从同花顺爬取并入库，后续直接读缓存。

### data/sector_fund.db — 板块资金流向缓存

```sql
CREATE TABLE sector_fund (
    key       TEXT PRIMARY KEY,   -- 格式: {sector_type}_{period}_{top}，如 concept_today_inflow
    value     TEXT NOT NULL,      -- JSON 序列化的板块排行列表
    updated_at REAL NOT NULL      -- 写入时间戳（用于 TTL 判断）
);
```

> TTL = 60s，过期后重新请求东方财富 API 并更新缓存。

### 市场分段定义

| key | label | 代码前缀 / 来源 |
|-----|-------|---------|
| hs_main | 沪深A | 600/601/603/605/000/001/002/003 |
| gem | 创业板 | 300/301 |
| star | 科创板 | 688 |
| hs_etf | 沪深ETF | 5/159/16/18 |
| hk_main | 港股 | 东方财富 API（fs=m:116+t:3） |
| us_main | 美股 | 东方财富 API（fs=m:105,m:106,m:107） |

### 数据同步流程

#### 手动初始化新市场

前端选择市场 → 点击"加载" → 后台异步执行：

```
init_segment(seg_key)
    ↓
_fetch_stocks_by_segment()    → 拉取完整股票列表（分页）
    ↓
stock_list_replace_market()   → 全量替换写入 market_stock_list
    ↓
全量 K 线同步（4 线程）        → 每只股票拉日/周/月线，stock_info_sync_atomic 原子写 stock_info
    ↓
_cleanup_delisted()           → 清理 stock_info 有但列表无的退市股
    ↓
market_sync_ts_set()          → 全部完成后写入 stock_market.sync_ts
```

- A 股/ETF 数据来源：同花顺 K 线 API（d.10jqka.com.cn）
- 港股/美股 K 线：Yahoo Finance（query1.finance.yahoo.com）
- 美股股票列表：东方财富 push2delay
- 支持"终止"操作：取消后自动回滚（删除已写入的列表和 K 线数据）

#### 增量更新已有市场

前端选择市场 → 点击"更新" / 后台定时触发：

```
update_market(seg_key)
    ↓
_need_update()                → 检查 stock_market.sync_ts，判断市场是否需要更新
    ↓
_list_need_refresh()          → 判断股票列表是否需要重拉（需要则拉取并全量替换）
    ↓
筛选 to_update                → 对比 stock_info 的 daily_ts/weekly_ts/monthly_ts 与最近交易日
    ↓
增量 K 线同步（4 线程）        → per-period 独立判断，只拉需要更新的周期
    ↓（全部个股完成后）
market_sync_ts_set()          → 写入 stock_market.sync_ts
    ↓
_cleanup_delisted()
```

- **中途终止不回退**：已完成个股的 kline + stock_info 已落地，stock_market.sync_ts 未写。下次更新自动跳已完成个股，续传剩余
- `_need_update()` 逻辑：对比 stock_market.sync_ts 与当前时间，考虑各市场交易时间（A 股 9:30-15:00，港股 9:30-16:00，美股 21:30-04:00），跨 1 个交易日以上需更新
- per-period 增量判断：各周期独立对比时间戳，日K落后只拉日K，周K月K不落后就跳过

#### 收市后定时增量同步

后台线程每 60 秒检查北京时间，收市 30 分钟后自动触发**已有市场**的增量 K 线同步：

| 市场 | 收市 | 触发 | 候选市场 |
|------|------|------|---------|
| 港股 | 14:00 | 14:30 | hk_main |
| A股 | 15:00 | 15:30 | hs_main, gem, star, hs_etf |
| 美股 | 04:00 | 04:30 | us_main |

- **只同步 `stock_list.db` 里已有的市场**，未加载的自动跳过
- 周末跳过，同日不重复触发
- **不同市场可并行**：加载美股时港股定时同步不受影响
- 与手动加载互斥：检测到已有同步任务运行中会自动跳过

#### K 线数据源

| 市场 | 股票列表 | K 线 |
|------|---------|------|
| A 股（沪/深/创业/科创/ETF） | 东方财富 push2delay | 同花顺 d.10jqka.com.cn（含成交额、换手率） |
| 港股 | 东方财富 push2delay | Yahoo Finance |
| 美股 | 东方财富 push2delay | Yahoo Finance |

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

应用启动时启动后台线程：

```
app.run()
  │
  ├─ [立即] 行情轮询线程 _background_poller()
  │   ├─ 首次启动：若当日缓存不存在，一次性全量抓取 7 类数据 → money_flow.db
  │   │     ① major_indices     上证/深证指数实时行情（东方财富 push2delay）
  │   │     ② market_breadth    涨跌家数（东方财富 push2delay）
  │   │     ③ sh_minute         上证指数日内分时走势（东方财富 trends2）
  │   │     ④ fund_flow         主力资金净流入分时（东方财富 fflow/kline）
  │   │     ⑤ turnover_minute   成交额分时（同花顺 dq.10jqka.com.cn）
  │   │     ⑥ margin_trading    近 60 天融资融券余额（上交所 + 深交所）
  │   │     ⑦ daily_closes      沪深指数近 30 天日K收盘价（腾讯 ifzq.gtimg.cn）
  │   │
  │   └─ 交易时段循环（周一至五 09:15-11:35, 12:55-15:05）：
  │       ├─ 每 5s：刷新 ①（大盘指数）
  │       └─ 每 60s：刷新 ②③④⑤⑥⑦（当日一次性数据仅首次刷新）
  │
  ├─ [立即] cleanup_old_data()  →  清理 longhu_bang.db 中 90 天前的龙虎榜数据
  │
  └─ [延迟 2s] 全市场同步线程 _startup_worker()（4 线程并发）
      │
      ├─ 步骤1 _refresh_stock_list()  →  拉取在市的股票列表 → market_stock_list
      │     只拉取 stock_market 中已存在的市场分段（非全部 SEGMENTS）
      │     分页拉取（东方财富 push2delay，每页 1000 条）
      │     通过 f2（价格）字段过滤退市股（价格为 '-' 的排除）
      │     stock_list_replace_market 全量替换：该段旧数据全部删除后重新写入
      │     按 stock_market.sync_ts 同日已同步的市场跳过
      │
      ├─ 步骤2 _sync_klines()  →  遍历 market_stock_list → 增量/全量 K 线 → stock_klines + stock_info
      │     预加载 stock_info 为内存 map（避免每只查 DB），仅提交需要更新的股票
      │     周末自动推算最近交易日（周六/日回退到周五），非交易时段跳过已同步股票
      │     per-period 独立判断：各周期独立对比时间戳，只拉需要的周期
      │     写入使用 BEGIN IMMEDIATE 单事务，stock_klines + stock_info 原子落盘
      │     SQLite WAL 模式 + PRAGMA synchronous=FULL，中途重启不丢进度
      │     全部个股完成后写入 stock_market.sync_ts
      │
      └─ 步骤3 _cleanup_delisted()  →  stock_info 有但列表里没有的 → 删除 K 线和元信息（退市股票）
```

### 按需加载（API 实时拉取）

以下 API 由前端在用户操作时触发，实时从外部数据源拉取（不做服务端持久化缓存）：

| API | 数据 | 数据源 |
|-----|------|--------|
| `GET /api/stock-quotes` | 批量股票实时行情（价/量/额/换手/PE/PB/市值） | 东方财富 push2delay |
| `GET /api/stock-extra` | 单只股票量比/委比 | 东方财富 push2delay |
| `GET /api/stock-minute` | 个股分时走势 | A股：东方财富（单日）/ 新浪（多日）；港股美股：Yahoo Finance |
| `GET /api/stock-kline` | 个股K线（日/周/月） | A股：同花顺 d.10jqka.com.cn（前复权，含成交额/换手率）；港股美股：Yahoo Finance |
| `GET /api/search-stock` | 股票搜索（名称/代码）+ 实时行情 | 东方财富 searchapi |
| `GET /api/goodwill` | 商誉率 + 质押率（10 线程并发） | 东方财富 财务报表 + 数据中心 |
| `GET /api/stock-concepts` | 单只股票核心概念题材 | 东方财富 CoreConception |
| `GET /api/stock-biz-comp` | 单只股票主营构成（按产品分类） | 东方财富 BusinessAnalysis |
| `GET /api/lifting` | 自选股+选股列表限售股解禁（近一月） | adata 库 |
| `GET /api/announcements` | 自选股+选股列表公司公告（近 15 天） | 东方财富 公告 API |
| `GET /api/earnings` | 自选股+选股列表业绩报告（近两年）：业绩预告 + 业绩快报 + 业绩报表 | 东方财富 数据中心 |
| `GET /api/abnormal/prediction` | 异动预测（接近交易所异常波动阈值的股票，按 今日/次日/未标记 分组） | 悟道数据（stock.quicktiny.cn） |
| `GET /api/abnormal/monitor` | 异动监控（已被交易所重点监控的股票列表，含统计） | 悟道数据（stock.quicktiny.cn） |
| `POST /api/abnormal/analyze` | 异动分析器（单只股票偏离度/回撤/均线偏离/涨跌停价测算） | 同花顺 K 线 API + 本地计算 |
| `POST /api/stock-predictions` | 批量明日涨跌预测评分（基于K线多因子模型：短期动量+量价关系+位置高低+K线形态） | stock_detail_list.db + 本地计算 |
| `GET /api/longhu-bang?date=` | 龙虎榜每日明细（含买卖席位、上榜原因、机构/游资标签） | 同花顺 lhbggxq + SQLite 缓存（90 天自动清理） |
| `GET /api/global-commodities` | 全球大宗商品行情（贵金属/有色/能化/黑色/农产品，7行×12列）+ 全球指数 | 新浪财经 hq.sinajs.cn |
| `GET /api/global-forex` | 外汇汇率行情（离岸/在岸人民币 + 主流货币对） | 新浪财经 hq.sinajs.cn |
| `GET /api/sector-fund?type=&period=` | 行业/概念板块主力资金流入/流出排行（今日/5日/10日） | 东方财富 push2delay + SQLite 缓存（60s TTL） |
| `GET /api/sector-stocks?code=` | 板块成分股列表（按涨跌幅排序） | 东方财富 push2delay |
| `GET /api/is-trading-day` | 判断今天是否为交易日（含节假日） | chinese_calendar 库 |
| `GET /api/trading-days?count=` | 获取最近 N 个交易日列表 | chinese_calendar 库 |

### 聚合计算（基于缓存）

以下 API 从 `money_flow.db` 缓存读取数据后，在服务端加权聚合计算得出指数值（缓存 60s）：

| API | 指标 | 依赖缓存数据 | 分项权重 |
|-----|------|-------------|----------|
| `GET /api/fear-index` | 恐慌指数 0-100 | major_indices + sh_minute + market_breadth + fund_flow | 指数压力(22) + 日内压力(28) + 广度压力(22) + 资金压力(12) + 稳定因子(6) + 基础分(20) |
| `GET /api/risk-index` | 风险指数 0-100 | margin_trading + daily_closes + market_breadth | 融资因子(35) + 趋势因子(30) + 情绪因子(20) + 结构因子(15) |

### 手动操作

```
加载 / 更新 / 清库：
  POST /api/market-db/init/<seg_key>    →  异步初始化新市场（拉列表 + 全量 K 线）
  POST /api/market-db/update/<seg_key>  →  增量更新已有市场（中途终止不回退，下次续传）
  POST /api/market-db/clear/<seg_key>   →  清除市场全部数据（列表 + K 线 + 元信息）
  GET  /api/market-db/init/status       →  查询进度 {running, total, done, phase}
  POST /api/market-db/init/cancel       →  终止运行中的任务
  GET  /api/market-db/segments          →  获取各市场状态 + 股票数
  GET  /api/market-db/status            →  总股票数统计

技术选股（离线扫描，基于 stock_lib.db，不请求外部数据源）：
  GET  /api/technical/strategies                   →  获取可用策略列表（三上悠亚）
  POST /api/technical/ascending-channel            →  启动扫描 {market, strategy}，支持 pipeline 串联，扫描完成后自动附加预测评分
  GET  /api/technical/ascending-channel/status     →  轮询进度 + 结果（按评分降序）

个股预测评分（基于 stock_lib.db K 线多因子模型）：
  POST /api/stock-predictions                      →  批量评分 {stocks: [{code, market}]}，返回 {code: {direction, score, detail}}
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
| 增量更新 | 点击"更新"按钮 | `POST market-db/update/{key}` + `GET init/status`（每 1s 轮询进度） | 手动，终止不丢进度 |
| 运行选股 | 选择策略 + 市场点击"扫描" | `POST technical/ascending-channel` + `GET ascending-channel/status`（每 2s 轮询进度） | 支持 pipeline 串联筛选，完成后自动对结果计算预测评分 |

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
| 分析器执行 | 点击"分析"按钮 | `POST abnormal/analyze` | 调同花顺 K 线 → 计算偏离度/回撤/均线等指标 → 渲染分析卡片 |
| 分析器历史 | 每次分析自动保存 | localStorage | 上限 10 条，重复去重，点击历史标签快捷重新分析 |

#### 龙虎榜

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 导航切换 / 初始化 | `initLHB()` → `fetchTradingDays()` | `GET /api/trading-days?count=30` | 获取最近 30 个交易日列表，默认选中最新交易日 |
| 加载龙虎榜数据 | `loadLonghuBang(date)` | `GET /api/longhu-bang?date={date}` | 无缓存，每次切换日期都请求后端；后端 SQLite 有缓存则直接返回 |
| 切换日期 | 点击日期条按钮 | `selectLHBDate(date)` → `loadLonghuBang(date)` | 更新日期条选中状态，重新请求数据 |
| 切换分类 | 点击标签（全部/机构榜/游资榜/机构+游资） | `selectLHBTab(tab)` | 前端从本地数据筛选渲染，不请求后端 |
| 展开席位明细 | 点击股票行 | `toggleLHBDetail(idx)` | 前端展开/收起买卖席位表格 |
| 首次无数据 | 自动回溯 | 依次请求前 10 天的 `/api/longhu-bang` | 直到找到有数据的日期 |

#### 全球行情

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 导航切换 | `loadGlobalCommodities()` + `loadGlobalForex()` | `GET /api/global-commodities` + `GET /api/global-forex` | 并行请求，commodities 接口同时返回全球指数数据 |

#### 板块资金

| 时机 | 触发 | API | 说明 |
|------|------|-----|------|
| 导航切换 | `loadSectorFund(type, period)` | `GET /api/sector-fund?type=&period=` | 默认 concept + today |
| 切换板块类型 | 点击行业/概念标签 | `switchSectorTab(type)` | 重新请求 |
| 切换时间段 | 点击今日/5日/10日标签 | `switchSectorPeriod(period)` | 重新请求 |
| 查看成分股 | 点击板块行 | `GET /api/sector-stocks?code=` | 弹窗显示成分股列表（按涨跌幅排序） |

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
| 行业/概念板块资金流向 | `push2delay.eastmoney.com/api/qt/clist/get`（fs=m:90+t:2/t:3） |
| 板块成分股 | `push2delay.eastmoney.com/api/qt/clist/get`（fs=b:{sector_code}） |

### 腾讯证券

| 数据 | 接口 |
|------|------|
| 沪深指数近 30 天日K收盘价 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` |

### 同花顺

| 数据 | 接口 |
|------|------|
| A 股 K 线（日/周/月，前复权，含成交额/换手率） | `d.10jqka.com.cn/v4/line/{prefix}_{code}/{period_code}/{year}.js` |
| 全市场成交额分时 | `dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data` |
| 龙虎榜每日明细 + 席位分类 | `data.10jqka.com.cn/ifmarket/lhbggxq/report/{date}/` |

### 新浪财经

| 数据 | 接口 |
|------|------|
| A 股多日分时走势（5 分钟K线） | `money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData` |
| 全球指数行情（A股 + 海外） | `hq.sinajs.cn/list=`（s_sh/s_sz/int_/znb_ 前缀） |
| 大宗商品行情（国际期货 + 国内期货连续合约） | `hq.sinajs.cn/list=`（hf_/nf_ 前缀） |
| 外汇汇率行情 | `hq.sinajs.cn/list=`（fx_s 前缀） |

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

### chinese_calendar（Python 库）

| 数据 | 接口 |
|------|------|
| 交易日判断（含中国法定节假日） | `chinese_calendar.is_workday()` |

## ML 训练

### 训练流程

```
cd back_end
..\venv\Scripts\python -m ml_train.train
```

或双击 `back_end\train_ml.bat`。

### 特征工程（45 维）

从日 K 线列表提取技术指标，供训练和实时预测共用：

| 类别 | 维度 | 特征 |
|------|------|------|
| 价格与均线偏离度 | 6 | MA5/10/20/30/60/120 偏离度 |
| 均线多头排列 | 3 | MA5>MA10 / MA10>MA20 / MA20>MA60 |
| 成交量特征 | 3 | 量比(5日/20日) + 量趋势 |
| 布林带 | 2 | BB 位置 + BB 宽度 |
| RSI | 2 | RSI6 + RSI14 |
| MACD | 3 | DIF + DEA + 柱状 |
| 价格动量 | 4 | 1/5/10/20 日收益率 |
| 波动率 | 2 | 10日/20日年化波动率 |
| ATR | 1 | ATR/收盘价 |
| 连续涨跌 | 2 | 连续上涨天数 + 连续下跌天数 |
| 日内位置 | 1 | 当日高低价位置 |
| 跳空缺口 | 1 | 开盘跳空幅度 |
| 最大回撤 | 2 | 20日/60日最大回撤 |
| 高低点相对位置 | 4 | 20日/60日位置 + 创新高标记 |
| KDJ | 3 | K + D + J |
| OBV | 1 | OBV 10日变化率 |
| CCI | 2 | CCI14 + CCI20 |
| WR | 1 | WR14 |
| 量价关系 | 7 | 相关性 + 涨跌量比 + 分位数 + 缩量 + MFI |
| 成交额 | 3 | log成交额 + 5日/20日比 |
| 大盘对比 | 8 | 相对收益率(1/5/10/20日) + 相关性 + Beta + 相对位置 |

### 训练参数

| 参数 | 值 | 说明 |
|------|-----|------|
| FORWARD_DAYS | 3 | 标签：未来 N 个交易日涨幅 |
| RISE_THRESHOLD | 5% | 涨幅超过 5% 标记为正样本 |
| TEST_MONTHS | 6 | 最近 6 个月数据作为测试集 |
| MIN_KLINES | 180 | 最少需要 180 根日K线 |
| 模型 | XGBoost | n_estimators=200, max_depth=5, learning_rate=0.05 |
| 特征窗口 | 120 根 | 每只股票最近 120 根K线 |
| 自动保留最优 | 按测试 AUC | 新模型超过旧最优才替换，旧模型归档 |

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

## ML 训练

```powershell
# 用 venv python 训练
cd back_end
..\venv\Scripts\python -m ml_train.train
```

或双击 `back_end\train_ml.bat`。

## 打包

```powershell
# 用 venv python 运行
venv\Scripts\python.exe build_exe.py
# exe 输出到 dist\鑫多多.exe
```

## 依赖

```
Flask==2.3.3
requests==2.31.0
beautifulsoup4==4.12.2
lxml>=4.9.3
flask-cors==4.0.0
adata                    # 限售股解禁数据
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0      # ML 训练（precision/recall 评估）
xgboost>=2.0.0           # ML 训练模型
joblib>=1.3.0            # 模型序列化
chinese_calendar         # 交易日判断（含法定节假日）
```
