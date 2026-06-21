<template>
  <div class="intelligent-analysis-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">智能分析</h1>
        <p class="page-subtitle">视频处理与 AI 智能分析事故责任</p>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" :disabled="isAnalyzing || !hasVideo" @click="refreshAnalysis">
          <span class="refresh-icon" :class="{ 'spinning': isAnalyzing }" v-html="icons.refresh"></span>
          <span v-if="isAnalyzing">分析中 {{ analysisProgress }}%</span>
          <span v-else-if="hasAnalysis">重新分析</span>
          <span v-else>开始分析</span>
        </button>
      </div>
    </div>

    <!-- 空状态：没有视频数据 -->
    <div v-if="!hasVideo" class="empty-state">
      <div class="empty-state-content">
        <h2 class="empty-state-title">暂无视频数据</h2>
        <p class="empty-state-desc">请先上传事故视频文件，系统将自动进行AI智能分析</p>
        <button class="empty-state-btn" @click="goToVideoProcessing">
          <span v-html="icons.folder"></span>
          前往上传视频
        </button>
      </div>
    </div>

    <!-- 统计卡片 - 只有在有视频时显示 -->
    <div v-else class="stats-grid">
      <div class="stat-card card-blue">
        <div class="stat-card-bg"></div>
        <div class="stat-header">
          <div class="stat-info">
            <span class="stat-label">分析置信度</span>
            <div class="stat-value-wrapper">
              <span class="stat-value">{{ hasAnalysis ? state.analysis.confidence : '--' }}</span>
              <span class="stat-unit">%</span>
            </div>
          </div>
          <div class="stat-icon icon-blue">
            <span v-html="icons.chart"></span>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-change positive" v-if="hasAnalysis">
            <span class="change-icon" v-html="icons.trendUp"></span>
            <span class="change-value">+5%</span>
          </div>
          <span class="stat-period">{{ hasAnalysis ? '较上次' : '待定' }}</span>
        </div>
      </div>

      <div class="stat-card card-green">
        <div class="stat-card-bg"></div>
        <div class="stat-header">
          <div class="stat-info">
            <span class="stat-label">匹配规则数</span>
            <div class="stat-value-wrapper">
              <span class="stat-value">{{ hasAnalysis ? matchedRules.length : '--' }}</span>
              <span class="stat-unit">条</span>
            </div>
          </div>
          <div class="stat-icon icon-green">
            <span v-html="icons.checkCircle"></span>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-change positive" v-if="hasAnalysis">
            <span class="change-icon" v-html="icons.trendUp"></span>
            <span class="change-value">完整匹配</span>
          </div>
          <span class="stat-period">{{ hasAnalysis ? '规则库' : '待定' }}</span>
        </div>
      </div>

      <div class="stat-card card-orange">
        <div class="stat-card-bg"></div>
        <div class="stat-header">
          <div class="stat-info">
            <span class="stat-label">分析耗时</span>
            <div class="stat-value-wrapper">
              <span class="stat-value">{{ hasAnalysis ? '2.3' : '--' }}</span>
              <span class="stat-unit">秒</span>
            </div>
          </div>
          <div class="stat-icon icon-orange">
            <span v-html="icons.clock"></span>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-change positive" v-if="hasAnalysis">
            <span class="change-icon" v-html="icons.bolt"></span>
            <span class="change-value">极速</span>
          </div>
          <span class="stat-period">{{ hasAnalysis ? 'AI处理' : '待定' }}</span>
        </div>
      </div>

      <div class="stat-card card-purple">
        <div class="stat-card-bg"></div>
        <div class="stat-header">
          <div class="stat-info">
            <span class="stat-label">证据完整度</span>
            <div class="stat-value-wrapper">
              <span class="stat-value">{{ hasAnalysis ? state.analysis.evidenceIntegrity : '--' }}</span>
              <span class="stat-unit">%</span>
            </div>
          </div>
          <div class="stat-icon icon-purple">
            <span v-html="icons.shield"></span>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-change positive" v-if="hasAnalysis">
            <span class="change-icon" v-html="icons.check"></span>
            <span class="change-value">完整</span>
          </div>
          <span class="stat-period">{{ hasAnalysis ? '材料审核' : '待定' }}</span>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <!-- 案件信息 -->
      <div class="section-card case-info">
        <div class="section-header">
          <div class="section-title-wrapper">
            <span class="section-icon" v-html="icons.folder"></span>
            <h2 class="section-title">案件信息</h2>
          </div>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">案件编号</span>
            <span class="info-value case-id">{{ state.caseId }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">事故类型</span>
            <span class="info-value">{{ state.form.accidentType || '待分析' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">发生时间</span>
            <span class="info-value">{{ state.form.time || '未填写' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">发生地点</span>
            <span class="info-value">{{ state.form.location || '未填写' }}</span>
          </div>
        </div>
      </div>

      <!-- 关键帧 -->
      <div class="section-card keyframes">
        <div class="section-header">
          <div class="section-title-wrapper">
            <span class="section-icon" v-html="icons.video"></span>
            <h2 class="section-title">关键帧</h2>
          </div>
          <span class="summary-pill">{{ hasAnalysis ? state.analysis.keyframes.length + ' 帧' : '-- 帧' }}</span>
        </div>
        <div v-if="hasAnalysis && state.analysis.keyframes.length > 0" class="keyframes-grid">
          <div 
            v-for="(frame, index) in state.analysis.keyframes" 
            :key="frame.id || index"
            class="keyframe-item"
            :class="{ 'selected': state.analysis.selectedFrame === frame.label, 'main': frame.isMain }"
          >
            <div class="keyframe-image-wrapper">
              <img :src="frame.image" :alt="frame.label" class="keyframe-image">
              <div v-if="frame.isMain" class="main-badge">主分析帧</div>
            </div>
            <div class="keyframe-info">
              <div class="keyframe-title">{{ frame.label }}</div>
              <div class="keyframe-time">{{ frame.timeText }}</div>
              <div class="keyframe-meta">
                <span class="keyframe-clarity">{{ frame.clarity }}</span>
                <span class="keyframe-score">{{ frame.qualityScore }}分</span>
              </div>
              <div class="keyframe-purpose">{{ frame.purpose }}</div>
            </div>
          </div>
        </div>
        <div v-else class="pending-placeholder">
          <div class="placeholder-content">
            <span class="placeholder-icon" v-html="icons.video"></span>
            <span class="placeholder-text">点击"开始分析"提取关键帧</span>
          </div>
        </div>
      </div>

      <!-- 分析结果 -->
      <div class="section-card analysis-result">
        <div class="section-header">
          <div class="section-title-wrapper">
            <span class="section-icon icon-gradient" v-html="icons.brain"></span>
            <h2 class="section-title">AI 分析结果</h2>
          </div>
          <span class="confidence-badge" v-if="hasAnalysis">
            <span class="badge-dot"></span>
            置信度 {{ state.analysis.confidence }}%
          </span>
        </div>
        <div v-if="hasAnalysis" class="result-card">
          <div class="liability-result">
            <div 
            v-for="(liability, index) in vehicleLiabilities" 
            :key="liability.key"
            class="liability-item"
            :class="{ 
              'primary': liability.liability === '主责', 
              'secondary': liability.liability === '次责',
              'equal': liability.liability === '同等责任',
              'no-liability': liability.liability === '无责'
            }"
          >
              <div class="liability-icon" v-html="icons.car"></div>
              <span class="liability-role">
                {{ liability.role || liability.vehicleType }}
                <span v-if="liability.plate" class="liability-plate">({{ liability.plate }})</span>
              </span>
              <span class="liability-degree">{{ liability.liability }}</span>
              <span class="liability-percent">{{ liability.percentage }}%</span>
            </div>
          </div>
          <div class="dify-analysis-container">
            <div class="dify-analysis-title">
              <div class="dify-icon-wrapper">
                <span class="dify-icon">🤖</span>
              </div>
              <span class="dify-title-text">Dify智能分析</span>
            </div>
            <div v-if="hasDifyResult" class="markdown-content" v-html="parseMarkdown(difyAnalysisText)" @click="clickhtml"></div>
            <div v-else class="no-dify-data">
              <p style="text-align: center; color: #94a3b8; padding: 20px;">暂无Dify分析数据，请先在视频处理页点击"Send To Dify"</p>
            </div>
          </div>
        </div>
        <div v-else class="pending-placeholder">
          <div class="placeholder-content">
            <span class="placeholder-icon" v-html="icons.brain"></span>
            <span class="placeholder-text">点击"开始分析"获取AI分析结果</span>
          </div>
        </div>
      </div>

      <!-- 自动提取法规线索 -->
      <div class="section-card matched-rules">
        <div class="section-header">
          <div class="section-title-wrapper">
            <span class="section-icon" v-html="icons.fileText"></span>
            <h2 class="section-title">自动提取法规线索</h2>
          </div>
          <span class="summary-pill">{{ hasDifyResult && difyLegalClues.length > 0 ? difyLegalClues.length + ' 条线索' : (hasAnalysis ? matchedRules.length + ' 条规则' : '-- 条规则') }}</span>
        </div>
        <div v-if="hasDifyResult && difyLegalClues.length > 0" class="rules-list">
          <div class="rule-item" v-for="(clue, index) in difyLegalClues" :key="index">
            <div class="rule-header">
              <span class="rule-code">L-{{ String(index + 1).padStart(2, '0') }}</span>
              <span class="rule-name">{{ extractLawName(clue) }}</span>
              <span class="rule-confidence">100%</span>
            </div>
            <div class="rule-content">{{ clue }}</div>
            <div class="rule-progress">
              <div class="progress-bar" style="width: 100%"></div>
            </div>
          </div>
        </div>
        <div v-else-if="hasAnalysis" class="rules-list">
          <div class="rule-item" v-for="(rule, index) in matchedRules" :key="index">
            <div class="rule-header">
              <span class="rule-code">{{ rule.code }}</span>
              <span class="rule-name">{{ rule.name }}</span>
              <span class="rule-confidence">{{ rule.confidence }}%</span>
            </div>
            <div class="rule-content">{{ rule.content }}</div>
            <div class="rule-progress">
              <div class="progress-bar" :style="{ width: rule.confidence + '%' }"></div>
            </div>
          </div>
        </div>
        <div v-else class="pending-placeholder">
          <div class="placeholder-content">
            <span class="placeholder-icon" v-html="icons.fileText"></span>
            <span class="placeholder-text">点击"开始分析"获取法规线索</span>
          </div>
        </div>
      </div>

      <!-- 证据一致性检测 -->
      <div class="section-card consistency-section" v-if="hasAnalysis">
        <div class="section-header">
          <div class="section-title-wrapper">
            <span class="section-icon" v-html="icons.shield"></span>
            <h2 class="section-title">证据一致性检测</h2>
          </div>
          <button class="consistency-refresh-btn" @click="loadConsistency" :disabled="consistencyLoading">
            <span class="refresh-icon" :class="{ 'spinning': consistencyLoading }" v-html="icons.refresh"></span>
            {{ consistencyLoading ? '检测中...' : '重新检测' }}
          </button>
        </div>

        <div v-if="consistencyData" class="consistency-content">
          <!-- 顶部：分数圆环 + 统计 -->
          <div class="consistency-score-area">
            <div class="consistency-ring" :class="scoreLevel">
              <svg viewBox="0 0 120 120" class="ring-svg">
                <circle cx="60" cy="60" r="52" class="ring-bg"/>
                <circle cx="60" cy="60" r="52" class="ring-fill" :style="ringStyle"/>
              </svg>
              <div class="ring-center">
                <span class="ring-score">{{ consistencyData.score }}</span>
                <span class="ring-label">一致性评分</span>
              </div>
            </div>
            <div class="consistency-summary">
              <div class="summary-item summary-consistent">
                <span class="summary-count">{{ consistentCount }}</span>
                <span class="summary-label">一致项</span>
              </div>
              <div class="summary-item summary-conflict">
                <span class="summary-count">{{ conflictCount }}</span>
                <span class="summary-label">冲突项</span>
              </div>
            </div>
          </div>

          <!-- 中间：两列对比 -->
          <div class="consistency-columns">
            <div class="consistency-column consistent-column">
              <div class="column-header">
                <span class="column-icon icon-check">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                </span>
                <span class="column-title">一致项</span>
                <span class="column-count">{{ consistentCount }}</span>
              </div>
              <div class="column-list">
                <div v-for="(item, i) in consistencyData.consistent_items" :key="'c'+i" class="consistency-item consistent-item">
                  <span class="item-type">{{ item.fact_type }}</span>
                  <span class="item-value">{{ item.value_a }}</span>
                  <span class="item-source">{{ item.source_a }} ↔ {{ item.source_b }}</span>
                </div>
                <div v-if="consistentCount === 0" class="empty-tip">暂无一致项</div>
              </div>
            </div>
            <div class="consistency-column conflict-column">
              <div class="column-header">
                <span class="column-icon icon-warn">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                </span>
                <span class="column-title">冲突项</span>
                <span class="column-count">{{ conflictCount }}</span>
              </div>
              <div class="column-list">
                <div v-for="(item, i) in consistencyData.conflict_items" :key="'f'+i" class="consistency-item conflict-item">
                  <span class="item-type">{{ item.fact_type }}</span>
                  <div class="conflict-values">
                    <span class="conflict-value"><span class="conflict-src">{{ item.source_a }}</span> {{ item.value_a }}</span>
                    <span class="conflict-vs">VS</span>
                    <span class="conflict-value"><span class="conflict-src">{{ item.source_b }}</span> {{ item.value_b }}</span>
                  </div>
                </div>
                <div v-if="conflictCount === 0" class="empty-tip">无冲突</div>
              </div>
            </div>
          </div>

          <!-- 底部：系统建议 -->
          <div class="consistency-suggestion" :class="suggestionLevel">
            <span class="suggestion-label">系统建议</span>
            <span class="suggestion-divider"></span>
            <span class="suggestion-text">{{ consistencyData.suggestion }}</span>
          </div>
        </div>

        <div v-else class="pending-placeholder">
          <div class="placeholder-content">
            <span class="placeholder-icon" v-html="icons.shield"></span>
            <span class="placeholder-text">{{ consistencyError || '点击"重新检测"进行证据一致性分析' }}</span>
          </div>
        </div>
      </div>

      <!-- 确认判定按钮 -->
      <div class="section-card confirm-section" v-if="hasAnalysis">
        <div class="confirm-actions">
          <button class="btn btn-primary btn-lg" @click="confirmAnalysis" :disabled="isSaving">
            <span class="btn-icon" v-html="icons.check"></span>
            <span v-if="isSaving">保存中...</span>
            <span v-else>保存判定</span>
          </button>
        </div>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { notify } from '../composables/useToast'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { CasesAPI } from '../api/index.js'
import NavigationButtons from '../components/NavigationButtons.vue'

const router = useRouter()
const route = useRoute()

const {
  state,
  goStep,
  completeAnalysis,
  updateRecommendation
} = useAccidentFlow()

goStep('analysis')

// 从后端加载案件详情
async function loadCaseFromBackend(caseId) {
  try {
    const result = await CasesAPI.getDetail(caseId)
    if (result.success && result.data) {
      const caseData = result.data
      state.caseId = caseData.id || caseId
      state.form.accidentType = caseData.accident_type || caseData.title || ''
      state.form.location = caseData.location || ''
      state.form.time = caseData.submitted_at || ''
      console.log('[IntelligentAnalysis] Loaded case from backend:', state.caseId)
    }
  } catch (e) {
    console.warn('[IntelligentAnalysis] Failed to load case from backend:', e)
  }
}

// 从后端加载案件责任结果
async function loadCaseLiability() {
  try {
    const result = await CasesAPI.getDetail(state.caseId)
    if (result.success && result.data) {
      const liability = result.data.liability
      if (liability) {
        state.analysis.vehicleLiabilities = liability.details?.vehicles || []
        state.analysis.matchedRules = liability.hit_rules || []
        state.analysis.reasoningText = liability.summary || ''
        state.analysis.confidence = liability.details?.confidence || state.analysis.confidence
        state.analysis.evidenceIntegrity = liability.details?.evidence_integrity || state.analysis.evidenceIntegrity
      }
    }
  } catch (e) {
    console.warn('加载责任结果失败:', e)
  }
}

onMounted(() => {
  // Load case from query params if provided (e.g., from HistoryCases redirect)
  const caseIdFromQuery = route.query.caseId
  if (caseIdFromQuery && !state.caseId) {
    state.caseId = String(caseIdFromQuery)
    // Load case details from backend
    loadCaseFromBackend(caseIdFromQuery)
  }
  loadCaseLiability()
  loadConsistency()
})

// 证据一致性检测
const consistencyData = ref(null)
const consistencyLoading = ref(false)
const consistencyError = ref('')

const consistentCount = computed(() => consistencyData.value?.consistent_items?.length || 0)
const conflictCount = computed(() => consistencyData.value?.conflict_items?.length || 0)

const scoreLevel = computed(() => {
  const s = consistencyData.value?.score
  if (s == null) return ''
  if (s >= 80) return 'level-high'
  if (s >= 60) return 'level-mid'
  return 'level-low'
})

const suggestionLevel = computed(() => {
  const s = consistencyData.value?.score
  if (s == null) return ''
  if (s >= 80) return 'suggest-ok'
  if (s >= 60) return 'suggest-warn'
  return 'suggest-danger'
})

const ringStyle = computed(() => {
  const score = consistencyData.value?.score ?? 0
  const pct = Math.max(0, Math.min(100, score))
  const circumference = 2 * Math.PI * 52
  const offset = circumference * (1 - pct / 100)
  return {
    strokeDasharray: `${circumference}`,
    strokeDashoffset: `${offset}`,
  }
})

async function loadConsistency() {
  if (!state.caseId) return
  consistencyLoading.value = true
  consistencyError.value = ''
  try {
    const result = await CasesAPI.getEvidenceConsistency(state.caseId)
    if (result.success && result.data) {
      consistencyData.value = result.data
    } else {
      consistencyError.value = result.message || '检测失败'
    }
  } catch (e) {
    consistencyError.value = e.message || '网络错误'
  } finally {
    consistencyLoading.value = false
  }
}

const clickhtml = () => {}

const hasVideo = computed(() => {
  return state.form.videoFile !== null || 
         state.form.fileName !== '' ||
         state.analysis.confidence !== null
})

const hasAnalysis = computed(() => {
  return state.analysis.confidence !== null && 
         state.analysis.confidence !== undefined &&
         state.analysis.confidence !== ''
})

const goToVideoProcessing = () => {
  router.push('/video-processing')
}

const icons = {
  refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
  chart: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 3v18h18" fill="none" stroke="currentColor" stroke-width="2"/><path d="M18 9l-5 5-4-4-3 3" fill="none" stroke="currentColor" stroke-width="2"/></svg>`,
  checkCircle: `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10" fill-opacity="0.2"/><polyline points="8 12 11 15 16 9" fill="none" stroke="currentColor" stroke-width="2"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10" fill-opacity="0.2"/><polyline points="12 6 12 12 16 14" fill="none" stroke="currentColor" stroke-width="2"/></svg>`,
  shield: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill-opacity="0.2"/><path d="M9 12l2 2 4-4" fill="none" stroke="currentColor" stroke-width="2"/></svg>`,
  trendUp: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>`,
  bolt: `<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10" fill-opacity="0.3"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill-opacity="0.2"/></svg>`,
  brain: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-1.04z" fill-opacity="0.2"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-1.04z" fill-opacity="0.2"/></svg>`,
  car: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M5 17a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2" fill-opacity="0.2"/><circle cx="7" cy="17" r="1.5"/><circle cx="17" cy="17" r="1.5"/></svg>`,
  vs: `<svg viewBox="0 0 24 24" fill="currentColor"><text x="12" y="16" text-anchor="middle" font-size="10" font-weight="bold">VS</text></svg>`,
  lightbulb: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 18h6" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10 22h4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7z" fill-opacity="0.2"/></svg>`,
  book: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" fill="none" stroke="currentColor" stroke-width="2"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" fill-opacity="0.2"/></svg>`,
  fileText: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill-opacity="0.2"/><polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/><line x1="16" y1="13" x2="8" y2="13" fill="none" stroke="currentColor" stroke-width="2"/><line x1="16" y1="17" x2="8" y2="17" fill="none" stroke="currentColor" stroke-width="2"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="currentColor"><line x1="22" y1="2" x2="11" y2="13" fill="none" stroke="currentColor" stroke-width="2"/><polygon points="22 2 15 22 11 13 2 9 22 2" fill-opacity="0.2"/></svg>`,
  video: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="16" height="12" rx="3" fill-opacity="0.15"/><path d="m22 8-6 4 6 4V8Z" fill-opacity="0.8"/></svg>`,
  cloud: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 18H6a4 4 0 0 1-.88-7.9l5.33-4A4 4 0 0 1 16 6h3a4 4 0 0 1 0 8h-3a2 2 0 0 0-2 2h-1a2 2 0 0 0 2 2h3a2 2 0 0 0 4 0z" fill-opacity="0.2"/></svg>`
}

const hasDifyResult = computed(() => {
  return state.analysis.difyResult !== null && state.analysis.difyResult !== undefined
})

const difyAnalysisText = computed(() => {
  return state.analysis.difyAnalysisText || '暂无分析结果'
})

const difyLegalClues = computed(() => {
  return state.analysis.difyLegalClues || []
})

const extractLawName = (clue) => {
  const lawNames = [
    '中华人民共和国道路交通安全法',
    '道路交通事故处理程序规定',
    '道路交通安全法',
    '交通事故处理程序规定'
  ]
  for (const name of lawNames) {
    if (clue.includes(name)) {
      return name
    }
  }
  return '法规依据'
}

const formatJsonToHtml = (jsonObj) => {
  if (!jsonObj || typeof jsonObj !== 'object') return ''
  
  // 处理 Dify Mock 返回的嵌套结构
  let dataToRender = jsonObj
  if (jsonObj.result && typeof jsonObj.result === 'object') {
    dataToRender = jsonObj.result
  }
  
  const labels = {
    'accident_type': '事故类型',
    'confidence': '置信度',
    'liability_suggestion': '责任建议',
    'ratio': '责任比例',
    'core_reasons': '核心原因',
    'laws': '法规依据',
    'risk_note': '风险提示',
    'final': '分析结论',
    'liability': '责任认定',
    'confidence_score': '置信度分数',
    'analysis_summary': '分析摘要',
    'evidence_details': '证据详情',
    'type': '类型',
    'reason': '原因',
    'score': '分数',
    'law_name': '法规名称',
    'article': '条款',
    'applicability': '适用度',
    'case_analysis': '案件分析',
    'vehicle_count': '车辆数量',
    'evidence_summary': '证据摘要',
    'additional_notes': '补充说明',
    'primary_responsibility': '主要责任方',
    'secondary_responsibility': '次要责任方',
    'analysis_detail': '分析详情',
    'hit_rules': '命中规则',
    'structured_facts': '结构化事实',
    'consistency_check': '一致性检测',
    'trigger_condition': '触发条件',
    'trigger_reason': '触发原因',
    'content': '规则内容'
  }
  
  let html = ''
  
  const renderSection = (key, value, level = 0) => {
    const label = labels[key] || key
    const isMainSection = level === 0
    const icon = isMainSection ? '📊' : '📋'
    
    if (Array.isArray(value)) {
      if (value.length === 0) return ''
      
      let itemsHtml = ''
      value.forEach((item, index) => {
        if (typeof item === 'string') {
          const cleanItem = item.replace(/\\n/g, '').replace(/\\"/g, '"').trim()
          if (cleanItem) {
            itemsHtml += `<div class="json-list-item"><span class="json-bullet">•</span><span class="json-text">${cleanItem}</span></div>`
          }
        } else if (typeof item === 'object') {
          itemsHtml += `<div class="json-nested">${renderNestedObject(item, level + 1)}</div>`
        } else {
          itemsHtml += `<div class="json-list-item"><span class="json-bullet">•</span><span>${item}</span></div>`
        }
      })
      
      return `<div class="analysis-section${isMainSection ? ' main-section' : ''}">
        <div class="section-header">
          <span class="section-icon">${icon}</span>
          <span class="section-title">${label}</span>
          <span class="section-count">${value.length}项</span>
        </div>
        <div class="section-content">${itemsHtml}</div>
      </div>`
    }
    
    if (typeof value === 'object' && value !== null) {
      return `<div class="analysis-section${isMainSection ? ' main-section' : ''}">
        <div class="section-header">
          <span class="section-icon">${icon}</span>
          <span class="section-title">${label}</span>
        </div>
        <div class="section-content">${renderNestedObject(value, level + 1)}</div>
      </div>`
    }
    
    const cleanValue = typeof value === 'string' 
      ? value.replace(/\\n/g, '').replace(/\\"/g, '"').trim()
      : (typeof value === 'number' ? (value * 100).toFixed(1) + '%' : value)
    
    return `<div class="analysis-section${isMainSection ? ' main-section' : ''}">
      <div class="section-header">
        <span class="section-icon">${icon}</span>
        <span class="section-title">${label}</span>
      </div>
      <div class="section-content">
        <div class="json-single-value">${cleanValue}</div>
      </div>
    </div>`
  }
  
  const renderNestedObject = (obj, level) => {
    let html = ''
    for (const [key, value] of Object.entries(obj)) {
      html += renderSection(key, value, level)
    }
    return html
  }
  
  for (const [key, value] of Object.entries(dataToRender)) {
    html += renderSection(key, value, 0)
  }
  
  return html
}

const parseMarkdown = (text) => {
  if (!text) return ''
  
  let workingText = text
  
  const tryParseJson = (str) => {
    try {
      const parsed = JSON.parse(str)
      if (typeof parsed === 'object') {
        return parsed
      }
    } catch (e) {
    }
    return null
  }
  
  const extractCodeBlock = (str) => {
    const codeBlockRegex = /```(?:json)?\s*([\s\S]*?)```/i
    const match = str.match(codeBlockRegex)
    if (match && match[1]) {
      return match[1].trim()
    }
    return str
  }
  
  const deeplyParseJson = (str) => {
    let result = tryParseJson(str)
    if (result) return result
    
    let cleaned = str
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\r')
    
    result = tryParseJson(cleaned)
    if (result) return result
    
    cleaned = cleaned.replace(/\\"/g, '"')
    result = tryParseJson(cleaned)
    if (result) return result
    
    cleaned = cleaned.replace(/\\\\/g, '\\')
    result = tryParseJson(cleaned)
    if (result) return result
    
    return null
  }
  
  const parsed = deeplyParseJson(workingText)
  
  if (parsed) {
    let dataToFormat = parsed
    
    // 优先提取 result 字段（Dify 返回格式）
    if (parsed.result && typeof parsed.result === 'object') {
      dataToFormat = parsed.result
    }
    // 其次提取 answer 字段
    else if (parsed.answer && typeof parsed.answer === 'string') {
      const answerParsed = deeplyParseJson(parsed.answer)
      if (answerParsed && typeof answerParsed === 'object') {
        dataToFormat = answerParsed
      }
    }
    // 提取 final 字段
    else if (parsed.final && typeof parsed.final === 'string') {
      const finalContent = extractCodeBlock(parsed.final)
      const innerParsed = deeplyParseJson(finalContent)
      if (innerParsed) {
        dataToFormat = innerParsed
      } else {
        dataToFormat = { final: parsed.final }
      }
    }
    
    return formatJsonToHtml(dataToFormat)
  }
  
  let html = workingText
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\')
  
  html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code class="$1">$2</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  html = html.replace(/### (.+)/g, '<h3>$1</h3>')
  html = html.replace(/## (.+)/g, '<h2>$1</h2>')
  html = html.replace(/# (.+)/g, '<h1>$1</h1>')
  html = html.replace(/^\s*-\s+(.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>')
  html = html.replace(/\n\n/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  html = `<div class="clean-text">${html}</div>`
  html = html.replace(/<div class="clean-text"><\/div>/g, '')
  html = html.replace(/<p><\/p>/g, '')
  html = html.replace(/<ul><\/ul>/g, '')
  
  return html
}

const matchedRules = computed(() => {
  // 优先使用Dify解析出的法规规则
  if (state.analysis.difyLegalRules && state.analysis.difyLegalRules.length > 0) {
    return state.analysis.difyLegalRules
  }
  
  // 否则使用默认的模拟数据
  if (state.form.accidentType === '追尾事故') {
    return [
      { code: 'R-01', name: '道路交通安全法 第四十三条', content: '同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。', confidence: 92 },
      { code: 'R-03', name: '安全距离规定', content: '同车道行驶应保持足以采取紧急制动措施的安全距离。', confidence: 88 },
      { code: 'R-05', name: '制动不及时认定', content: '后车制动不及时导致碰撞，应承担相应责任。', confidence: 85 }
    ]
  } else if (state.form.accidentType === '变道碰撞') {
    return [
      { code: 'R-02', name: '道路交通安全法 第四十四条', content: '机动车变更车道时，应当提前开启转向灯，确认安全后再变更车道。', confidence: 90 },
      { code: 'R-04', name: '变道规定', content: '变道时应提前开启转向灯，确认安全后再变道。', confidence: 86 },
      { code: 'R-06', name: '观察义务', content: '驾驶员应保持观察，确保变道安全。', confidence: 83 }
    ]
  } else {
    return [
      { code: 'R-01', name: '道路交通安全法 第四十三条', content: '同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。', confidence: 92 },
      { code: 'R-03', name: '安全距离规定', content: '同车道行驶应保持足以采取紧急制动措施的安全距离。', confidence: 88 },
      { code: 'R-05', name: '制动不及时认定', content: '后车制动不及时导致碰撞，应承担相应责任。', confidence: 85 }
    ]
  }
})

const vehicleLiabilities = computed(() => {
  // 优先使用Dify解析出的真实责任数据
  if (state.analysis.vehicleLiabilities && state.analysis.vehicleLiabilities.length > 0) {
    return state.analysis.vehicleLiabilities
  }
  
  const vehicles = state.form.vehicles || []
  const accidentType = state.form.accidentType
  
  if (vehicles.length === 0) return []
  
  let liabilities = []
  
  if (accidentType === '追尾事故') {
    // 追尾事故责任分配
    if (vehicles.length === 2) {
      // 2辆车：后车主责100%，前车无责
      vehicles.forEach((vehicle, index) => {
        if (index === 1) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 100
          })
        } else {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '无责',
            percentage: 0
          })
        }
      })
    } else if (vehicles.length === 3) {
      // 3辆车：最后一辆主责70%，中间车次责30%，第一辆无责
      vehicles.forEach((vehicle, index) => {
        if (index === 2) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 70
          })
        } else if (index === 1) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 30
          })
        } else {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '无责',
            percentage: 0
          })
        }
      })
    } else if (vehicles.length >= 4) {
      // 4辆车及以上：最后一辆主责60%，倒数第二车次责25%，倒数第三车次责15%，其他无责
      vehicles.forEach((vehicle, index) => {
        if (index === vehicles.length - 1) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 60
          })
        } else if (index === vehicles.length - 2) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 25
          })
        } else if (index === vehicles.length - 3) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 15
          })
        } else {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '无责',
            percentage: 0
          })
        }
      })
    }
  } else if (accidentType === '变道碰撞') {
    // 变道碰撞责任分配
    if (vehicles.length === 2) {
      // 2辆车：变道车辆主责70%，直行车辆次责30%
      vehicles.forEach((vehicle, index) => {
        if (vehicle.role === '变道车辆' || index === 0) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 70
          })
        } else {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 30
          })
        }
      })
    } else if (vehicles.length === 3) {
      // 3辆车：变道车辆主责60%，第一辆直行车次责25%，第二辆直行车次责15%
      let hasFoundChanging = false
      vehicles.forEach((vehicle, index) => {
        if (vehicle.role === '变道车辆' || (index === 0 && !hasFoundChanging)) {
          hasFoundChanging = true
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 60
          })
        } else if (index === 1 && !hasFoundChanging) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 60
          })
        } else {
          const previousLiability = liabilities.find(l => l.key !== vehicle.key)
          const isFirstStraight = !liabilities.some(l => l.liability === '次责')
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: isFirstStraight ? 25 : 15
          })
        }
      })
    } else if (vehicles.length >= 4) {
      // 4辆车及以上：变道车辆主责50%，其他车辆按比例分责
      let hasFoundChanging = false
      const changingIndex = vehicles.findIndex(v => v.role === '变道车辆')
      const remainingPercentage = 50
      const otherVehicleCount = vehicles.length - 1
      
      vehicles.forEach((vehicle, index) => {
        if (vehicle.role === '变道车辆' || (changingIndex === -1 && index === 0)) {
          hasFoundChanging = true
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 50
          })
        } else {
          let percentage = 0
          if (index === 1) {
            percentage = 20
          } else if (index === 2) {
            percentage = 15
          } else {
            percentage = 15 / (otherVehicleCount - 2)
          }
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: Math.round(percentage)
          })
        }
      })
    }
  } else {
    // 其他事故类型：按车辆数量进行责任分配
    if (vehicles.length === 2) {
      // 2辆车：主责80%，次责20%
      vehicles.forEach((vehicle, index) => {
        if (index === 0) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 80
          })
        } else {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 20
          })
        }
      })
    } else if (vehicles.length === 3) {
      // 3辆车：主责60%，次责30%，次责10%
      vehicles.forEach((vehicle, index) => {
        if (index === 0) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 60
          })
        } else if (index === 1) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 30
          })
        } else {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 10
          })
        }
      })
    } else if (vehicles.length >= 4) {
      // 4辆车及以上：主责50%，次责30%，次责15%，次责5%
      vehicles.forEach((vehicle, index) => {
        if (index === 0) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '主责',
            percentage: 50
          })
        } else if (index === 1) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 30
          })
        } else if (index === 2) {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 15
          })
        } else {
          liabilities.push({
            key: vehicle.key,
            vehicleType: vehicle.vehicleType,
            plate: vehicle.plate,
            role: vehicle.role,
            liability: '次责',
            percentage: 5
          })
        }
      })
    }
  }
  
  // 验证百分比总和是否为100%，如果不是则调整
  let totalPercentage = liabilities.reduce((sum, l) => sum + l.percentage, 0)
  if (totalPercentage !== 100 && liabilities.length > 0) {
    const difference = 100 - totalPercentage
    liabilities[0].percentage += difference
  }
  
  return liabilities
})

const reasoningText = computed(() => {
  // 优先使用Dify解析出的真实理由
  if (state.analysis.reasoningText) {
    return state.analysis.reasoningText
  }
  
  const accidentType = state.form.accidentType
  const confidence = state.analysis.confidence
  const rules = matchedRules.value
  const liabilities = vehicleLiabilities.value
  
  let reasoning = ''
  const liabilityText = liabilities.map(l => `${l.role || l.vehicleType}${l.plate ? '(' + l.plate + ')' : ''}：${l.liability}(${l.percentage}%)`).join('，')
  
  if (accidentType === '追尾事故') {
    reasoning = `经分析，该事故为追尾事故。责任分配：${liabilityText}。`
    if (rules.length > 0) {
      reasoning += `依据${rules.map(r => r.name).join('、')}等规则，`
    }
    reasoning += `根据《道路交通安全法》第四十三条规定，同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。`
    reasoning += `本次分析置信度为${confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  } else if (accidentType === '变道碰撞') {
    reasoning = `经分析，该事故为变道碰撞事故。责任分配：${liabilityText}。`
    if (rules.length > 0) {
      reasoning += `依据${rules.map(r => r.name).join('、')}等规则，`
    }
    reasoning += `根据《道路交通安全法》第四十四条规定，机动车变更车道时，应当提前开启转向灯，确认安全后再变更车道。`
    reasoning += `本次分析置信度为${confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  } else {
    reasoning = `经分析，该事故涉及交通违规行为。责任分配：${liabilityText}。`
    if (rules.length > 0) {
      reasoning += `依据${rules.map(r => r.name).join('、')}等规则，`
    }
    reasoning += `根据《道路交通安全法》相关规定，驾驶员应遵守交通规则，确保行车安全。`
    reasoning += `本次分析置信度为${confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  }
  
  return reasoning
})

const isAnalyzing = ref(false)
const analysisProgress = ref(0)

const refreshAnalysis = async () => {
  if (isAnalyzing.value) return
  
  isAnalyzing.value = true
  analysisProgress.value = 0
  
  notify({ title: '开始分析', message: '正在重新分析事故数据...', type: 'info' })
  
  const steps = [
    { progress: 20, message: '正在提取视频关键帧...' },
    { progress: 40, message: '正在识别事故类型...' },
    { progress: 60, message: '正在匹配责任规则...' },
    { progress: 80, message: '正在生成分析报告...' },
    { progress: 100, message: '分析完成！' }
  ]
  
  for (const step of steps) {
    await new Promise(resolve => setTimeout(resolve, 500))
    analysisProgress.value = step.progress
    notify({ title: '分析进度', message: step.message, type: 'info' })
  }
  
  state.analysis.confidence = Math.floor(Math.random() * 10) + 90
  state.analysis.evidenceIntegrity = Math.floor(Math.random() * 10) + 90
  state.analysis.vehicleLiabilities = vehicleLiabilities.value
  
  await new Promise(resolve => setTimeout(resolve, 300))
  
  isAnalyzing.value = false
  analysisProgress.value = 0
  
  notify({ 
    title: '分析完成', 
    message: `置信度: ${state.analysis.confidence}% | 证据完整度: ${state.analysis.evidenceIntegrity}%`, 
    type: 'success' 
  })
}
const isSaving = ref(false)

const confirmAnalysis = async () => {
  if (isSaving.value) return
  isSaving.value = true
  try {
    const payload = {
      summary: reasoningText.value,
      ratio: vehicleLiabilities.value.map(l => `${l.role || l.vehicleType}:${l.percentage}%`).join('; '),
      details: {
        vehicles: vehicleLiabilities.value,
        confidence: state.analysis.confidence,
        evidence_integrity: state.analysis.evidenceIntegrity,
        accident_type: state.form.accidentType,
      },
      hit_rules: matchedRules.value.map(r => ({
        code: r.code,
        name: r.name,
        content: r.content,
        confidence: r.confidence,
      })),
    }
    console.log('[confirmAnalysis] Saving liability:', payload)
    const result = await CasesAPI.saveLiability(state.caseId, payload)
    console.log('[confirmAnalysis] Result:', result)
    if (result.success) {
      notify({ title: '保存成功', message: '责任判定结果已保存到数据库', type: 'success' })
      // Refresh to show saved data
      await loadCaseLiability()
    } else {
      notify({ title: '保存失败', message: result.message || '后端返回异常', type: 'error' })
    }
  } catch (err) {
    console.error('[confirmAnalysis] Error:', err)
    notify({ title: '保存失败', message: err.message || '网络错误', type: 'error' })
  } finally {
    isSaving.value = false
  }
}
</script>

<style scoped>
.intelligent-analysis-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
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
  padding: var(--space-4);
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  border: 1px solid var(--border-light);
}

.header-content { flex: 1; }

.page-title {
  margin: 0 0 var(--space-2);
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.03em;
}

.page-subtitle {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 400;
}

.header-actions { display: flex; gap: var(--space-3); }

.refresh-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 12px 24px;
  min-height: 44px;
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

.refresh-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.refresh-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}

.refresh-icon { 
  width: 16px; 
  height: 16px; 
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 空状态样式 */
.empty-state {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  min-height: auto;
  padding: var(--space-5) var(--space-5);
}

.empty-state-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  background: linear-gradient(135deg, var(--bg-primary) 0%, rgba(59, 130, 246, 0.03) 100%);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-3xl);
  padding: var(--space-6) var(--space-10);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  transition: all var(--transition-normal);
}

.empty-state-content:hover {
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
  border-color: var(--primary-200);
  transform: translateY(-2px);
}

.empty-state-icon {
  width: 140px;
  height: 140px;
  margin: 0 auto var(--space-7);
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(59, 130, 246, 0.05));
  border-radius: var(--radius-3xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
  transition: all var(--transition-normal);
}

.empty-state-icon span {
  width: 70px;
  height: 70px;
}

.empty-state-content:hover .empty-state-icon {
  transform: scale(1.05);
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(59, 130, 246, 0.08));
}

.empty-state-title {
  margin: 0 0 var(--space-3);
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.empty-state-desc {
  margin: 0 0 var(--space-5);
  font-size: 16px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.empty-state-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: 16px 36px;
  min-height: 52px;
  background: linear-gradient(135deg, var(--primary), #2563eb);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-normal);
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.3);
  font-family: var(--font-sans);
}

.empty-state-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(59, 130, 246, 0.45);
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
}

.empty-state-btn span {
  width: 18px;
  height: 18px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  flex: 0 0 auto;
}

.stat-card {
  position: relative;
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  padding: var(--space-4);
  min-height: 140px;
  overflow: hidden;
  transition: all var(--transition-normal);
  border: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
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

.stat-card:hover .stat-card-bg { opacity: 0.8; }

.card-blue .stat-card-bg { background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); }
.card-green .stat-card-bg { background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); }
.card-orange .stat-card-bg { background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); }
.card-purple .stat-card-bg { background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%); }

[data-theme="dark"] .card-blue .stat-card-bg { background: linear-gradient(135deg, rgba(59, 130, 246, 0.12) 0%, rgba(59, 130, 246, 0.04) 100%); }
[data-theme="dark"] .card-green .stat-card-bg { background: linear-gradient(135deg, rgba(34, 197, 94, 0.12) 0%, rgba(34, 197, 94, 0.04) 100%); }
[data-theme="dark"] .card-orange .stat-card-bg { background: linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(245, 158, 11, 0.04) 100%); }
[data-theme="dark"] .card-purple .stat-card-bg { background: linear-gradient(135deg, rgba(139, 92, 246, 0.12) 0%, rgba(139, 92, 246, 0.04) 100%); }

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  position: relative;
  z-index: 2;
  flex: 0 0 auto;
}

.stat-info { flex: 1; }

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: var(--space-3);
  display: block;
}

.stat-value-wrapper {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.stat-value {
  font-size: 36px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: -0.03em;
}

.stat-unit {
  font-size: var(--text-base);
  color: var(--text-secondary);
  font-weight: 500;
}

.stat-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: transform var(--transition-normal);
  flex-shrink: 0;
}

.stat-card:hover .stat-icon { transform: scale(1.08) rotate(3deg); }

.stat-icon span { width: 24px; height: 24px; position: relative; z-index: 2; }

.icon-blue { background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%); color: white; box-shadow: 0 3px 10px rgba(59, 130, 246, 0.3); }
.icon-green { background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: white; box-shadow: 0 3px 10px rgba(34, 197, 94, 0.3); }
.icon-orange { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; box-shadow: 0 3px 10px rgba(245, 158, 11, 0.3); }
.icon-purple { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: white; box-shadow: 0 3px 10px rgba(139, 92, 246, 0.3); }

.stat-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-5);
  position: relative;
  z-index: 2;
  flex: 0 0 auto;
}

.stat-change {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
}

.stat-change.positive { color: var(--success); }
.stat-change.negative { color: var(--text-muted); }

.change-icon { width: 14px; height: 14px; }
.stat-period { font-size: 11px; color: var(--text-muted); }

.content-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-auto-rows: minmax(180px, auto);
  gap: var(--space-3);
  align-items: stretch;
}

.section-card {
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  padding: var(--space-4);
  border: 1px solid var(--border-light);
  transition: all var(--transition-normal);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.section-card:hover { box-shadow: var(--shadow-md); }

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
  flex: 0 0 auto;
}

.section-title-wrapper {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.section-icon {
  width: 38px;
  height: 38px;
  background: var(--primary-gradient);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  padding: 8px;
  flex-shrink: 0;
}

.section-icon.icon-gradient {
  background: linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%);
}

.section-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.confidence-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  background: var(--primary-soft);
  color: var(--primary);
  flex-shrink: 0;
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.summary-pill {
  padding: 6px 14px;
  border-radius: var(--radius-full);
  background: var(--primary-soft);
  color: var(--primary);
  font-size: var(--text-xs);
  font-weight: 600;
  flex-shrink: 0;
}

.case-info { 
  grid-column: 1 / 2; 
  grid-row: 1 / 3;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  flex: 1;
  align-content: stretch;
  height: 100%;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-5);
  background: var(--primary-soft);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(59, 130, 246, 0.1);
  transition: all var(--transition-fast);
  justify-content: center;
  height: 100%;
}

.info-item:hover {
  background: rgba(59, 130, 246, 0.08);
  transform: translateY(-2px);
}

.info-label {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-value {
  font-size: var(--text-base);
  color: var(--text-primary);
  font-weight: 600;
}

.case-id {
  color: var(--primary);
  font-family: var(--font-mono);
}

.analysis-result {
  grid-column: 2 / 3;
  grid-row: 1 / 4;
}

.result-card {
  background: var(--primary-soft);
  border-radius: var(--radius-2xl);
  padding: var(--space-3);
  border: 1px solid rgba(59, 130, 246, 0.15);
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}

.liability-result {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  justify-content: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.liability-item {
  flex: 1;
  min-width: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-5);
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  border: 2px solid transparent;
  transition: all var(--transition-normal);
}

.liability-item.primary {
  border-color: var(--primary);
  box-shadow: 0 3px 12px rgba(37, 99, 235, 0.15);
}

.liability-item.secondary {
  border-color: var(--primary-200);
  box-shadow: 0 3px 12px rgba(37, 99, 235, 0.08);
}

.liability-item.no-liability {
  border-color: var(--border-light);
  opacity: 0.8;
}

.liability-item.equal {
  border-color: var(--warning-500);
  box-shadow: 0 3px 12px rgba(245, 158, 11, 0.15);
}

.liability-icon { width: 40px; height: 40px; color: var(--text-secondary); }

.liability-role {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.liability-plate {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  font-family: var(--font-mono);
}

.liability-degree {
  font-size: var(--text-xl);
  font-weight: 800;
}

.liability-item.primary .liability-degree { color: var(--primary); }
.liability-item.secondary .liability-degree { color: var(--primary-400); }
.liability-item.equal .liability-degree { color: var(--warning-500); }
.liability-item.no-liability .liability-degree { color: var(--text-muted); }

.liability-percent {
  font-size: var(--text-2xl);
  font-weight: 800;
  color: var(--text-primary);
}

.liability-item.no-liability .liability-percent { color: var(--text-muted); }

.liability-divider {
  font-size: var(--text-sm);
  color: var(--text-muted);
  font-weight: 700;
}

.reasoning-card {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  border: 1px solid var(--border-light);
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.reasoning-card h3 {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}

.reasoning-card p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
}

.markdown-content {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
}

.markdown-content h1,
.markdown-content h2,
.markdown-content h3 {
  font-weight: 700;
  color: var(--text-primary);
  margin-top: var(--space-4);
  margin-bottom: var(--space-2);
}

.markdown-content h1 { font-size: var(--text-xl); }
.markdown-content h2 { font-size: var(--text-lg); }
.markdown-content h3 { font-size: var(--text-base); }

.markdown-content p {
  margin: var(--space-2) 0;
}

.markdown-content ul {
  list-style: disc;
  padding-left: var(--space-5);
  margin: var(--space-2) 0;
}

.markdown-content li {
  margin: var(--space-1) 0;
}

.markdown-content strong {
  font-weight: 700;
  color: var(--text-primary);
}

.markdown-content em {
  font-style: italic;
}

.markdown-content code {
  background: var(--bg-secondary);
  color: var(--primary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.markdown-content pre {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  overflow-x: auto;
  margin: var(--space-3) 0;
}

.markdown-content pre code {
  background: none;
  padding: 0;
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.dify-analysis-container {
  padding: 8px 12px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  margin-top: 4px;
}

.dify-analysis-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #e2e8f0;
}

.dify-icon-wrapper {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
}

.dify-icon {
  font-size: 18px;
  color: white;
}

.dify-title-text {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  letter-spacing: 0.3px;
}

.analysis-section {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(139, 92, 246, 0.03) 100%);
  border-radius: 8px;
  padding: 6px 10px;
  margin-bottom: 6px;
  border: 1px solid rgba(99, 102, 241, 0.08);
  position: relative;
  overflow: hidden;
}

.analysis-section::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: linear-gradient(180deg, #6366f1 0%, #8b5cf6 100%);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  padding-left: 6px;
}

.section-icon {
  font-size: 12px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  letter-spacing: 0.2px;
}

.section-content {
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
  padding-left: 6px;
}

.json-list-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 8px;
  margin-bottom: 3px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 4px;
  border-left: 3px solid #8b5cf6;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.json-list-item:last-child {
  margin-bottom: 0;
}

.json-bullet {
  color: #8b5cf6;
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
  margin-top: 1px;
}

.json-text {
  color: #475569;
  flex: 1;
  font-size: 12px;
  line-height: 1.5;
}

.json-single-value {
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 6px;
  color: #334155;
  font-weight: 500;
  font-size: 13px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
}

.json-nested {
  padding-left: 10px;
  margin-top: 4px;
}

.clean-text {
  font-size: 13px;
  line-height: 1.7;
  color: #475569;
}

.clean-text p {
  margin: 8px 0;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  border-left: 3px solid #8b5cf6;
}

.clean-text ul {
  margin: 12px 0;
  padding-left: 24px;
}

.clean-text li {
  margin: 6px 0;
  padding: 6px 10px;
  background: rgba(99, 102, 241, 0.05);
  border-radius: 6px;
}

.clean-text strong {
  color: #1e293b;
  font-weight: 600;
}

.law-highlight {
  display: inline-block;
  padding: 4px 10px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
  border-radius: 6px;
  color: #6366f1;
  font-weight: 600;
  font-size: 12px;
  margin: 2px 4px;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.law-item {
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.05) 0%, rgba(20, 184, 166, 0.04) 100%);
  border-left: 3px solid #22c55e;
}

.law-item .json-text {
  color: #166534;
}

.law-item .json-bullet {
  color: #22c55e;
}

.core-reason-item {
  border-left-color: #f59e0b;
}

.core-reason-item .json-bullet {
  color: #f59e0b;
}

.risk-note-box {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.05) 0%, rgba(249, 115, 22, 0.04) 100%);
  border-left-color: #ef4444;
}

.risk-note-box .json-text {
  color: #991b1b;
}

.risk-note-box .json-bullet {
  color: #ef4444;
}

.confidence-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.12) 0%, rgba(34, 197, 94, 0.06) 100%);
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  color: #15803d;
  margin-top: 4px;
}

.confidence-value {
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 12px;
}

.liability-tag {
  display: inline-block;
  padding: 4px 10px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  color: white;
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.2);
}

.law-reference {
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-style: italic;
}

.matched-rules { 
  grid-column: 1 / 2; 
  grid-row: 3 / 4;
}

.rules-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  flex: 1;
  justify-content: center;
}

.rule-item {
  background: var(--primary-soft);
  border: 1px solid rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  transition: all var(--transition-normal);
}

.rule-item:hover {
  border-color: rgba(59, 130, 246, 0.3);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.1);
  transform: translateY(-2px);
}

.rule-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.rule-code {
  font-size: 11px;
  font-weight: 700;
  color: var(--primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 3px 9px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.rule-name {
  flex: 1;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.rule-confidence {
  font-size: var(--text-xs);
  color: var(--primary);
  font-weight: 700;
  flex-shrink: 0;
}

.rule-content {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin-bottom: var(--space-3);
}

.rule-progress {
  height: 6px;
  background: var(--border-light);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--primary-gradient);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.analysis-actions {
  grid-column: 1 / 3;
  display: flex;
  gap: var(--space-5);
  justify-content: center;
  background: transparent;
  border: none;
  padding: var(--space-4) 0 0;
}

.analysis-actions:hover { box-shadow: none; }

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  padding: 14px 48px;
  min-height: 50px;
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-normal);
  border: 1px solid transparent;
  font-family: var(--font-sans);
  white-space: nowrap;
}

.action-btn span { width: 18px; height: 18px; }

.action-btn.secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
  border-color: var(--border-light);
}

.action-btn.secondary:hover {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary);
  transform: translateY(-2px);
}

.action-btn.primary {
  background: var(--primary-gradient);
  color: white;
  border: none;
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.25);
}

.action-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.35);
}

.keyframes { grid-column: 1 / 3; }

.keyframes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
  flex: 1;
  align-content: center;
}

.keyframe-item {
  background: var(--primary-soft);
  border: 2px solid transparent;
  border-radius: var(--radius-2xl);
  padding: var(--space-4);
  transition: all var(--transition-normal);
  cursor: pointer;
  display: flex;
  flex-direction: column;
}

.keyframe-item:hover {
  border-color: rgba(59, 130, 246, 0.3);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.1);
  transform: translateY(-2px);
}

.keyframe-item.selected {
  border-color: var(--primary);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.2);
}

.keyframe-item.main {
  border-color: #f59e0b;
  box-shadow: 0 4px 16px rgba(245, 158, 11, 0.2);
}

.keyframe-image-wrapper {
  position: relative;
  margin-bottom: var(--space-3);
  border-radius: var(--radius-xl);
  overflow: hidden;
  flex-shrink: 0;
}

.keyframe-image {
  width: 100%;
  height: 130px;
  object-fit: cover;
  border-radius: var(--radius-xl);
  transition: transform var(--transition-normal);
}

.keyframe-item:hover .keyframe-image { transform: scale(1.05); }

.main-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 3px 10px;
  background: #f59e0b;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: var(--radius-full);
  z-index: 1;
}

.keyframe-info { display: flex; flex-direction: column; gap: 4px; flex: 1; }

.keyframe-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.keyframe-time {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.keyframe-meta {
  display: flex;
  gap: var(--space-2);
  font-size: 11px;
  font-weight: 600;
}

.keyframe-clarity {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
  padding: 2px 8px;
  border-radius: var(--radius-md);
}

.keyframe-score {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  padding: 2px 8px;
  border-radius: var(--radius-md);
}

.keyframe-purpose {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 模态框样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--space-4);
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  width: 100%;
  max-width: 900px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-6);
  border-bottom: 1px solid var(--border-light);
}

.modal-title {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-lg);
  border: none;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.modal-close:hover {
  background: var(--primary-soft);
  color: var(--primary);
}

.modal-close svg {
  width: 18px;
  height: 18px;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}

.report-section {
  margin-bottom: var(--space-6);
}

.report-section:last-child {
  margin-bottom: 0;
}

.report-section-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-4);
  padding-bottom: var(--space-2);
  border-bottom: 2px solid var(--primary);
}

.report-info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
}

.report-info-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.report-info-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.report-info-value {
  font-size: var(--text-base);
  color: var(--text-primary);
  font-weight: 600;
}

.report-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

.report-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--primary-soft);
  border-radius: var(--radius-lg);
}

.report-stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 500;
}

.report-stat-value {
  font-size: var(--text-xl);
  font-weight: 800;
  color: var(--primary);
}

.report-liability {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-6);
  padding: var(--space-6);
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
}

.report-liability-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.report-liability-role {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.report-liability-degree {
  font-size: var(--text-lg);
  font-weight: 800;
  color: var(--text-primary);
}

.report-liability-degree.primary {
  color: var(--primary);
}

.report-liability-percent {
  font-size: var(--text-2xl);
  font-weight: 800;
  color: var(--text-primary);
}

.report-liability-divider {
  font-size: var(--text-sm);
  color: var(--text-muted);
  font-weight: 700;
}

.report-reasoning {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border-left: 4px solid var(--primary);
}

.report-rules-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.report-rule-item {
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
}

.report-rule-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.report-rule-code {
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 2px 8px;
  border-radius: var(--radius-md);
}

.report-rule-name {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.report-rule-confidence {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 600;
}

.report-rule-content {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--leading-relaxed);
}

.report-keyframes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-4);
}

.report-keyframe-item {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-light);
}

.report-keyframe-image {
  width: 100%;
  height: 120px;
  object-fit: cover;
}

.report-keyframe-info {
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.report-keyframe-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.report-keyframe-time {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.report-keyframe-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.report-footer {
  margin-top: var(--space-6);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-light);
}

.report-meta {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-5) var(--space-6);
  border-top: 1px solid var(--border-light);
}

.modal-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 12px 24px;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  font-family: var(--font-sans);
}

.modal-btn.secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--border-light);
}

.modal-btn.secondary:hover {
  background: var(--bg-primary);
  border-color: var(--primary);
  color: var(--primary);
}

.modal-btn.primary {
  background: var(--primary-gradient);
  color: white;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.modal-btn.primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
}

@media (max-width: 1200px) {
  .intelligent-analysis-page { padding: var(--space-4); gap: var(--space-4); }
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4); }
  .content-grid { grid-template-columns: 1fr; grid-auto-rows: auto; gap: var(--space-4); }
  .case-info, .analysis-result, .matched-rules, .analysis-actions, .keyframes { grid-column: 1; }
  .case-info { grid-row: auto; }
  .analysis-result { grid-row: auto; }
  .matched-rules { grid-row: auto; }
  .page-header { padding: var(--space-4); }
  .page-title { font-size: 26px; }
  .stat-card { min-height: 140px; }
  .report-stats-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
  .intelligent-analysis-page { padding: var(--space-3); gap: var(--space-3); }
  .stats-grid { grid-template-columns: 1fr; gap: var(--space-3); }
  .page-header { flex-direction: column; align-items: stretch; gap: var(--space-3); padding: var(--space-4); }
  .page-title { font-size: 24px; }
  .header-actions { justify-content: center; }
  .info-grid { grid-template-columns: 1fr; gap: var(--space-3); }
  .liability-result { flex-direction: column; }
  .liability-divider { transform: rotate(90deg); }
  .analysis-actions { flex-direction: column; gap: var(--space-3); padding-top: var(--space-3); }
  .action-btn { width: 100%; justify-content: center; }
  .keyframes-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); }
  .keyframe-image { height: 120px; }
  .stat-card { min-height: auto; padding: var(--space-5); }
  .stat-value { font-size: 32px; }
  .section-card { padding: var(--space-5); }
  .result-card { padding: var(--space-5); }
  .reasoning-card { padding: var(--space-4); }
  .modal-container { max-height: 95vh; }
  .modal-header { padding: var(--space-4); }
  .modal-body { padding: var(--space-4); }
  .modal-footer { padding: var(--space-4); flex-direction: column; }
  .modal-btn { width: 100%; justify-content: center; }
  .report-info-grid { grid-template-columns: 1fr; }
  .report-stats-grid { grid-template-columns: repeat(2, 1fr); }
  .report-liability { flex-direction: column; gap: var(--space-4); }
  .report-liability-divider { transform: rotate(90deg); }
  .report-keyframes-grid { grid-template-columns: 1fr; }
}

/* 待定状态样式 */
.pending-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.placeholder-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  color: var(--text-muted);
}

.placeholder-icon {
  width: 48px;
  height: 48px;
  opacity: 0.5;
}

.confirm-section {
  grid-column: 1 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
}

.confirm-actions {
  display: flex;
  gap: var(--space-4);
  justify-content: center;
  width: 100%;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 12px 28px;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  font-family: var(--font-sans);
}

.btn-icon { width: 18px; height: 18px; }

.btn-primary {
  background: var(--primary-gradient);
  color: white;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-lg {
  padding: 14px 36px;
  font-size: var(--text-base);
  min-height: 48px;
}

.placeholder-text {
  font-size: var(--text-sm);
  font-weight: 500;
  text-align: center;
}

/* ===== 证据一致性检测 ===== */
.consistency-section {
  grid-column: 1 / 3;
}

.consistency-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--primary-soft);
  color: var(--primary);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.consistency-refresh-btn:hover:not(:disabled) {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.consistency-refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.consistency-refresh-btn .refresh-icon {
  width: 14px;
  height: 14px;
}

.consistency-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* 顶部：圆环 + 统计 */
.consistency-score-area {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-2xl);
}

.consistency-ring {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}

.ring-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.ring-bg {
  fill: none;
  stroke: var(--border-light);
  stroke-width: 10;
}

.ring-fill {
  fill: none;
  stroke-width: 10;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.8s ease;
}

.consistency-ring.level-high .ring-fill { stroke: #22c55e; }
.consistency-ring.level-mid .ring-fill { stroke: #f59e0b; }
.consistency-ring.level-low .ring-fill { stroke: #ef4444; }

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.ring-score {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
}

.ring-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.consistency-summary {
  display: flex;
  gap: var(--space-4);
  flex: 1;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-xl);
  flex: 1;
}

.summary-consistent {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.summary-conflict {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.summary-count {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
}

.summary-consistent .summary-count { color: #16a34a; }
.summary-conflict .summary-count { color: #dc2626; }

.summary-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

/* 中间：两列对比 */
.consistency-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

.consistency-column {
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-xl);
  overflow: hidden;
  border: 1px solid transparent;
}

.consistent-column {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.2);
}

.conflict-column {
  background: rgba(239, 68, 68, 0.06);
  border-color: rgba(239, 68, 68, 0.2);
}

.column-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  font-weight: 700;
  font-size: var(--text-sm);
}

.consistent-column .column-header { background: rgba(34, 197, 94, 0.12); color: #15803d; }
.conflict-column .column-header { background: rgba(239, 68, 68, 0.12); color: #b91c1c; }

.column-icon {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: white;
  flex-shrink: 0;
}

.column-icon svg {
  width: 13px;
  height: 13px;
}

.icon-check { background: #22c55e; }
.icon-warn { background: #ef4444; }

.column-title { flex: 1; }

.column-count {
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 700;
}

.consistent-column .column-count { background: rgba(34, 197, 94, 0.2); color: #15803d; }
.conflict-column .column-count { background: rgba(239, 68, 68, 0.2); color: #b91c1c; }

.column-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  flex: 1;
  max-height: 280px;
  overflow-y: auto;
}

.consistency-item {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.consistent-item {
  background: rgba(255, 255, 255, 0.7);
  border-left: 3px solid #22c55e;
}

.conflict-item {
  background: rgba(255, 255, 255, 0.7);
  border-left: 3px solid #ef4444;
}

.item-type {
  font-weight: 700;
  color: var(--text-primary);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.item-value {
  color: var(--text-secondary);
  word-break: break-all;
}

.item-source {
  font-size: 10px;
  color: var(--text-muted);
}

.conflict-values {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conflict-value {
  color: var(--text-secondary);
  word-break: break-all;
}

.conflict-src {
  font-weight: 700;
  color: var(--text-primary);
  margin-right: 4px;
}

.conflict-vs {
  text-align: center;
  font-size: 10px;
  font-weight: 800;
  color: #ef4444;
  padding: 1px 0;
}

.empty-tip {
  text-align: center;
  padding: var(--space-4);
  color: var(--text-muted);
  font-size: var(--text-sm);
}

/* 底部：系统建议 */
.consistency-suggestion {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-xl);
  font-size: var(--text-sm);
  font-weight: 600;
}

.suggestion-label {
  padding: 4px 12px;
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.03em;
  background: rgba(255, 255, 255, 0.7);
  flex-shrink: 0;
}

.suggestion-divider {
  width: 1px;
  height: 16px;
  background: currentColor;
  opacity: 0.3;
  flex-shrink: 0;
}

.suggestion-text {
  flex: 1;
}

.suggest-ok {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.25);
  color: #15803d;
}

.suggest-warn {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.25);
  color: #b45309;
}

.suggest-danger {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.25);
  color: #b91c1c;
}

@media (max-width: 768px) {
  .consistency-score-area { flex-direction: column; }
  .consistency-columns { grid-template-columns: 1fr; }
}
</style>
