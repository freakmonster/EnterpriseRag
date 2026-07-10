# RAG 企业员工智能问答系统

**FastAPI + LangGraph + React** · **ChromaDB + Elasticsearch** · **DeepSeek + DashScope**


---

## 一分钟启动

```bash
# 1. 初始化数据库
cd backend
python -m infrastructure.database.init_db

# 2. 设置密钥
$env:DEEPSEEK_API_KEY="sk-xxx"
$env:DASHSCOPE_API_KEY="sk-xxx"
$env:DB_HOST = "localhost"
$env:DB_USER = "root"
$env:DB_PASSWORD = "your_password"
$env:DB_NAME = "your_db_name"
$env:REDIS_HOST = "localhost"
$env:ES_HOST = "localhost"

# 3. 启动后端
python app.py

# 4. 启动前端（新终端）
cd ../frontend
npm run dev
```

打开 `http://localhost:5173` 注册账号即可使用。

---
<img width="1043" height="517" alt="image" src="https://github.com/user-attachments/assets/d2e3e58d-bbd3-414b-a40a-d2555ed93db6" />

<img width="1043" height="517" alt="image" src="https://github.com/user-attachments/assets/924ecf44-dc8a-474c-a569-ed2ef10e3509" />


## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      前端 (React)                        │
│                    localhost:5173                        │
└──────────────────────┬──────────────────────────────────┘
                       │ SSE 流式
┌──────────────────────▼──────────────────────────────────┐
│                   后端 (FastAPI)                          │
│                   localhost:8001                          │
│                                                          │
│  ┌─ JWT 鉴权 ─► 配额检查 ─► 防注入守卫 ─┐                │
│  │                                       │                │
│  │     ┌──────────────────────┐          │                │
│  │     │  LangGraph ReAct     │          │                │
│  │     │  Agent ⇄ Tools 循环  │          │                │
│  │     └────────┬─────────────┘          │                │
│  │              │ 工具调用                 │                │
│  │     ┌────────▼─────────────────────┐  │                │
│  │     │  简单检索  │ BM25  │ 混合召回 │  │                │
│  │     └────────┬─────────────────────┘  │                │
│  │              │ Rerank 精排             │                │
│  │              ▼                         │                │
│  │     ┌──────────────────────┐          │                │
│  │     │  DeepSeek 流式生成    │          │                │
│  │     │  + 引用来源自动注入   │          │                │
│  │     └──────────────────────┘          │                │
│  └───────────────────────────────────────┘                │
│                                                          │
│  依赖服务：MySQL │ Redis │ ES │ ChromaDB │ DashScope API   │
└──────────────────────────────────────────────────────────┘
```

---

## 核心能力

### 智能问答

| 特性 | 说明 |
|------|------|
| ReAct Agent | LangGraph 驱动，自主决策调用哪种检索工具 |
| 混合检索 | 向量语义 + BM25 关键词，双路互补 |
| Rerank 精排 | DashScope qwen3-vl-rerank 二次排序 |
| 强制引用 | 每个回答标注信息来源编号，底部展示引用文档卡片 |
| 流式响应 | SSE 逐 token 返回，前端实时渲染 |
| 防注入 | 输入先过安全检查，命中则拒答 |

### 多轮对话

| 特性 | 说明 |
|------|------|
| 短期记忆 | Redis 列表存储最近对话轮次 |
| 会话标题 | 首条问题自动生成标题（支持 LLM 摘要） |
| 长对话压缩 | 超阈值自动异步压缩历史为摘要，避免上下文溢出 |
| 多会话 | 支持新建/切换/删除会话，历史持久化 MySQL |

### 运维管控

| 特性 | 说明 |
|------|------|
| 用户认证 | 注册/登录，JWT + bcrypt 密码哈希 |
| 角色配额 | 按角色限制：每日请求数、每日 token、RPM |
| 成本追踪 | LLM / Embedding / Rerank 调用日志全记录 |
| 灰度发布 | MinIO 触发 → 写入 is_gray=True 数据 → Nacos 控制分流 → 验证上线/回滚 |
| 管理看板 | `/dashboard` 静态页面展示调用统计和成本趋势 |

---

## 所需依赖

**必须：**

| 服务 | 用途 | 默认端口 |
|------|------|---------|
| Python 3.10+ | 后端运行时 | — |
| Node.js 20+ | 前端构建 | — |
| MySQL 8+ | 用户、对话历史、配额、成本日志 | 3306 |
| Redis | 会话记忆、灰度标记缓存 | 6379 |
| Elasticsearch 8+ | BM25 关键词索引 | 9200 |

**可选：**

| 服务 | 用途 |
|------|------|
| MinIO | 政策文档上传 + Webhook 触发灰度更新 |
| Nacos | 灰度流量比例动态配置 |

---

## 项目文件地图

```
Rag/
│
├── backend/
│   ├── app.py                    入口
│   ├── config/                   配置（settings、常量、技能描述）
│   ├── api/
│   │   ├── routers/              chat / auth / admin / webhook 路由
│   │   └── schemas/              请求响应模型
│   ├── agents/
│   │   ├── workflows/            对话编排 + Webhook 编排
│   │   ├── nodes/                LangGraph 图节点（Agent / Tool / 路由）
│   │   └── state/                AgentState 类型定义
│   ├── tools/                    Agent 工具集（检索、技能、引用上下文）
│   ├── retrieval/
│   │   ├── document_loader.py    Markdown 文档加载
│   │   ├── document_splitter.py  按二级标题切分 / SentenceSplitter 切分
│   │   ├── init_store.py         向量库初始化
│   │   ├── gray_updater.py       灰度更新编排
│   │   ├── vectorstores/         ChromaDB 存储与检索
│   │   └── retrievers/           ES BM25 检索与索引管理
│   ├── models/
│   │   ├── llm_providers/        DeepSeek 客户端工厂
│   │   └── prompts/              System Prompt / 守卫 Prompt / 标题 Prompt
│   ├── services/                 鉴权、防注入、记忆压缩、配额、统计
│   ├── infrastructure/
│   │   ├── database/             MySQL ORM + 建库建表脚本
│   │   ├── cache/                Redis 客户端
│   │   ├── storage/              MinIO 客户端
│   │   ├── config/               Nacos 灰度配置
│   │   └── observability/        LLM 调用成本记录
│   ├── data/policies/            示例政策 Markdown 文档
│   └── tests/                    RAG 召回评测 + 生成评测 + 基础测试
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx               聊天主界面 (会话列表 + 对话 + 引用卡片)
│   │   ├── Login.tsx             登录注册界面
│   │   ├── api.ts                SSE 流式 + REST API 封装
│   │   ├── App.css               样式（红色主题、引用上标、高亮动画）
│   │   └── main.tsx              入口
│   ├── vite.config.ts            代理 /api → localhost:8001
│   └── package.json
│
├── envConfigParameter.txt        环境变量模板
└── README.md
```

---

## 环境变量速查

> 完整定义见 `backend/config/settings.py`

| 变量 | 作用 | 无设置时的值 |
|------|------|------------|
| `DEEPSEEK_API_KEY` | 大模型 API Key | 空（必填） |
| `DASHSCOPE_API_KEY` | Embedding + Rerank | 空（必填） |
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL 连接 | localhost / root / root / EnterpriseRag_db |
| `REDIS_HOST` / `REDIS_PORT` | Redis 连接 | localhost / 6379 |
| `ES_HOST` / `ES_PORT` | Elasticsearch | localhost / 9200 |
| `JWT_SECRET` | 令牌签名密钥 | 内置开发默认值 |

---

## 知识库与检索策略

### 文档处理流程

```
本地 .md 文件
    → SimpleDirectoryReader 加载
    → clean_text() 清洗换行与空格
    → 按 Markdown 二级标题 (## ) 切分为 chunk
    → DashScope text-embedding-v2 生成 1536 维向量
    → 双写：ChromaDB（向量） + Elasticsearch（BM25 索引）
```

### 检索策略对比

| 工具 | 适用场景 | 走法 |
|------|---------|------|
| `simple_retrieve_policy` | 简单/口语化问题 | 向量检索 → Rerank → Top 3 |
| `es_retrieve_policy` | 复杂跨文档问题 | BM25 关键词检索 → Top 3 |
| `complex_retrieve_policy` | 高难度综合问题 | 多 Query 向量 + BM25 → 各自 Rerank → 合并去重 |

### 引用来源机制

回答中的每个事实性陈述必须标注 `[n]` 引用编号，后端从真实检索结果自动生成引用来源卡片，不依赖 LLM 自主输出。详情见 `.trae/specs/hallucination-citation/`。

---

## 初始化与运维

```bash
# 创建数据库及所有表
python -m infrastructure.database.init_db

# 初始化 ChromaDB 向量库
python -m retrieval.init_store

# 初始化 ChromaDB + ES + 重置灰度配置
python -c "from retrieval.gray_updater import init_policies; init_policies()"
```

---

## FAQ

**Q: 为什么启动后端时报 Access denied for user 'root'？**
A: MySQL root 密码与 `DB_PASSWORD` 不匹配。在 `envConfigParameter.txt` 中有正确的环境变量，PowerShell 中逐行执行即可。

**Q: Redis 报 "unknown command 'HELLO'" 怎么办？**
A: redis-py 5.x 不兼容旧版 Redis。降级到 `redis>=4.0.0,<5.0.0` 或升级 Redis 到 6+。

**Q: ChromaDB 在 Windows 上崩溃？**
A: 已知问题。项目已禁用 ChromaDB 内置 ONNX embedding（`embedding_function=None`），改用 DashScope API 生成向量。

**Q: 端口 8001 被占用？**
```bash
netstat -ano | findstr :8001
taskkill /F /PID <进程ID>
```

**Q: 如何切换文档切分策略？**
A: 修改 `retrieval/init_store.py` 或 `retrieval/gray_updater.py` 中的切分函数调用，`split_document_by_markdown_sections` 和 `split_document_by_title` 可互换。
