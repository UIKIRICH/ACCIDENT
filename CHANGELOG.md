# 变更日志

## [v2.0.0] - 2026-06-28 — 复核辅助模块完整实现

### 新增：复核辅助模块 (Review Assist)

**后端**

- `backend/models/review_assist.py` — Pydantic 数据模型，包含 `route_type`、`review_priority_score`、`review_focus`、`conflict_summary`、`evidence_status`、`evidence_required_items`、`risk_notes` 等字段
- `backend/services/review_assist_service.py` — 核心服务
  - 评分规则：基础分 35 + 多项加分（模型冲突 +20 / 责任敏感 +8 / 视角不完整 +5 等）
  - 复核重点识别：7 种复核重点自动判定（模型结论冲突、视角不完整、证据不足、低置信度、责任敏感、规则依据需核对、快速确认）
  - 冲突摘要生成 / 补证建议生成
  - 统计聚合函数 `get_review_assist_statistics()`
- 4 个新 API 端点：
  - `POST /api/cases/{id}/review-assist/generate` — 单案例生成复核辅助
  - `GET /api/cases/{id}/review-assist` — 查询复核辅助结果
  - `POST /api/review-assist/batch-generate` — 批量生成（100 案例）
  - `GET /api/review-assist/statistics` — 统计分布

**前端**

- `src/api/index.js` — 新增 `ReviewAssistAPI`（`get` / `generate` / `batchGenerate` / `statistics`）
- `src/stores/useAccidentFlow.js` — 新增 `reviewAssist` / `reviewAssistLoading` / `reviewAssistError` 状态
- `src/views/ManualReview.vue` — 复核辅助卡片（路由类型、优先级分数-等级、复核重点标签、冲突摘要、补证建议列表、风险提示）
- `src/views/RuleBasis.vue` — 复核重点提示 + 建议人工核对清单
- `src/views/WorkQueue.vue` — 优先级排序 + 复核辅助列（优先级等级-分数 + 证据状态）
- `src/views/ReportDetail.vue` — 复核辅助结果小节
- `src/views/ReviewPriority.vue` — 全新可视化分析页（概览卡片、优先级柱状图、路由类型卡片、复核重点分布图、证据状态圆环图）

---

### 修复：Dify 集成

- 修复 `KeyError: 'compensation_status'` — 模板占位符 `{compensation_status}` / `{conflict_status}` / `{insufficient_status}` 未被 format() 传入
- `_call_dify_workflow()` 底层从 `urllib.request` 替换为 `requests` 库，解决 Dify 返回 HTML 而非 JSON 的问题
- Dify 调用已恢复正常，返回结构化事故分析结果（事故类型、责任归属、事实依据、法规依据）

---

### 修复：数据统计与页面联通

- `backend/database.py:get_stats()` — 扩展返回 `accidentTypeDist`（事故类型分布）、`ruleHitTop`（规则命中 TOP5）、`reviewStats`（复核通过率）
- `ruleHitTop` 增加三级回退查询：`matched_rules` 表 → `rules` 表 → 事故类型分布
- 复核通过率计算修正：原 `completed/total`（25%）→ `completed/(completed+驳回)`（72%）
- 案例状态从 2 种扩展为 7 种：已完成/处理中/待复核/待分析/复核中/驳回/待处理
- `matched_rules` 表从 2 条填充至 166 条真实命中记录
- 100 案例日期分布到 2026 年 1-3 月

---

### 修复：前端死数据清除

- `src/views/DashboardScreen.vue` — 事故类型分布、规则命中 TOP5、复核通过率均从后端 API 动态获取
- `src/views/Overview.vue` — 卡片 `change` 值从硬编码 `+12/+8/+3/+2` 改为动态计算
- `src/views/RuleBasis.vue` — 移除 6 条假规则 `defaultRules` 数组（applied 156/134/87/203/98/312）
- `src/views/WorkQueue.vue` — ETA 从 `30分钟/1小时/15分钟` 改为 `排队中/待人工审核/分析中`，审核人从 `张警官` 改为 `待分配`

---

### 整理：项目文件结构

- 新增 `backend/tmp/` — 临时 JSON/视频文件归档（已加入 `.gitignore`）
- 新增 `backend/previews/` — 数据集预览图、关键帧研究图归档
- 新增 `backend/data/` — 案例原始数据（`case_data_brief.csv`、`case_data_export.json`）
- 新增 `tests/` — 测试脚本归档（`test_api.py`、`test_upload_pipeline.py`）
- 删除 `src/views/# Focus Chain List for Task 178114419032.md`
- `.gitignore` 追加 `backend/tmp/`
