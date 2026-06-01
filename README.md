# 鑫多多

A股/港股/美股实时行情监控面板，支持指数分时走势、资金流向、选股列表、K 线弹窗、融资融券、恐慌/风险指数等。

## 目录结构

```
stock/
├── back_end/                  # 🔧 后端
│   ├── app.py                 # Flask 入口：路由注册 + 启动
│   ├── services/              # 业务逻辑层
│   │   ├── __init__.py        # 共享配置（代理、常量）
│   │   ├── market_data.py     # 指数行情、分时走势、资金流、恐慌/风险指数、融资融券
│   │   ├── money_flow.py      # 概念/行业/指数板块资金流向 + 市场成交额
│   │   ├── finance.py         # 财务数据（商誉率/质押率）
│   │   └── search.py          # 股票搜索
│   ├── requirements.txt       # Python 依赖
│   ├── start.bat              # 启动服务
│   ├── stop.bat               # 停止服务（精确杀端口 5000）
│   └── restart.bat            # 重启服务
├── front_end/                 # 🎨 前端
│   ├── templates/
│   │   └── index.html         # 页面骨架 + 导航/Tab 绑定 + 初始化
│   └── static/
│       ├── style.css          # 全局样式
│       └── js/
│           ├── charts.js      # 图表渲染：分时走势、资金流、融资融券
│           ├── stock-pick.js  # 选股：搜索、缓存、列表渲染、K 线入口
│           ├── kline-popup.js # K 线弹窗：蜡烛图 + 成交量 + 十字线提示
│           └── auto-refresh.js# 自动刷新：实时指数/图表/恐慌风险更新 + 选股行情
├── gitpush.bat                # 一键 git add/commit/push
└── README.md
```

## 功能模块

| 页面 | 功能 |
|------|------|
| 资金流向 | 上证指数分时走势、大盘资金净流入(大/中/散户)、融资融券、市场恐慌/风险指数、板块资金流向 |
| 选股 | 股票搜索、多股列表(价格/涨跌/PE/PB/市值/商誉率/质押率)、点击名称弹 K 线 |

### K 线弹窗

点击选股列表中股票名称，弹出 LightweightCharts 蜡烛图 + 成交量柱：

- 标题栏：实时价格、涨跌
- 参数行：总市值/流通市值/PE(TTM)/PB/成交量/成交额/换手/振幅
- 十字线提示：日期、高/低、开/收、涨跌额/涨跌幅、成交量/成交额/换手率
- 底部日期刻度：`yyyy-MM-dd` 格式，约 2~3 周间隔

## 数据源

### 行情 + K 线

| 数据 | 市场 | 来源 |
|------|------|------|
| 选股列表行情 | A/港/美 | 东方财富 `push2delay.eastmoney.com` |
| 日K线 | A 股 | 同花顺 `d.10jqka.com.cn`（开高低收/量/额/换手） |
| 日K线 | 港股 | Yahoo Finance `query1.finance.yahoo.com` |
| 日K线 | 美股 | Yahoo Finance `query1.finance.yahoo.com` |
| 上证指数分时 | A 股 | 东方财富 `push2delay.eastmoney.com`（5 秒缓存） |

### 大盘指标

| 数据 | 来源 |
|------|------|
| 大盘资金净流入 | 东方财富 `push2delay.eastmoney.com` |
| 板块资金流向 | 同花顺 `data.10jqka.com.cn` |
| 成交额 | 同花顺 `dq.10jqka.com.cn` |
| 恐慌/风险指数 | 东方财富 `push2delay` + 新浪行情 + akshare 融资数据 |
| 融资融券 | akshare（沪深两市每日数据） |

### 财务数据

| 数据 | 来源 | 备注 |
|------|------|------|
| 商誉率 | 东方财富 F10 资产负债表 | 日级前端 localStorage 缓存 |
| 质押率 | 东方财富数据中台 `RPT_CSDC_LIST` | 日级前端 localStorage 缓存 |
| 股票搜索 | 东方财富 `searchapi.eastmoney.com` | — |

### 不可用的数据源

`push2his.eastmoney.com` / `push2.eastmoney.com` 的 K 线 API 在此网络环境被东方财富反爬拦截（TLS 握手阶段断开），已用同花顺 + Yahoo 替代。

## 环境要求

- Python 3.9+
- 依赖见 `back_end/requirements.txt`

## 快速开始

```powershell
# 1. 创建虚拟环境（项目根目录下）
python -m venv venv
.\venv\Scripts\activate

# 2. 安装依赖
pip install -r back_end\requirements.txt

# 3. 启动服务
cd back_end
python app.py

# 4. 浏览器访问
# http://localhost:5000
```

或直接双击 `back_end\start.bat`。

## 开发指南

### 加新数据接口

1. 在 `back_end/services/` 下新建模块
2. 在 `back_end/app.py` 中 import 并注册路由：

```python
from services.new_feature import get_new_data

@app.route('/api/new-endpoint')
def new_endpoint():
    return jsonify(get_new_data())
```

### 加新页面

1. 在 `front_end/templates/index.html` 中加 `<div id="page-xxx">` 容器
2. 在左侧导航 `.nav-item` 中加入口
3. 新增 JS 逻辑放入 `front_end/static/js/` 对应文件
4. 样式统一写 `front_end/static/style.css`
