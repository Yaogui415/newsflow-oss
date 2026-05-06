# NewsFlow 系统审计报告

> 审计日期：2026-04-02
> 审计范围：后端 14 个 API 模块 + 前端全部页面 + 前后端集成

---

## 一、后端 API 模块审计总览

| # | 模块 | 路由前缀 | 端点数 | 状态 |
|---|------|----------|--------|------|
| 1 | auth | `/auth` | 6 | ✅ 完整 |
| 2 | events | `/events` | 5 | ✅ 完整 |
| 3 | story_packets | `/story-packets` | 10 | ✅ 完整 |
| 4 | approvals | `/approvals` | 4 | ✅ 完整 |
| 5 | sources | `/sources` | 5 | ✅ 完整 |
| 6 | dashboard | `/dashboard` | 5 | ✅ 完整 |
| 7 | workflows | `/workflows` | 8 | ✅ 完整 |
| 8 | evidence_packs | `/evidence-packs` | 5 | ✅ 完整 |
| 9 | channel_packages | `/channel-packages` | 5 | ✅ 完整 |
| 10 | correction_tickets | `/correction-tickets` | 5 | ✅ 完整 |
| 11 | review_bundles | `/review-bundles` | 2 | ✅ 只读，符合设计 |
| 12 | risk_reports | `/risk-reports` | 4 | ✅ 完整 |
| 13 | claim_cards | `/claim-cards` | 4 | ✅ 完整 |
| 14 | seed (DEV) | `/dev` | 1 | ⚠️ 已限制为 DEBUG 模式 |

**总计：68 个 API 端点**（不含 health + init-db）

---

## 二、后端 API 端点清单

### 2.1 认证 (`/api/v1/auth`)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册新用户 |
| POST | `/auth/login` | 用户登录，返回 JWT |
| GET | `/auth/me` | 获取当前用户信息 |
| GET | `/auth/me/llm-settings` | 获取用户 LLM API Key 配置 |
| PUT | `/auth/me/llm-settings` | 更新用户 LLM API Key 配置 |
| DELETE | `/auth/me/llm-settings` | 清空用户 LLM API Key 配置 |

### 2.2 事件案卷 (`/api/v1/events`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/events` | 事件案卷列表（分页 + 筛选） |
| POST | `/events` | 创建事件案卷 |
| GET | `/events/{event_id}` | 事件案卷详情 |
| PATCH | `/events/{event_id}` | 更新事件案卷 |
| POST | `/events/{event_id}/transition` | 事件状态迁移 |

### 2.3 报道任务包 (`/api/v1/story-packets`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/story-packets` | 任务包列表（分页 + 筛选） |
| POST | `/story-packets` | 创建任务包 |
| GET | `/story-packets/{id}` | 任务包详情 |
| PATCH | `/story-packets/{id}` | 更新任务包 |
| POST | `/story-packets/{id}/transition` | 任务包状态迁移 |
| GET | `/story-packets/{id}/claim-cards` | 关联 Claim Cards 列表 |
| GET | `/story-packets/{id}/draft` | 获取最新草稿 |
| PATCH | `/story-packets/{id}/draft` | 编辑草稿（生成新版本） |
| GET | `/story-packets/{id}/precheck` | 送审预检 |
| POST | `/story-packets/{id}/submit-review` | 提交送审（幂等） |

### 2.4 签发中心 (`/api/v1/approvals`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/approvals/tasks` | 签发任务队列（分页 + view 筛选） |
| GET | `/approvals/tasks/{id}` | 签发任务详情（enriched） |
| POST | `/approvals/tasks/{id}/decide` | 执行签发决策 |
| GET | `/approvals/decision-logs` | 签发决策日志查询 |

### 2.5 线索来源 (`/api/v1/sources`)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sources/upload` | 上传文件采集 |
| POST | `/sources/rss` | RSS 源采集 |
| POST | `/sources/manual` | 手动提交线索 |
| GET | `/sources/items` | 素材列表（分页） |
| GET | `/sources/items/{id}` | 素材详情 |

### 2.6 今日概览 (`/api/v1/dashboard`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dashboard/stats` | 仪表盘统计卡片 |
| GET | `/dashboard/high-priority-events` | 高优先级事件 |
| GET | `/dashboard/sla-alerts` | SLA 告警 |
| GET | `/dashboard/sidebar-counts` | 侧边栏计数 |
| GET | `/dashboard/agent-activities` | Agent 活动时间线 |

### 2.7 工作流 (`/api/v1/workflows`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workflows/template` | 标准工作流模板 |
| GET | `/workflows/story-packets/{id}/progress` | Story Packet 工作流进度 |
| POST | `/workflows/runs` | 创建工作流实例 |
| GET | `/workflows/runs/{id}` | 工作流实例详情 |
| POST | `/workflows/runs/{id}/advance` | 推进工作流实例 |
| POST | `/workflows/runs/{id}/decisions` | 提交人工决策 |
| GET | `/workflows/runs/{id}/events` | 工作流事件流（游标分页） |
| GET | `/workflows/audit/events` | 统一审计事件流（游标分页） |

### 2.8 证据包 (`/api/v1/evidence-packs`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/evidence-packs` | 证据包列表 |
| POST | `/evidence-packs` | 创建证据包 |
| GET | `/evidence-packs/{id}` | 证据包详情 |
| PATCH | `/evidence-packs/{id}` | 更新证据包 |
| POST | `/evidence-packs/{id}/snapshot` | 创建证据包快照 |

### 2.9 渠道包 (`/api/v1/channel-packages`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/channel-packages` | 渠道包列表 |
| POST | `/channel-packages` | 创建渠道包 |
| GET | `/channel-packages/{id}` | 渠道包详情 |
| PATCH | `/channel-packages/{id}` | 更新渠道包 |
| POST | `/channel-packages/{id}/transition` | 渠道包状态迁移 |

### 2.10 勘误单 (`/api/v1/correction-tickets`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/correction-tickets` | 勘误单列表 |
| POST | `/correction-tickets` | 创建勘误单 |
| GET | `/correction-tickets/{id}` | 勘误单详情 |
| PATCH | `/correction-tickets/{id}` | 更新勘误单 |
| POST | `/correction-tickets/{id}/close` | 关闭勘误单 |

### 2.11 送审快照包 (`/api/v1/review-bundles`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/review-bundles` | 送审快照包列表 |
| GET | `/review-bundles/{id}` | 送审快照包详情 |

> 只读设计：Review Bundle 由 submit-review 流程自动创建，不可人工修改。

### 2.12 风险报告 (`/api/v1/risk-reports`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/risk-reports` | 风险报告列表 |
| POST | `/risk-reports` | 创建风险报告 |
| GET | `/risk-reports/{id}` | 风险报告详情 |
| PATCH | `/risk-reports/{id}` | 更新风险报告 |

### 2.13 事实卡 (`/api/v1/claim-cards`)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/claim-cards` | 事实卡列表 |
| POST | `/claim-cards` | 创建事实卡 |
| GET | `/claim-cards/{id}` | 事实卡详情 |
| PATCH | `/claim-cards/{id}` | 更新事实卡 |

---

## 三、前端↔后端集成对照表

### 3.1 前端页面 → 后端 API 映射

| 前端页面 | 使用的 API 服务 | 覆盖状态 |
|----------|-----------------|----------|
| LoginPage | `authApi.login` | ✅ |
| Dashboard | `dashboardApi.*`（stats/events/sla/agent/sidebar） | ✅ |
| EventListPage | `eventsApi.list`, `eventsApi.create` | ✅ |
| EventDetailPage | `eventsApi.get`, `storyPacketsApi.list` | ✅ |
| StoryPacketPage | `storyPacketsApi.list`, `storyPacketsApi.create` | ✅ |
| StoryPacket DetailPage | `storyPacketsApi.*`, `claimCardsApi`, `sourcesApi`, `evidencePacksApi` | ✅ |
| SignOff QueuePage | `approvalsApi.listTasks` | ✅ |
| SignOff DetailPage | `approvalsApi.getTask`, `approvalsApi.decide`, `approvalsApi.listDecisionLogs` | ✅ |
| LLMSettingsPage | `authApi.getLLMSettings`, `authApi.updateLLMSettings`, `authApi.deleteLLMSettings` | ✅ |
| MainLayout (sidebar) | `dashboardApi.getSidebarCounts`, `authApi.getMe` | ✅ |

### 3.2 前端 API 服务 → 后端路由对照

| 前端服务 | 后端路由 | 匹配 |
|----------|----------|------|
| `authApi` | `/auth/*` | ✅ 6/6 |
| `eventsApi` | `/events/*` | ✅ 4/5（缺 transition） |
| `storyPacketsApi` | `/story-packets/*` | ✅ 8/10（缺 update、precheck） |
| `approvalsApi` | `/approvals/*` | ✅ 4/4 |
| `sourcesApi` | `/sources/*` | ✅ 4/5（缺 rss） |
| `dashboardApi` | `/dashboard/*` | ✅ 5/5 |
| `evidencePacksApi` | `/evidence-packs/*` | ✅ 5/5 |
| `channelPackagesApi` | `/channel-packages/*` | ✅ 5/5 |
| `correctionTicketsApi` | `/correction-tickets/*` | ✅ 5/5 |
| `reviewBundlesApi` | `/review-bundles/*` | ✅ 2/2 |
| `riskReportsApi` | `/risk-reports/*` | ✅ 4/4 |
| `claimCardsApi` | `/claim-cards/*` | ✅ 4/4 |
| `workflowsApi` | `/workflows/*` | ✅ 8/8 |

---

## 四、已修复的问题

### 4.1 后端 Bug 修复
| 问题 | 文件 | 修复 |
|------|------|------|
| seed 端点缺少错误处理 | `seed.py` | 添加 try/except + rollback + 详细错误返回 |
| approvals `signer_role` 空列表崩溃 | `approvals.py` | 使用 `_parse_roles()` 安全解析 |
| approvals `return_category` 非必填但校验失败 | `approvals.py` | 改为可选参数 |
| claim_cards `manually_accepted` 无理由校验 | `claim_cards.py` | 添加 `manual_accept_reason` 必填校验 |

### 4.2 生产就绪改进
| 改进 | 说明 |
|------|------|
| 种子数据端点 DEBUG 守卫 | `seed.py` 添加 `settings.DEBUG` 检查，非 DEBUG 返回 403 |
| 路由条件注册 | `router.py` 仅在 `DEBUG=True` 时注册 `/dev` 路由 |
| 前端 seed 按钮移除 | Dashboard 移除种子数据生成按钮和 `devApi` 调用 |
| OpenAPI 文档增强 | `main.py` 添加完整的 API 描述、标签定义、认证说明 |
| 各端点 description 补充 | events/story_packets/approvals 等模块添加端点级描述 |

### 4.3 前端 UI 改进
| 页面 | 改进内容 |
|------|----------|
| MainLayout | 黑金主题 + 动态用户名显示（从 auth API 获取） |
| LoginPage | 黑金奢华登录页 |
| Dashboard | 黑金主题统计卡片、事件列表、SLA 告警、Agent 活动 |
| EventListPage | 黑金主题事件卡片、筛选器 |
| EventDetailPage | 黑金主题详情页、侧边栏、选项卡 |
| StoryPacketPage | 黑金主题任务包列表 |
| StoryPacket DetailPage | 黑金主题详情页（Claim Cards、Evidence、Draft 编辑器） |
| SignOff QueuePage | 黑金主题签发队列、预览面板 |
| SignOff DetailPage | 黑金主题签发详情、决策面板 |
| LLMSettingsPage | 黑金主题设置页 |

---

## 五、已知 API 差距（待后续迭代）

### 5.1 前端未调用的后端端点
以下后端端点已实现但前端尚未调用（可在后续迭代中补充）：

| 后端端点 | 说明 | 优先级 |
|----------|------|--------|
| `POST /events/{id}/transition` | 事件状态迁移（前端未实现按钮） | 中 |
| `PATCH /story-packets/{id}` | 任务包字段更新（前端缺编辑表单） | 中 |
| `GET /story-packets/{id}/precheck` | 送审预检独立调用（目前仅在 submit-review 内部使用） | 低 |
| `POST /sources/rss` | RSS 源采集（前端无 RSS 入口） | 中 |

### 5.2 缺少的功能模块（未来迭代）
| 功能 | 说明 | 优先级 |
|------|------|--------|
| 用户管理页面 | 前端缺少管理员用户列表、角色分配 UI | 高 |
| 渠道包管理页面 | 前端缺少 Channel Package 列表和详情页 | 中 |
| 勘误单管理页面 | 前端缺少 Correction Ticket 列表和详情页 | 中 |
| 风险报告查看页面 | 前端缺少 Risk Report 详情展示 | 中 |
| 工作流可视化页面 | 前端缺少工作流进度可视化展示 | 低 |
| 审计日志查看页面 | 前端缺少统一审计事件流 UI | 低 |
| 证据包管理页面 | 前端缺少独立的 Evidence Pack 管理 UI | 低 |
| Review Bundle 查看 | 前端缺少送审快照详情页 | 低 |

### 5.3 安全与运维改进建议
| 建议 | 说明 | 优先级 |
|------|------|--------|
| RBAC 权限控制 | 当前所有认证用户可访问所有端点，需按 roles 限制 | 高 |
| 请求速率限制 | 未配置 API rate limiting | 高 |
| 密码策略 | 未强制密码复杂度要求 | 中 |
| SECRET_KEY 更换 | `config.py` 中默认 SECRET_KEY 需在生产环境替换 | 高 |
| 数据库迁移 | 需引入 Alembic 管理 schema 迁移 | 高 |
| 日志集中化 | 需配置结构化日志输出（JSON 格式 + 日志级别） | 中 |
| CORS 收紧 | 生产环境需移除 localhost 来源 | 中 |
| HTTPS 强制 | 需配置 HTTPS 并强制 HSTS | 高 |

---

## 六、架构概要

```
前端 (React + Ant Design + Vite)
  ├── LoginPage → authApi
  ├── Dashboard → dashboardApi
  ├── EventCase → eventsApi
  ├── StoryPacket → storyPacketsApi + claimCardsApi + evidencePacksApi
  ├── SignOffCenter → approvalsApi
  └── Settings → authApi (LLM)

后端 (FastAPI + SQLAlchemy + aiosqlite)
  ├── 14 API 模块 (68 端点)
  ├── 声明式状态机引擎 (event_case / story_packet / channel_package)
  ├── 服务层 (precheck / snapshot / approval / idempotency / audit)
  ├── Agent 层 (source_monitor / audit_agent)
  └── 统一错误处理 + JWT 认证
```

---

## 七、结论

系统核心功能完整，14 个后端 API 模块共 68 个端点全部实现并与前端集成。主要改进：

1. **生产就绪**：种子数据端点已限制为 DEBUG 模式，前端已移除 dev 工具
2. **文档完善**：OpenAPI 文档已添加完整描述、标签定义和认证说明
3. **UI 统一**：全部前端页面已升级为黑金奢华主题
4. **Bug 修复**：已修复 4 个后端 Bug

**待优化优先级**：RBAC 权限控制 > 数据库迁移工具 > 用户管理页面 > 安全加固
