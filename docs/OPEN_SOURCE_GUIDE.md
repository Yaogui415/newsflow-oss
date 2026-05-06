# NewsFlow 开源发布说明

这份文档用于整理 NewsFlow 在 GitHub 开源时最需要的信息，包括仓库简介、图标定位、建议 Topics、发布检查项和第一版开源资料清单。

## 1. GitHub 仓库简介建议

### 简介版本 A

An AI-assisted newsroom workflow system for event tracking, evidence organization, approval chains, correction handling, and post-publication monitoring.

### 简介版本 B

NewsFlow is a newsroom workflow system that helps teams manage events, evidence, drafting, approval, and corrections with human-in-the-loop control.

### 中文简介版本

面向新闻生产全流程的人机协同系统，覆盖事件管理、证据组织、写稿协作、签发审批、勘误闭环与发布后监测。

## 2. GitHub Topics 建议

建议优先选择下面这些标签：

- `ai-agents`
- `newsroom`
- `journalism`
- `workflow`
- `human-in-the-loop`
- `fastapi`
- `react`
- `typescript`
- `editorial-workflow`
- `approval-workflow`
- `fact-checking`

## 3. 图标方向说明

当前仓库已补充 `image/newsflow-icon.svg`。

图标表达的是三个意思：

- 文档外形代表新闻稿件与事实材料
- 内部的连接节点代表工作流与 Agent 协作链
- 蓝绿渐变代表信息流动、核验推进和发布后闭环

如果后续你想继续升级视觉，可以沿着这三个方向扩展：

- 做一版带字标的横向 Logo
- 做一张 GitHub social preview banner
- 做一套 favicon / app icon / presentation cover 统一视觉

## 4. 首次开源建议包含的文件

建议第一版公开仓库至少包含：

- `README.md`
- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `backend/.env.example`
- `frontend/.env.example`
- `docs/OPEN_SOURCE_GUIDE.md`
- `image/newsflow-icon.svg`

## 5. 开源前检查项

### 安全与隐私

- 检查是否提交了真实数据库连接串
- 检查是否提交了真实 API Key
- 检查是否提交了真实用户数据、真实采访数据或隐私信息
- 检查部署配置是否还绑定生产实例

### 文档入口

- README 是否能在 30 秒内说明项目是什么
- README 是否能在 3 分钟内让开发者跑起来
- 是否有清楚的环境变量示例
- 是否说明了项目当前仍是高保真原型，而不是完整商用系统

### 协作体验

- 是否有 LICENSE
- 是否有贡献指南
- 是否说明安全问题如何上报
- 是否准备好了 issue / PR 模板

## 6. 建议的第一批 GitHub Issue 标签

可以先准备这些标签：

- `good first issue`
- `bug`
- `frontend`
- `backend`
- `documentation`
- `design`
- `workflow`
- `security`
- `help wanted`

## 7. 开源定位建议

NewsFlow 最适合强调的不是“自动生成新闻”，而是下面这几个卖点：

- 面向高责任场景的工作流设计
- 围绕事件与 Story Packet 的对象模型
- 可追溯的审批链与 Decision Log
- 将勘误与发布后监测纳入主流程
- 重视人机协同边界，而不是只强调模型能力

## 8. 推荐的发布文案方向

你在 GitHub 首页、介绍页或发布帖里，可以优先强调这句：

> NewsFlow is not just an AI writing tool. It is a newsroom workflow system designed for evidence organization, approval traceability, and responsible human-AI collaboration.
