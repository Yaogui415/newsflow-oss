# NewsFlow

![NewsFlow icon](./image/newsflow-icon.svg)

> 面向新闻生产全流程的人机协同系统  
> AI-assisted newsroom workflow for event tracking, evidence organization, approval chains, correction handling, and post-publication monitoring.

NewsFlow 不是一个只围绕“自动写稿”的 AI 工具。它更关注新闻生产中真正高成本、也更高责任的中间流程：线索进入、事件归并、证据组织、Claim 结构化、风险暴露、签发审批、勘误流转，以及发布后的监测与知识回写。

当前仓库更适合以下几类使用方式：

- 本地部署与产品研究
- 新闻工作流 / Agent 工作流教学演示
- 前后端一体化原型开发
- 围绕人机协同、可追溯审批链、新闻治理的二次开发

## 当前状态

- 已具备前后端联动、核心对象模型与关键工作流页面
- 适合自托管体验、课程展示和二次开发
- 当前更接近高保真原型，不建议直接作为真实新闻生产环境投入使用

## 开源协作入口

- `CONTRIBUTING.md`：贡献方式与开发建议
- `SECURITY.md`：安全问题上报与敏感数据边界
- `docs/OPEN_SOURCE_GUIDE.md`：GitHub 简介、Topics、发布检查项
- `backend/.env.example`：后端环境变量示例
- `frontend/.env.example`：前端环境变量示例

## 项目架构

```text
newsflow/
├── backend/                    # 后端服务 (FastAPI + Python)
│   ├── app/
│   │   ├── agents/            # 12 个 AI Agent
│   │   ├── api/v1/            # REST API 端点
│   │   ├── core/              # 核心模块（配置、状态机、权限）
│   │   ├── models/            # ORM 数据模型
│   │   └── services/          # 业务服务层
│   ├── migrations/            # Alembic 数据库迁移
│   └── tests/                 # 测试用例
├── frontend/                   # 前端应用 (React + TypeScript + Ant Design)
│   └── src/
│       ├── pages/             # 页面组件
│       └── layouts/           # 布局组件
└── 实施方案/                   # 详细实施文档
```

## 核心 Agent 列表

| Agent | 职责 | 阶段 |
| ----- | ---- | ---- |
| Source Monitor | 多源线索采集与 5W1H 提取 | 输入侧 |
| Dedup & Cluster | 去重与聚类决策 | 输入侧 |
| Triage | 分诊评估与风险定级 | 输入侧 |
| Evidence Structuring | 证据结构化与 Claim 生成 | 认知侧 |
| Relationship Investigation | 关系调查与事件图谱 | 认知侧 |
| Verification | 多源核验与置信度计算 | 认知侧 |
| Redaction & Risk | 脱敏处理与风险识别 | 治理侧 |
| Audit | 审计日志与链式完整性 | 治理侧 |
| Drafting | 智能写稿与结构规划 | 生产侧 |
| Channel Adaptation | 多渠道适配与漂移检测 | 生产侧 |
| Orchestrator | 总控编排与状态机管理 | 编排层 |
| Post-Publish Monitor | 发布后监测与勘误流程 | 闭环层 |

## 功能特性

### 输入侧

- RSS/API/人工上传多源采集
- 智能去重与事件聚类
- 自动风险等级评估（L0-L3）
- 编辑立项建议

### 认知侧

- 5W1H 结构化提取
- Claim Card 自动生成
- 多源证据核验
- 实体关系图谱构建

### 治理侧

- 三门脱敏机制（录入/写稿/发布前）
- PII 自动检测（手机号/身份证/地址）
- 匿名源保护
- 不可篡改审计日志

### 生产侧

- AI 辅助写稿
- 多渠道自动适配
- 语义漂移检测
- 平台规范校验

### 审批流程

- 状态机驱动的工作流
- 多级多签审批策略
- SLA 超时管理
- 人工闸口控制

### 签发中心 UI

- 今日概览仪表盘
- 签发队列与任务筛选
- 风险摘要与决策面板
- 版本 Diff 对比

## 快速开始

### 1. 启动基础依赖

```bash
docker compose up -d
```

### 2. 配置环境变量

- 复制 `backend/.env.example` 为 `backend/.env`
- 复制 `frontend/.env.example` 为 `frontend/.env.local`

### 3. 启动后端

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 5. 访问地址

- 前端：`http://localhost:5173`
- 后端健康检查：`http://localhost:8000/health`
- 后端接口文档：`http://localhost:8000/docs`

### 6. 额外说明

- 前端通过 `VITE_API_BASE_URL` 连接后端
- 默认本地开发地址为 `http://localhost:8000/api/v1`
- 如果需要调用 LLM 相关能力，请在 `backend/.env` 中配置 `OPENAI_API_KEY`

## API 端点

| 路径 | 描述 |
| ---- | ---- |
| `/api/v1/auth` | 认证与授权 |
| `/api/v1/events` | 事件案卷管理 |
| `/api/v1/story-packets` | 报道任务包管理 |
| `/api/v1/approvals` | 签发审批管理 |
| `/api/v1/sources` | 线索源管理 |
| `/api/v1/dashboard` | 仪表盘数据 |

## 数据模型

- **EventCase**: 事件案卷
- **StoryPacket**: 报道任务包
- **ClaimCard**: 事实断言卡
- **EvidencePack**: 证据包
- **DraftVersion**: 草稿版本
- **ChannelPackage**: 渠道稿件包
- **ReviewBundle**: 送审包
- **ApprovalTask**: 签发任务
- **DecisionLog**: 决策日志
- **SourceVault**: 敏感来源保险库
- **RiskReport**: 风险报告
- **CorrectionTicket**: 勘误工单
- **AuditLog**: 审计日志

## 技术栈

### 后端

- FastAPI + Uvicorn
- SQLAlchemy + Alembic + aiosqlite
- LangChain + LangGraph
- Redis (缓存/消息队列)

### 前端

- React 18 + TypeScript
- Ant Design 5
- React Router 6
- Vite

### AI/LLM

- OpenAI GPT-4o / GPT-4o-mini
- LangChain Core
- 向量检索（计划集成 Milvus）

## 项目状态与路线图

- [x] 第一阶段：项目初始化与技术选型
- [x] 第二阶段：核心对象模型与状态机
- [x] 第三阶段：输入侧 Agent 开发
- [x] 第四阶段：认知侧 Agent 开发
- [x] 第五阶段：治理侧 Agent 开发
- [x] 第六阶段：生产侧 Agent 开发
- [x] 第七阶段：签发中心与人机协同界面
- [x] 第八阶段：总控编排与端到端集成
- [x] 第九阶段：发布后监测与闭环机制
- [x] 第十阶段：测试优化与部署上线
- [x] 开源基础资料补齐
- [ ] 更完整的自托管部署说明
- [ ] 更细粒度的权限、证据锚点与长期记忆治理

## 相关文档

- `docs/AUDIT_FINDINGS.md`：当前系统审计结果
- `docs/OPEN_SOURCE_GUIDE.md`：开源发布建议
- `实施方案/`：课程阶段材料与项目文档

## 许可证

本项目基于 [MIT License](./LICENSE) 开源。
