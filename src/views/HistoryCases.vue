<template>
  <div class="history-cases-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">历史案例</h1>
        <p class="page-subtitle">案例查询与快速查看</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goToWorkQueue">
          <span class="btn-icon" v-html="icons.clock"></span>
          工作队列
        </button>
        <button class="btn btn-secondary" @click="refreshCases">
          <span class="btn-icon" v-html="icons.refresh"></span>
          刷新
        </button>
      </div>
    </div>
    <div class="cases-container">
      <div class="cases-search card-surface">
        <div class="search-filters">
          <div class="search-input-wrapper">
            <span class="search-icon" v-html="icons.search"></span>
            <input v-model.trim="keyword" class="search-input" placeholder="搜索案件编号、地点或事故类型">
          </div>
          <select v-model="statusFilter" class="filter-select">
            <option value="全部">全部状态</option>
            <option>待处理</option>
            <option>待分析</option>
            <option>处理中</option>
            <option>待复核</option>
            <option>已完成</option>
            <option>已归档</option>
          </select>
          <select v-model="priorityFilter" class="filter-select">
            <option value="全部">全部优先级</option>
            <option>高</option>
            <option>中</option>
            <option>低</option>
          </select>
          <button class="btn btn-secondary" @click="resetFilters">
            <span class="btn-icon" v-html="icons.refresh"></span>
            重置
          </button>
        </div>
      </div>
      <div class="cases-table card-surface">
        <table>
          <thead>
            <tr>
              <th>案件编号</th>
              <th>事故类型</th>
              <th>发生地点</th>
              <th>提交时间</th>
              <th>处理状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in pagedCases" :key="item.caseId">
              <td><span class="case-id-badge">{{ item.caseId }}</span></td>
              <td><span class="type-tag">{{ item.title || item.accident_type || '未命名' }}</span></td>
              <td>
                <span class="location-text">
                  <span class="location-icon" v-html="icons.mapPin"></span>
                  {{ item.location || '未记录' }}
                </span>
              </td>
              <td>{{ item.archivedAt }}</td>
              <td>
                <span class="status-badge" :class="getStatusClass(item.status)">
                  <span class="status-dot"></span>
                  {{ item.status }}
                </span>
              </td>
              <td>
                <div class="action-buttons">
                  <button class="action-btn view-btn" @click="viewCase(item)" title="查看详情">
                    <span v-html="icons.eye"></span>
                  </button>
                  <button v-if="item.status !== '已完成' && item.status !== '已归档'" 
                          class="action-btn continue-btn" 
                          @click="continueCase(item)" 
                          title="继续处理">
                    <span v-html="icons.play"></span>
                  </button>
                  <button class="action-btn edit-btn" @click="editCase(item)" title="编辑">
                    <span v-html="icons.edit"></span>
                  </button>
                  <button class="action-btn delete-btn" @click="deleteCase(item)" title="删除">
                    <span v-html="icons.trash"></span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="filteredCases.length === 0" class="empty-state">
          <div class="empty-icon" v-html="icons.folder"></div>
          <p class="empty-text">暂无匹配的案例</p>
        </div>
      </div>
      <div class="cases-pagination">
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
    <div v-if="selectedCase && !showEditModal" class="modal-mask" @click.self="selectedCase=null">
      <div class="modal-card">
        <div class="modal-header">
          <h3 class="modal-title">
            <span class="modal-icon" v-html="icons.folder"></span>
            {{ selectedCase.caseId }}
          </h3>
          <button class="modal-close" @click="selectedCase=null" title="关闭">
            <span v-html="icons.close"></span>
          </button>
        </div>
        <div class="modal-body">
          <div class="info-row">
            <span class="info-label">事故类型</span>
            <span class="info-value">{{ selectedCase.title }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">地点</span>
            <span class="info-value">{{ selectedCase.location || '未记录' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <span class="status-badge" :class="getStatusClass(selectedCase.status)">
                <span class="status-dot"></span>
                {{ selectedCase.status }}
              </span>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">归档时间</span>
            <span class="info-value">{{ selectedCase.archivedAt }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">处理流程</span>
            <span class="info-value">{{ selectedCase.route || '未记录' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">证据来源</span>
            <span class="info-value">{{ selectedCase.source || '未记录' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">优先级</span>
            <span class="info-value">{{ selectedCase.priority || '中' }}</span>
          </div>
          <div class="info-row full">
            <span class="info-label">备注</span>
            <span class="info-value">{{ selectedCase.note || '无备注' }}</span>
          </div>
          <div class="info-row full">
            <span class="info-label">结论</span>
            <span class="info-value">{{ selectedCase.conclusion }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="selectedCase=null">
            <span class="btn-icon" v-html="icons.close"></span>
            关闭
          </button>
          <button class="btn btn-primary" @click="editCase(selectedCase)">
            <span class="btn-icon" v-html="icons.edit"></span>
            编辑
          </button>
        </div>
      </div>
    </div>
    <div v-if="showEditModal && editingCase" class="modal-mask" @click.self="showEditModal=false">
      <div class="modal-card edit-modal">
        <div class="modal-header">
          <h3 class="modal-title">
            <span class="modal-icon" v-html="icons.edit"></span>
            编辑案件 - {{ editingCase.caseId }}
          </h3>
          <button class="modal-close" @click="cancelEdit" title="关闭">
            <span v-html="icons.close"></span>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">案件编号</label>
              <input v-model.trim="editForm.caseId" class="form-input" disabled placeholder="自动生成">
            </div>
            <div class="form-group">
              <label class="form-label">事故类型</label>
              <input v-model.trim="editForm.title" class="form-input" placeholder="追尾事故、变道事故等">
            </div>
            <div class="form-group">
              <label class="form-label">发生地点</label>
              <input v-model.trim="editForm.location" class="form-input" placeholder="省市区街道">
            </div>
            <div class="form-group">
              <label class="form-label">处理状态</label>
              <select v-model="editForm.status" class="form-select">
                <option>待处理</option>
                <option>处理中</option>
                <option>已完成</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">优先级</label>
              <select v-model="editForm.priority" class="form-select">
                <option>高</option>
                <option>中</option>
                <option>低</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">归档时间</label>
              <input v-model.trim="editForm.archivedAt" class="form-input" placeholder="2024-01-01 12:00:00">
            </div>
            <div class="form-group full">
              <label class="form-label">备注</label>
              <textarea v-model.trim="editForm.note" class="form-textarea" placeholder="案件备注信息..."></textarea>
            </div>
            <div class="form-group full">
              <label class="form-label">结论</label>
              <textarea v-model.trim="editForm.conclusion" class="form-textarea" placeholder="案件最终结论..."></textarea>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="cancelEdit">
            <span class="btn-icon" v-html="icons.close"></span>
            取消
          </button>
          <button class="btn btn-primary" @click="saveEdit">
            <span class="btn-icon" v-html="icons.save"></span>
            保存
          </button>
        </div>
      </div>
    </div>
    <div v-if="showDeleteConfirm" class="modal-mask" @click.self="showDeleteConfirm=false">
      <div class="modal-card delete-modal">
        <div class="modal-header">
          <h3 class="modal-title">
            <span class="modal-icon danger" v-html="icons.warning"></span>
            确认删除
          </h3>
        </div>
        <div class="modal-body">
          <p class="delete-message">确定要删除案件 <strong>{{ caseToDelete?.caseId }}</strong> 吗？此操作无法撤销。</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showDeleteConfirm=false">
            <span class="btn-icon" v-html="icons.close"></span>
            取消
          </button>
          <button class="btn btn-danger" @click="confirmDelete">
            <span class="btn-icon" v-html="icons.trash"></span>
            确认删除
          </button>
        </div>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import { CasesAPI, StatsAPI } from '../api/index.js'
import NavigationButtons from '../components/NavigationButtons.vue'

const route = useRoute()
const router = useRouter()

const icons = {
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill-opacity="0.2"/></svg>`,
  eye: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
  chevronLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>`,
  chevronRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`,
  warning: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" fill-opacity="0.2"/><line x1="12" y1="9" x2="12" y2="13" fill="none" stroke-width="2"/><circle cx="12" cy="17" r="1"/></svg>`,
  mapPin: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" fill-opacity="0.2"/><circle cx="12" cy="10" r="3"/></svg>`,
  save: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" fill-opacity="0.2"/><polyline points="17 21 17 13 7 13 7 21" fill="none"/><polyline points="7 3 7 8 15 8" fill="none"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3" fill-opacity="0.2"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8" fill-opacity="0.2"/><polyline points="12 6 12 12 16 14" fill="none" stroke-width="2"/></svg>`
}

const { state, resetFlow, updateArchivedCase, deleteArchivedCase } = useAccidentFlow()

const keyword = ref('')
const statusFilter = ref('全部')
const priorityFilter = ref('全部')
const page = ref(1)
const pageSize = 5
const selectedCase = ref(null)
const showDeleteConfirm = ref(false)
const caseToDelete = ref(null)
const showEditModal = ref(false)
const editingCase = ref(null)
const allCases = ref([])  // 从API获取的案件列表
const loading = ref(false)

const editForm = reactive({
  caseId: '',
  title: '',
  location: '',
  status: '',
  archivedAt: '',
  priority: '中',
  note: '',
  conclusion: ''
})

// 从后端获取历史案件
async function fetchHistoryCases() {
  loading.value = true
  try {
    const result = await StatsAPI.getHistoryCases({ limit: 100 })
    if (result.success && Array.isArray(result.data)) {
      allCases.value = result.data.map(c => ({
        caseId: c.id,
        title: c.title || c.accident_type || '未命名案件',
        accident_type: c.accident_type,
        location: c.location || '未记录',
        status: c.status || '待处理',
        archivedAt: c.submitted_at || c.created_at || '--',
        conclusion: '',
        source: '',
        note: '',
        route: '',
        priority: c.priority || '中',
        description: c.description || ''
      }))
    }
  } catch (err) {
    console.warn('获取历史案件失败:', err)
    allCases.value = []
  } finally {
    loading.value = false
  }
}

// 合并本地store中的案件（当前正在处理的）
const cases = computed(() => {
  const apiCases = [...allCases.value]
  // 如果当前案件未归档，添加到列表头部
  if (state.step !== 'overview' && state.step !== 'archived') {
    const currentCase = {
      caseId: state.caseId,
      title: state.form.accidentType || '未命名案件',
      location: state.form.location,
      status: state.step === 'accident-entry' || state.step === 'video-processing' ? '待分析' : '处理中',
      archivedAt: new Date().toLocaleString(),
      conclusion: state.recommendation.summary || '待处理',
      source: state.form.fileType || '未上传',
      note: state.manualReview.note || '无备注',
      route: '录入 → 视频处理 → 智能分析 → 责任建议 → 规则依据 → 人工复核',
      priority: state.analysis.riskLevel || '中',
      description: ''
    }
    apiCases.unshift(currentCase)
  }
  return apiCases
})

const filteredCases = computed(() => cases.value.filter((item) => {
  const matchKeyword = !keyword.value || [item.caseId, item.title, item.location].some((value) => value?.toLowerCase().includes(keyword.value.toLowerCase()))
  const matchStatus = statusFilter.value === '全部' || item.status === statusFilter.value
  const matchPriority = priorityFilter.value === '全部' || (item.priority || '中') === priorityFilter.value
  return matchKeyword && matchStatus && matchPriority
}))

// 监听筛选变化，自动返回第一页
watch([keyword, statusFilter, priorityFilter], () => {
  page.value = 1
})

const resetFilters = () => {
  keyword.value = ''
  statusFilter.value = '全部'
  priorityFilter.value = '全部'
  page.value = 1
}

const totalPages = computed(() => Math.max(1, Math.ceil(filteredCases.value.length / pageSize)))

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
const pagedCases = computed(() => filteredCases.value.slice(startIndex.value, startIndex.value + pageSize))

const getStatusClass = (status) => {
  const map = {
    '待处理': 'status-pending',
    '处理中': 'status-processing',
    '已完成': 'status-completed',
    '待分析': 'status-pending',
    '待复核': 'status-processing',
    '已归档': 'status-archived'
  }
  return map[status] || 'status-default'
}

const viewCase = (item) => {
  selectedCase.value = item
  showEditModal.value = false
}

const continueCase = (item) => {
  notify({ title: '继续处理', message: `正在加载案件 ${item.caseId}` })
  const status = item.status
  let targetPath = '/accident-entry'
  if (status === '待分析') {
    targetPath = '/intelligent-analysis'
  } else if (status === '待复核') {
    targetPath = '/manual-review'
  }
  router.push({ path: targetPath, query: { caseId: String(item.caseId) } })
}

const goToWorkQueue = () => {
  router.push('/work-queue')
}

const editCase = (item) => {
  editingCase.value = { ...item }
  editForm.caseId = item.caseId
  editForm.title = item.title || item.accident_type || ''
  editForm.location = item.location || ''
  editForm.status = item.status || '处理中'
  editForm.archivedAt = item.archivedAt || ''
  editForm.priority = item.priority || '中'
  editForm.note = item.note || ''
  editForm.conclusion = item.conclusion || ''
  selectedCase.value = null
  showEditModal.value = true
}

const cancelEdit = () => {
  showEditModal.value = false
  editingCase.value = null
}

const saveEdit = async () => {
  if (!editForm.title && !editForm.caseId) {
    notify({ title: '保存失败', message: '请至少填写案件编号或事故类型', type: 'warning' })
    return
  }

  const caseId = String(editingCase.value.caseId)
  const updates = {
    title: editForm.title || '未命名案件',
    location: editForm.location || '未记录',
    status: editForm.status,
    priority: editForm.priority,
  }
  
  console.log('[saveEdit] caseId:', caseId, 'updates:', updates)

  try {
    const result = await CasesAPI.update(caseId, updates)
    console.log('[saveEdit] Result:', result)
    if (result.success) {
      notify({ title: '保存成功', message: `案件 ${caseId} 已更新`, type: 'success' })
      await fetchHistoryCases()
    } else {
      notify({ title: '保存失败', message: result.message || '后端返回异常', type: 'error' })
    }
  } catch (err) {
    console.error('[saveEdit] Error:', err)
    notify({ title: '保存失败', message: err.message || '网络错误', type: 'error' })
  }

  showEditModal.value = false
  editingCase.value = null
}

const deleteCase = (item) => {
  caseToDelete.value = item
  showDeleteConfirm.value = true
}

const confirmDelete = async () => {
  if (caseToDelete.value) {
    try {
      await CasesAPI.delete(caseToDelete.value.caseId)
      notify({ title: '删除成功', message: `案件 ${caseToDelete.value.caseId} 已删除`, type: 'success' })
      await fetchHistoryCases()
    } catch (err) {
      // Fallback to store
      const success = deleteArchivedCase(caseToDelete.value.caseId)
      if (success) notify({ title: '删除成功', message: `案件已删除`, type: 'success' })
    }
    showDeleteConfirm.value = false
    caseToDelete.value = null
    if (page.value > totalPages.value) {
      page.value = totalPages.value
    }
  }
}

const refreshCases = async () => {
  keyword.value = ''
  statusFilter.value = '全部'
  page.value = 1
  await fetchHistoryCases()
  notify({ title: '刷新成功', message: '案例列表已更新', type: 'success' })
}

// 页面加载时获取数据并处理路由参数
onMounted(async () => {
  await fetchHistoryCases()
  const { caseId, edit } = route.query
  if (caseId) {
    const targetCase = cases.value.find(c => c.caseId === caseId)
    if (targetCase) {
      if (edit === 'true') {
        editCase(targetCase)
      } else {
        viewCase(targetCase)
      }
    }
  }
})
</script>

<style scoped>
.history-cases-page, .cases-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.history-cases-page {
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
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 400;
}

.header-actions { display: flex; gap: var(--space-3); }

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 9px 18px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 600;
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

.btn-danger {
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
  color: white;
  border: none;
  box-shadow: 0 2px 8px rgba(220, 38, 38, 0.25);
}

.btn-danger:hover {
  background: linear-gradient(135deg, #b91c1c 0%, #991b1b 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(220, 38, 38, 0.35);
}

.cases-search, .card-surface {
  padding: var(--space-6);
  border-radius: var(--radius-2xl);
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-normal);
}

.cases-search:hover, .card-surface:hover { box-shadow: var(--shadow-md); }

.search-filters {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  align-items: center;
}

.search-input-wrapper {
  flex: 1;
  min-width: 240px;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 9px 14px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  transition: all var(--transition-fast);
}

.search-input-wrapper:focus-within {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
  background: var(--bg-primary);
}

.search-icon { width: 16px; height: 16px; color: var(--text-muted); }

.search-input, .filter-select {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
  font-family: var(--font-sans);
}

.search-input { flex: 1; }

.filter-select {
  padding: 9px 14px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  cursor: pointer;
}

.cases-table { overflow: auto; }

.cases-table table { width: 100%; border-collapse: collapse; }

.cases-table th, .cases-table td {
  padding: 14px;
  border-bottom: 1px solid var(--border-light);
  text-align: left;
  color: var(--text-primary);
}

.cases-table th {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  background: var(--bg-secondary);
}

.cases-table tbody tr { transition: background var(--transition-fast); }
.cases-table tbody tr:hover { background: var(--primary-soft); }

.case-id-badge {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 3px 10px;
  border-radius: var(--radius-md);
}

.type-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
}

.location-text {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.location-icon { width: 14px; height: 14px; color: var(--text-muted); }

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

.status-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.status-pending { background: rgba(245, 158, 11, 0.1); color: var(--warning-500); }
.status-processing { background: var(--primary-soft); color: var(--primary); }
.status-completed { background: rgba(34, 197, 94, 0.1); color: var(--success-500); }
.status-archived { background: var(--bg-secondary); color: var(--text-muted); }

.action-buttons { display: flex; gap: var(--space-2); }

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  font-size: var(--text-xs);
  font-weight: 500;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.action-btn span { width: 13px; height: 13px; }

.view-btn { background: var(--primary-soft); color: var(--primary); }
.view-btn:hover { background: var(--primary); color: white; transform: translateY(-1px); }

.continue-btn { background: rgba(34, 197, 94, 0.1); color: var(--success-500); }
.continue-btn:hover { background: var(--success-500); color: white; transform: translateY(-1px); }

.edit-btn { background: rgba(139, 92, 246, 0.1); color: #8b5cf6; }
.edit-btn:hover { background: #8b5cf6; color: white; transform: translateY(-1px); }

.delete-btn { background: rgba(239, 68, 68, 0.1); color: var(--danger-500); }
.delete-btn:hover { background: var(--danger-500); color: white; transform: translateY(-1px); }

.empty-state { padding: 48px var(--space-6); text-align: center; }

.empty-icon { width: 60px; height: 60px; margin: 0 auto var(--space-4); color: var(--text-muted); opacity: 0.5; }

.empty-text { color: var(--text-muted); font-size: var(--text-sm); }

.cases-pagination, .pagination-buttons, .modal-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
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

.edit-modal { width: min(640px, calc(100vw - 48px)); }
.delete-modal { width: min(420px, calc(100vw - 48px)); }

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
.modal-icon.danger { color: var(--danger-500); }

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

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
}

.form-grid .form-group.full { grid-column: 1 / -1; }

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.form-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.form-input, .form-select {
  width: 100%;
  padding: 9px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  outline: none;
  transition: all var(--transition-fast);
}

.form-input:focus, .form-select:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
  background: var(--bg-primary);
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-textarea {
  width: 100%;
  min-height: 100px;
  padding: 9px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  outline: none;
  resize: vertical;
  line-height: var(--leading-relaxed);
  transition: all var(--transition-fast);
}

.form-textarea:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
  background: var(--bg-primary);
}

.delete-message { color: var(--text-secondary); font-size: var(--text-sm); line-height: var(--leading-relaxed); }
.delete-message strong { color: var(--text-primary); font-weight: 600; }

.modal-actions {
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border-light);
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .cases-pagination { align-items: flex-start; flex-direction: column; }
  .pagination-buttons { width: 100%; justify-content: center; }
  .search-filters { flex-direction: column; }
  .search-input-wrapper { width: 100%; }
  .filter-select { width: 100%; }
  .form-grid { grid-template-columns: 1fr; }
}
</style>
