<template>
  <div class="work-queue-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">工作队列</h1>
        <p class="page-subtitle">待处理的事故案件</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goToHistoryCases">
          <span class="btn-icon" v-html="icons.folder"></span>
          历史案例
        </button>
      </div>
    </div>
    <div class="queue-container">
      <div class="queue-stats">
        <div class="stat-card" v-for="card in stats" :key="card.label">
          <div class="stat-icon" :class="card.iconClass">
            <span v-html="card.icon"></span>
          </div>
          <div class="stat-info">
            <div class="stat-number">{{ card.value }}</div>
            <div class="stat-label">{{ card.label }}</div>
          </div>
        </div>
      </div>
      <div class="queue-filter">
        <div class="filter-buttons">
          <button v-for="item in filters" :key="item" class="filter-btn" :class="{ active: activeFilter===item }" @click="activeFilter=item">
            {{ item }}
          </button>
        </div>
      </div>
      <div class="queue-list card-surface">
        <div class="list-header">
          <h2 class="section-title">案件列表</h2>
        </div>
        <div v-if="loading" class="queue-items">
          <div class="empty-state">
            <p class="empty-text">正在加载案例数据...</p>
          </div>
        </div>
        <div class="queue-items" v-else>
          <div class="queue-item" v-for="item in pagedCases" :key="item.id">
            <div class="queue-item-header">
              <div>
                <h4 class="item-title">
                  <span class="case-id-badge">{{ item.id }}</span>
                </h4>
                <p class="item-subtitle">{{ item.type }} - {{ item.location }}</p>
              </div>
              <div class="item-status" :class="statusClass(item.status)">
                <span class="status-dot"></span>
                {{ item.status }}
              </div>
            </div>
            <div class="queue-item-body">
              <div class="item-meta">
                <span class="meta-item">
                  <span class="meta-icon" v-html="icons.clock"></span>
                  提交时间: {{ item.submittedAt }}
                </span>
                <span class="meta-item">
                  <span class="meta-icon" v-html="icons.user"></span>
                  {{ item.status==='处理中' ? `处理人: ${item.reviewer || '张警官'}` : `预计处理时间: ${item.eta}` }}
                </span>
              </div>
              <div class="item-actions">
                <button class="action-btn process-btn" @click="processCase(item)">
                  <span v-html="icons.play"></span>
                  开始处理
                </button>
                <button class="action-btn details-btn" @click="openCase(item)">
                  <span v-html="icons.eye"></span>
                  查看详情
                </button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="filteredCases.length === 0" class="empty-state">
          <div class="empty-icon" v-html="icons.folder"></div>
          <p class="empty-text">暂无案件</p>
        </div>
      </div>
      <div class="queue-pagination">
        <div class="pagination-info">显示 {{ startIndex + 1 }}-{{ Math.min(startIndex + pageSize, filteredCases.length) }} 条，共 {{ filteredCases.length }} 条</div>
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
    <div v-if="selectedCase" class="modal-mask" @click.self="selectedCase=null">
      <div class="modal-card">
        <div class="modal-header">
          <h3 class="modal-title">
            <span class="modal-icon" v-html="icons.folder"></span>
            {{ selectedCase.id }}
          </h3>
          <button class="modal-close" @click="selectedCase=null" title="关闭">
            <span v-html="icons.close"></span>
          </button>
        </div>
        <div class="modal-body">
          <div class="info-row">
            <span class="info-label">事故类型</span>
            <span class="info-value">{{ selectedCase.type }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">地点</span>
            <span class="info-value">{{ selectedCase.location }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <select v-model="editingStatus" class="status-select">
                <option v-for="status in ['待分析', '待复核', '已完成']" :key="status" :value="status">{{ status }}</option>
              </select>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">提交时间</span>
            <span class="info-value">{{ selectedCase.submittedAt }}</span>
          </div>
          <div class="info-row full">
            <span class="info-label">说明</span>
            <span class="info-value">{{ selectedCase.description || '无' }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="selectedCase=null">
            <span class="btn-icon" v-html="icons.close"></span>
            关闭
          </button>
          <button class="btn btn-primary" @click="saveStatus">
            <span class="btn-icon" v-html="icons.check"></span>
            保存
          </button>
        </div>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import NavigationButtons from '../components/NavigationButtons.vue'

const router = useRouter()

const icons = {
  clock: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" fill-opacity="0.2"/><polyline points="12 6 12 12 16 14" fill="none" stroke-width="2"/></svg>`,
  user: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" fill="none" stroke-width="2"/><circle cx="12" cy="7" r="4" fill-opacity="0.2"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3" fill-opacity="0.2"/></svg>`,
  eye: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill-opacity="0.2"/></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
  chevronLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>`,
  chevronRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`
}

const { state, resetFlow, setCurrentCase } = useAccidentFlow()

const filters = ['全部', '待分析', '待复核', '已完成']
const activeFilter = ref('全部')
const selectedCase = ref(null)
const editingStatus = ref('')
const page = ref(1)
const pageSize = 5
const cases = ref([])
const loading = ref(false)

// 从后端 API 获取真实案例列表
async function fetchCases() {
  loading.value = true
  try {
    const token = localStorage.getItem('auth-token')
    const res = await fetch('/api/cases?limit=200', {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const json = await res.json()
    if (json.success && Array.isArray(json.data)) {
      cases.value = json.data
    }
  } catch (e) {
    console.error('[WorkQueue] 获取案例列表失败:', e)
    notify({ title: '数据加载失败', message: '无法从服务器获取案例列表，请检查后端服务。' })
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchCases()
})

// 切换筛选条件时回到第一页
watch(activeFilter, () => {
  page.value = 1
})

// 将后端案例数据映射为工作队列展示所需的格式
function mapCaseToWorkItem(c) {
  const status = c.status || '待分析'
  let eta = '已归档'
  if (status === '待分析') eta = '30分钟'
  else if (status === '待复核' || status === '复核中') eta = '1小时'
  else if (status === '处理中') eta = '15分钟'

  return {
    id: c.id,
    type: c.title || c.accident_type || '未命名案件',
    location: c.location || '未记录',
    status,
    submittedAt: c.submitted_at || c.created_at || '',
    description: c.description || '',
    eta,
    priority: c.priority || '中',
    weather: c.weather || '',
    roadEnv: c.road_env || ''
  }
}

const workItems = computed(() => cases.value.map(mapCaseToWorkItem))

const filteredCases = computed(() => {
  if (activeFilter.value === '全部') return workItems.value
  return workItems.value.filter((item) => item.status === activeFilter.value)
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredCases.value.length / pageSize)))

const displayPages = computed(() => {
  const pages = []
  const start = Math.max(1, page.value - 2)
  const end = Math.min(totalPages.value, start + 4)
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
})

const startIndex = computed(() => (page.value - 1) * pageSize)
const pagedCases = computed(() => filteredCases.value.slice(startIndex.value, startIndex.value + pageSize))

const stats = computed(() => [
  { label: '待分析', value: workItems.value.filter((i) => i.status === '待分析').length, iconClass: 'icon-orange', icon: icons.clock },
  { label: '待复核', value: workItems.value.filter((i) => i.status === '待复核' || i.status === '复核中').length, iconClass: 'icon-blue', icon: icons.user },
  { label: '已完成', value: workItems.value.filter((i) => i.status === '已完成').length, iconClass: 'icon-green', icon: icons.check },
  { label: '处理率', value: `${workItems.value.length ? Math.round(workItems.value.filter((i) => i.status === '已完成').length / workItems.value.length * 100) : 0}%`, iconClass: 'icon-purple', icon: icons.folder }
])

const openCase = (item) => {
  selectedCase.value = item
  editingStatus.value = item.status
}

const processCase = (item) => {
  notify({ title: '开始处理', message: `正在处理案件 ${item.id}` })

  // 设置当前案件 ID，后续页面可通过 getCurrentCase() 获取
  setCurrentCase(item.id)

  // 根据案件状态跳转到对应的处理页面
  if (item.status === '待分析') {
    router.push('/intelligent-analysis')
  } else if (item.status === '待复核' || item.status === '复核中') {
    router.push('/manual-review')
  } else {
    router.push('/accident-entry')
  }
}

const saveStatus = async () => {
  if (!selectedCase.value) return

  const caseId = selectedCase.value.id
  const newStatus = editingStatus.value

  try {
    const token = localStorage.getItem('auth-token')
    const res = await fetch(`/api/cases/${caseId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify({ status: newStatus })
    })

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${res.status}`)
    }

    // 更新本地缓存
    const idx = cases.value.findIndex(c => c.id === caseId)
    if (idx !== -1) {
      cases.value[idx] = { ...cases.value[idx], status: newStatus }
    }

    notify({ title: '状态已更新', message: `${caseId} 状态已变更为 ${newStatus}。` })
  } catch (e) {
    console.error('[WorkQueue] 更新案件状态失败:', e)
    notify({ title: '更新失败', message: `无法更新 ${caseId} 的状态: ${e.message}` })
  }

  selectedCase.value = null
}

const statusClass = (status) => {
  const map = {
    '待分析': 'status-pending',
    '待复核': 'status-processing',
    '复核中': 'status-processing',
    '已完成': 'status-done'
  }
  return map[status] || 'status-default'
}

const goToHistoryCases = () => {
  router.push('/history-cases')
}
</script>

<style scoped>
.work-queue-page,
.queue-container,
.queue-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.work-queue-page {
  animation: pageIn 0.4s var(--ease-default);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
  margin-bottom: var(--space-8);
}

.header-content { flex: 1; }

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

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 9px 18px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 500;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.btn-icon { width: 15px; height: 15px; }

.btn-primary {
  background: var(--primary-gradient);
  color: white;
  border: none;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.btn-primary:hover {
  background: var(--primary-gradient-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.btn-secondary:hover {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary-300);
  transform: translateY(-1px);
}

.queue-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-5);
}

.stat-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  padding: var(--space-6);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  transition: all var(--transition-normal);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
  border-color: var(--primary-200);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform var(--transition-normal);
}

.stat-icon span { width: 22px; height: 22px; }

.stat-card:hover .stat-icon { transform: scale(1.08) rotate(3deg); }

.icon-orange { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; box-shadow: 0 3px 10px rgba(245, 158, 11, 0.3); }
.icon-blue { background: var(--primary-gradient); color: white; box-shadow: 0 3px 10px rgba(59, 130, 246, 0.3); }
.icon-green { background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: white; box-shadow: 0 3px 10px rgba(34, 197, 94, 0.3); }
.icon-purple { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: white; box-shadow: 0 3px 10px rgba(139, 92, 246, 0.3); }

.stat-info { flex: 1; }

.stat-number {
  font-size: 32px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  margin-bottom: var(--space-1);
  letter-spacing: -0.03em;
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 500;
}

.card-surface,
.queue-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-normal);
}

.card-surface:hover,
.queue-item:hover { box-shadow: var(--shadow-md); }

.queue-filter { display: flex; justify-content: flex-start; }

.filter-buttons,
.item-actions,
.item-meta {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.filter-btn,
.action-btn {
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
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
}

.filter-btn:hover,
.action-btn:hover {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary-300);
  transform: translateY(-1px);
}

.filter-btn.active {
  background: var(--primary-gradient);
  color: #fff;
  border: none;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.filter-btn.active:hover {
  background: var(--primary-gradient-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.filter-btn span,
.action-btn span { width: 13px; height: 13px; }

.list-header {
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border-light);
}

.section-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.queue-items {
  padding: var(--space-5) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.queue-item {
  padding: var(--space-5);
  transition: all var(--transition-normal);
}

.queue-item:hover {
  transform: translateX(3px);
  border-color: var(--primary-200);
}

.queue-item-header,
.queue-item-body {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  align-items: center;
  flex-wrap: wrap;
}

.queue-item-header { margin-bottom: var(--space-3); }

.case-id-badge {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 3px 10px;
  border-radius: var(--radius-md);
}

.item-title { color: var(--text-primary); margin-bottom: 3px; }

.item-subtitle,
.meta-item {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.meta-item { display: flex; align-items: center; gap: 5px; }

.meta-icon { width: 14px; height: 14px; color: var(--text-muted); }

.item-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  font-weight: 600;
  font-size: 11px;
}

.status-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }

.status-pending { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
.status-processing { background: var(--primary-soft); color: var(--primary); }
.status-done { background: rgba(34, 197, 94, 0.1); color: #22c55e; }

.details-btn { color: var(--primary); border-color: var(--primary); }
.details-btn:hover { background: var(--primary); color: white; }

.empty-state { padding: 48px var(--space-6); text-align: center; }
.empty-icon { width: 60px; height: 60px; margin: 0 auto var(--space-4); color: var(--text-muted); opacity: 0.5; }
.empty-text { color: var(--text-muted); font-size: var(--text-sm); }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(3, 10, 20, 0.55);
  display: grid;
  place-items: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.modal-card {
  width: min(520px, calc(100vw - 48px));
  background: var(--bg-primary);
  padding: 0;
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-2xl);
  overflow: hidden;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border-light);
}

.modal-title {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.modal-icon { width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; color: var(--primary); }

.modal-close {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.modal-close:hover { background: var(--bg-secondary); color: var(--text-primary); }
.modal-close span { width: 16px; height: 16px; }

.modal-body { padding: var(--space-6); }

.info-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-light);
}

.info-row:last-child { border-bottom: none; }
.info-row.full { flex-direction: column; gap: var(--space-2); }

.info-label { min-width: 80px; color: var(--text-secondary); font-size: var(--text-xs); font-weight: 500; }
.info-value { flex: 1; color: var(--text-primary); font-size: var(--text-sm); }

.status-select {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--transition-fast);
  outline: none;
}

.status-select:hover { border-color: var(--primary-300); }

.status-select:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: 9px 18px;
  font-size: var(--text-sm);
  font-weight: 600;
  border: none;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
  white-space: nowrap;
  font-family: var(--font-sans);
}

.btn-icon { width: 15px; height: 15px; }

.btn-primary {
  background: var(--primary-gradient);
  color: white;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.btn-primary:hover {
  background: var(--primary-gradient-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-light);
}

.btn-secondary:hover {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary-300);
  transform: translateY(-1px);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border-light);
}

.queue-pagination,
.pagination-buttons {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-4);
}

.pagination-info { color: var(--text-secondary); font-size: var(--text-sm); }

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
  font-size: var(--text-sm);
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

@media (max-width: 768px) {
  .queue-stats { grid-template-columns: repeat(2, 1fr); }
  .item-actions { width: 100%; }
  .action-btn { flex: 1; }
}

@media (max-width: 480px) {
  .queue-stats { grid-template-columns: 1fr; }
  .queue-item-header, .queue-item-body { flex-direction: column; align-items: flex-start; }
}
</style>
