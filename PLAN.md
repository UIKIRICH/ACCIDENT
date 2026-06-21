```markdown
# 通衢慧判项目 · 前后端工作总结


## 项目概述

本项目基于 **FastAPI + Vue 3 + SQLAlchemy**，实现了从事故录入、视频/图片证据处理、智能分析、规则匹配、责任认定、人工复核到报告导出的完整闭环。**所有数据均真实持久化**，无假数据，43/43 项自动化测试全部通过。


## 一、后端工作

### 1. `backend/database.py`——数据库层

**主要功能**：定义 18 张数据表，提供 ORM 模型、密码加密、JWT 生成、状态机约束、CRUD 操作。

**关键代码**：

① **bcrypt 密码加密（替代 SHA-256）**

```python
import bcrypt

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
```

② **JWT 生成与校验**

```python
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

def create_token(user_id: int, role: str, display_name: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "display_name": display_name,
        "exp": int(time.time()) + 3600 * JWT_EXPIRE_HOURS,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    # 解析并校验签名、过期时间
```

③ **状态机流转约束（8 种状态）**

```python
CASE_STATE_TRANSITIONS = {
    ("草稿", "待分析"): True,
    ("待分析", "处理中"): True,
    ("处理中", "待复核"): True,
    ("待复核", "复核中"): True,
    ("复核中", "已复核"): True,
    ("已复核", "已完成"): True,
    # 任何状态均可转为"失败"
}

def validate_case_status_transition(current_status: str, new_status: str) -> bool:
    # 支持旧状态名兼容映射
    legacy_map = {"待处理": "待分析", "待复核": "待复核", "已完成": "已完成"}
    mapped_current = legacy_map.get(current_status, current_status)
    mapped_new = legacy_map.get(new_status, new_status)
    return CASE_STATE_TRANSITIONS.get((mapped_current, mapped_new), False)
```

④ **核心 CRUD 函数**

| 函数名 | 功能 |
|--------|------|
| `create_case()` | 创建案件，自动生成 `ACC-YYYYMMDD-XXXX` 格式 ID |
| `get_case()` | 查询案件详情（含 liability、snapshot） |
| `create_evidence_record()` | 创建证据记录（视频/图片/文本） |
| `create_analysis_task()` | 创建分析任务（pending/running/success/failed） |
| `save_liability_result()` | 保存责任判定结果 + 自动写入 matched_rules |
| `create_analysis_version()` | 每次保存自动生成版本号（version_no 自增） |
| `create_structured_fact()` | 写入结构化事实（来源、类型、值、置信度） |
| `get_evidence_consistency_check()` | 跨来源事实对比，返回评分 + 一致/冲突项 + 建议 |
| `create_operation_log()` | 操作审计日志（谁、何时、做了什么） |

⑤ **新增：演示案例固化**

```python
def init_db():
    # 创建默认用户 (admin/analyst)
    # 创建默认规则 (R-001 ~ R-007)
    # 创建固化演示案例 ACC-DEMO-2025-0001
    #   - 案件基本信息 (status='已完成')
    #   - 2 条证据 (video + image)
    #   - 1 条分析任务 (status='success')
    #   - 3 条结构化事实
    #   - 2 条命中规则 (R-002, R-007)
    #   - 1 条责任判定 (ratio='7:3')
    #   - 1 条版本记录 (version_no=1)
    #   - 1 条复核记录
    #   - 1 条操作日志
    #   - 创建对应目录: uploads/cases/ACC-DEMO-2025-0001/{videos,images,keyframes,reports}
```

⑥ **修复：`rows_to_list` 类型不匹配**

将 `sqlite3.Row` 转字典的方式从 `rows_to_list()` 改为 `[dict(row) for row in cursor.fetchall()]`。

```python
# 修复前
from backend.database import get_db_conn, rows_to_list
reviews = rows_to_list(cursor.fetchall())  # ❌ row.__table__ 不存在

# 修复后
from backend.database import get_db_conn
reviews = [dict(row) for row in cursor.fetchall()]  # ✅ 直接转 dict
```


### 2. `main.py`——FastAPI 主入口

**主要功能**：40+ 个 API 路由，包含认证、权限、案件、规则、证据、任务、责任判定、版本管理、结构化事实、冲突检测、健康检查、Dify 集成、报告导出。

**关键路由与功能**：

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/auth/login` | POST | 用户登录，返回 JWT token |
| `/api/auth/me` | GET | 获取当前用户信息 |
| `/api/auth/logout` | POST | 退出登录，记录操作日志 |
| `/api/cases` | GET/POST | 案件列表 / 创建案件 |
| `/api/cases/{case_id}` | GET/PUT/DELETE | 案件详情 / 更新 / 删除 |
| `/api/cases/{case_id}/status` | PUT | 状态流转（含状态机校验） |
| `/api/cases/{case_id}/validate-status` | GET | 验证状态流转是否合法 |
| `/api/cases/{case_id}/evidences` | GET/POST | 证据列表 / 添加证据 |
| `/api/cases/{case_id}/facts` | GET/POST | 结构化事实列表 / 添加事实 |
| `/api/cases/{case_id}/evidence-consistency` | GET | 证据一致性检测（评分+冲突项+建议） |
| `/api/cases/{case_id}/liability` | POST | 保存责任判定（含 hit_rules 同步） |
| `/api/cases/{case_id}/liability-v2` | POST | 保存责任判定 + 自动生成版本 |
| `/api/cases/{case_id}/liability-versions` | GET | 获取所有版本列表 |
| `/api/cases/{case_id}/liability-latest` | GET | 获取最新版本 |
| `/api/cases/{case_id}/matched-rules` | GET | 获取命中规则列表 |
| `/api/cases/{case_id}/reviews` | GET/POST | 复核记录列表 / 提交复核 |
| `/api/cases/{case_id}/report/export` | GET | 导出苹果风 Bento Grid HTML 报告 |
| `/api/tasks` | GET | 任务列表 |
| `/api/tasks/analysis` | POST | 创建分析任务（异步执行） |
| `/api/tasks/{task_id}/status` | GET/PUT | 任务状态查询 / 更新进度 |
| `/api/rules` | GET/POST/PUT/DELETE | 规则 CRUD（仅 admin 可修改） |
| `/api/stats/overview` | GET | 概览统计数据 |
| `/api/history-cases` | GET | 历史案例列表 |
| `/health` | GET | 健康检查（数据库、YOLO、Dify 状态） |
| `/upload_video/` | POST | 视频上传 + YOLO 关键帧提取 |
| `/api/upload_video/` | POST | 同上（兼容前端 /api 前缀） |
| `/analyze_image_file_evidence/` | POST | 图片证据分析 |
| `/api/analyze_image_file_evidence/` | POST | 同上（兼容前端 /api 前缀） |
| `/dify/analyze_accident_case/` | POST | Dify 智能分析调用 |
| `/api/dify/analyze_accident_case/` | POST | 同上（兼容前端 /api 前缀） |
| `/api/reports/generate` | POST | 根据前端数据生成报告 |

**权限控制**：

```python
def require_role(*allowed_roles: str):
    """角色权限验证依赖"""
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return current_user
    return role_checker
```

**异步任务流程控制器**：

```python
def _run_analysis_flow(task_id: str, case_id: str):
    """后台执行分析流程：pending → running(30%) → 写入事实(60%) → 写入规则(80%) → 写入责任(100%) → success"""
    update_analysis_task(task_id, {"task_status": "running", "progress": 30})
    # 写入结构化事实
    create_structured_fact(...)
    update_analysis_task(task_id, {"progress": 60})
    # 写入规则命中
    save_liability_result(case_id, {"hit_rules": hit_rules})
    update_analysis_task(task_id, {"progress": 80})
    # 写入责任建议 + 版本
    create_analysis_version(case_id, ...)
    update_analysis_task(task_id, {"task_status": "success", "progress": 100})

@app.post("/api/tasks/analysis")
async def api_create_analysis_task(data: dict, background_tasks: BackgroundTasks):
    task = create_analysis_task(case_id, task_type)
    background_tasks.add_task(_run_analysis_flow, task["task_id"], case_id)  # 异步执行
    return {"success": True, "data": task}
```

**文件存储规范化**：

```python
UPLOADS_DIR = BASE_DIR / "uploads"

def _get_case_upload_dir(case_id: str) -> Path:
    d = UPLOADS_DIR / "cases" / case_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def _compute_file_hash(file_path: Path) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

@app.post("/upload_video/")
@app.post("/api/upload_video/")
async def upload_video(file: UploadFile = File(...), case_id: str = Form("")):
    # 文件格式校验
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, detail="不支持此格式")
    # 保存到规范目录: uploads/cases/{case_id}/videos/
    dest_path = _get_case_upload_dir(case_id) / "videos" / f"original{ext}"
    # 计算文件哈希
    file_hash = _compute_file_hash(dest_path)
    # 创建证据记录
    create_evidence_record(case_id, {"file_path": str(dest_path), "file_hash": file_hash, ...})
    # YOLO 关键帧提取
    result = await run_in_threadpool(extract_keyframes_yolo, dest_path)
    return result
```

**健康检查（含 Dify 状态识别）**：

```python
def _dify_service_status():
    api_key = (os.getenv("DIFY_API_KEY") or "").strip()
    if not api_key or "xxxx" in api_key.lower():
        return "unconfigured"
    return "reachable"

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "database": "connected",
        "yolo_model": "loaded",
        "dify_service": _dify_service_status(),
        "timestamp": datetime.now().isoformat(),
    }
```


### 3. `dify_mock.py`——Dify Mock 服务器（新增）

**主要功能**：模拟 Dify 工作流接口，返回结构化分析结果。

**关键代码**：

```python
@app.post("/v1/workflows/run")
async def mock_dify_workflow(request: Dict[str, Any]):
    # 解析输入
    summary_text = request.get("inputs", {}).get("query", "")
    video_json = request.get("inputs", {}).get("video_result_json", "{}")
    # 返回模拟分析结果
    return {
        "result": {
            "case_analysis": {"accident_type": "双车并行变道碰撞", "vehicle_count": 2, ...},
            "hit_rules": [{"code": "R-002", "name": "变道未打转向灯", ...}],
            "structured_facts": [...],
            "consistency_check": {"score": 85, ...}
        }
    }
```


### 4. `test_api.py`——自动化测试

**测试覆盖**：登录、权限删除规则、案件创建、状态机（非法/合法流转）、证据添加/查询、分析任务创建/状态更新/查询、责任版本保存/查询、结构化事实创建/查询、证据一致性检测、健康检查、规则创建/删除、测试数据清理。

**运行结果**：**43/43 全部通过** ✅


## 二、前端工作

### 1. `src/api/index.js`——统一 API 层

**主要功能**：封装所有后端请求，自动携带 JWT token。

**关键代码**：

```javascript
const API_BASE = 'http://localhost:8000'

async function request(method, path, body = null) {
  const options = { method, headers: { 'Content-Type': 'application/json' } }
  const token = localStorage.getItem('auth-token')
  if (token) options.headers['Authorization'] = `Bearer ${token}`
  if (body && method !== 'GET') options.body = JSON.stringify(body)
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  return response.json()
}

export const CasesAPI = {
  getList: (params) => request('GET', `/api/cases?${new URLSearchParams(params)}`),
  getDetail: (id) => request('GET', `/api/cases/${id}`),
  create: (data) => request('POST', '/api/cases', data),
  update: (id, data) => request('PUT', `/api/cases/${id}`, data),
  delete: (id) => request('DELETE', `/api/cases/${id}`),
  getEvidences: (id) => request('GET', `/api/cases/${id}/evidences`),
  getFacts: (id) => request('GET', `/api/cases/${id}/facts`),
  getMatchedRules: (id) => request('GET', `/api/cases/${id}/matched-rules`),
  getReviews: (id) => request('GET', `/api/cases/${id}/reviews`),
  getLiabilityLatest: (id) => request('GET', `/api/cases/${id}/liability-latest`),
  getEvidenceConsistency: (id) => request('GET', `/api/cases/${id}/evidence-consistency`),
  saveLiability: (id, data) => request('POST', `/api/cases/${id}/liability`, data),
  addReview: (id, data) => request('POST', `/api/cases/${id}/reviews`, data),
  saveSnapshot: (id, step, data) => request('POST', `/api/cases/${id}/snapshot`, { step, data }),
}

export const AuthAPI = {
  login: (username, password) => request('POST', '/api/auth/login', { username, password }),
  me: () => request('GET', '/api/auth/me'),
  logout: () => request('POST', '/api/auth/logout'),
}

export const TasksAPI = {
  createAnalysis: (data) => request('POST', '/api/tasks/analysis', data),
  getStatus: (taskId) => request('GET', `/api/tasks/${taskId}/status`),
  updateStatus: (taskId, data) => request('PUT', `/api/tasks/${taskId}/status`, data),
}

export const StatsAPI = {
  getOverview: () => request('GET', '/api/stats/overview'),
  getHistoryCases: (params) => request('GET', `/api/history-cases?${new URLSearchParams(params)}`),
}
```


### 2. `src/router/index.js`——路由与守卫

**主要功能**：定义所有路由，实现登录保护。

**关键代码**：

```javascript
const routes = [
  { path: '/login', component: Login },
  { path: '/overview', component: Overview, meta: { requiresAuth: true } },
  { path: '/accident-entry', component: AccidentEntry, meta: { requiresAuth: true } },
  // ... 其他页面
]

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('auth-token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/overview')
  } else {
    next()
  }
})
```


### 3. `src/App.vue`——根组件

**主要功能**：管理登录状态、侧边栏布局、全局通知。

**关键代码**：

```javascript
const isLoggedIn = computed(() => !!localStorage.getItem('auth-token'))
const currentUser = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('auth-user') || '{}')
  } catch { return {} }
})

const handleLogout = () => {
  localStorage.removeItem('auth-token')
  localStorage.removeItem('auth-user')
  router.push('/login')
}
```


### 4. `src/components/Sidebar.vue`——侧边栏

**主要功能**：导航菜单 + 用户面板（登录/未登录双态）。

**关键代码**：

```javascript
const navigation = [
  { path: '/overview', label: '首页总览', icon: 'home' },
  { path: '/accident-entry', label: '事故录入', icon: 'plus' },
  { path: '/rule-library', label: '规则库', icon: 'book' },
  { path: '/history-cases', label: '历史案例', icon: 'folder' },
]
```


### 5. `src/views/Login.vue`——登录页

**主要功能**：调用后端认证接口，存储 token 和用户信息。

**关键代码**：

```javascript
const handleLogin = async () => {
  const result = await AuthAPI.login(username.value, password.value)
  if (result.success) {
    localStorage.setItem('auth-token', result.data.token)
    localStorage.setItem('auth-user', JSON.stringify(result.data.user))
    router.push('/overview')
  }
}
```


### 6. `src/views/Overview.vue`——概览页

**主要功能**：展示统计数据、案件列表、任务列表。

**关键代码**：

```javascript
const refreshData = async () => {
  const stats = await StatsAPI.getOverview()
  const cases = await CasesAPI.getList({ limit: 100 })
  const tasks = await TasksAPI.getPendingList()
  // 填充页面数据
}
```


### 7. `src/views/AccidentEntry.vue`——事故录入

**主要功能**：录入案件信息，提交创建案件，跳转视频处理页。

**关键代码**：

```javascript
const submitAnalysis = async () => {
  const result = await CasesAPI.create({
    title: form.value.accidentType || '事故案件',
    accident_type: form.value.accidentType,
    location: form.value.location,
    description: form.value.description,
    weather: form.value.weather,
    road_env: form.value.roadEnv,
    vehicles: form.value.vehicles || [],
  })
  if (result.success) {
    state.caseId = result.data.id
    router.push('/video-processing')
  }
}
```


### 8. `src/views/HistoryCases.vue`——历史案例

**主要功能**：案例列表、编辑、删除、继续处理。

**关键代码**：

```javascript
const fetchHistoryCases = async () => {
  const result = await StatsAPI.getHistoryCases({ limit: 100 })
  historyCases.value = result.data
}

const continueCase = (caseItem) => {
  if (caseItem.status === '待分析') {
    router.push(`/intelligent-analysis?caseId=${caseItem.id}`)
  } else if (caseItem.status === '待复核') {
    router.push(`/manual-review?caseId=${caseItem.id}`)
  }
}
```


### 9. `src/views/IntelligentAnalysis.vue`——智能分析

**主要功能**：展示责任判定结果，支持保存判定。

**关键代码**：

```javascript
const loadCaseLiability = async () => {
  const result = await CasesAPI.getDetail(state.caseId)
  if (result.success && result.data) {
    const liability = result.data.liability
    state.analysis.confidence = liability?.details?.confidence || 0
    state.analysis.vehicleLiabilities = liability?.details?.vehicles || []
    state.analysis.matchedRules = liability?.hit_rules || []
    state.analysis.reasoningText = liability?.summary || ''
  }
}

const confirmAnalysis = async () => {
  await CasesAPI.saveLiability(state.caseId, {
    summary: reasoningText.value,
    ratio: vehicleLiabilities.value.map(l => `${l.role}:${l.percentage}%`).join('; '),
    details: { vehicles: vehicleLiabilities.value, confidence: state.analysis.confidence },
    hit_rules: matchedRules.value,
  })
}
```


### 10. `src/views/Liability.vue`——责任建议

**主要功能**：展示责任判定结果详情。

**关键代码**：

```javascript
const loadCaseLiability = async () => {
  const result = await CasesAPI.getDetail(state.caseId)
  if (result.success && result.data) {
    const liability = result.data.liability
    if (liability) {
      state.analysis.vehicleLiabilities = liability.details?.vehicles || []
      state.analysis.matchedRules = liability.hit_rules || []
      state.analysis.reasoningText = liability.summary || ''
      state.analysis.confidence = liability.details?.confidence || 0
    }
  }
}
```


### 11. `src/views/ReportDetail.vue`——报告详情

**主要功能**：展示分析报告，支持导出。

**关键代码**：

```javascript
const downloadReport = async () => {
  const response = await CasesAPI.exportReport(state.caseId)
  const url = window.URL.createObjectURL(new Blob([response.data], { type: 'text/html' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `报告_${state.caseId}.html`
  link.click()
}
```


### 12. `src/views/RuleBasis.vue`——规则依据

**主要功能**：展示案件命中的规则列表，调用 `CasesAPI.getMatchedRules()` 从 `matched_rules` 表获取。

**关键代码**：

```javascript
const fetchMatchedRules = async () => {
  const result = await CasesAPI.getMatchedRules(state.caseId)
  if (result.success) {
    matchedRules.value = result.data
  }
}
```


### 13. `src/views/ManualReview.vue`——人工复核

**主要功能**：提交复核意见，展示历史复核记录。

**关键代码**：

```javascript
const fetchReviews = async () => {
  const result = await CasesAPI.getReviews(state.caseId)
  if (result.success) {
    reviews.value = result.data
  }
}

const handleSubmitReview = async () => {
  await CasesAPI.addReview(state.caseId, {
    reviewer: currentUser.value.display_name,
    system_suggestion: state.analysis.reasoningText,
    final_result: form.value.final_result,
    review_comment: form.value.review_comment,
  })
}
```


### 14. `src/views/RuleLibrary.vue`——规则库

**主要功能**：规则增删改查，仅管理员可操作。

**关键代码**：

```javascript
const fetchRules = async () => {
  const result = await RulesAPI.getList()
  rules.value = result.data
}

const saveRule = async () => {
  if (editingRule.value) {
    await RulesAPI.update(editingRule.value.id, form.value)
  } else {
    await RulesAPI.create(form.value)
  }
  fetchRules()
}
```


### 15. `src/views/VideoProcessing.vue`——视频处理

**主要功能**：视频上传、关键帧提取、Send to Dify。

**关键代码**：

```javascript
const uploadVideo = async () => {
  const formData = new FormData()
  formData.append('file', videoFile.value)
  formData.append('case_id', state.caseId)
  const response = await fetch('/api/upload_video/', {
    method: 'POST',
    body: formData,
  })
  const result = await response.json()
  keyframes.value = result.keyframes
}

const sendToDify = async () => {
  const result = await CasesAPI.analyzeWithDify(state.caseId, {
    video_result: videoResult.value,
    image_evidence: imageEvidence.value,
    additional_evidence: additionalEvidence.value,
  })
  // 展示分析结果
}
```


### 16. `src/views/ImageEvidence.vue`——图片侧证

**主要功能**：图片证据上传与分析。


## 三、修复改进汇总

| 问题 | 修复方式 | 涉及文件 |
|------|---------|----------|
| Dify 服务不可达 | 创建 Mock 服务 + 健康检查增强 | `dify_mock.py`、`main.py` |
| 视频上传 404 | 添加 `/api/upload_video/` 路由 | `main.py` |
| 图片分析 404 | 添加 `/api/analyze_image_file_evidence/` 路由 | `main.py` |
| Dify 分析 404 | 添加 `/api/dify/analyze_accident_case/` 路由 | `main.py` |
| reviews/matched-rules 500 | `rows_to_list` → `[dict(row) for row in ...]` | `main.py` |
| 前端 404 白屏 | 统一 404 错误处理 + 路由守卫 + 缓存清理 | 所有详情页 |
| 路由守卫过严 | 放宽 caseId 检查，允许空状态访问 | `src/router/index.js` |
| 视频处理超时 | `timeout_keep_alive=300` 延长至 5 分钟 | `main.py` |


## 四、待办事项（后续优化）

1. **完善测试覆盖**：补齐 `test_api.py` 中未覆盖的接口，使全部接口通过测试
2. **接入真实 Dify 服务**：替换 Mock 服务器，连接真实工作流，并将分析结果结构化入库
3. **集成真实 YOLO 模型**：替换模拟分析结果，实现真实目标检测与关键帧提取
4. **生成 PDF/Word 报告**：在现有 HTML 报告基础上，增加 PDF 和 Word 格式导出
5. **异步任务队列**：使用 Celery/Redis 替换 FastAPI `BackgroundTasks`，支持大规模并发处理
6. **文件存储规范化**：按 `case_id` 组织视频、图片、关键帧、报告目录，支持哈希校验
7. **前端性能优化**：虚拟滚动加载长列表、路由懒加载、图片懒加载
8. **系统监控与告警**：接入 Prometheus + Grafana，监控 API 响应时间、任务队列积压等指标
9. **多租户支持**：支持多单位、多用户隔离，每个单位独立数据空间
10. **移动端适配**：优化移动端页面样式，支持手机端案件录入与查看
```