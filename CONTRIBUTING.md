# Contributing to NewsFlow

感谢你愿意参与 NewsFlow。

NewsFlow 是一个面向新闻生产流程的人机协同系统。它的目标不是把 AI 包装成“自动写稿工具”，而是围绕事件、证据、审批、勘误和发布后闭环，搭建一个更适合高责任场景的工作流系统。

## 你可以贡献什么

- 修复 Bug
- 改进前端交互与可用性
- 补充后端接口与测试
- 完善部署、文档和示例数据
- 优化 AI Agent 的可解释性、边界控制和人机协同体验

## 开始之前

请先确认以下几点：

- 不要提交任何真实密钥、数据库连接串或平台凭证
- 不要在仓库中放入真实新闻源、真实个人隐私信息或敏感采访材料
- 如果你的改动会影响 API、对象模型或工作流状态，请同步更新文档
- 如果你的改动涉及高风险节点，请明确写出边界、回退方式和人工接管点

## 本地开发

### 1. 启动依赖服务

在项目根目录运行：

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
uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

## 提交改动建议

在提交 Pull Request 前，请尽量完成下面几项：

- 说明改动解决了什么问题
- 说明是否影响前端、后端、数据模型或部署方式
- 如果改动涉及 UI，附上截图或录屏
- 如果改动涉及 API，给出关键请求示例
- 如果改动涉及工作流节点，说明状态迁移和人工介入点

## Pull Request 标题建议

你可以参考下面的格式：

- `feat: add configurable API base URL for self-hosting`
- `fix: prevent unsafe approval auto-transition in sign-off flow`
- `docs: add open-source setup guide`
- `refactor: simplify story packet detail loading logic`

## 文档与表达风格

NewsFlow 的文档希望保持下面的风格：

- 清楚、直接、可执行
- 少空话，少“AI 很强大”式表述
- 明确系统边界，而不是只强调能力
- 能说清楚人应该在哪些地方判断、接管、复核

## 安全问题

如果你发现的是安全漏洞，而不是普通 Bug，请不要直接公开提 issue。

请查看 `SECURITY.md` 中的说明。
