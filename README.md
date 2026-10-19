# WebIntel-Agent v2.0

> 自动化行业情报 RAG 系统 — 抓取、解析、结构化，一键完成。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Dark Mode)                          │
│   index.html ─ style.css ─ app.js                               │
│   CSS Grid/Flexbox · 情感仪表盘 · 历史面板 · 响应式               │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI + Pydantic)                      │
│                                                                  │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│   │   API 路由    │──▶│   抓取引擎    │──▶│   LLM 分析器     │   │
│   │  /api/analyze │   │ httpx + PW   │   │ DeepSeek/OpenAI  │   │
│   └──────────────┘   └──────────────┘   └──────────────────┘   │
│          │                                      │                │
│          ▼                                      ▼                │
│   ┌──────────────┐                   ┌──────────────────┐       │
│   │  内存历史记录  │                   │  Pydantic Schema │       │
│   │  /api/history │                   │  严格输出校验     │       │
│   └──────────────┘                   └──────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                        外部服务                                   │
│   DeepSeek API / OpenAI API / 目标网站                           │
└─────────────────────────────────────────────────────────────────┘
```

### 数据流

```
用户输入 URL
    │
    ▼
httpx 快速抓取 ──成功──▶ 内容 > 100字? ──是──▶ LLM 分析
    │                        │
    │失败                    │否
    ▼                        ▼
Playwright 无头浏览器    回退到 Playwright
    │
    ▼
BeautifulSoup 提取正文
    │
    ▼
LLM API 结构化提取
    │
    ▼
Pydantic Schema 校验
    │
    ▼
JSON 响应 + 历史记录
```

## 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装

```bash
# 1. 进入项目
cd "Agentic 行业风向哨兵"

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装 Playwright 浏览器
playwright install chromium

# 5. 配置 API Key（可选，不配置则使用模拟分析）
copy .env.example .env
# 编辑 .env 填入你的 API Key
```

### 启动

```bash
cd backend
python main.py
```

访问 `http://localhost:8000`

### 运行测试

```bash
python -m pytest tests/ -v
```

### 运行审计

```bash
python audit_and_fix.py
```

## API 文档

### 健康检查

```
GET /api/health
```

```json
{
  "status": "ok",
  "service": "WebIntel-Agent",
  "version": "2.0.0",
  "llm_configured": true
}
```

### 分析网页

```
POST /api/analyze
Content-Type: application/json

{"url": "https://example.com"}
```

**成功响应 (200)：**

```json
{
  "url": "https://example.com",
  "title": "页面标题",
  "page_type": "article",
  "content_length": 3500,
  "analysis": {
    "summary": "内容摘要...",
    "key_insights": [
      {"point": "关键观点", "confidence": 0.9}
    ],
    "sentiment_score": 0.75,
    "sentiment_label": "positive",
    "tech_stack": [
      {"name": "React", "category": "框架"}
    ],
    "keywords": ["AI", "行业", "增长"]
  },
  "fetched_at": "2026-06-25T18:00:00",
  "status": "success"
}
```

### 获取历史

```
GET /api/history?limit=20
```

### 清空历史

```
DELETE /api/history
```

## Pydantic Schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `summary` | `str` (max 500) | 内容摘要 |
| `key_insights` | `list[KeyInsight]` | 1-5 个关键观点，各附置信度 |
| `sentiment_score` | `float` (0-1) | 情感得分：0=消极, 0.5=中性, 1=积极 |
| `sentiment_label` | `enum` | positive / negative / neutral |
| `tech_stack` | `list[TechStackItem]` | 识别到的技术栈 |
| `keywords` | `list[str]` (3-10) | 核心关键词 |

## 项目结构

```
Agentic 行业风向哨兵/
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理 (pydantic-settings)
│   ├── api/
│   │   └── routes.py        # API 路由定义
│   ├── core/
│   │   ├── fetcher.py       # 抓取引擎 (httpx + Playwright)
│   │   └── analyzer.py      # LLM 分析器
│   └── models/
│       └── schemas.py       # Pydantic 数据模型
├── frontend/
│   ├── index.html           # Dark Mode Dashboard
│   ├── style.css            # CSS Grid/Flexbox 布局
│   └── app.js               # 前端交互逻辑
├── tests/
│   ├── conftest.py
│   └── test_main.py         # 25 个测试用例
├── audit_and_fix.py         # 自动审计脚本
├── requirements.txt
├── .env.example
└── README.md
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | 异步高性能 Web 框架 |
| 数据校验 | Pydantic v2 | 严格 Schema 校验 |
| 配置管理 | pydantic-settings | 环境变量 / .env |
| HTTP 抓取 | httpx | 异步 HTTP 客户端 |
| SPA 抓取 | Playwright | 无头浏览器 |
| HTML 解析 | BeautifulSoup4 + lxml | DOM 解析 |
| LLM 接口 | OpenAI SDK | 兼容 DeepSeek/OpenAI |
| 测试 | Pytest | 单元 + 集成测试 |
| 前端 | 原生 HTML/CSS/JS | 零依赖 |

## LLM 配置

### DeepSeek（推荐，性价比高）

```env
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

### OpenAI

```env
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

### 模拟模式

不配置 `LLM_API_KEY` 即可使用内置的模拟分析（基于规则，无需 API 费用）。

服务默认只监听 `127.0.0.1`，并仅允许同一本地服务来源跨域访问。需要局域网部署时，请显式设置 `HOST` 与 `CORS_ORIGINS`，不要使用通配来源；本服务可以保存 LLM API Key，禁止直接暴露到公网。

---

**WebIntel-Agent v2.0** — 让行业情报触手可及。
