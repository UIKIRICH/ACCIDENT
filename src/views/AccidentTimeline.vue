<template>
  <div class="timeline-page">
    <!-- 顶部：标题 + 案件选择器 -->
    <div class="page-header-bar">
      <div class="header-left">
        <h1 class="page-title">事故时间轴复盘</h1>
        <p class="page-subtitle">关键事件回溯与证据关联分析</p>
      </div>
      <div class="case-selector">
        <label class="selector-label">选择案件</label>
        <select
          v-model="selectedCaseId"
          class="selector-select"
          :disabled="loading || cases.length === 0"
          @change="onCaseChange"
        >
          <option value="" disabled>请选择案件</option>
          <option v-for="c in cases" :key="c.caseId" :value="c.caseId">
            {{ c.caseId }} · {{ c.title }}
          </option>
        </select>
      </div>
    </div>

    <!-- 案件基本信息条 -->
    <div v-if="caseInfo" class="case-info-bar">
      <div class="case-info-item">
        <span class="info-key">案件编号</span>
        <span class="info-val">{{ caseInfo.caseId }}</span>
      </div>
      <div class="case-info-item">
        <span class="info-key">事故类型</span>
        <span class="info-val">{{ caseInfo.title }}</span>
      </div>
      <div class="case-info-item">
        <span class="info-key">发生地点</span>
        <span class="info-val">{{ caseInfo.location }}</span>
      </div>
      <div class="case-info-item">
        <span class="info-key">提交时间</span>
        <span class="info-val">{{ caseInfo.time }}</span>
      </div>
      <div class="case-info-item">
        <span class="info-key">状态</span>
        <span class="info-val status-tag">{{ caseInfo.status }}</span>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="state-box">
      <div class="loading-spinner"></div>
      <p class="state-text">正在加载时间轴数据...</p>
    </div>

    <!-- 未选择案件 -->
    <div v-else-if="!selectedCaseId" class="state-box">
      <div class="state-icon" v-html="icons.clipboard"></div>
      <p class="state-text">请从右上角选择一个案件以查看事故时间轴</p>
    </div>

    <!-- 案件无时间轴数据 -->
    <div v-else-if="timelineNodes.length === 0" class="state-box">
      <div class="state-icon" v-html="icons.empty"></div>
      <p class="state-text">该案件暂无可用的时间轴数据</p>
      <p class="state-sub">未检索到带时间标签的事实或关键帧证据</p>
    </div>

    <!-- 时间轴主体：左 30% + 右 70% -->
    <div v-else class="timeline-container">
      <!-- 左侧时间轴 -->
      <div class="timeline-left">
        <div class="timeline-track">
          <div
            v-for="(node, index) in timelineNodes"
            :key="index"
            class="timeline-node"
            :class="{
              active: index === selectedIndex,
              collision: isCollisionNode(node)
            }"
            @click="selectNode(index)"
          >
            <span class="node-dot"></span>
            <div class="node-content">
              <span class="node-time">{{ node.time_label }}</span>
              <span class="node-title">{{ node.event_title }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧关键帧 + 事实 -->
      <div class="timeline-right">
        <!-- 使用 key 触发切换时的淡入动画 -->
        <div :key="selectedIndex" class="keyframe-card">
          <!-- 关键帧图片 -->
          <div v-if="currentNode.frame_url && !frameLoadError" class="keyframe-image-wrap">
            <img
              :src="currentNode.frame_url"
              class="keyframe-image"
              alt="关键帧"
              @error="onImgError"
            />
            <span class="time-overlay" :class="{ collision: isCollisionNode(currentNode) }">
              {{ currentNode.time_label }}
            </span>
          </div>
          <div v-else class="keyframe-placeholder">
            <div class="placeholder-icon" v-html="icons.image"></div>
            <p class="placeholder-text">该节点暂无关键帧图片</p>
          </div>

          <!-- 事件标题与描述 -->
          <div class="event-info">
            <div class="event-header">
              <span
                class="event-time-badge"
                :class="{ collision: isCollisionNode(currentNode) }"
              >
                {{ currentNode.time_label }}
              </span>
              <h3 class="event-title">{{ currentNode.event_title }}</h3>
            </div>
            <p v-if="currentNode.event_desc" class="event-desc">
              {{ currentNode.event_desc }}
            </p>
          </div>

          <!-- 识别事实列表 -->
          <div class="info-block">
            <h4 class="block-title">识别事实</h4>
            <ul v-if="nodeFacts.length" class="facts-list">
              <li v-for="(fact, i) in nodeFacts" :key="i" class="fact-item">
                <span class="fact-bullet"></span>
                <span class="fact-text">{{ fact }}</span>
              </li>
            </ul>
            <p v-else class="empty-inline">暂无识别事实</p>
          </div>

          <!-- 证据来源 + 置信度 -->
          <div class="info-row">
            <div class="info-block">
              <h4 class="block-title">证据来源</h4>
              <span class="source-tag">{{ currentNode.evidence_source || '未标注' }}</span>
            </div>
            <div class="info-block">
              <h4 class="block-title">置信度</h4>
              <div class="confidence-display">
                <div class="confidence-bar">
                  <div
                    class="confidence-fill"
                    :class="{ 'fill-collision': isCollisionNode(currentNode) }"
                    :style="{ width: confidencePercent + '%' }"
                  ></div>
                </div>
                <span class="confidence-text">{{ confidenceText }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { CasesAPI, StatsAPI } from '../api/index.js'
import { notify } from '../composables/useToast'
import { useAccidentFlow } from '../stores/useAccidentFlow'

const router = useRouter()
const route = useRoute()
const { setCurrentCase, getCurrentCase } = useAccidentFlow()

// 内联 SVG 图标
const icons = {
  clipboard: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 2h6a1 1 0 0 1 1 1v1H8V3a1 1 0 0 1 1-1z"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h4"/></svg>`,
  empty: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>`,
  image: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>`
}

// ── 状态 ──
const cases = ref([])              // 案件列表
const selectedCaseId = ref('')     // 当前选中案件 ID
const loading = ref(false)         // 加载状态
const timelineNodes = ref([])      // 时间轴节点
const selectedIndex = ref(0)       // 当前选中节点索引
const caseDetail = ref(null)       // 案件详情
const rawFacts = ref([])           // 原始结构化事实
const rawEvidences = ref([])       // 原始证据列表
const frameLoadError = ref(false)  // 关键帧图片加载失败标记

// 当前选中节点
const currentNode = computed(() => timelineNodes.value[selectedIndex.value])

// 案件基本信息（从详情中提取）
const caseInfo = computed(() => {
  if (!caseDetail.value) return null
  const d = caseDetail.value
  return {
    caseId: d.id || d.caseId || '--',
    title: d.title || d.accident_type || '未命名案件',
    location: d.location || '未记录',
    time: d.submitted_at || d.created_at || d.time || '--',
    status: d.status || '--'
  }
})

// ── 加载案件列表（用于选择器）──
async function loadCases() {
  try {
    const result = await StatsAPI.getHistoryCases({ limit: 100 })
    if (result.success && Array.isArray(result.data)) {
      cases.value = result.data.map(c => ({
        caseId: c.id,
        title: c.title || c.accident_type || '未命名案件',
        location: c.location || '未记录',
        status: c.status || '待处理',
        archivedAt: c.submitted_at || c.created_at || '--'
      }))
    }
  } catch (err) {
    notify({ title: '加载失败', message: '案件列表获取失败', type: 'error' })
    cases.value = []
  }
}

// ── 选择案件后加载时间轴 ──
async function onCaseChange() {
  if (!selectedCaseId.value) return
  // 同步到全局 store
  setCurrentCase(selectedCaseId.value)
  selectedIndex.value = 0
  await loadTimeline(selectedCaseId.value)
}

// ── 加载时间轴数据：详情 + 证据 + 事实 ──
async function loadTimeline(caseId) {
  loading.value = true
  timelineNodes.value = []
  caseDetail.value = null
  rawFacts.value = []
  rawEvidences.value = []
  frameLoadError.value = false

  try {
    // 并行加载，任一失败不影响其他
    const [detailRes, evidencesRes, factsRes] = await Promise.allSettled([
      CasesAPI.getDetail(caseId),
      CasesAPI.getEvidences(caseId),
      CasesAPI.getFacts(caseId)
    ])

    if (detailRes.status === 'fulfilled' && detailRes.value?.success) {
      caseDetail.value = detailRes.value.data
    }
    if (evidencesRes.status === 'fulfilled' && evidencesRes.value?.success) {
      rawEvidences.value = evidencesRes.value.data || []
    }
    if (factsRes.status === 'fulfilled' && factsRes.value?.success) {
      rawFacts.value = factsRes.value.data || []
    }

    // 组织时间轴
    timelineNodes.value = buildTimeline(rawFacts.value, rawEvidences.value)
    selectedIndex.value = 0
  } catch (err) {
    notify({ title: '加载失败', message: err.message || '时间轴数据加载失败', type: 'error' })
  } finally {
    loading.value = false
  }
}

// ── 判断是否为碰撞时刻（用于红色高亮）──
function isCollisionNode(node) {
  if (!node) return false
  const text = `${node.time_label || ''} ${node.event_title || ''} ${node.event_desc || ''}`
  return /T0\b|碰撞|撞击|相撞|collision/i.test(text)
}

// ── 解析时间标签为秒数，用于排序 ──
function parseTimeLabel(label) {
  const m = String(label || '').match(/T\s*([+-]?\d+(?:\.\d+)?)\s*s?/i)
  if (m) return parseFloat(m[1])
  return 0
}

// ── 从证据中提取关键帧图片 ──
function extractKeyframes(evidences) {
  const frames = []
  ;(evidences || []).forEach(ev => {
    const type = String(ev.evidence_type || ev.type || '').toLowerCase()
    const isFrame =
      type.includes('frame') ||
      type.includes('keyframe') ||
      type.includes('关键帧') ||
      type.includes('image') ||
      type.includes('图片')
    const url = ev.frame_url || ev.url || ev.thumbnail || ev.file_url
    if (isFrame || url) {
      frames.push({
        url,
        name: ev.file_name || ev.name || '关键帧',
        source: ev.source || ev.evidence_type || ev.type || '视频证据',
        confidence: ev.confidence ?? ev.score ?? null
      })
    }
  })
  return frames
}

// ── 为节点匹配关键帧 ──
function pickFrame(frames, idx, fact) {
  if (!frames.length) return null
  // 优先使用事实自带的帧引用
  if (fact?.frame_url) return fact.frame_url
  if (fact?.frame_index != null && frames[fact.frame_index]) {
    return frames[fact.frame_index].url
  }
  // 按索引轮询匹配
  const frame = frames[idx % frames.length]
  return frame.url
}

// ── 组织时间轴数据：facts + evidences ──
function buildTimeline(facts, evidences) {
  const nodes = []
  const frames = extractKeyframes(evidences)

  // 1. 优先使用带时间标签的事实
  const timedFacts = (facts || [])
    .filter(f => f.time_label || f.time || f.timestamp)
    .sort((a, b) => parseTimeLabel(a.time_label || a.time) - parseTimeLabel(b.time_label || b.time))

  if (timedFacts.length > 0) {
    timedFacts.forEach((f, idx) => {
      nodes.push({
        time_label: f.time_label || f.time || `T+${idx}s`,
        event_title: f.title || f.fact_value || f.description || `关键事件 ${idx + 1}`,
        event_desc: f.description || f.fact_value || '',
        frame_url: pickFrame(frames, idx, f),
        confidence: f.confidence ?? f.score ?? null,
        evidence_source: f.source_type || f.source || '结构化事实'
      })
    })
    return nodes
  }

  // 2. 没有时间标签但有事实：按原始顺序展示，不伪造时间标签
  if (facts && facts.length > 0) {
    facts.forEach((f, idx) => {
      nodes.push({
        time_label: `事件 ${idx + 1}`,
        event_title: f.title || f.fact_value || f.fact_type || `事件 ${idx + 1}`,
        event_desc: f.description || f.fact_value || '',
        frame_url: pickFrame(frames, idx, f),
        confidence: f.confidence ?? f.score ?? null,
        evidence_source: f.source_type || f.source || '结构化事实'
      })
    })
    return nodes
  }

  // 3. 没有事实，仅有证据：用关键帧组织，不伪造时间标签
  if (frames.length > 0) {
    frames.forEach((fr, idx) => {
      nodes.push({
        time_label: `关键帧 ${idx + 1}`,
        event_title: fr.name,
        event_desc: fr.description || '关键帧截图',
        frame_url: fr.url,
        confidence: fr.confidence,
        evidence_source: fr.source
      })
    })
    return nodes
  }

  return nodes
}

// ── 当前节点的识别事实列表 ──
const nodeFacts = computed(() => {
  if (!currentNode.value) return []
  const facts = []
  // 当前节点自身事实
  if (currentNode.value.event_desc) {
    facts.push(currentNode.value.event_desc)
  }
  // 同时间标签的其他事实
  const sameTime = rawFacts.value.filter(f => {
    const label = f.time_label || f.time
    return label === currentNode.value.time_label &&
      (f.description || f.fact_value) !== currentNode.value.event_desc
  })
  sameTime.forEach(f => {
    const text = f.description || f.fact_value
    if (text && !facts.includes(text)) facts.push(text)
  })
  // 兜底：展示前几条结构化事实
  if (facts.length === 0 && rawFacts.value.length) {
    rawFacts.value.slice(0, 3).forEach(f => {
      const text = `${f.fact_type || ''}：${f.fact_value || ''}`.replace(/^：|：$/g, '')
      if (text && text !== '：') facts.push(text)
    })
  }
  return facts
})

// ── 置信度展示 ──
const confidencePercent = computed(() => {
  const c = currentNode.value?.confidence
  if (c == null) return 0
  const num = typeof c === 'number' ? c : parseFloat(c)
  if (isNaN(num)) return 0
  return num <= 1 ? num * 100 : num
})

const confidenceText = computed(() => {
  const c = currentNode.value?.confidence
  if (c == null) return '未评估'
  const num = typeof c === 'number' ? c : parseFloat(c)
  if (isNaN(num)) return String(c)
  return `${Math.round(num <= 1 ? num * 100 : num)}%`
})

// ── 节点切换 ──
function selectNode(index) {
  selectedIndex.value = index
}

// 切换节点时重置图片加载失败标记
watch(selectedIndex, () => {
  frameLoadError.value = false
})

function onImgError() {
  frameLoadError.value = true
}

// ── 页面初始化 ──
onMounted(async () => {
  await loadCases()
  // 优先使用路由参数中的 caseId，其次使用 store 中当前案件
  const queryCaseId = route.query.caseId
  const currentCase = getCurrentCase()
  const initialId = queryCaseId || currentCase
  if (initialId && cases.value.find(c => String(c.caseId) === String(initialId))) {
    selectedCaseId.value = String(initialId)
    await loadTimeline(selectedCaseId.value)
  }
})
</script>

<style scoped>
/* Apple 风格配色（局部变量，覆盖设计系统主色以符合复盘页风格） */
.timeline-page {
  --tl-primary: #007AFF;
  --tl-primary-soft: rgba(0, 122, 255, 0.1);
  --tl-bg: #F2F2F7;
  --tl-collision: #FF3B30;
  --tl-collision-soft: rgba(255, 59, 48, 0.1);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  animation: pageIn 0.4s var(--ease-default);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── 顶部标题 + 案件选择器 ── */
.page-header-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-5);
  flex-wrap: wrap;
}

.header-left { flex: 1; min-width: 220px; }

.page-title {
  font-size: 26px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: var(--tracking-tight);
  margin-bottom: var(--space-2);
}

.page-subtitle {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 400;
}

.case-selector {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.selector-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.selector-select {
  min-width: 280px;
  padding: 10px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: 500;
  font-family: var(--font-sans);
  outline: none;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-fast);
}

.selector-select:focus {
  border-color: var(--tl-primary);
  box-shadow: 0 0 0 3px var(--tl-primary-soft);
}

.selector-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ── 案件基本信息条 ── */
.case-info-bar {
  display: flex;
  gap: var(--space-6);
  flex-wrap: wrap;
  padding: var(--space-4) var(--space-6);
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
}

.case-info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-key {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.info-val {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
}

.status-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  background: var(--tl-primary-soft);
  color: var(--tl-primary);
  border-radius: var(--radius-full);
  font-size: 11px;
  width: fit-content;
}

/* ── 状态占位（加载/空数据）── */
.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: 80px var(--space-6);
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  text-align: center;
}

.state-icon {
  width: 56px;
  height: 56px;
  color: var(--text-muted);
  opacity: 0.5;
}

.state-text {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
}

.state-sub {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-light);
  border-top-color: var(--tl-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ── 时间轴主体：左右分栏 ── */
.timeline-container {
  display: grid;
  grid-template-columns: 30% 70%;
  gap: var(--space-6);
  align-items: stretch;
}

/* ── 左侧时间轴 ── */
.timeline-left {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  padding: var(--space-6) var(--space-5);
  position: relative;
}

.timeline-track {
  position: relative;
  padding-left: 8px;
}

/* 竖线 */
.timeline-track::before {
  content: '';
  position: absolute;
  left: 15px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: linear-gradient(180deg, var(--tl-primary) 0%, var(--border-light) 100%);
  border-radius: var(--radius-full);
}

.timeline-node {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-3) var(--space-5) 36px;
  cursor: pointer;
  border-radius: var(--radius-lg);
  transition: background var(--transition-fast);
}

.timeline-node:hover {
  background: var(--tl-bg);
}

/* 圆形节点 */
.node-dot {
  position: absolute;
  left: 9px;
  top: 14px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--bg-primary);
  border: 2px solid var(--tl-primary);
  box-shadow: 0 0 0 3px var(--bg-primary);
  transition: all var(--transition-normal);
  z-index: 1;
}

/* 碰撞节点：红色 */
.timeline-node.collision .node-dot {
  border-color: var(--tl-collision);
}

/* 选中节点：高亮放大 */
.timeline-node.active .node-dot {
  transform: scale(1.4);
  background: var(--tl-primary);
  box-shadow: 0 0 0 3px var(--bg-primary), 0 0 0 6px var(--tl-primary-soft);
}

.timeline-node.active.collision .node-dot {
  background: var(--tl-collision);
  box-shadow: 0 0 0 3px var(--bg-primary), 0 0 0 6px var(--tl-collision-soft);
}

.node-content {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-width: 0;
}

.node-time {
  font-size: 11px;
  font-weight: 700;
  color: var(--tl-primary);
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}

.timeline-node.collision .node-time {
  color: var(--tl-collision);
}

.node-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  line-height: var(--leading-snug);
  transition: color var(--transition-fast);
}

.timeline-node.active .node-title {
  color: var(--text-primary);
  font-weight: 600;
}

/* ── 右侧关键帧 + 事实 ── */
.timeline-right {
  min-width: 0;
}

.keyframe-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  padding: var(--space-6);
  height: 100%;
  /* 切换时淡入动画 */
  animation: fadeSlideIn 0.35s var(--ease-default);
}

@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 关键帧图片 */
.keyframe-image-wrap {
  position: relative;
  width: 100%;
  border-radius: var(--radius-xl);
  overflow: hidden;
  background: #000;
  aspect-ratio: 16 / 9;
}

.keyframe-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.time-overlay {
  position: absolute;
  top: var(--space-3);
  left: var(--space-3);
  padding: 5px 12px;
  border-radius: var(--radius-full);
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
  backdrop-filter: blur(8px);
}

.time-overlay.collision {
  background: var(--tl-collision);
}

/* 关键帧占位 */
.keyframe-placeholder {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-xl);
  background: var(--tl-bg);
  border: 1px dashed var(--border-medium);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
}

.placeholder-icon {
  width: 44px;
  height: 44px;
  color: var(--text-muted);
  opacity: 0.6;
}

.placeholder-text {
  color: var(--text-muted);
  font-size: var(--text-xs);
}

/* 事件信息 */
.event-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.event-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.event-time-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  background: var(--tl-primary-soft);
  color: var(--tl-primary);
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
}

.event-time-badge.collision {
  background: var(--tl-collision-soft);
  color: var(--tl-collision);
}

.event-title {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: var(--tracking-tight);
  line-height: var(--leading-tight);
}

.event-desc {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
}

/* 信息块 */
.info-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.block-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

/* 识别事实列表 */
.facts-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.fact-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--tl-bg);
  border-radius: var(--radius-md);
}

.fact-bullet {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--tl-primary);
  margin-top: 7px;
  flex-shrink: 0;
}

.fact-text {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: var(--leading-snug);
}

/* 证据来源 + 置信度 */
.info-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
}

.source-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  background: var(--tl-bg);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 500;
  width: fit-content;
}

.confidence-display {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.confidence-bar {
  flex: 1;
  height: 8px;
  background: var(--tl-bg);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.confidence-fill {
  height: 100%;
  background: var(--tl-primary);
  border-radius: var(--radius-full);
  transition: width var(--duration-slow) var(--ease-default);
}

.confidence-fill.fill-collision {
  background: var(--tl-collision);
}

.confidence-text {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
  min-width: 48px;
  text-align: right;
}

.empty-inline {
  color: var(--text-muted);
  font-size: var(--text-xs);
  padding: var(--space-2) 0;
}

/* ── 响应式：小屏幕改为上下布局 ── */
@media (max-width: 1024px) {
  .timeline-container {
    grid-template-columns: 1fr;
  }

  .timeline-left {
    order: 1;
  }

  .timeline-right {
    order: 2;
  }

  /* 小屏幕下时间轴改为横向滚动 */
  .timeline-track {
    display: flex;
    overflow-x: auto;
    padding-left: 0;
    padding-bottom: var(--space-2);
    gap: var(--space-2);
  }

  .timeline-track::before {
    display: none;
  }

  .timeline-node {
    flex-direction: column;
    padding: var(--space-3);
    min-width: 140px;
    border: 1px solid var(--border-light);
  }

  .node-dot {
    position: static;
    margin-bottom: var(--space-2);
  }
}

@media (max-width: 768px) {
  .page-header-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .selector-select {
    min-width: 0;
    width: 100%;
  }

  .case-info-bar {
    gap: var(--space-4);
  }

  .info-row {
    grid-template-columns: 1fr;
  }

  .keyframe-card {
    padding: var(--space-4);
  }
}
</style>
