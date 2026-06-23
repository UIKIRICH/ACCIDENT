<template>
  <div class="dashboard-screen">
    <!-- 顶部刷新进度条 -->
    <div class="refresh-progress-bar">
      <div class="refresh-progress-fill" :style="{ width: refreshProgress + '%' }"></div>
    </div>

    <!-- 顶部标题栏 -->
    <header class="dashboard-header">
      <div class="header-side header-left">
        <div class="header-deco"></div>
        <div class="header-titles">
          <h1 class="dashboard-title">事故处置态势大屏</h1>
          <p class="dashboard-subtitle">ACCIDENT DISPOSITION SITUATION AWARENESS</p>
        </div>
      </div>
      <div class="header-center">
        <div class="time-block">
          <span class="time-icon" v-html="icons.clock"></span>
          <span class="time-text">{{ currentTime }}</span>
        </div>
      </div>
      <div class="header-side header-right">
        <div class="refresh-indicator" :class="{ refreshing: loading }">
          <span class="refresh-dot"></span>
          <span class="refresh-text">{{ loading ? '数据刷新中' : '自动刷新' }}</span>
          <span class="refresh-countdown">{{ nextRefreshCountdown }}s</span>
        </div>
        <button class="manual-refresh-btn" @click="manualRefresh" :disabled="loading">
          <span class="manual-refresh-icon" :class="{ spinning: loading }" v-html="icons.refresh"></span>
        </button>
      </div>
    </header>

    <!-- 主体内容 -->
    <div class="dashboard-body">
      <!-- 第一行：4 个数字卡片 -->
      <div class="stats-row">
        <div
          class="stat-card"
          v-for="card in statCards"
          :key="card.key"
          :class="card.cls"
        >
          <div class="stat-card-glow"></div>
          <div class="stat-card-icon" v-html="card.icon"></div>
          <div class="stat-card-content">
            <div class="stat-card-value">
              <transition name="flip" mode="out-in">
                <span :key="card.value" class="stat-number">{{ card.value }}</span>
              </transition>
              <span class="stat-unit">{{ card.unit }}</span>
            </div>
            <div class="stat-card-label">{{ card.label }}</div>
          </div>
          <div class="stat-card-corner"></div>
        </div>
      </div>

      <!-- 第二行：事故类型分布 + 规则命中 Top5 -->
      <div class="charts-row">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-bar"></span>
              <span class="panel-title">事故类型分布</span>
            </div>
            <span class="panel-subtitle">按事故类型统计</span>
          </div>
          <div class="panel-body">
            <div v-if="accidentTypeDist.length" class="bar-chart">
              <div class="bar-item" v-for="(item, index) in accidentTypeDist" :key="index">
                <div class="bar-label" :title="item.name">{{ item.name }}</div>
                <div class="bar-track">
                  <div class="bar-fill" :style="{ width: item.percent + '%' }">
                    <span class="bar-value">{{ item.count }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="empty-data">
              <span class="empty-icon" v-html="icons.chart"></span>
              <span>暂无数据</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-bar"></span>
              <span class="panel-title">规则命中 Top5</span>
            </div>
            <span class="panel-subtitle">高频触发规则</span>
          </div>
          <div class="panel-body">
            <div v-if="ruleHitTop.length" class="column-chart">
              <div class="column-item" v-for="(item, index) in ruleHitTop" :key="index">
                <div class="column-value">{{ item.count }}</div>
                <div class="column-track">
                  <div class="column-fill" :style="{ height: item.percent + '%' }"></div>
                </div>
                <div class="column-label" :title="item.name">{{ item.name }}</div>
              </div>
            </div>
            <div v-else class="empty-data">
              <span class="empty-icon" v-html="icons.chart"></span>
              <span>暂无数据</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 第三行：复核通过率 + 系统健康 -->
      <div class="status-row">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-bar"></span>
              <span class="panel-title">复核通过率</span>
            </div>
            <span class="panel-subtitle">案件复核统计</span>
          </div>
          <div class="panel-body">
            <div class="ring-container">
              <div class="ring-chart" :style="ringStyle">
                <div class="ring-inner">
                  <div class="ring-value">{{ reviewPassRate }}<span class="ring-percent">%</span></div>
                  <div class="ring-label">通过率</div>
                </div>
              </div>
              <div class="ring-legend">
                <div class="legend-item">
                  <span class="legend-dot legend-pass"></span>
                  <span class="legend-label">已通过</span>
                  <span class="legend-value">{{ reviewPassed }}</span>
                </div>
                <div class="legend-item">
                  <span class="legend-dot legend-pending"></span>
                  <span class="legend-label">待复核</span>
                  <span class="legend-value">{{ reviewPending }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-bar"></span>
              <span class="panel-title">系统健康状态</span>
            </div>
            <span class="panel-subtitle">服务运行监控</span>
          </div>
          <div class="panel-body">
            <div class="health-grid">
              <div class="health-item" v-for="item in healthItems" :key="item.key">
                <div class="health-icon-wrap" :class="item.statusClass">
                  <span class="health-dot"></span>
                </div>
                <div class="health-info">
                  <div class="health-name">{{ item.label }}</div>
                  <div class="health-status" :class="item.statusClass">{{ item.text }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 第四行：高风险/证据冲突案件列表 -->
      <div class="risk-row">
        <div class="panel panel-full">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-bar"></span>
              <span class="panel-title">高风险 / 证据冲突案件</span>
              <span class="panel-badge">{{ highRiskCases.length }}</span>
            </div>
            <span class="panel-subtitle">需重点关注</span>
          </div>
          <div class="panel-body">
            <div v-if="highRiskCases.length" class="risk-table">
              <div class="risk-table-head">
                <div class="risk-col col-id">案件编号</div>
                <div class="risk-col col-type">事故类型</div>
                <div class="risk-col col-location">发生地点</div>
                <div class="risk-col col-time">提交时间</div>
                <div class="risk-col col-status">处理状态</div>
                <div class="risk-col col-risk">风险标记</div>
              </div>
              <div class="risk-table-body">
                <div
                  class="risk-table-row"
                  v-for="item in highRiskCases"
                  :key="item.caseId"
                  @click="viewCase(item)"
                >
                  <div class="risk-col col-id">{{ item.caseId }}</div>
                  <div class="risk-col col-type">{{ item.title }}</div>
                  <div class="risk-col col-location">{{ item.location }}</div>
                  <div class="risk-col col-time">{{ item.time }}</div>
                  <div class="risk-col col-status">
                    <span class="status-tag" :class="getStatusClass(item.status)">{{ item.status }}</span>
                  </div>
                  <div class="risk-col col-risk">
                    <span class="risk-tag" :class="item.riskClass">{{ item.riskLabel }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="empty-data">
              <span class="empty-icon" v-html="icons.shield"></span>
              <span>暂无高风险案件</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { StatsAPI, TasksAPI, HealthAPI } from '../api/index.js'
import { notify } from '../composables/useToast'

const router = useRouter()

// 响应式数据
const stats = ref({})           // 统计概览
const health = ref(null)        // 系统健康
const pendingTasks = ref([])    // 待处理任务
const historyCases = ref([])    // 历史案例
const highRiskCases = ref([])   // 高风险案件
const loading = ref(false)      // 加载状态
const currentTime = ref('')     // 当前时间
const refreshProgress = ref(0)  // 刷新进度（0-100）
const nextRefreshCountdown = ref(30) // 下次刷新倒计时（秒）

let progressTimer = null   // 进度/倒计时定时器
let timeTimer = null       // 时间定时器

// 刷新间隔（秒）
const REFRESH_INTERVAL = 30

// SVG 图标
const icons = {
  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>`,
  chart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
  shield: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  analyze: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 21l-4.35-4.35"/><circle cx="11" cy="11" r="8"/></svg>`,
  review: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
  done: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
}

// 统一获取统计字段（兼容驼峰 / 下划线命名，缺失时返回默认值）
const getStat = (camelKey, snakeKey, defaultVal = 0) => {
  const s = stats.value || {}
  const val = s[camelKey] ?? s[snakeKey]
  return val == null ? defaultVal : val
}

// 加载所有数据
const loadData = async () => {
  loading.value = true
  try {
    // 并行请求，任一失败不影响其它
    const results = await Promise.allSettled([
      StatsAPI.getOverview(),
      TasksAPI.getPendingList(),
      StatsAPI.getHistoryCases({ limit: 10 }),
      HealthAPI.check()
    ])

    // 统计概览
    if (results[0].status === 'fulfilled' && results[0].value?.success) {
      stats.value = results[0].value.data || {}
    }

    // 待处理任务
    if (results[1].status === 'fulfilled' && results[1].value?.success) {
      pendingTasks.value = results[1].value.data || []
    }

    // 历史案例
    if (results[2].status === 'fulfilled' && results[2].value?.success) {
      historyCases.value = results[2].value.data || []
    }

    // 系统健康
    if (results[3].status === 'fulfilled') {
      health.value = results[3].value
    }

    // 计算高风险案件
    computeHighRiskCases()
  } catch (e) {
    console.error('大屏数据加载失败:', e)
  } finally {
    loading.value = false
  }
}

// 手动刷新
const manualRefresh = () => {
  if (loading.value) return
  nextRefreshCountdown.value = REFRESH_INTERVAL
  refreshProgress.value = 0
  loadData()
  notify({ title: '手动刷新', message: '正在获取最新态势数据', type: 'info' })
}

// 计算高风险 / 证据冲突案件
const computeHighRiskCases = () => {
  const cases = historyCases.value || []
  const risky = cases
    .filter(c => {
      const status = c.status || ''
      // 待复核 / 复核中 状态，或存在证据冲突标记
      const isPendingReview =
        status === '待复核' || status === '复核中' || status === 'pending_review'
      const hasConflict =
        c.evidence_conflict === true ||
        c.has_conflict === true ||
        c.conflict === true
      return isPendingReview || hasConflict
    })
    .map(c => {
      const status = c.status || '待处理'
      const isPendingReview =
        status === '待复核' || status === '复核中' || status === 'pending_review'
      return {
        caseId: c.id || c.caseId || '--',
        title: c.title || c.accident_type || '未命名案件',
        location: c.location || '未记录',
        time: formatTime(c.submitted_at || c.created_at),
        status,
        riskLabel: isPendingReview ? '待复核' : '证据冲突',
        riskClass: isPendingReview ? 'risk-medium' : 'risk-high'
      }
    })
  highRiskCases.value = risky
}

// 格式化时间
const formatTime = (dateStr) => {
  if (!dateStr) return '--'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return String(dateStr)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 更新当前时间
const updateTime = () => {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  currentTime.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

// ── 计算属性 ──

// 4 个数字卡片
const statCards = computed(() => [
  {
    key: 'todayNew',
    label: '今日新增案件',
    value: getStat('todayNew', 'today_new'),
    unit: '件',
    cls: 'card-cyan',
    icon: icons.plus
  },
  {
    key: 'pendingAnalysis',
    label: '待分析案件',
    value: getStat('pendingAnalysis', 'pending_analysis'),
    unit: '件',
    cls: 'card-orange',
    icon: icons.analyze
  },
  {
    key: 'pendingReview',
    label: '待复核案件',
    value: getStat('pendingReview', 'pending_review'),
    unit: '件',
    cls: 'card-blue',
    icon: icons.review
  },
  {
    key: 'completed',
    label: '已完成案件',
    value: getStat('completedCases', 'completed'),
    unit: '件',
    cls: 'card-green',
    icon: icons.done
  }
])

// 事故类型分布（接口字段缺失时，从历史案例中统计兜底）
const accidentTypeDist = computed(() => {
  const s = stats.value || {}
  let dist = s.accident_type_dist || s.accidentTypeDist
  if (!Array.isArray(dist) || dist.length === 0) {
    // 从历史案例中按事故类型聚合
    const counts = {}
    historyCases.value.forEach(c => {
      const type = c.accident_type || c.title || '未分类'
      counts[type] = (counts[type] || 0) + 1
    })
    dist = Object.entries(counts).map(([name, count]) => ({ name, count }))
  }
  if (!dist || dist.length === 0) return []
  const max = Math.max(...dist.map(d => Number(d.count) || 0), 1)
  return dist
    .slice(0, 6)
    .map(d => ({
      name: d.name || d.type || '未分类',
      count: Number(d.count) || Number(d.value) || 0,
      percent: Math.round(((Number(d.count) || Number(d.value) || 0) / max) * 100)
    }))
})

// 规则命中 Top5（接口未提供时显示暂无数据）
const ruleHitTop = computed(() => {
  const s = stats.value || {}
  const dist = s.rule_hit_top || s.ruleHitTop
  if (!Array.isArray(dist) || dist.length === 0) return []
  const max = Math.max(...dist.map(d => Number(d.count) || 0), 1)
  return dist
    .slice(0, 5)
    .map(d => ({
      name: d.name || d.rule_name || d.rule || '未命名',
      count: Number(d.count) || Number(d.value) || 0,
      percent: Math.round(((Number(d.count) || Number(d.value) || 0) / max) * 100)
    }))
})

// 复核通过率
const reviewPassed = computed(() => getStat('completedCases', 'completed'))
const reviewPending = computed(() => getStat('pendingReview', 'pending_review'))
const reviewPassRate = computed(() => {
  const total = reviewPassed.value + reviewPending.value
  if (total <= 0) return 0
  return Math.round((reviewPassed.value / total) * 100)
})
// 环形图 conic-gradient 样式
const ringStyle = computed(() => ({
  background: `conic-gradient(#22c55e 0% ${reviewPassRate.value}%, var(--bg-tertiary) ${reviewPassRate.value}% 100%)`
}))

// 系统健康状态项
const healthItems = computed(() => {
  const h = health.value
  if (!h) {
    return [
      { key: 'database', label: '数据库', statusClass: 'status-unknown', text: '检测中' },
      { key: 'yolo', label: 'YOLO 模型', statusClass: 'status-unknown', text: '检测中' },
      { key: 'dify', label: 'Dify 服务', statusClass: 'status-unknown', text: '检测中' }
    ]
  }
  return [
    {
      key: 'database',
      label: '数据库',
      statusClass: h.database === 'connected' ? 'status-ok' : 'status-error',
      text: h.database === 'connected' ? '正常' : '异常'
    },
    {
      key: 'yolo',
      label: 'YOLO 模型',
      statusClass: h.yolo_model === 'loaded' ? 'status-ok' : 'status-error',
      text: h.yolo_model === 'loaded' ? '正常' : '异常'
    },
    {
      key: 'dify',
      label: 'Dify 服务',
      statusClass:
        h.dify_service === 'reachable'
          ? 'status-ok'
          : h.dify_service === 'unconfigured'
            ? 'status-warn'
            : 'status-error',
      text:
        h.dify_service === 'reachable'
          ? '正常'
          : h.dify_service === 'unconfigured'
            ? '未配置'
            : '异常'
    }
  ]
})

// 状态标签样式
const getStatusClass = (status) => {
  const map = {
    '待处理': 'tag-orange',
    '待分析': 'tag-orange',
    '处理中': 'tag-blue',
    '待复核': 'tag-blue',
    '复核中': 'tag-blue',
    '已完成': 'tag-green',
    '已归档': 'tag-gray'
  }
  return map[status] || 'tag-gray'
}

// 查看案件详情
const viewCase = (item) => {
  router.push({ path: '/history-cases', query: { caseId: String(item.caseId) } })
}

// 生命周期
onMounted(() => {
  loadData()
  updateTime()
  // 时间每秒更新
  timeTimer = setInterval(updateTime, 1000)
  // 进度 / 倒计时每秒更新，到点触发刷新
  progressTimer = setInterval(() => {
    nextRefreshCountdown.value--
    refreshProgress.value = ((REFRESH_INTERVAL - nextRefreshCountdown.value) / REFRESH_INTERVAL) * 100
    if (nextRefreshCountdown.value <= 0) {
      nextRefreshCountdown.value = REFRESH_INTERVAL
      refreshProgress.value = 0
      loadData()
    }
  }, 1000)
})

onUnmounted(() => {
  clearInterval(progressTimer)
  clearInterval(timeTimer)
})
</script>

<style scoped>
/* ============================================
   事故处置态势大屏 - 浅色 Apple 风格
   与平台设计系统保持一致
   ============================================ */

.dashboard-screen {
  /* 突破外层 content-area 的内边距，实现全屏浅色背景 */
  margin: calc(-1 * var(--content-padding));
  min-height: 100%;
  background: var(--bg-secondary);
  color: var(--text-primary);
  padding: var(--space-5) var(--space-6) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  font-family: var(--font-sans);
  position: relative;
  overflow-x: hidden;
}

/* 顶部刷新进度条 */
.refresh-progress-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--border-light);
  z-index: 100;
}

.refresh-progress-fill {
  height: 100%;
  background: var(--primary-gradient);
  transition: width 1s linear;
}

/* ── 顶部标题栏 ── */
.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-6);
  padding: var(--space-5) var(--space-7);
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  position: relative;
}

.header-side {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.header-left {
  flex-shrink: 0;
}

.header-deco {
  width: 5px;
  height: 42px;
  background: var(--primary-gradient);
  border-radius: var(--radius-sm);
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dashboard-title {
  font-size: 26px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: var(--tracking-tight);
  margin: 0;
}

.dashboard-subtitle {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 2px;
  margin: 0;
  font-weight: 500;
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.time-block {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.time-icon {
  width: 18px;
  height: 18px;
  color: var(--primary-600);
}

.time-text {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: 1px;
}

.header-right {
  flex-shrink: 0;
}

.refresh-indicator {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--success-50);
  border: 1px solid var(--success-100);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--success-700);
  transition: all var(--transition-normal);
}

.refresh-indicator.refreshing {
  background: var(--primary-50);
  border-color: var(--primary-100);
  color: var(--primary-700);
}

.refresh-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success-500);
  animation: pulse 1.6s ease-in-out infinite;
}

.refresh-indicator.refreshing .refresh-dot {
  background: var(--primary-500);
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

.refresh-countdown {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--text-primary);
}

.manual-refresh-btn {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--primary-600);
  box-shadow: var(--shadow-xs);
  transition: all var(--transition-fast);
}

.manual-refresh-btn:hover:not(:disabled) {
  background: var(--primary-50);
  border-color: var(--primary-200);
}

.manual-refresh-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.manual-refresh-icon {
  width: 18px;
  height: 18px;
  display: flex;
}

.manual-refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── 主体布局 ── */
.dashboard-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ── 第一行：数字卡片 ── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-5);
}

.stat-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-5);
  padding: var(--space-6);
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: transform var(--transition-normal), box-shadow var(--transition-normal);
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-md);
}

/* 移除霓虹光效 */
.stat-card-glow {
  display: none;
}

.stat-card-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

.stat-card-icon svg { width: 26px; height: 26px; }

.card-cyan .stat-card-icon { background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%); color: #fff; box-shadow: 0 3px 10px rgba(6, 182, 212, 0.25); }
.card-orange .stat-card-icon { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: #fff; box-shadow: 0 3px 10px rgba(245, 158, 11, 0.25); }
.card-blue .stat-card-icon { background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: #fff; box-shadow: 0 3px 10px rgba(59, 130, 246, 0.25); }
.card-green .stat-card-icon { background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: #fff; box-shadow: 0 3px 10px rgba(34, 197, 94, 0.25); }

.stat-card-content {
  flex: 1;
  position: relative;
  z-index: 1;
  min-width: 0;
}

.stat-card-value {
  display: flex;
  align-items: baseline;
  gap: 6px;
  line-height: 1;
}

.stat-number {
  font-size: 48px;
  font-weight: 800;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -1px;
  display: inline-block;
}

.stat-unit {
  font-size: var(--text-base);
  color: var(--text-secondary);
  font-weight: 500;
}

.stat-card-label {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
  letter-spacing: 0.5px;
}

.stat-card-corner {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 60px;
  height: 3px;
}

.card-cyan .stat-card-corner { background: linear-gradient(90deg, #06b6d4, transparent); }
.card-orange .stat-card-corner { background: linear-gradient(90deg, #f59e0b, transparent); }
.card-blue .stat-card-corner { background: linear-gradient(90deg, #3b82f6, transparent); }
.card-green .stat-card-corner { background: linear-gradient(90deg, #22c55e, transparent); }

/* 数字翻牌动画 */
.flip-enter-active,
.flip-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.flip-enter-from {
  opacity: 0;
  transform: translateY(-18px) rotateX(80deg);
}
.flip-leave-to {
  opacity: 0;
  transform: translateY(18px) rotateX(-80deg);
}

/* ── 通用面板 ── */
.panel {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: box-shadow var(--transition-normal);
}

.panel:hover {
  box-shadow: var(--shadow-md);
}

.panel-full {
  flex: 1;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-secondary);
}

.panel-title-group {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.panel-bar {
  width: 4px;
  height: 16px;
  background: var(--primary-gradient);
  border-radius: var(--radius-sm);
}

.panel-title {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.5px;
}

.panel-subtitle {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.panel-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  background: var(--danger-50);
  color: var(--danger-700);
  border: 1px solid var(--danger-100);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.panel-body {
  flex: 1;
  padding: var(--space-5);
  min-height: 0;
}

/* ── 第二行图表 ── */
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
}

/* 横向条形图 */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.bar-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.bar-label {
  width: 90px;
  flex-shrink: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bar-track {
  flex: 1;
  height: 22px;
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  overflow: hidden;
  position: relative;
}

.bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  background: linear-gradient(90deg, var(--primary-500), var(--primary-400));
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 10px;
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 28px;
}

.bar-item:nth-child(2n) .bar-fill {
  background: linear-gradient(90deg, #8b5cf6, #6366f1);
}
.bar-item:nth-child(3n) .bar-fill {
  background: linear-gradient(90deg, var(--success-500), #14b8a6);
}
.bar-item:nth-child(4n) .bar-fill {
  background: linear-gradient(90deg, var(--warning-500), #f97316);
}
.bar-item:nth-child(5n) .bar-fill {
  background: linear-gradient(90deg, #ec4899, #f43f5e);
}

.bar-value {
  font-size: var(--text-xs);
  font-weight: 700;
  color: #fff;
  font-variant-numeric: tabular-nums;
}

/* 柱状图 */
.column-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  gap: var(--space-3);
  height: 220px;
  padding: 0 var(--space-2);
}

.column-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  height: 100%;
  min-width: 0;
}

.column-value {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.column-track {
  flex: 1;
  width: 100%;
  max-width: 48px;
  display: flex;
  align-items: flex-end;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  overflow: hidden;
}

.column-fill {
  width: 100%;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  background: linear-gradient(180deg, var(--info-500) 0%, var(--primary-500) 100%);
  transition: height 0.8s cubic-bezier(0.4, 0, 0.2, 1);
  min-height: 4px;
}

.column-item:nth-child(2n) .column-fill { background: linear-gradient(180deg, #a78bfa 0%, #6366f1 100%); }
.column-item:nth-child(3n) .column-fill { background: linear-gradient(180deg, var(--success-500) 0%, #14b8a6 100%); }
.column-item:nth-child(4n) .column-fill { background: linear-gradient(180deg, #fbbf24 0%, var(--warning-600) 100%); }
.column-item:nth-child(5n) .column-fill { background: linear-gradient(180deg, #f472b6 0%, #f43f5e 100%); }

.column-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* ── 第三行 ── */
.status-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
}

/* 环形图 */
.ring-container {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: var(--space-6);
  padding: var(--space-2) 0;
}

.ring-chart {
  width: 160px;
  height: 160px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  flex-shrink: 0;
  transition: background 0.8s ease;
}

.ring-inner {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 0 1px var(--border-light);
}

.ring-value {
  font-size: 36px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.ring-percent {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-secondary);
}

.ring-label {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.ring-legend {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.legend-pass { background: var(--success-500); }
.legend-pending { background: var(--border-medium); }

.legend-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.legend-value {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  margin-left: auto;
}

/* 系统健康 */
.health-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-4);
}

.health-item {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  transition: background var(--transition-normal);
}

.health-item:hover {
  background: var(--bg-tertiary);
}

.health-icon-wrap {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
}

.health-icon-wrap::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  animation: health-pulse 2s ease-in-out infinite;
}

.health-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.status-ok { background: var(--success-50); border: 1px solid var(--success-100); }
.status-ok .health-dot { background: var(--success-500); }
.status-ok::after { background: rgba(34, 197, 94, 0.2); }

.status-error { background: var(--danger-50); border: 1px solid var(--danger-100); }
.status-error .health-dot { background: var(--danger-500); }
.status-error::after { background: rgba(239, 68, 68, 0.2); }

.status-warn { background: var(--warning-50); border: 1px solid var(--warning-100); }
.status-warn .health-dot { background: var(--warning-500); }
.status-warn::after { background: rgba(245, 158, 11, 0.2); }

.status-unknown { background: var(--slate-100); border: 1px solid var(--border-light); }
.status-unknown .health-dot { background: var(--text-muted); }
.status-unknown::after { background: rgba(148, 163, 184, 0.15); }

@keyframes health-pulse {
  0%, 100% { transform: scale(1); opacity: 0.6; }
  50% { transform: scale(1.4); opacity: 0; }
}

.health-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.health-name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.health-status {
  font-size: var(--text-xs);
  font-weight: 500;
}

.health-status.status-ok { color: var(--success-700); }
.health-status.status-error { color: var(--danger-700); }
.health-status.status-warn { color: var(--warning-700); }
.health-status.status-unknown { color: var(--text-muted); }

/* ── 第四行：高风险案件表 ── */
.risk-row {
  display: flex;
}

.risk-table {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.risk-table-head,
.risk-table-row {
  display: grid;
  grid-template-columns: 140px 1.2fr 1.5fr 1.3fr 120px 120px;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-3) var(--space-4);
}

.risk-table-head {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
}

.risk-table-head .risk-col {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-tertiary);
  letter-spacing: 0.5px;
}

.risk-table-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  max-height: 320px;
  overflow-y: auto;
}

.risk-table-body::-webkit-scrollbar { width: 6px; }
.risk-table-body::-webkit-scrollbar-track { background: transparent; }
.risk-table-body::-webkit-scrollbar-thumb { background: var(--border-medium); border-radius: 3px; }

.risk-table-row {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.risk-table-row:hover {
  background: var(--primary-50);
  border-color: var(--primary-200);
  transform: translateX(3px);
}

.risk-col {
  font-size: var(--text-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-id { color: var(--primary-600); font-weight: 600; font-variant-numeric: tabular-nums; }

.status-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

.tag-orange { background: var(--warning-50); color: var(--warning-700); }
.tag-blue { background: var(--primary-50); color: var(--primary-700); }
.tag-green { background: var(--success-50); color: var(--success-700); }
.tag-gray { background: var(--slate-100); color: var(--text-secondary); }

.risk-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

.risk-high { background: var(--danger-50); color: var(--danger-700); border: 1px solid var(--danger-100); }
.risk-medium { background: var(--warning-50); color: var(--warning-700); border: 1px solid var(--warning-100); }

/* ── 空数据 ── */
.empty-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-10) var(--space-5);
  color: var(--text-muted);
  font-size: var(--text-base);
}

.empty-icon {
  width: 40px;
  height: 40px;
  display: flex;
  opacity: 0.4;
}

.empty-icon svg { width: 100%; height: 100%; }

/* ── 暗色主题适配 ── */
[data-theme="dark"] .refresh-indicator { background: rgba(34, 197, 94, 0.12); border-color: rgba(34, 197, 94, 0.2); color: #4ade80; }
[data-theme="dark"] .refresh-indicator.refreshing { background: rgba(59, 130, 246, 0.12); border-color: rgba(59, 130, 246, 0.2); color: #93c5fd; }
[data-theme="dark"] .time-block { background: rgba(255, 255, 255, 0.04); border-color: rgba(255, 255, 255, 0.08); }
[data-theme="dark"] .manual-refresh-btn { background: rgba(255, 255, 255, 0.04); border-color: rgba(255, 255, 255, 0.08); }
[data-theme="dark"] .panel-header { background: rgba(255, 255, 255, 0.02); }
[data-theme="dark"] .bar-track { background: rgba(255, 255, 255, 0.04); }
[data-theme="dark"] .column-track { background: rgba(255, 255, 255, 0.03); }
[data-theme="dark"] .health-item { background: rgba(255, 255, 255, 0.03); border-color: rgba(255, 255, 255, 0.06); }
[data-theme="dark"] .health-item:hover { background: rgba(255, 255, 255, 0.05); }
[data-theme="dark"] .status-ok { background: rgba(34, 197, 94, 0.12); border-color: rgba(34, 197, 94, 0.2); }
[data-theme="dark"] .status-error { background: rgba(239, 68, 68, 0.12); border-color: rgba(239, 68, 68, 0.2); }
[data-theme="dark"] .status-warn { background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.2); }
[data-theme="dark"] .status-unknown { background: rgba(148, 163, 184, 0.1); border-color: rgba(148, 163, 184, 0.15); }
[data-theme="dark"] .health-status.status-ok { color: #4ade80; }
[data-theme="dark"] .health-status.status-error { color: #fca5a5; }
[data-theme="dark"] .health-status.status-warn { color: #fbbf24; }
[data-theme="dark"] .risk-table-row { background: rgba(255, 255, 255, 0.02); border-color: rgba(255, 255, 255, 0.04); }
[data-theme="dark"] .risk-table-row:hover { background: rgba(59, 130, 246, 0.08); border-color: rgba(59, 130, 246, 0.2); }
[data-theme="dark"] .tag-orange { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
[data-theme="dark"] .tag-blue { background: rgba(59, 130, 246, 0.15); color: #93c5fd; }
[data-theme="dark"] .tag-green { background: rgba(34, 197, 94, 0.15); color: #4ade80; }
[data-theme="dark"] .tag-gray { background: rgba(148, 163, 184, 0.12); color: #cbd5e1; }
[data-theme="dark"] .risk-high { background: rgba(239, 68, 68, 0.15); color: #fca5a5; border-color: rgba(239, 68, 68, 0.2); }
[data-theme="dark"] .risk-medium { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border-color: rgba(245, 158, 11, 0.2); }
[data-theme="dark"] .panel-badge { background: rgba(239, 68, 68, 0.15); color: #fca5a5; border-color: rgba(239, 68, 68, 0.2); }
[data-theme="dark"] .ring-inner { box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06); }

/* ── 响应式适配 ── */
@media (max-width: 1400px) {
  .stat-number { font-size: 42px; }
  .dashboard-title { font-size: 22px; }
}

@media (max-width: 1200px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .charts-row { grid-template-columns: 1fr; }
  .status-row { grid-template-columns: 1fr; }
  .dashboard-header { flex-wrap: wrap; }
  .header-center { order: 3; flex: 1 1 100%; justify-content: flex-start; }
}

@media (max-width: 768px) {
  .dashboard-screen { padding: var(--space-4); }
  .stats-row { grid-template-columns: 1fr; }
  .stat-card { padding: var(--space-4); }
  .stat-number { font-size: 36px; }
  .dashboard-title { font-size: 18px; letter-spacing: 1px; }
  .dashboard-subtitle { display: none; }
  .ring-container { flex-direction: column; }
  .risk-table-head { display: none; }
  .risk-table-row {
    grid-template-columns: 1fr 1fr;
    gap: var(--space-2);
    padding: var(--space-3);
  }
  .col-location, .col-time { grid-column: span 2; }
  .header-right .refresh-indicator { padding: 6px 10px; font-size: 12px; }
}
</style>
