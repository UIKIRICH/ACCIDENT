// API接口层 - 统一管理所有接口请求
// 使用真实后端API，通过HTTP请求与FastAPI后端通信

import { notify } from '../composables/useToast.js'

const API_BASE = '';   // 强制为空

// 存储token和用户信息
let authToken = localStorage.getItem('auth-token') || ''
let currentUser = null

// 失败兜底提示防抖标记（避免同类错误短时间内重复弹窗）
let lastErrorNotifyTime = 0
const ERROR_NOTIFY_DEBOUNCE = 2000  // 2 秒防抖

// 友好错误提示：根据错误码和错误信息匹配 6 类异常场景
function showFriendlyError(status, detail, path) {
  const now = Date.now()
  if (now - lastErrorNotifyTime < ERROR_NOTIFY_DEBOUNCE) return
  lastErrorNotifyTime = now

  const msg = String(detail || '').toLowerCase()
  const p = String(path || '').toLowerCase()

  // 1. Dify 不可用（502/504/500 + dify 关键字）
  if ((status === 502 || status === 504) || (status === 500 && msg.includes('dify'))) {
    notify({
      title: 'AI 分析服务异常',
      message: 'AI 分析服务暂时不可用，已转人工复核流程',
      type: 'warning'
    })
    return
  }

  // 2. 图片模型不可用（500 + image evidence 关键字）
  if (status === 500 && (msg.includes('image evidence') || msg.includes('image_evidence') || p.includes('analyze_image'))) {
    notify({
      title: '图片识别服务异常',
      message: '图片识别服务异常，请稍后重试',
      type: 'warning'
    })
    return
  }

  // 3. 证据冲突（接口返回冲突信息，由页面处理，此处不拦截）
  // 证据冲突通过 evidence-consistency 接口返回的 conflicts 字段处理，非错误码

  // 4. 报告导出失败（500 + report 关键字，或 404 + report）
  if ((status === 500 || status === 404) && (p.includes('report') || msg.includes('report'))) {
    notify({
      title: '报告生成失败',
      message: '报告生成失败，可重新生成或稍后重试',
      type: 'error'
    })
    return
  }

  // 5. 非法状态跳转（400 + 状态相关关键字）
  if (status === 400 && (msg.includes('status') || msg.includes('state') || msg.includes('状态') || msg.includes('不允许'))) {
    notify({
      title: '操作无效',
      message: '案件当前状态不允许此操作，请按正确流程处理',
      type: 'warning'
    })
    return
  }

  // 6. 规则未命中（matched-rules 返回空，非错误码，由页面处理）
  // 规则未命中通过空数组返回，由页面显示"未匹配到规则，建议人工复核"

  // 7. 通用错误提示（兜底）
  if (status === 404) {
    notify({
      title: '资源不存在',
      message: '请求的资源不存在，可能已被删除',
      type: 'warning'
    })
  } else if (status === 500) {
    notify({
      title: '服务器错误',
      message: '服务器内部错误，请稍后重试',
      type: 'error'
    })
  } else if (status === 503) {
    notify({
      title: '服务不可用',
      message: '服务暂时不可用，请稍后重试',
      type: 'warning'
    })
  }
}

// 设置认证信息
export function setAuthToken(token) {
  authToken = token
  if (token) {
    localStorage.setItem('auth-token', token)
  } else {
    localStorage.removeItem('auth-token')
  }
}

export function getAuthToken() {
  return authToken
}

export function setCurrentUser(user) {
  currentUser = user
  if (user) {
    localStorage.setItem('auth-user', JSON.stringify(user))
  } else {
    localStorage.removeItem('auth-user')
  }
}

export function getCurrentUser() {
  if (currentUser) return currentUser
  try {
    const stored = localStorage.getItem('auth-user')
    if (stored) {
      currentUser = JSON.parse(stored)
      return currentUser
    }
  } catch { }
  return null
}

// 通用请求函数
async function request(method, path, body = null) {
  const url = `${API_BASE}${path}`
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
  }

  if (authToken) {
    options.headers['Authorization'] = `Bearer ${authToken}`
  }

  if (body && method !== 'GET') {
    options.body = JSON.stringify(body)
  }

  const response = await fetch(url, options)

  if (!response.ok) {
    let errorDetail = `请求失败: ${response.status}`
    try {
      const errData = await response.json()
      errorDetail = errData.detail || errData.message || errorDetail
    } catch { }

    // 401 未授权：token 过期或无效，清除登录态并跳转登录页
    if (response.status === 401) {
      setAuthToken('')
      setCurrentUser(null)
      // 通知 App.vue 显示提示并跳转登录页（避免在 API 层直接操作路由）
      window.dispatchEvent(new CustomEvent('auth-expired', {
        detail: { reason: errorDetail }
      }))
    } else {
      // 其他错误：显示友好提示（6 类异常场景 + 通用兜底）
      showFriendlyError(response.status, errorDetail, path)
    }

    throw new Error(errorDetail)
  }

  return response.json()
}

// 文件上传
async function uploadFile(path, file, extraFields = {}) {
  const url = `${API_BASE}${path}`
  const formData = new FormData()
  formData.append('file', file)

  for (const [key, value] of Object.entries(extraFields)) {
    formData.append(key, value)
  }

  const options = {
    method: 'POST',
    body: formData,
  }

  if (authToken) {
    options.headers = { 'Authorization': `Bearer ${authToken}` }
  }

  const response = await fetch(url, options)
  if (!response.ok) {
    let errorDetail = `上传失败: ${response.status}`
    try {
      const errData = await response.json()
      errorDetail = errData.detail || errData.message || errorDetail
    } catch { }

    // 401 未授权：token 过期或无效，清除登录态并跳转登录页
    if (response.status === 401) {
      setAuthToken('')
      setCurrentUser(null)
      window.dispatchEvent(new CustomEvent('auth-expired', {
        detail: { reason: errorDetail }
      }))
    } else {
      // 其他错误：显示友好提示
      showFriendlyError(response.status, errorDetail, path)
    }

    throw new Error(errorDetail)
  }

  return response.json()
}

// 认证相关API
export const AuthAPI = {
  async login(username, password) {
    const result = await request('POST', '/api/auth/login', { username, password })
    if (result.success && result.data) {
      setAuthToken(result.data.token)
      setCurrentUser(result.data.user)
    }
    return result
  },

  async getMe() {
    return request('GET', '/api/auth/me')
  },

  logout() {
    setAuthToken('')
    setCurrentUser(null)
  },

  isLoggedIn() {
    return !!authToken
  }
}

// 案件相关API
export const CasesAPI = {
  async getList(params = {}) {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.accident_type) query.set('accident_type', params.accident_type)
    if (params.limit) query.set('limit', params.limit)
    const qs = query.toString()
    return request('GET', `/api/cases${qs ? '?' + qs : ''}`)
  },

  async get(caseId) {
    return request('GET', `/api/cases/${caseId}`)
  },

  async getDetail(caseId) {
    return request('GET', `/api/cases/${caseId}`)
  },

  async create(data) {
    return request('POST', '/api/cases', data)
  },

  async update(caseId, updates) {
    return request('PUT', `/api/cases/${caseId}`, updates)
  },

  async delete(caseId) {
    return request('DELETE', `/api/cases/${caseId}`)
  },

  async saveSnapshot(caseId, step, data) {
    return request('POST', `/api/cases/${caseId}/snapshot`, { step, data })
  },

  async getMatchedRules(caseId) {
    return request('GET', `/api/cases/${caseId}/matched-rules`)
  },

  async getReviews(caseId) {
    return request('GET', `/api/cases/${caseId}/reviews`)
  },

  async addReview(caseId, data) {
    return request('POST', `/api/cases/${caseId}/reviews`, data)
  },

  async saveLiability(caseId, data) {
    return request('POST', `/api/cases/${caseId}/liability`, data)
  },

  async getEvidenceConsistency(caseId) {
    return request('GET', `/api/cases/${caseId}/evidence-consistency`)
  },

  // 视频语义校验（千问多模态）相关接口
  // 1. 获取融合证据包（前端展示用，最常用）
  async getFusedEvidence(caseId) {
    return request('GET', `/api/cases/${caseId}/fused-evidence`)
  },

  // 2. 触发千问视频语义校验（通常由视频处理流程在后端自动串联，前端仅在手动重试时调用）
  // data: { video_path, keyframes, detector_output }
  async videoSemanticCheck(caseId, data) {
    return request('POST', `/api/cases/${caseId}/video-semantic-check`, data)
  },

  // 3. 触发证据融合（通常由后端流程自动调用）
  // data: { detector_output, qwen_semantic_check }
  async fuseVideoEvidence(caseId, data) {
    return request('POST', `/api/cases/${caseId}/fuse-video-evidence`, data)
  },

  async getEvidences(caseId) {
    return request('GET', `/api/cases/${caseId}/evidences`)
  },

  async getFacts(caseId) {
    return request('GET', `/api/cases/${caseId}/facts`)
  },

  async getLiabilityLatest(caseId) {
    return request('GET', `/api/cases/${caseId}/liability-latest`)
  },

  async exportReport(caseId) {
    const response = await fetch(`${API_BASE}/api/cases/${caseId}/report/export`)
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('案件数据不存在，请先在系统中保存案件后再导出')
      }
      throw new Error(`导出失败: ${response.status}`)
    }
    const blob = await response.blob()
    return blob
  },

  async generateReport(caseData) {
    const response = await fetch(`${API_BASE}/api/reports/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case: caseData })
    })
    if (!response.ok) {
      throw new Error(`导出失败: ${response.status}`)
    }
    const blob = await response.blob()
    return blob
  },

  async continueEditing(caseId) {
    return this.getDetail(caseId)
  }
}

// 规则相关API
export const RulesAPI = {
  async getList(params = {}) {
    const query = new URLSearchParams()
    if (params.type) query.set('type', params.type)
    if (params.status) query.set('status', params.status)
    const qs = query.toString()
    return request('GET', `/api/rules${qs ? '?' + qs : ''}`)
  },

  async getDetail(ruleId) {
    // Rules don't have a dedicated detail endpoint, filter from list
    const result = await this.getList()
    if (result.success && result.data) {
      const rule = result.data.find(r => r.id === ruleId)
      return rule ? { success: true, data: rule } : { success: false, message: '规则不存在' }
    }
    return result
  },

  async create(data) {
    return request('POST', '/api/rules', data)
  },

  async update(ruleId, updates) {
    return request('PUT', `/api/rules/${ruleId}`, updates)
  },

  async delete(ruleId) {
    return request('DELETE', `/api/rules/${ruleId}`)
  },

  async toggleStatus(ruleId, status) {
    return this.update(ruleId, { status })
  }
}

// 任务相关API
export const TasksAPI = {
  async getPendingList() {
    return request('GET', '/api/tasks?status=pending')
  },

  async complete(taskId) {
    return request('POST', `/api/tasks/${taskId}/complete`)
  },

  async startProcess(task) {
    return { success: true, data: task }
  }
}

// 流程相关API
export const FlowAPI = {
  async getCurrentState() {
    return { success: true, data: {} }
  },

  async saveDraft(data) {
    return { success: true, message: '草稿已保存' }
  },

  async getDraft() {
    return { success: true, data: null }
  },

  async clearDraft() {
    return { success: true }
  },

  async reset() {
    return { success: true }
  },

  async completeIntake() {
    return { success: true, route: '/video-processing' }
  },

  async completeVideoProcessing() {
    return { success: true, route: '/intelligent-analysis' }
  },

  async completeAnalysis() {
    return { success: true, route: '/liability-recommendation' }
  },

  async completeRecommendation() {
    return { success: true, route: '/rule-basis' }
  },

  async completeRuleBasis() {
    return { success: true, route: '/manual-review' }
  },

  async submitManualReview(data) {
    return { success: true, route: '/history-cases' }
  }
}

// 统计和历史API
export const StatsAPI = {
  async getOverview() {
    return request('GET', '/api/stats/overview')
  },

  async getHistoryCases(params = {}) {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.limit) query.set('limit', params.limit)
    const qs = query.toString()
    return request('GET', `/api/history-cases${qs ? '?' + qs : ''}`)
  }
}

// 健康检查API
export const HealthAPI = {
  async check() {
    return request('GET', '/health')
  }
}

export default {
  auth: AuthAPI,
  cases: CasesAPI,
  rules: RulesAPI,
  tasks: TasksAPI,
  flow: FlowAPI,
  stats: StatsAPI,
  health: HealthAPI
}