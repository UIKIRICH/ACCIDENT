<template>
  <div class="review-priority-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">复核优先级可视化分析</h1>
        <p class="page-subtitle">基于冲突识别与证据完整度的复核辅助统计</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="refresh" :disabled="loading">
          <span class="btn-icon">&#x21bb;</span>
          {{ loading ? '加载中...' : '刷新数据' }}
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading && !data" class="loading-state card-surface">
      <div class="loading-spinner"></div>
      <p>正在加载统计数据...</p>
    </div>

    <!-- 数据为空 -->
    <div v-else-if="!data" class="empty-state card-surface">
      <p>暂无可用的复核辅助统计数据</p>
      <button class="btn btn-primary" @click="refresh">重新加载</button>
    </div>

    <!-- 主体内容 -->
    <template v-else>
      <!-- 概览卡片 -->
      <div class="overview-cards">
        <div class="overview-card" v-for="card in overviewCards" :key="card.key" :class="card.cls">
          <div class="card-value">{{ card.value }}</div>
          <div class="card-label">{{ card.label }}</div>
        </div>
      </div>

      <!-- 图表行1: 优先级分布 + 路由类型 -->
      <div class="charts-row">
        <div class="chart-panel card-surface">
          <h3 class="chart-title">复核优先级分布</h3>
          <div class="bar-chart-v">
            <div class="bar-row" v-for="item in priorityBars" :key="item.name">
              <span class="bar-label">{{ item.name }}</span>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: item.pct + '%' }" :class="'bar-' + item.cls">
                  <span class="bar-value">{{ item.count }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="chart-legend">
            <span class="legend-item" v-for="item in priorityBars" :key="item.name">
              <span class="legend-dot" :class="'dot-' + item.cls"></span>
              {{ item.name }}: {{ item.count }}
            </span>
          </div>
        </div>

        <div class="chart-panel card-surface">
          <h3 class="chart-title">复核路由类型</h3>
          <div class="route-cards">
            <div class="route-card" v-for="item in routeCards" :key="item.name" :class="item.cls">
              <div class="route-count">{{ item.count }}</div>
              <div class="route-name">{{ item.name }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 图表行2: 复核重点分布 + 证据状态 -->
      <div class="charts-row">
        <div class="chart-panel card-surface">
          <h3 class="chart-title">复核重点分布</h3>
          <div class="bar-chart-v">
            <div class="bar-row" v-for="item in focusBars" :key="item.name">
              <span class="bar-label">{{ item.name }}</span>
              <div class="bar-track">
                <div class="bar-fill bar-blue" :style="{ width: item.pct + '%' }">
                  <span class="bar-value">{{ item.count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="chart-panel card-surface">
          <h3 class="chart-title">证据状态分布</h3>
          <div class="evidence-grid">
            <div class="evidence-item" v-for="item in evidenceBars" :key="item.name" :class="item.cls">
              <div class="evidence-ring" :class="item.cls">
                <div class="ring-inner">
                  <span class="ring-num">{{ item.count }}</span>
                </div>
              </div>
              <span class="evidence-label">{{ item.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ReviewAssistAPI } from '../api/index.js'
import { notify } from '../composables/useToast'

const loading = ref(false)
const data = ref(null)

// 概览卡片
const overviewCards = computed(() => {
  const d = data.value || {}
  return [
    { key: 'total', label: '总案例', value: d.total_cases || 0, cls: 'card-total' },
    { key: 'conflict', label: '模型冲突案例', value: d.model_conflict_cases || 0, cls: 'card-conflict' },
    { key: 'high', label: '高优先级案例', value: d.high_priority_cases || 0, cls: 'card-high' },
    { key: 'evidence_insufficient', label: '证据不足案例', value: d.evidence_insufficient_cases || 0, cls: 'card-evidence' }
  ]
})

// 优先级柱状图
const priorityBars = computed(() => {
  const p = (data.value || {}).review_priority_level || {}
  const total = Object.values(p).reduce((s, v) => s + v, 0) || 1
  return [
    { name: '高 (85-100)', count: p['高'] || 0, cls: 'high', pct: Math.round(((p['高'] || 0) / total) * 100) },
    { name: '中 (70-84)', count: p['中'] || 0, cls: 'medium', pct: Math.round(((p['中'] || 0) / total) * 100) },
    { name: '低 (0-69)', count: p['低'] || 0, cls: 'low', pct: Math.round(((p['低'] || 0) / total) * 100) }
  ]
})

// 路由类型卡片
const routeCards = computed(() => {
  const r = (data.value || {}).route_type_cn || {}
  return [
    { name: '重点复核', count: r['重点复核'] || 0, cls: 'route-review' },
    { name: '快速确认', count: r['快速确认'] || 0, cls: 'route-quick' },
    { name: '补证复核', count: r['补证复核'] || 0, cls: 'route-evidence' }
  ]
})

// 复核重点分布
const focusBars = computed(() => {
  const f = (data.value || {}).review_focus || {}
  const total = Object.values(f).reduce((s, v) => s + v, 0) || 1
  const keys = [
    '模型结论冲突', '责任敏感', '视角不完整', '规则依据需核对',
    '低置信度', '证据不足', '快速确认', '复杂路况', '报告生成验证'
  ]
  return keys
    .filter(k => f[k] > 0)
    .map(k => ({ name: k, count: f[k], pct: Math.round((f[k] / total) * 100) }))
    .sort((a, b) => b.count - a.count)
})

// 证据状态分布
const evidenceBars = computed(() => {
  const e = (data.value || {}).evidence_status || {}
  return [
    { name: '证据有冲突', count: e['证据有冲突'] || 0, cls: 'evi-conflict' },
    { name: '证据充分', count: e['证据充分'] || 0, cls: 'evi-sufficient' },
    { name: '证据不足', count: e['证据不足'] || 0, cls: 'evi-insufficient' },
    { name: '证据需核对', count: e['证据需核对'] || 0, cls: 'evi-check' }
  ].filter(i => i.count > 0)
})

async function refresh() {
  loading.value = true
  try {
    const res = await ReviewAssistAPI.statistics()
    if (res.success && res.data) {
      data.value = res.data
    } else {
      data.value = null
    }
  } catch (err) {
    console.error('加载复核辅助统计失败:', err)
    notify({ title: '加载失败', message: err.message || '请稍后重试', type: 'error' })
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.review-priority-page {
  padding: var(--space-5);
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-6);
}
.page-title { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); margin: 0; }
.page-subtitle { font-size: var(--text-sm); color: var(--text-muted); margin: 4px 0 0; }

/* 概览卡片 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}
.overview-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  text-align: center;
}
.overview-card .card-value { font-size: 2rem; font-weight: 700; margin-bottom: 4px; }
.overview-card .card-label { font-size: var(--text-xs); color: var(--text-muted); }
.card-total .card-value { color: var(--primary-500); }
.card-conflict .card-value { color: #ef4444; }
.card-high .card-value { color: var(--warning-500); }
.card-evidence .card-value { color: var(--info-500); }

/* 图表行 */
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
  margin-bottom: var(--space-5);
}
.chart-panel {
  padding: var(--space-5);
}
.chart-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
}

/* 柱状图 */
.bar-chart-v { display: flex; flex-direction: column; gap: var(--space-3); }
.bar-row { display: flex; align-items: center; gap: var(--space-3); }
.bar-label { font-size: var(--text-xs); color: var(--text-secondary); min-width: 100px; text-align: right; }
.bar-track { flex: 1; height: 24px; background: var(--bg-tertiary); border-radius: var(--radius-full); overflow: hidden; }
.bar-fill { height: 100%; border-radius: var(--radius-full); display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; transition: width 0.6s ease; }
.bar-fill .bar-value { font-size: 11px; font-weight: 600; color: #fff; }
.bar-high { background: linear-gradient(90deg, #ef4444, #f87171); }
.bar-medium { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.bar-low { background: linear-gradient(90deg, #64748b, #94a3b8); }
.bar-blue { background: linear-gradient(90deg, #3b82f6, #60a5fa); }

.chart-legend { display: flex; gap: var(--space-4); margin-top: var(--space-3); font-size: var(--text-xs); color: var(--text-muted); }
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-high { background: #ef4444; }
.dot-medium { background: #f59e0b; }
.dot-low { background: #64748b; }

/* 路由卡片 */
.route-cards { display: flex; gap: var(--space-4); }
.route-card { flex: 1; text-align: center; padding: var(--space-4); border-radius: var(--radius-lg); }
.route-card .route-count { font-size: 1.75rem; font-weight: 700; margin-bottom: 2px; }
.route-card .route-name { font-size: var(--text-xs); }
.route-review { background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); }
.route-review .route-count { color: var(--warning-500); }
.route-quick { background: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.2); }
.route-quick .route-count { color: var(--success-500); }
.route-evidence { background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.2); }
.route-evidence .route-count { color: var(--primary-500); }

/* 证据状态圆环 */
.evidence-grid { display: flex; justify-content: space-around; }
.evidence-item { display: flex; flex-direction: column; align-items: center; gap: var(--space-2); }
.evidence-ring { width: 72px; height: 72px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.evidence-ring .ring-inner { width: 54px; height: 54px; border-radius: 50%; background: var(--bg-primary); display: flex; align-items: center; justify-content: center; }
.evidence-ring .ring-num { font-size: 1.2rem; font-weight: 700; }
.evi-conflict { border: 3px solid #ef4444; }
.evi-conflict .ring-num { color: #ef4444; }
.evi-sufficient { border: 3px solid var(--success-500); }
.evi-sufficient .ring-num { color: var(--success-500); }
.evi-insufficient { border: 3px solid var(--warning-500); }
.evi-insufficient .ring-num { color: var(--warning-500); }
.evi-check { border: 3px solid var(--text-muted); }
.evi-check .ring-num { color: var(--text-muted); }
.evidence-label { font-size: var(--text-xs); color: var(--text-secondary); }

.loading-state, .empty-state { padding: var(--space-12); text-align: center; color: var(--text-muted); }
.loading-spinner { width: 32px; height: 32px; border: 3px solid var(--bg-tertiary); border-top-color: var(--primary-500); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto var(--space-3); }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 768px) {
  .overview-cards { grid-template-columns: repeat(2, 1fr); }
  .charts-row { grid-template-columns: 1fr; }
  .bar-label { min-width: 70px; }
}
</style>
