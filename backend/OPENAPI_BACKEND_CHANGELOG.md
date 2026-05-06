# NewsFlow 后端 OpenAPI 变更对照（2026-03-31）

> 适用环境：`/api/v1`  
> 说明：仅包含本轮后端新增/变更接口，供前端直接联调。

## 0) 全局错误响应规范（新增）

- 本轮起，后端错误响应统一为以下结构（含业务错误与参数校验错误）：
- 统一模型来源：`app/api/v1/schemas.py` 中的 `ErrorResponse`（Swagger 统一引用）

```json
{
  "code": "ERROR_CODE",
  "message": "可读错误信息",
  "status": 400,
  "details": {}
}
```

- 参数校验错误（`422`）示例：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数校验失败",
  "status": 422,
  "details": {
    "errors": []
  }
}
```

## 1) 签发中心（Approvals）

### 1.1 `GET /api/v1/approvals/tasks`
- 变更类型：**行为增强（新增 query 过滤逻辑）**
- 新增 Query 参数：
  - `view`: `pending | initiated | returned`
  - `mine_only`: `boolean`（保留，行为增强）

#### Query 语义
- `view=pending`：返回“待我签发”（按签位角色/指派用户匹配当前用户）
- `view=initiated`：返回“我发起的”（Review Bundle 的 `submitted_by=当前用户`）
- `view=returned`：返回“我退回的”（当前用户产生过 `action=return` 的任务）

#### 响应结构（未变）
```json
{
  "items": [
    {
      "id": "task-id",
      "review_bundle_id": "bundle-id",
      "approval_stage": "risk_review",
      "status": "pending",
      "signer_slots": [],
      "execution_mode": "any",
      "sla_deadline": "2026-03-31T10:00:00Z",
      "created_at": "2026-03-31T08:00:00Z",
      "updated_at": "2026-03-31T08:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 1.2 `POST /api/v1/approvals/tasks/{task_id}/decide`
- 变更类型：**文档增强（显式错误响应模型）**
- Swagger 说明：已显式声明 `400/404/422` 标准错误响应模型（统一结构）

## 2) Story Packet

### 2.1 `GET /api/v1/story-packets/{packet_id}/claim-cards`
- 变更类型：**新增接口**
- 功能：Claim Cards 真实筛选
- Query 参数：
  - `risk_level`: 逗号分隔，如 `L0,L1,L2,L3`
  - `status`: 逗号分隔，如 `supported,disputed,insufficient`

#### 响应
```json
[
  {
    "id": "claim-id",
    "story_packet_id": "packet-id",
    "claim_text": "...",
    "risk_level": "L2",
    "status": "supported",
    "supporting_evidence": [],
    "contradicting_evidence": [],
    "missing_evidence": [],
    "confidence_score": 0.86,
    "manual_accept_reason": null,
    "draft_anchor_ref": "p3-s2",
    "verified_by": "user-id",
    "created_at": "2026-03-31T08:00:00Z",
    "updated_at": "2026-03-31T09:00:00Z"
  }
]
```

### 2.2 `GET /api/v1/story-packets/{packet_id}/draft`
- 变更类型：**新增接口**
- 功能：获取当前正文草稿（若不存在会自动创建 `version=1`）

### 2.3 `PATCH /api/v1/story-packets/{packet_id}/draft`
- 变更类型：**新增接口**
- 功能：编辑正文草稿并生成新版本

#### 请求体
```json
{
  "title": "可选",
  "lead": "可选",
  "body": "可选",
  "body_html": "可选",
  "claim_anchor_map": {}
}
```

#### 响应
```json
{
  "id": "draft-id",
  "story_packet_id": "packet-id",
  "version": 2,
  "title": "...",
  "lead": "...",
  "body": "...",
  "body_html": null,
  "claim_anchor_map": {},
  "word_count": 128,
  "is_frozen": false,
  "created_at": "2026-03-31T10:00:00Z",
  "created_by": "user-id"
}
```

### 2.4 `POST /api/v1/story-packets/{packet_id}/submit-review`
- 变更类型：**行为增强（幂等键 + 重试语义）**
- 新增请求头（可选）：
  - `Idempotency-Key: <string>`
- Swagger 说明：已显式声明 `400/404/409/422` 标准错误响应模型（统一结构）

#### 幂等语义
- 首次请求：正常执行送审流程，返回 `replayed=false`
- 相同 `Idempotency-Key` + 相同请求体再次提交：直接返回首次结果，`replayed=true`
- 相同 `Idempotency-Key` + 不同请求体：返回 `409`（`IDEMPOTENCY_CONFLICT`）
- 相同 `Idempotency-Key` 正在处理中：返回 `409`（`REQUEST_IN_PROGRESS`）

#### 响应新增字段
```json
{
  "precheck": {"passed": true, "blocking_items": [], "warning_items": []},
  "review_bundle": {"id": "bundle-id", "story_packet_id": "packet-id", "bundle_type": "editorial", "bundle_hash": "...", "status": "active", "submit_note": "...", "created_at": "2026-03-31T15:00:00Z"},
  "approval_task_id": "task-id",
  "idempotency_key": "req-20260331-001",
  "replayed": false
}
```

---

## 3) 素材来源（Sources）

### 3.1 `POST /api/v1/sources/upload`
- 变更类型：**入参增强 + 返回结构增强**
- 新增 Form 字段：
  - `event_case_id`（可选）
- 行为变更：
  - 若未传 `event_case_id`，后端会自动创建一个 `EventCase`
  - 真实落库到 `event_source_items`
  - 优先使用当前用户配置的 API Key（若存在）

### 3.2 `POST /api/v1/sources/manual`
- 变更类型：**入参增强 + 返回结构增强**
- 新增 Form 字段：
  - `event_case_id`（可选）
- 行为同上

### 3.3 `GET /api/v1/sources/items`
- 变更类型：**新增接口**
- 功能：素材列表
- Query：
  - `page`（默认 1）
  - `page_size`（默认 20）
  - `event_case_id`（可选）

### 3.4 `GET /api/v1/sources/items/{source_item_id}`
- 变更类型：**新增接口**
- 功能：素材详情（可点击打开）

#### `source_item` 结构（upload/manual/items/items/{id} 通用）
```json
{
  "id": "source-id",
  "event_case_id": "event-id",
  "source_type": "upload",
  "url": null,
  "title": null,
  "raw_content": "...",
  "file_ref": "xxx.pdf",
  "extracted_5w1h": {"summary": "..."},
  "risk_tags": ["pii:phone"],
  "agent_summary": "...",
  "ingested_at": "2026-03-31T09:00:00Z"
}
```

---

## 4) 用户 API Key（Auth）

### 4.1 `GET /api/v1/auth/me/llm-settings`
- 变更类型：**新增接口**
- 功能：读取当前用户 API Key 配置（掩码返回）

### 4.2 `PUT /api/v1/auth/me/llm-settings`
- 变更类型：**新增接口**
- 功能：更新当前用户 API Key 配置

#### 请求体
```json
{
  "api_key": "sk-...",
  "daily_budget_usd": 20,
  "model_preference": "gpt-4o-mini",
  "provider": "openai"
}
```

### 4.3 `DELETE /api/v1/auth/me/llm-settings`
- 变更类型：**新增接口**
- 功能：清空当前用户配置

#### LLM Settings 响应结构
```json
{
  "user_id": "user-id",
  "provider": "openai",
  "has_api_key": true,
  "api_key_masked": "sk-1************9X",
  "daily_budget_usd": 20,
  "model_preference": "gpt-4o-mini",
  "updated_at": "2026-03-31T10:00:00+00:00"
}
```

---

## 5) 工作流可观测（Workflows）

### 5.1 `GET /api/v1/workflows/template`
- 变更类型：**新增接口**
- 功能：返回标准工作流模板（含“渠道审”阶段）

### 5.2 `GET /api/v1/workflows/story-packets/{packet_id}/progress`
- 变更类型：**新增接口**
- 功能：返回 Story Packet 在标准链路中的当前阶段、高亮状态、阻塞信息、审批统计

#### 响应示例
```json
{
  "story_packet_id": "packet-id",
  "story_packet_status": "channel_review",
  "current_stage_key": "channel_review",
  "blocked": false,
  "blockers_count": 0,
  "approval_pending_count": 1,
  "approval_returned_count": 0,
  "stages": [
    {"key": "source_ingestion", "name": "Source Item 进入系统", "type": "agent", "state": "completed"},
    {"key": "channel_review", "name": "渠道审", "type": "human_gate", "state": "current"}
  ],
  "generated_at": "2026-03-31T10:00:00Z"
}
```

### 5.3 `POST /api/v1/workflows/runs`
- 变更类型：**新增接口（持久化工作流实例）**
- 功能：创建一个可持久化的工作流运行实例

#### 请求体
```json
{
  "event_case_id": "可选",
  "source_items": [
    {"id": "source-1", "content": "..."}
  ]
}
```

#### 响应（WorkflowRunResponse）
```json
{
  "run_id": "workflow-id",
  "event_case_id": "event-id",
  "story_packet_id": null,
  "current_stage": "source_ingestion",
  "status": "running",
  "last_error": null,
  "created_by": "user-id",
  "created_at": "2026-03-31T14:00:00+00:00",
  "updated_at": "2026-03-31T14:00:00+00:00",
  "state": {}
}
```

### 5.4 `GET /api/v1/workflows/runs/{run_id}`
- 变更类型：**新增接口**
- 功能：读取持久化工作流实例详情（含完整状态快照）

### 5.5 `POST /api/v1/workflows/runs/{run_id}/advance`
- 变更类型：**新增接口**
- 功能：推进工作流一步并持久化最新状态

### 5.6 `POST /api/v1/workflows/runs/{run_id}/decisions`
- 变更类型：**新增接口**
- 功能：提交人工决策并触发下一步推进

#### 请求体
```json
{
  "decision_type": "project_decision",
  "action": "approved",
  "reason": "立项通过"
}
```

### 5.7 `GET /api/v1/workflows/runs/{run_id}/events`
- 变更类型：**新增接口**
- 功能：读取工作流事件流（创建、推进、人工决策等）
- Query：
  - `cursor`（可选，时间游标分页令牌）
  - `limit`（默认 `100`，最大 `200`）

#### 错误码
- `400 INVALID_CURSOR`：`cursor` 非法或损坏

- Swagger 说明：已显式声明 `400/422` 标准错误响应模型（统一结构）

#### 错误响应示例
```json
{
  "code": "INVALID_CURSOR",
  "message": "cursor 非法或已损坏",
  "status": 400,
  "details": {}
}
```

#### 响应示例
```json
{
  "items": [
    {
      "id": 12,
      "run_id": "workflow-id",
      "event_type": "workflow_advanced",
      "payload": {
        "current_stage": "triage",
        "status": "running",
        "error": null
      },
      "created_at": "2026-03-31T14:05:00+00:00"
    }
  ],
  "next_cursor": "MjAyNi0wMy0zMVQxNDowNTowMCswMDowMHwxMg==",
  "has_more": true,
  "limit": 100
}
```

#### 游标分页调用方式
- 首次请求：不传 `cursor`
- 继续翻页：把上一次响应里的 `next_cursor` 作为下一次请求的 `cursor`
- 当 `has_more=false` 或 `next_cursor=null` 时，表示已到末页

### 5.8 `GET /api/v1/workflows/audit/events`
- 变更类型：**新增接口（统一审计流）**
- 功能：统一查询审批事件 + 工作流事件 + 送审事件，支持回放与追责
- Query：
  - `object_type`（可选，如 `workflow_run` / `approval_task` / `story_packet`）
  - `object_id`（可选）
  - `action`（可选）
  - `actor_type`（可选：`human|system|agent`）
  - `cursor`（可选，时间游标分页令牌）
  - `limit`（默认 `100`，最大 `200`）

#### 错误码
- `400 INVALID_CURSOR`：`cursor` 非法或损坏

- Swagger 说明：已显式声明 `400/422` 标准错误响应模型（统一结构）

#### 错误响应示例
```json
{
  "code": "INVALID_CURSOR",
  "message": "cursor 非法或已损坏",
  "status": 400,
  "details": {}
}
```

#### 响应示例
```json
{
  "items": [
    {
      "id": "audit-id",
      "actor_id": "user-id",
      "actor_type": "human",
      "action": "approval_decision_made",
      "object_type": "approval_task",
      "object_id": "task-id",
      "details": {
        "review_bundle_id": "bundle-id",
        "decision_action": "return",
        "task_status": "returned"
      },
      "previous_hash": "...",
      "override_ai_flag": false,
      "override_reason": null,
      "created_at": "2026-03-31T15:10:00+00:00"
    }
  ],
  "next_cursor": "MjAyNi0wMy0zMVQxNToxMDowMCswMDowMHxhdWRpdC1pZA==",
  "has_more": true,
  "limit": 100
}
```

#### 游标分页调用方式
- 首次请求：不传 `cursor`
- 继续翻页：把上一次响应里的 `next_cursor` 作为下一次请求的 `cursor`
- 当 `has_more=false` 或 `next_cursor=null` 时，表示已到末页

---

## 联调建议（前端）
- 签发三Tab统一走 `GET /approvals/tasks?view=...`
- 草稿编辑统一走 `/story-packets/{id}/draft` 的 GET/PATCH
- Claim 筛选走 `/story-packets/{id}/claim-cards` Query 参数
- 送审提交建议统一带 `Idempotency-Key` 请求头（如 `packetId + 本地请求uuid`）
- 素材区走 `/sources/items` + `/sources/items/{id}`，上传时尽量传 `event_case_id`
- 设置页新增 `/auth/me/llm-settings` 的读写与删除
- 工作流流程图与高亮走 `/workflows/template` + `/workflows/story-packets/{id}/progress`
- 若需“真实执行态”联动（非静态流程图），请接入：
  - 创建实例：`POST /workflows/runs`
  - 推进实例：`POST /workflows/runs/{run_id}/advance`
  - 人工决策：`POST /workflows/runs/{run_id}/decisions`
  - 读取状态：`GET /workflows/runs/{run_id}`
  - 拉取事件流：`GET /workflows/runs/{run_id}/events`
- 若需统一回放与审计检索，请接入：`GET /workflows/audit/events`
- 运行事件流与统一审计流均使用同一分页协议：`items + next_cursor + has_more + limit`
- 长列表回放请使用游标翻页：`cursor + limit`，避免一次性拉全量
