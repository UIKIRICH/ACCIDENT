<template>
  <div class="overview-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">首页总览</h1>
        <p class="page-subtitle">查看平台整体运行状态与最新动态</p>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="refreshData">
          <span class="refresh-icon" v-html="icons.refresh"></span>
          刷新数据
        </button>
      </div>
    </div>

    <div class="quick-entry-section">
      <div class="quick-entry-header">
        <h2 class="quick-entry-title">快捷入口</h2>
      </div>
      <div class="quick-entry-buttons">
        <button v-if="state.step !== 'intake' && state.step !== 'archived'" class="quick-entry-btn primary" @click="continueCurrentCase">
          <span class="btn-icon" v-html="icons.play"></span>
          继续当前案件
          <span class="case-info">{{ state.caseId }}</span>
        </button>
        <button class="quick-entry-btn secondary" @click="startNewCase">
          <span class="btn-icon" v-html="icons.plus"></span>
          事故录入
        </button>
        <button class="quick-entry-btn secondary" @click="goToHistoryCases">
          <span class="btn-icon" v-html="icons.folder"></span>
          历史案例
        </button>
      </div>
      <div class="current-case-status" v-if="state.step !== 'overview' && state.step !== 'archived'">
        <div class="status-item">
          <span class="status-label">当前案件:</span>
          <span class="status-value">{{ state.caseId }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">当前步骤:</span>
          <span class="status-value">{{ getStepLabel(state.step) }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">事故类型:</span>
          <span class="status-value">{{ state.form.accidentType || '待填写' }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">素材类型:</span>
          <span class="status-value">{{ state.form.fileType || '待上传' }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">下一步:</span>
          <span class="status-value">{{ getNextStepLabel(state.step) }}</span>
        </div>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card" v-for="(stat, index) in statsCards" :key="stat.key" :class="stat.cardClass">
        <div class="stat-card-bg"></div>
        <div class="stat-card-glow"></div>
        <div class="stat-header">
          <div class="stat-info">
            <span class="stat-label">{{ stat.label }}</span>
            <div class="stat-value-wrapper">
              <span class="stat-value">{{ stat.value }}</span>
              <span class="stat-unit">{{ stat.unit }}</span>
            </div>
          </div>
          <div class="stat-icon" :class="stat.iconClass">
            <span v-html="stat.icon"></span>
            <div class="icon-bg"></div>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-change" :class="stat.changeClass">
            <span class="change-icon" v-html="stat.changeIcon"></span>
            <span class="change-value">{{ stat.change }}</span>
          </div>
          <span class="stat-period">较上周</span>
        </div>
        <div class="stat-sparkline">
          <svg viewBox="0 0 100 30" preserveAspectRatio="none">
            <path :d="stat.sparkline" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <div class="section-card recent-cases">
        <div class="section-header">
          <div class="section-title-wrapper">
            <span class="section-icon" v-html="icons.folder"></span>
            <h2 class="section-title">最近事故记录</h2>
          </div>
          <button class="section-action" @click="goToHistoryCases">
            查看全部
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </button>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>案件编号</th>
                <th>事故类型</th>
                <th>状态</th>
                <th>地点</th>
                <th>时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="caseItem in pagedCases" :key="caseItem.id">
                <td>
                  <span class="case-id">{{ caseItem.id }}</span>
                </td>
                <td>{{ caseItem.type }}</td>
                <td>
                  <span class="badge" :class="getStatusClass(caseItem.status)">
                    <span class="badge-dot"></span>
                    {{ caseItem.status }}
                  </span>
                </td>
                <td class="location-cell">
                  <svg viewBox="0 0 24 24" fill="currentColor" class="location-icon">
                    <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                  </svg>
                  {{ caseItem.location }}
                </td>
                <td>{{ formatDate(caseItem.time) }}</td>
                <td>
                  <div class="action-buttons">
                    <button class="action-btn view" title="查看详情" @click="viewCaseDetail(caseItem)">
                      <span v-html="icons.eye"></span>
                    </button>
                    <button class="action-btn edit" title="编辑基本信息" @click="editCase(caseItem)">
                      <span v-html="icons.edit"></span>
                    </button>
                    <button v-if="caseItem.status !== '已完成' && caseItem.status !== '已归档'" 
                            class="action-btn continue" 
                            title="继续处理" 
                            @click="continueEditCase(caseItem)">
                      <span v-html="icons.play"></span>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="cases-pagination">
          <div class="pagination-info">显示 {{ startIndex + 1 }}-{{ Math.min(startIndex + pageSize, recentCases.length) }} 条，共 {{ recentCases.length }} 条</div>
          <div class="pagination-buttons">
            <button class="page-btn" :disabled="page===1" @click="page--">
              <span v-html="icons.chevronLeft"></span>
              上一页
            </button>
            <button v-for="item in displayPages" :key="item" class="page-btn" :class="{ active: page===item }" @click="page=item">{{ item }}</button>
            <button class="page-btn" :disabled="page===totalPages" @click="page++">
              下一页
              <span v-html="icons.chevronRight"></span>
            </button>
          </div>
        </div>
      </div>

      <div class="section-card tasks-section">
        <div class="section-header">
          <div class="section-title-wrapper">
            <span class="section-icon" v-html="icons.list"></span>
            <h2 class="section-title">待处理任务</h2>
          </div>
          <button class="section-action" @click="goToWorkQueue">
            查看全部
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </button>
        </div>
        <div class="tasks-list">
          <div 
            v-for="task in pagedTasks"
            :key="task.id"
            class="task-card"
            @click="goToWorkQueue"
          >
            <div class="task-header">
              <span class="task-id">{{ task.id }}</span>
              <span class="priority-badge" :class="getPriorityClass(task.priority)">
                {{ getPriorityLabel(task.priority) }}
              </span>
            </div>
            <h3 class="task-title">{{ task.title }}</h3>
            <div class="task-meta">
              <span class="task-type">
                <span class="type-dot"></span>
                {{ getTaskTypeLabel(task.type) }}
              </span>
              <span class="task-deadline">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/>
                </svg>
                {{ task.deadline }}
              </span>
            </div>
            <div class="task-actions">
              <button class="task-btn primary" @click.stop="processTask(task)">立即处理</button>
              <button class="task-btn secondary" @click.stop="delayTask(task)">稍后</button>
            </div>
          </div>
        </div>
        <div class="tasks-pagination">
          <div class="pagination-info">显示 {{ taskStartIndex + 1 }}-{{ Math.min(taskStartIndex + taskPageSize, pendingTasksList.length) }} 条，共 {{ pendingTasksList.length }} 条</div>
          <div class="pagination-buttons">
            <button class="page-btn" :disabled="taskPage===1" @click="taskPage--">
              <span v-html="icons.chevronLeft"></span>
              上一页
            </button>
            <button v-for="item in displayTaskPages" :key="item" class="page-btn" :class="{ active: taskPage===item }" @click="taskPage=item">{{ item }}</button>
            <button class="page-btn" :disabled="taskPage===totalTaskPages" @click="taskPage++">
              下一页
              <span v-html="icons.chevronRight"></span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { notify } from '../composables/useToast'
import { StatsAPI, CasesAPI, TasksAPI, RulesAPI } from '../api/index.js'
import { useAccidentFlow } from '../stores/useAccidentFlow'

const router = useRouter()
const { 
  state, 
  resetFlow, 
  getRecentCases, 
  getPendingTasks,
  completeTask,
  initRuleLibrary 
} = useAccidentFlow()

// 初始化
onMounted(() => {
  if (initRuleLibrary) initRuleLibrary()
  refreshData()
})

const isRefreshing = ref(false)
const dashboardStats = ref([])
// 最近事故记录分页
const page = ref(1)
const pageSize = 5
// 待处理任务分页
const taskPage = ref(1)
const taskPageSize = 3

// 从API获取的数据
const statsData = ref({
  totalCases: 0,
  pendingAnalysis: 0,
  pendingReview: 0,
  completedCases: 0,
  pendingTasks: 0,
  activeRules: 0,
  todayNew: 0,
})

const recentCases = ref([])
const pendingTasksList = ref([])
const loading = ref(false)

const totalPages = computed(() => Math.max(1, Math.ceil(recentCases.value.length / pageSize)))

const displayPages = computed(() => {
  const pages = []
  const start = Math.max(1, page.value - 2)
  const end = Math.min(totalPages.value, start + 4)
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  return pages
})

const startIndex = computed(() => (page.value - 1) * pageSize)
const pagedCases = computed(() => recentCases.value.slice(startIndex.value, startIndex.value + pageSize))

// 待处理任务分页计算
const totalTaskPages = computed(() => Math.max(1, Math.ceil(pendingTasksList.value.length / taskPageSize)))

const displayTaskPages = computed(() => {
  const pages = []
  const start = Math.max(1, taskPage.value - 2)
  const end = Math.min(totalTaskPages.value, start + 4)
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  return pages
})

const taskStartIndex = computed(() => (taskPage.value - 1) * taskPageSize)
const pagedTasks = computed(() => pendingTasksList.value.slice(taskStartIndex.value, taskStartIndex.value + taskPageSize))

// 计算统计数据（合并API数据+本地兜底）
const stats = computed(() => ({
  totalCases: statsData.value.totalCases || recentCases.value.length || 0,
  analyzedCases: statsData.value.completedCases || 0,
  pendingReview: statsData.value.pendingReview || 0,
  ruleCount: statsData.value.activeRules || state.ruleLibrary.rules.length || 0
}))

const statsCards = computed(() => [
  {
    key: 'total',
    label: '事故总数',
    value: stats.value.totalCases,
    unit: '件',
    change: '+12',
    changeClass: 'positive',
    changeIcon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>`,
    cardClass: 'card-blue',
    iconClass: 'icon-blue',
    icon: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill-opacity="0.2"/></svg>`,
    sparkline: 'M0,25 Q10,20 20,22 T40,18 T60,15 T80,10 T100,8'
  },
  {
    key: 'analyzed',
    label: '已分析案件',
    value: stats.value.analyzedCases,
    unit: '件',
    change: '+8',
    changeClass: 'positive',
    changeIcon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>`,
    cardClass: 'card-green',
    iconClass: 'icon-green',
    icon: `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10" fill-opacity="0.2"/><polyline points="8 12 11 15 16 9" fill="none" stroke="currentColor" stroke-width="2"/></svg>`,
    sparkline: 'M0,20 Q15,18 25,15 T50,12 T75,8 T100,5'
  },
  {
    key: 'pending',
    label: '待复核案件',
    value: stats.value.pendingReview,
    unit: '件',
    change: '+3',
    changeClass: 'negative',
    changeIcon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>`,
    cardClass: 'card-orange',
    iconClass: 'icon-orange',
    icon: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" fill-opacity="0.2"/><line x1="12" y1="9" x2="12" y2="13" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="17" r="1"/></svg>`,
    sparkline: 'M0,15 Q20,18 35,20 T60,22 T80,18 T100,20'
  },
  {
    key: 'rules',
    label: '规则数量',
    value: stats.value.ruleCount,
    unit: '条',
    change: '+2',
    changeClass: 'positive',
    changeIcon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>`,
    cardClass: 'card-purple',
    iconClass: 'icon-purple',
    icon: `<svg viewBox="0 0 24 24" fill="currentColor"><ellipse cx="12" cy="5" rx="9" ry="3" fill-opacity="0.2"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" fill="none" stroke="currentColor"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" fill="none" stroke="currentColor"/></svg>`,
    sparkline: 'M0,22 Q10,20 20,18 T45,15 T70,12 T100,10'
  }
])



const icons = {
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill-opacity="0.2"/></svg>`,
  list: `<svg viewBox="0 0 24 24" fill="currentColor"><line x1="8" y1="6" x2="21" y2="6" stroke="currentColor" stroke-width="2"/><line x1="8" y1="12" x2="21" y2="12" stroke="currentColor" stroke-width="2"/><line x1="8" y1="18" x2="21" y2="18" stroke="currentColor" stroke-width="2"/><circle cx="4" cy="6" r="1.5"/><circle cx="4" cy="12" r="1.5"/><circle cx="4" cy="18" r="1.5"/></svg>`,
  eye: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`,
  chevronLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>`,
  chevronRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`
}

const getStatusClass = (status) => {
  const map = {
    '待分析': 'badge-orange',
    '待复核': 'badge-blue',
    '已完成': 'badge-green',
    '已归档': 'badge-gray'
  }
  return map[status] || 'badge-gray'
}

const getPriorityClass = (priority) => {
  const map = {
    'high': 'priority-high',
    'medium': 'priority-medium',
    'low': 'priority-low'
  }
  return map[priority] || 'priority-low'
}

const getPriorityLabel = (priority) => {
  const labels = { high: '高优先级', medium: '中优先级', low: '低优先级' }
  return labels[priority] || priority
}

const getTaskTypeLabel = (type) => {
  const labels = {
    analysis: '智能分析',
    review: '人工复核',
    report: '报告生成',
    archive: '归档处理',
    '智能分析': '智能分析',
    '人工复核': '人工复核',
    '结案归档': '结案归档'
  }
  return labels[type] || type
}

const formatDate = (dateStr) => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const refreshData = async () => {
  isRefreshing.value = true
  loading.value = true
  try {
    // 1. 获取统计数据
    try {
      const statsResult = await StatsAPI.getOverview()
      if (statsResult.success) {
        statsData.value = statsResult.data
      }
    } catch (e) {
      console.warn('获取统计数据失败，使用本地数据:', e)
      // Fallback to local store data
    }

    // 2. 获取案件列表
    try {
      const casesResult = await CasesAPI.getList({ limit: 100 })
      if (casesResult.success && Array.isArray(casesResult.data)) {
        recentCases.value = casesResult.data.map(c => ({
          id: c.id || c.caseId,
          type: c.title || c.accident_type || '未命名',
          status: c.status || '待处理',
          location: c.location || '未记录',
          time: c.submitted_at || c.created_at || new Date().toISOString(),
          hasVideo: false
        }))
      }
    } catch (e) {
      console.warn('获取案件列表失败:', e)
      // Fallback to local store
      try {
        const localCases = getRecentCases(100)
        recentCases.value = localCases
      } catch {}
    }

    // 3. 获取任务列表
    try {
      const tasksResult = await TasksAPI.getPendingList()
      if (tasksResult.success && Array.isArray(tasksResult.data)) {
        pendingTasksList.value = tasksResult.data.map(t => ({
          id: t.id,
          caseId: t.case_id,
          title: t.title || t.case_title || '任务',
          type: t.task_type || 'analysis',
          status: t.status || 'pending',
          priority: t.priority || 'medium',
          deadline: t.deadline || t.created_at || '',
          createdAt: t.created_at || ''
        }))
      }
    } catch (e) {
      console.warn('获取任务列表失败:', e)
      pendingTasksList.value = []
    }

    notify({ title: '数据已刷新', message: '已获取最新的平台运行数据', type: 'success' })
  } catch (error) {
    notify({ title: '刷新失败', message: '无法获取最新数据，请检查网络连接', type: 'error' })
  } finally {
    loading.value = false
    setTimeout(() => {
      isRefreshing.value = false
    }, 500)
  }
}

const continueCurrentCase = () => {
  switch (state.step) {
    case 'video-processing':
      router.push('/video-processing')
      break
    case 'analysis':
      router.push('/intelligent-analysis')
      break
    case 'recommendation':
      router.push('/liability-recommendation')
      break
    case 'rule-basis':
      router.push('/rule-basis')
      break
    case 'manual-review':
      router.push('/manual-review')
      break
    default:
      router.push('/accident-entry')
  }
}

const startNewCase = () => {
  resetFlow()
  router.push('/accident-entry')
}

const goToHistoryCases = () => {
  router.push('/history-cases')
}

const handleContinueCase = () => {
  if (recentCases.value.length > 0) {
    const latestCase = recentCases.value[0]
    notify({ title: '继续处理', message: `正在继续处理案件 ${latestCase.id}: ${latestCase.type}` })
    router.push('/accident-entry')
  } else {
    notify({ title: '提示', message: '当前没有待处理的案件', type: 'info' })
  }
}

const goToWorkQueue = () => {
  router.push('/work-queue')
}

const viewCaseDetail = (caseItem) => {
  notify({ title: '查看详情', message: `正在查看 ${caseItem.id} 的详情` })
  // 跳转到历史案例页面并打开详情
  router.push({
    path: '/history-cases',
    query: { caseId: caseItem.id }
  })
}

const editCase = (caseItem) => {
  notify({ title: '编辑案件', message: `正在编辑 ${caseItem.id}` })
  // 跳转到历史案例页面并打开编辑
  router.push({
    path: '/history-cases',
    query: { caseId: caseItem.id, edit: 'true' }
  })
}

const continueEditCase = async (caseItem) => {
  try {
    // 尝试直接从store中恢复案件数据
    const archivedCase = state.archivedCases.find(c => c.caseId === caseItem.id)
    if (archivedCase && archivedCase.snapshot) {
      resetFlow()
      Object.assign(state, archivedCase.snapshot.state)
      state.caseId = caseItem.id
      
      notify({ title: '恢复成功', message: `已恢复案件 ${caseItem.id}，请继续处理`, type: 'success' })
      // 根据案件当前状态跳转到对应页面
      continueCurrentCase()
    } else {
      notify({ title: '恢复失败', message: '无法找到案件数据', type: 'error' })
    }
  } catch (error) {
    notify({ title: '错误', message: '恢复案件失败', type: 'error' })
  }
}

const processTask = (task) => {
  notify({ title: '处理任务', message: `开始处理 ${task.id}` })
  
  // 尝试从案件ID中提取caseId（task.id格式是T-ACC-xxx）
  const caseId = task.caseId || task.id.replace('T-', '')
  
  // 尝试恢复案件数据
  if (caseId) {
    const archivedCase = state.archivedCases.find(c => c.caseId === caseId)
    if (archivedCase && archivedCase.snapshot) {
      resetFlow()
      Object.assign(state, archivedCase.snapshot.state)
      state.caseId = caseId
    }
  }
  
  if (task.type === '智能分析' || task.type === 'analysis') {
    router.push('/intelligent-analysis')
  } else if (task.type === '人工复核' || task.type === 'review') {
    router.push('/manual-review')
  } else {
    // 默认回到事故录入
    router.push('/accident-entry')
  }
}

const delayTask = (task) => {
  notify({ title: '已延后', message: `${task.id} 已延后处理` })
}

const getStepLabel = (step) => {
  const stepLabels = {
    overview: '首页总览',
    intake: '事故录入',
    'video-processing': '视频处理',
    analysis: '智能分析',
    recommendation: '责任建议',
    'rule-basis': '规则依据',
    'manual-review': '人工复核',
    archived: '已归档'
  }
  return stepLabels[step] || step
}

const getNextStepLabel = (step) => {
  const nextSteps = {
    intake: '视频处理',
    'video-processing': '智能分析',
    analysis: '责任建议',
    recommendation: '规则依据',
    'rule-basis': '人工复核',
    'manual-review': '已归档'
  }
  return nextSteps[step] || '无'
}
</script>

<style scoped>
.overview-page {
  padding: 0;
  animation: pageIn 0.4s var(--ease-default);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-header {
  margin-bottom: var(--space-8);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-5);
}

.header-content {
  flex: 1;
}

.page-title {
  font-size: 26px;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
  letter-spacing: var(--tracking-tight);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 400;
}

.header-actions {
  display: flex;
  gap: var(--space-3);
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 9px 18px;
  background: var(--primary-gradient);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-normal);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
  font-family: var(--font-sans);
}

.refresh-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.refresh-icon {
  width: 15px;
  height: 15px;
}

.quick-entry-section {
  margin-bottom: var(--space-8);
}

.quick-entry-header {
  margin-bottom: var(--space-4);
}

.quick-entry-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.quick-entry-buttons {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.quick-entry-btn {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 16px 28px;
  border-radius: var(--radius-xl);
  font-size: var(--text-lg);
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-normal);
  border: 2px solid transparent;
  font-family: var(--font-sans);
  min-width: 160px;
  justify-content: center;
}

.quick-entry-btn.primary {
  background: var(--primary-gradient);
  color: white;
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
}

.quick-entry-btn.primary:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 28px rgba(37, 99, 235, 0.5);
}

.quick-entry-btn.secondary {
  background: var(--bg-primary);
  color: var(--primary-700);
  border: 2px solid var(--primary-300);
  box-shadow: var(--shadow-sm);
}

.quick-entry-btn.secondary:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.25);
  border-color: var(--primary-500);
  background: var(--primary-50);
}

.btn-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.case-info {
  font-size: var(--text-xs);
  opacity: 0.9;
  background: rgba(255, 255, 255, 0.2);
  padding: 3px 10px;
  border-radius: var(--radius-full);
  margin-left: auto;
}

[data-theme="dark"] .case-info {
  background: rgba(255, 255, 255, 0.15);
}

.current-case-status {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-top: var(--space-4);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
}

.status-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
}

.status-label {
  color: var(--text-secondary);
  font-weight: 500;
}

.status-value {
  color: var(--text-primary);
  font-weight: 600;
  background: var(--primary-soft);
  padding: 3px 10px;
  border-radius: var(--radius-md);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-5);
  margin-bottom: var(--space-8);
}

.stat-card {
  position: relative;
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  padding: var(--space-6);
  overflow: hidden;
  transition: all var(--transition-normal);
  border: 1px solid var(--border-light);
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}

.stat-card-bg {
  position: absolute;
  inset: 0;
  opacity: 0.5;
  transition: opacity var(--transition-normal);
}

.stat-card:hover .stat-card-bg {
  opacity: 0.8;
}

.card-blue .stat-card-bg { background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); }
.card-green .stat-card-bg { background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); }
.card-orange .stat-card-bg { background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); }
.card-purple .stat-card-bg { background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%); }

[data-theme="dark"] .card-blue .stat-card-bg { background: linear-gradient(135deg, rgba(59, 130, 246, 0.12) 0%, rgba(59, 130, 246, 0.04) 100%); }
[data-theme="dark"] .card-green .stat-card-bg { background: linear-gradient(135deg, rgba(34, 197, 94, 0.12) 0%, rgba(34, 197, 94, 0.04) 100%); }
[data-theme="dark"] .card-orange .stat-card-bg { background: linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(245, 158, 11, 0.04) 100%); }
[data-theme="dark"] .card-purple .stat-card-bg { background: linear-gradient(135deg, rgba(139, 92, 246, 0.12) 0%, rgba(139, 92, 246, 0.04) 100%); }

.stat-card-glow {
  position: absolute;
  top: -50%;
  right: -50%;
  width: 100%;
  height: 100%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.25) 0%, transparent 70%);
  opacity: 0;
  transition: opacity var(--transition-normal);
}

.stat-card:hover .stat-card-glow { opacity: 1; }

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  position: relative;
  z-index: 2;
}

.stat-info { flex: 1; }

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: var(--space-2);
  display: block;
}

.stat-value-wrapper {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.stat-value {
  font-size: 32px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: -0.03em;
}

.stat-unit {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: transform var(--transition-normal);
}

.stat-card:hover .stat-icon { transform: scale(1.08) rotate(3deg); }

.stat-icon span {
  width: 22px;
  height: 22px;
  position: relative;
  z-index: 2;
}

.icon-blue { background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%); color: white; box-shadow: 0 3px 10px rgba(59, 130, 246, 0.3); }
.icon-green { background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: white; box-shadow: 0 3px 10px rgba(34, 197, 94, 0.3); }
.icon-orange { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; box-shadow: 0 3px 10px rgba(245, 158, 11, 0.3); }
.icon-purple { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: white; box-shadow: 0 3px 10px rgba(139, 92, 246, 0.3); }

.stat-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-4);
  position: relative;
  z-index: 2;
}

.stat-change {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: var(--text-xs);
  font-weight: 600;
}

.stat-change.positive { color: var(--success); }
.stat-change.negative { color: var(--danger); }

.change-icon { width: 13px; height: 13px; }
.stat-period { font-size: 11px; color: var(--text-muted); }

.stat-sparkline {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 36px;
  opacity: 0.25;
  z-index: 1;
}

.card-blue .stat-sparkline { color: #3b82f6; }
.card-green .stat-sparkline { color: #22c55e; }
.card-orange .stat-sparkline { color: #f59e0b; }
.card-purple .stat-sparkline { color: #8b5cf6; }

.stat-sparkline svg { width: 100%; height: 100%; }

.content-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: var(--space-6);
}

.section-card {
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  padding: var(--space-6);
  border: 1px solid var(--border-light);
  transition: all var(--transition-normal);
}

.section-card:hover { box-shadow: var(--shadow-md); }

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
}

.section-title-wrapper {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.section-icon {
  width: 34px;
  height: 34px;
  background: var(--primary-gradient);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  padding: 7px;
}

.section-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.section-action {
  display: flex;
  align-items: center;
  gap: 3px;
  background: transparent;
  border: none;
  color: var(--primary);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  padding: 6px 14px;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.section-action:hover { background: var(--primary-soft); }
.section-action svg { width: 14px; height: 14px; }

.table-container { overflow-x: auto; }

.data-table { width: 100%; border-collapse: collapse; }

.data-table th {
  text-align: left;
  padding: 10px 14px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-light);
}

.data-table th:nth-child(3) {
  width: 140px;
}

.data-table td {
  padding: 14px;
  font-size: var(--text-sm);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-light);
}

.data-table td:nth-child(3) {
  width: 140px;
}

.data-table tr:last-child td { border-bottom: none; }
.data-table tbody tr { transition: background var(--transition-fast); }
.data-table tbody tr:hover { background: var(--primary-soft); }

.case-id { font-weight: 600; color: var(--primary); }

.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 6px 16px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  min-width: 90px;
}

.badge-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.badge-orange { background: rgba(245, 158, 11, 0.1); color: var(--warning-500); }
.badge-blue { background: rgba(59, 130, 246, 0.1); color: var(--primary); }
.badge-green { background: rgba(34, 197, 94, 0.1); color: var(--success); }
.badge-gray { background: rgba(107, 114, 128, 0.1); color: var(--text-muted); }

.location-cell { display: flex; align-items: center; gap: 5px; }
.location-icon { width: 13px; height: 13px; color: var(--text-muted); flex-shrink: 0; }

.action-buttons { display: flex; gap: var(--space-2); }

.action-btn {
  width: 30px;
  height: 30px;
  border: none;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.action-btn span { width: 14px; height: 14px; color: var(--text-secondary); }
.action-btn:hover { background: var(--primary); }
.action-btn:hover span { color: white; }
.action-btn.continue { background: rgba(34, 197, 94, 0.1); }
.action-btn.continue span { color: var(--success); }
.action-btn.continue:hover { background: var(--success); }
.action-btn.continue:hover span { color: white; }

.tasks-list { display: flex; flex-direction: column; gap: var(--space-4); }

.task-card {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.04) 0%, rgba(139, 92, 246, 0.02) 100%);
  border: 1px solid rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  transition: all var(--transition-normal);
}

.task-card:hover {
  border-color: var(--primary-400);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.12);
  transform: translateX(3px);
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
}

.task-id { font-size: 11px; color: var(--text-muted); font-weight: 500; }

.priority-badge { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: var(--radius-full); }
.priority-high { background: rgba(239, 68, 68, 0.1); color: var(--danger-500); }
.priority-medium { background: rgba(245, 158, 11, 0.1); color: var(--warning-500); }
.priority-low { background: rgba(59, 130, 246, 0.1); color: var(--primary); }

.task-title { font-size: var(--text-base); font-weight: 600; color: var(--text-primary); margin-bottom: var(--space-3); }

.task-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.task-type { display: flex; align-items: center; gap: 5px; }
.type-dot { width: 5px; height: 5px; background: var(--primary); border-radius: 50%; }

.task-deadline { display: flex; align-items: center; gap: 3px; }
.task-deadline svg { width: 13px; height: 13px; }

.task-actions { display: flex; gap: var(--space-2); }

.task-btn {
  flex: 1;
  padding: 8px 14px;
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.task-btn.primary {
  background: var(--primary-gradient);
  color: white;
  border: none;
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
}

.task-btn.primary:hover { transform: translateY(-1px); box-shadow: 0 3px 10px rgba(37, 99, 235, 0.35); }

.task-btn.secondary {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
}

.task-btn.secondary:hover { background: var(--bg-secondary); color: var(--text-primary); }

.cases-pagination, .tasks-pagination, .pagination-buttons {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-4);
}

.pagination-info { color: var(--text-secondary); font-size: var(--text-xs); }

.page-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  cursor: pointer;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-xs);
  font-weight: 500;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.page-btn:hover:not(:disabled) {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary-300);
}

.page-btn.active {
  background: var(--primary-gradient);
  color: white;
  border-color: transparent;
}

.page-btn:disabled { opacity: 0.45; cursor: not-allowed; }

@media (max-width: 1200px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .content-grid { grid-template-columns: 1fr; }
}

@media (max-width: 768px) {
  .stats-grid { grid-template-columns: 1fr; }
  .page-header { flex-direction: column; align-items: stretch; }
  .header-actions { margin-top: var(--space-4); }
  .cases-pagination, .tasks-pagination { align-items: flex-start; flex-direction: column; }
  .pagination-buttons { width: 100%; justify-content: center; }
}
</style>
