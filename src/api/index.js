// API接口层 - 统一管理所有接口请求
// 使用真实后端API，通过HTTP请求与FastAPI后端通信

const API_BASE = '';   // 强制为空

// 存储token和用户信息
let authToken = localStorage.getItem('auth-token') || ''
let currentUser = null

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