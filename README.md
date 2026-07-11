# 鑫多多

A股/港股/美股实时行情监控面板，支持指数分时走势、资金流向、选股、自选股/场内ETF/持仓股（SQLite 持久化）、K 线弹窗（日/周/月 + 分钟K线）、融资融券、恐慌/风险指数、技术选股、解禁列表、业绩报告、公司公告、异动中心、市场资讯、龙虎榜、全球行情（指数/大宗商品/外汇）、板块资金流向、ML 训练（XGBoost）。

## 目录结构

```
stock/
├── .gitignore
├── README.md
├── note.md / note2.md
├── strategie.md                       # 技术选股策略文档
├── build_exe.py                       # PyInstaller 打包入口
├── 鑫多多.spec                         # PyInstaller spec 文件
├── gitpush.bat
│
├── back_end/                          # 后端（Flask）
│   ├── app.py                         # 主入口：路由 + 启动
│   ├── requirements.txt
│   ├── start.bat / stop.bat / restart.bat / train_ml.bat
│   │
│   ├── common/                        # 公共模块
│   │   ├── __init__.py
│   │   ├── utils.py                   # 格式化函数 + 市场常量 + 代码转换
│   │   └── finance.py                 # 商誉率 + 质押率
│   │
│   ├── data/                          # 运行时数据（.gitignore）
│   │   ├── stock_lib.db               # 市场 + 股票列表 + K线 + 股票元信息（合并单库）
│   │   ├── money_flow.db              # 资金流向 + 融资融券历史数据
│   │   ├── watchlist.db               # 自选股 + 场内ETF + 持仓股持久化
│   │   ├── longhu_bang.db             # 龙虎榜每日明细（SQLite 缓存，90 天自动清理）
│   │   └── sector_fund.db             # 板块资金流向缓存（60s TTL）
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
│   │   ├── turnover.py                # 成交额分时
│   │   └── storage.py                 # 数据库持久化 + 后台定时轮询
│   │
│   ├── longhu_bang/                   # 龙虎榜模块
│   │   ├── __init__.py
│   │   └── service.py                 # 龙虎榜数据爬取（同花顺）+ SQLite 缓存 + 席位解析
│   │
│   ├── global_market/                 # 全球行情模块
│   │   ├── __init__.py
│   │   ├── indices.py                 # 全球指数实时行情（A股8大指数 + 海外7大指数，新浪财经）
│   │   ├── commodities.py             # 大宗商品行情（贵金属/有色/能化/黑色系/农产品，新浪财经）
│   │   └── forex.py                   # 外汇汇率行情（离岸/在岸人民币 + 主流货币对，新浪财经）
│   │
│   ├── sector_fund/                   # 板块资金流向模块
│   │   ├── __init__.py
│   │   ├── service.py                 # 行业/概念板块主力流入流出排行 + 成分股 + ETF成分股
│   │   └── storage.py                 # SQLite 缓存存储（60s TTL）
│   │
│   ├── stock_pick/                    # 选股搜索模块
│   │   ├── __init__.py
│   │   └── service.py                 # 多市场股票搜索（A股/港股/美股）+ 批量行情
│   │
│   ├── technical_screen/              # 技术选股模块
│   │   ├── __init__.py
│   │   ├── service.py                 # 策略扫描引擎，支持 pipeline 串联筛选
│   │   └── strategies/                # 策略实现
│   │       ├── __init__.py
│   │       ├── san_shang_you_ya.py    # 三上悠亚：三周期布林中上轨共振
│   │       └── ml_score.py            # ML量化打分：XGBoost 模型预测上涨概率
│   │
│   ├── abnormal_center/               # 异动中心模块
│   │   ├── __init__.py
│   │   └── service.py                 # 异动预测/监控 API 代理 + 股票异动分析
│   │
│   ├── market_news/                   # 市场资讯模块
│   │   ├── __init__.py
│   │   └── service.py                 # 东方财富全球财经资讯（akshare，缓存30分钟）
│   │
│   ├── ml_train/                      # ML 训练模块（XGBoost）
│   │   ├── __init__.py
│   │   ├── features.py                # 特征工程：技术指标（MA偏离/均线排列/量价/布林/RSI/MACD/动量/波动率/ATR/KDJ/OBV/CCI/WR/MFI/大盘对比等）
│   │   ├── train.py                   # XGBoost 训练脚本：日K线 → 特征+标签 → 训练 → 保存最优模型
│   │   ├── model.pkl                  # 当前最优模型（joblib 序列化）
│   │   ├── feature_names.txt          # 特征名列表
│   │   └── training_history.csv       # 每次训练记录（AUC/样本数/是否最优）
│   │
│   └── watchlist/                     # 自选股 / 场内ETF / 持仓股模块
│       ├── __init__.py
│       └── service.py                 # 自选股 + 场内ETF + 持仓股 SQLite CRUD
│
├── front_end/                         # 前端（原生 HTML/CSS/JS）
│   ├── templates/
│   │   └── index.html                 # 主页面：导航 + 各模块初始化
│   └── static/
│       ├── style.css
│       └── js/
│           ├── common.js              # 公共工具：交易时间判断 / 缓存清理
│           ├── kline/                 # K线图表模块
│           │   ├── popup.js           # K线弹窗主逻辑
│           │   ├── chart.js           # 日K/周K/月K + 分钟K线（Lightweight Charts）
│           │   ├── minute.js          # 分时走势图
│           │   └── fiveday.js         # 五日走势图
│           ├── money_flow/            # 资金流向前端
│           │   ├── charts.js          # 资金流图表渲染（ECharts）
│           │   └── refresh.js         # 数据刷新逻辑
│           ├── longhu/               # 龙虎榜前端
│           │   └── service.js         # 交易日历 + 日期选择 + 分类标签 + 席位明细展开
│           ├── global_market/         # 全球行情前端
│           │   ├── indices.js         # 全球指数渲染
│           │   ├── commodities.js     # 大宗商品网格渲染
│           │   └── forex.js           # 外汇汇率网格渲染
│           ├── sector_fund/           # 板块资金前端
│           │   └── sector_fund.js     # 行业/概念切换 + 今日/5日/10日切换 + 成分股弹窗
│           ├── technical_screen/      # 技术选股前端
│           │   └── page.js            # 市场选择 + 策略选择 + 扫描进度 + 结果渲染
│           ├── unlock-list/           # 解禁列表前端
│           │   └── service.js         # 解禁数据获取 + 表格渲染 + 股票筛选
│           ├── announce/              # 公司公告前端
│           │   └── service.js         # 公告获取 + 表格渲染 + 股票筛选 + 颜色标记
│           ├── earnings/              # 业绩报告前端
│           │   └── service.js         # 业绩预告/快报/报表获取 + 渲染 + 股票筛选
│           ├── abnormal/              # 异动中心前端
│           │   └── service.js         # 异动预测/监控 + 异动分析器 + 搜索历史
│           ├── market-news/           # 市场资讯前端
│           │   └── service.js         # 东方财富资讯获取 + 分页渲染
│           ├── stock_pick/            # 选股前端
│           │   └── service.js         # 搜索 + 缓存 + 渲染
│           └── watchlist/             # 自选股前端
│               └── service.js         # 自选股/场内ETF/持仓股 三Tab + 刷新 + 拖拽排序
│
├── build/                             # PyInstaller 构建中间产物
├── dist/                              # PyInstaller 分发输出
└── venv/                              # Python 虚拟环境（gitignore）
```

## 功能页面

| 页面 | 功能 |
|------|------|
| 资金流向 | 上证/深证指数分时、市场成交额、主力资金净流入、融资融券、恐慌指数、风险指数 |
| 自选股 | 自选列表 + 场内ETF + 持仓股 三Tab，加/删/拖拽排序，批量行情（PE/PB/市值/行业），商誉率、量比/委比 |
| 选股 | 多市场股票搜索（A股/港股/美股）、实时行情查询 |
| 技术选股 | 按市场分段异步加载K线、双策略扫描（三上悠亚 + ML量化打分），支持 pipeline 串联 |
| K 线弹窗 | LightweightCharts 蜡烛图，日K/周K/月K + 分钟K线（1/5/15/30/60/120min），分时图、五日分时、MA/布林线 |
| 解禁列表 | 限售股解禁信息（近一月），支持股票筛选 |
| 业绩报告 | 业绩预告 + 业绩快报 + 业绩报表（近三年），按年报/半年报/季报细分，支持股票筛选 |
| 公司公告 | 上市公司公告信息（最近 15 天），按重要性颜色标记，支持股票筛选 |
| 异动中心 | 异动预测 + 异动监控 + 异动分析器（单股偏离度/回撤/均线偏离分析） |
| 市场资讯 | 东方财富全球财经资讯（200条，含标题/摘要/时间/原文链接），缓存30分钟，前端分页 |
| 龙虎榜 | 每日龙虎榜明细（同花顺数据源），日期选择器 + 分类标签（全部/机构/游资/机构+游资）+ 席位明细展开 |
| 全球行情 | 全球指数（A股8大 + 海外7大）+ 大宗商品（贵金属/有色/能化/黑色/农产品）+ 外汇汇率 |
| 板块资金 | 行业/概念板块主力资金流入/流出排行（今日/5日/10日），板块成分股弹窗 + ETF成分股弹窗 |

## SQLite 数据库表结构

### data/stock_lib.db — 市场 + 股票列表 + K线 + 股票元信息（合并单库）

```sql
-- 市场元信息（每个市场一条记录）
CREATE TABLE stock_market (
    market       TEXT PRIMARY KEY,  -- 市场分段（hs_main/gem/star/hs_etf/hk_main/us_main）
    sync_ts      TEXT,              -- K线上次同步完成时间
    list_sync_ts TEXT               -- 股票列表上次拉取时间
);

-- 股票列表
CREATE TABLE market_stock_list (
    code   TEXT NOT NULL,
    market TEXT NOT NULL,
    name   TEXT,
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

-- 股票元信息（per-period 独立时间戳）
CREATE TABLE stock_info (
    code       TEXT NOT NULL,
    market     TEXT NOT NULL,
    name       TEXT,
    daily_ts   TEXT,                -- 日K最后更新成功时间戳
    weekly_ts  TEXT,                -- 周K最后更新成功时间戳
    monthly_ts TEXT,                -- 月K最后更新成功时间戳
    PRIMARY KEY (code, market)
);
```

> `daily_ts` / `weekly_ts` / `monthly_ts`：三个周期独立记录最后更新时间戳。增量更新时各周期独立判断是否需要拉取。

### data/watchlist.db — 自选股 + 场内ETF + 持仓股

```sql
CREATE TABLE watchlist (
    code TEXT, market TEXT,
    created_at TEXT, added_price TEXT,
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (code, market)
);

CREATE TABLE etf (
    code TEXT, market TEXT,
    created_at TEXT, added_price TEXT,
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (code, market)
);

CREATE TABLE holdings (
    code TEXT, market TEXT,
    created_at TEXT,
    hold_price TEXT DEFAULT '', hold_qty TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (code, market)
);
```

> 三张表均支持 `sort_order`，前端支持拖拽排序，后端 `reorder` 接口批量更新。

### data/money_flow.db — 资金流向数据快照

```sql
CREATE TABLE market_data (
    key   TEXT PRIMARY KEY,          -- major_indices/sh_minute/fund_flow/turnover_minute/margin_trading/daily_closes/fear_index/risk_index/market_breadth
    value TEXT NOT NULL,             -- JSON 序列化的数据
    meta  TEXT                       -- 时间戳或日期字符串
);
```

### data/longhu_bang.db — 龙虎榜数据缓存

```sql
CREATE TABLE longhu_bang (
    trade_date TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
```

> 启动时自动清理 90 天前的数据。

### data/sector_fund.db — 板块资金流向缓存

```sql
CREATE TABLE sector_fund (
    key       TEXT PRIMARY KEY,   -- 格式: {sector_type}_{period}_{top}
    value     TEXT NOT NULL,
    updated_at REAL NOT NULL      -- 写入时间戳（60s TTL）
);
```

### 市场分段定义

| key | label | 代码前缀 / 来源 |
|-----|-------|---------|
| hs_main | 沪深A | 600/601/603/605/000/001/002/003 |
| gem | 创业板 | 300/301 |
| star | 科创板 | 688 |
| hs_etf | 沪深ETF | 5/159/16/18 |
| hk_main | 港股 | 东方财富 API |
| us_main | 美股 | 东方财富 API |

> 北交所（40/43/83/87/92 开头）股票列表引自东方财富，K线数据使用新浪财经 API。

## K 线数据源

| 市场 | 股票列表 | 日/周/月K线 | 分钟K线 |
|------|---------|------------|---------|
| A 股主板 | 东方财富 push2delay | 同花顺 d.10jqka.com.cn（前复权，含成交额/换手率） | 1min→东财，5/15/30/60min→新浪，120min→新浪60min合成 |
| 北交所 | 东方财富 push2delay | 新浪财经 | — |
| 债券 | — | 新浪财经 | — |
| 港股 | 东方财富 push2delay | stock_lib.db 本地缓存 + Yahoo Finance 兜底 | Yahoo Finance |
| 美股 | 东方财富 push2delay | stock_lib.db 本地缓存 + Yahoo Finance 兜底 | Yahoo Finance |

## 数据同步流程

### 手动初始化新市场

前端选择市场 → 点击"加载" → 后台异步执行：

```
init_segment(seg_key)
    ↓
拉取完整股票列表（分页）
    ↓
stock_list_replace_market()   → 全量替换写入
    ↓
全量 K 线同步（4 线程并发） → 每只股票日/周/月线
    ↓
_cleanup_delisted()           → 清理退市股
    ↓
全部完成后写入 sync_ts
```

- A 股/ETF K 线数据源：同花顺（d.10jqka.com.cn）
- 港股/美股 K 线：Yahoo Finance
- 支持"终止"操作：取消后自动回滚

### 增量更新已有市场

前端选择市场 → 点击"更新"：

```
update_market(seg_key)
    ↓
判断是否需要更新列表 → 需要则拉取替换
    ↓
筛选 to_update → per-period 独立判断（只拉需要更新的周期）
    ↓
增量 K 线同步（4 线程并发）
    ↓
写入 sync_ts + 清理退市股
```

- per-period 增量判断：日K落后只拉日K，周K月K不落后就跳过
- 中途终止不回退：已完成个股数据已落地，下次续传

### 收市后定时增量同步

后台线程每 60 秒检查，收市 30 分钟后自动触发增量同步：

| 市场 | 收市 | 触发 | 候选市场 |
|------|------|------|---------|
| 港股 | 16:00 | 16:30 | hk_main |
| A股 | 15:00 | 15:30 | hs_main, gem, star, hs_etf |
| 美股 | 04:00 | 04:30 | us_main |

> 仅同步已有数据的市场，周末跳过，同日不重复触发。

## API 路由

### 行情数据

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/major-indices` | GET | 上证/深证实时行情 |
| `/api/sh000001-minute` | GET | 上证分时走势 |
| `/api/index-minute` | GET | 指数分时 |
| `/api/turnover-minute` | GET | 成交额分时 |
| `/api/market-fund-flow` | GET | 主力资金净流入 |
| `/api/fear-index` | GET | 恐慌指数 0-100 |
| `/api/risk-index` | GET | 风险指数 0-100 |
| `/api/margin-trading` | GET | 融资融券余额 |

### 股票数据

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/stock-quotes` | GET | 批量股票实时行情（价/量/额/换手/PE/PB/市值/行业） |
| `/api/stock-extra` | GET | 单只股票量比/委比 |
| `/api/stock-minute` | GET | 个股分时走势（支持多日） |
| `/api/stock-kline` | GET | 个股K线（日/周/月 + 分钟K线 1/5/15/30/60/120min） |
| `/api/stock-concepts` | GET | 股票核心概念题材 |
| `/api/stock-biz-comp` | GET | 股票主营构成（按产品分类） |
| `/api/goodwill` | GET | 批量商誉率 + 质押率（10线程并发） |
| `/api/search-stock` | GET | 股票搜索（名称/代码） |

### 自选股 / 场内ETF / 持仓股

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/watchlist` | GET | 获取自选股列表 |
| `/api/watchlist` | POST | 添加自选股 |
| `/api/watchlist/<code>` | DELETE | 删除自选股 |
| `/api/watchlist/<code>` | PUT | 更新加选价格 |
| `/api/watchlist/reorder` | POST | 批量更新排序 |
| `/api/etf` | GET / POST | 场内ETF 列表 / 添加 |
| `/api/etf/<code>` | DELETE | 删除场内ETF |
| `/api/etf/reorder` | POST | 批量更新ETF排序 |
| `/api/holdings` | GET / POST | 持仓股 列表 / 添加（含成本价/股数） |
| `/api/holdings/<code>` | DELETE / PUT | 删除 / 更新持仓股 |
| `/api/holdings/reorder` | POST | 批量更新持仓排序 |

### 信息查询

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/lifting` | GET | 自选+持仓+选股 限售股解禁（近一月） |
| `/api/announcements` | GET | 自选+持仓+选股 公司公告（近15天） |
| `/api/earnings` | GET | 自选+持仓+选股 业绩报告（近三年） |
| `/api/market-news` | GET | 东方财富全球财经资讯 |
| `/api/longhu-bang` | GET | 龙虎榜每日明细 |
| `/api/global-commodities` | GET | 全球大宗商品 + 全球指数 |
| `/api/global-forex` | GET | 全球外汇汇率 |
| `/api/sector-fund` | GET | 板块资金流向排行（行业/概念 + 今日/5日/10日） |
| `/api/sector-stocks` | GET | 板块成分股列表 |
| `/api/etf-stocks` | GET | ETF成分股列表 |
| `/api/is-trading-day` | GET | 判断今日是否为A股交易日 |
| `/api/trading-days` | GET | 获取最近 N 个A股交易日 |

### 异动中心

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/abnormal/prediction` | GET | 异动预测 |
| `/api/abnormal/monitor` | GET | 异动监控 |
| `/api/abnormal/analyze` | POST | 异动分析器（单股偏离度/回撤/均线偏离） |

### 技术选股 + 市场数据库

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/technical/strategies` | GET | 获取可用策略列表 |
| `/api/technical/ascending-channel` | POST | 启动扫描（支持多策略 pipeline 串联） |
| `/api/technical/ascending-channel/status` | GET | 轮询扫描进度 + 结果 |
| `/api/market-db/init/<seg>` | POST | 异步初始化新市场 |
| `/api/market-db/update/<seg>` | POST | 增量更新已有市场 |
| `/api/market-db/clear/<seg>` | POST | 清除市场全部数据 |
| `/api/market-db/init/status` | GET | 查询同步进度 |
| `/api/market-db/init/cancel` | POST | 终止运行中的任务 |
| `/api/market-db/segments` | GET | 获取各市场状态 + 股票数 |
| `/api/market-db/status` | GET | 总股票数统计 |

## 技术选股策略

### 1. 三上悠亚 (`san_shang_you_ya`)

日K/周K/月K三周期布林带共振：股价在三个级别的布林带中长期运行在中轨到上轨之间，布林带趋势向上且倾斜温和，近期无极端涨跌，即使短期跌破中轨也能快速修复。

| 筛选条件 | 说明 |
|----------|------|
| 中上轨运行 | 日/周/月三周期近20根K线中 >= 中轨比例 >= 55%（或 >= 45% + 快速修复中） |
| 中轨向上 | 三周期中轨线性回归斜率均 > 0 |
| 斜率不过陡 | 日K ≤ 3%/根，周K ≤ 5%/根，月K ≤ 8%/根 |
| 无极端涨跌 | 近30个交易日无单日涨跌幅 > 7% |

> 详见 `strategie.md`

### 2. ML量化打分 (`ml_score`)

使用 `ml_train/train.py` 训练的 XGBoost 模型对每只股票打分（上涨概率 × 100）。

> 需先运行 ML 训练生成 `model.pkl`，否则策略可用但无结果。

### Pipeline 串联

支持多个策略串联筛选：第一个策略扫全量股票，后续策略只扫上一轮命中的股票，逐步收窄范围。

## ML 训练

### 训练流程

```powershell
cd back_end
..\venv\Scripts\python -m ml_train.train
```

或双击 `back_end\train_ml.bat`。

### 特征工程

从日K线提取技术指标，训练与实时预测共用（`ml_train/features.py`）：

| 类别 | 特征 |
|------|------|
| 价格与均线偏离度 | MA5/10/20/30/60/120 偏离度 |
| 均线多头排列 | MA5>MA10 / MA10>MA20 / MA20>MA60 |
| 成交量特征 | 量比(5日/20日) + 量趋势 |
| 布林带 | BB位置 + BB宽度 |
| RSI | RSI6 + RSI14 |
| MACD | DIF + DEA + 柱状 |
| 价格动量 | 1/5/10/20日收益率 |
| 波动率 | 10日/20日年化波动率 |
| ATR | ATR/收盘价 |
| 连续涨跌 | 连续上涨天数 + 连续下跌天数 |
| 日内位置 | 当日高低价位置 |
| 跳空缺口 | 开盘跳空幅度 |
| 最大回撤 | 20日/60日最大回撤 |
| 高低点相对位置 | 20日/60日位置 + 创新高标记 |
| KDJ | K + D + J |
| OBV | OBV 10日变化率 |
| CCI | CCI14 + CCI20 |
| WR | WR14 |
| 量价关系 | 量价相关性 + 涨跌量比 + 量分位数 + 缩量 + MFI |
| 成交额 | log成交额 + 5日/20日成交额比 |
| 大盘对比 | 相对收益率(1/5/10/20日) + 相关性 + Beta + 相对位置 |

### 训练参数

| 参数 | 值 | 说明 |
|------|-----|------|
| FORWARD_DAYS | 3 | 未来 N 个交易日涨幅 |
| RISE_THRESHOLD | 5% | 涨幅超过 5% 标记为正样本 |
| TEST_MONTHS | 6 | 最近 6 个月数据作为测试集 |
| MIN_KLINES | 180 | 最少需要 180 根日K线 |
| 模型 | XGBoost | n_estimators=200, max_depth=5, learning_rate=0.05 |
| 特征窗口 | 120 根 | 每只股票最近 120 根K线 |
| 自动保留最优 | 按测试 AUC | 新模型超过旧最优才替换 |

## 前端 localStorage 缓存

| Key | 使用页面 | 内容 | 跨天策略 |
|-----|----------|------|----------|
| `kl_cache` | K线弹窗 | K线/分时/五日/行情/商誉/量比委比 | 跨天全删 |
| `stockCache` | 选股页 | 已选股票列表 + 商誉/质押 | 跨天商誉失效，列表保留 |
| `watchlistCache` | 自选股页 | 自选股数据补充（商誉/质押） | 跨天商誉失效 |
| `abnormal-calc-history-v1` | 异动中心 | 分析器搜索历史（上限10条） | 跨天保留 |
| `stock-search-history-v1` | 选股页 | 搜索历史（上限10条） | 跨天保留 |

## 数据源

### 东方财富

| 数据 | 接口 |
|------|------|
| 大盘指数/批量行情/涨跌家数 | `push2delay.eastmoney.com/api/qt/ulist.np/get` |
| 单只股票量比/委比 | `push2delay.eastmoney.com/api/qt/stock/get` |
| 上证指数/个股日内分时 | `push2delay.eastmoney.com/api/qt/stock/trends2/get` |
| 1分钟K线 | `push2delay.eastmoney.com/api/qt/stock/kline/get` |
| 主力资金净流入分时 | `push2delay.eastmoney.com/api/qt/stock/fflow/kline/get` |
| 股票列表/板块排行/成分股 | `push2delay.eastmoney.com/api/qt/clist/get` |
| 股票搜索 | `searchapi.eastmoney.com/api/suggest/get` |
| 商誉率 | `emweb.securities.eastmoney.com/PC_HSF10/FinanceAnalysis/` |
| 质押率 + 业绩数据 | `datacenter-web.eastmoney.com/api/data/v1/get` |
| 概念题材 | `emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax` |
| 主营构成 | `emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/PageAjax` |
| 公司公告 | `np-anotice-stock.eastmoney.com/api/security/ann` |
| 全球财经资讯 | akshare → `stock_info_global_em()` |

### 同花顺

| 数据 | 接口 |
|------|------|
| A 股 K 线（日/周/月，前复权） | `d.10jqka.com.cn/v4/line/` |
| 全市场成交额分时 | `dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data` |
| 龙虎榜每日明细 | `data.10jqka.com.cn/ifmarket/lhbggxq/report/` |

### 新浪财经

| 数据 | 接口 |
|------|------|
| A 股 5/15/30/60 分钟K线 | `money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData` |
| 北交所/债券 日/周/月K线 | 同上（新浪 K线 API） |
| 全球指数/大宗商品/外汇 | `hq.sinajs.cn/list=` |

### Yahoo Finance

| 数据 | 接口 |
|------|------|
| 港股/美股 K线（日/周/月） | `query1.finance.yahoo.com/v8/finance/chart/` |
| 港股/美股 分钟K线 | 同上（range + interval 参数） |
| 港股/美股多日分时 | 同上（5min interval） |

### 其他

| 来源 | 数据 |
|------|------|
| 腾讯证券 | 沪深指数近30天日K收盘价 |
| adata（Python 库） | 限售股解禁（近一月） |
| 悟道数据（stock.quicktiny.cn） | 异动预测 + 异动监控 |
| 交易所 | 融资融券余额（上交所/深交所） |
| chinese_calendar（Python 库） | A股交易日判断（含法定节假日） |

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
cd back_end
..\venv\Scripts\python -m ml_train.train
```

或双击 `back_end\train_ml.bat`。

## 打包

```powershell
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
adata
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
xgboost>=2.0.0
joblib>=1.3.0
chinese_calendar
akshare
psutil          # 打包时自动检测，非运行时必需
```
