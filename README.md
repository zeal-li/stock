# 鑫多多

A股实时行情监控面板，支持指数分时走势、大盘资金流向、融资融券、恐慌/风险指数等。

## 目录结构

```
stock/
├── back_end/                  # 🔧 后端
│   ├── app.py                 # Flask 入口：路由注册 + 启动
│   ├── services/              # 业务逻辑层
│   │   ├── __init__.py        # 共享配置（代理、常量）
│   │   ├── market_data.py     # 指数行情、分时走势、资金流、恐慌/风险指数、融资融券
│   │   ├── money_flow.py      # 概念/行业/指数板块资金流向 + 市场成交额
│   │   ├── finance.py         # 财务数据（商誉率/质押率等）
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
│           ├── stock-pick.js  # 选股：搜索、缓存、列表渲染
│           └── auto-refresh.js# 自动刷新：实时指数/图表/恐慌风险更新
├── gitpush.bat                # 一键 git add/commit/push
└── README.md
```

## 功能模块

| 页面 | 功能 |
|------|------|
| 资金流向 | 上证指数分时走势、大盘资金净流入、融资融券、市场恐慌/风险指数、板块资金流 |
| 选股 | 股票名称/代码搜索 |

## 数据源

| 数据 | 来源 |
|------|------|
| 上证指数分时 | 新浪财经 K线 + 东方财富兜底 |
| 大盘资金净流入 | 东方财富 `push2delay.eastmoney.com` |
| 板块资金流向 | 同花顺 `data.10jqka.com.cn` |
| 成交额 | 同花顺 `dq.10jqka.com.cn` |
| 恐慌/风险指数 | 东方财富 `push2delay.eastmoney.com` |
| 融资融券 | akshare（沪市每日数据） |
| 股票搜索 | 东方财富 `searchapi.eastmoney.com` |

## 环境要求

- Python 3.9+
- 依赖见 `requirements.txt`

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

1. 在 `back_end/services/` 下新建模块（如 `back_end/services/new_feature.py`）
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
3. 新增 JS 逻辑放入 `front_end/static/js/` 对应文件：
   - 图表/资金流 → `charts.js`
   - 选股/搜索 → `stock-pick.js`
   - 实时推送 → `auto-refresh.js`
4. 样式统一写 `front_end/static/style.css`
