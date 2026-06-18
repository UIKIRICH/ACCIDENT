<template>
  <div class="manual-review-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">人工复核</h1>
        <p class="page-subtitle">对智能分析结果进行人工审核与最终确认</p>
      </div>
      <div class="header-badge" :class="state.manualReview.submitted ? 'submitted' : 'pending'">
        {{ state.manualReview.submitted ? '已提交' : '待审核' }}
      </div>
    </div>

    <div class="review-container">
      <!-- 案件信息概览 -->
      <div class="case-summary card-surface">
        <h2 class="section-title">案件信息概览</h2>
        <div class="summary-grid">
          <div class="summary-item">
            <span class="summary-label">案件编号</span>
            <span class="summary-value">{{ state.caseId }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">事故类型</span>
            <span class="summary-value">{{ state.form.accidentType || '未填写' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">发生时间</span>
            <span class="summary-value">{{ state.form.time || '未填写' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">发生地点</span>
            <span class="summary-value">{{ state.form.location || '未填写' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">车辆数量</span>
            <span class="summary-value">{{ state.form.vehicles.length }}辆</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">分析置信度</span>
            <span class="summary-value" :class="getConfidenceClass()">{{ hasAnalysis ? state.analysis.confidence + '%' : '未分析' }}</span>
          </div>
        </div>
      </div>

      <!-- 系统建议结果 -->
      <div class="system-result card-surface">
        <h2 class="section-title">系统责任建议</h2>
        <div v-if="hasAnalysis && state.analysis.vehicleLiabilities.length > 0" class="liability-display">
          <div class="liability-cards">
            <div v-for="(liability, idx) in state.analysis.vehicleLiabilities" :key="idx" class="liability-card">
              <div class="vehicle-info">
                <div class="vehicle-avatar">{{ liability.role.charAt(0) }}</div>
                <div class="vehicle-details">
                  <div class="vehicle-role">{{ liability.role }}</div>
                  <div class="vehicle-plate">{{ liability.plate || '无车牌' }}</div>
                  <div class="vehicle-type">{{ liability.vehicleType }}</div>
                </div>
              </div>
              <div class="liability-info">
                <div class="liability-badge" :class="getLiabilityClass(liability.liability)">
                  {{ liability.liability }}
                </div>
                <div class="liability-percentage">{{ liability.percentage }}%</div>
              </div>
            </div>
          </div>
          
          <div class="reasoning-section">
            <h3 class="reasoning-title">认定理由</h3>
            <p class="reasoning-text">{{ getReasoningText() }}</p>
          </div>
          
          <div v-if="state.recommendation.suggestions.length > 0" class="suggestions-section">
            <h3 class="suggestions-title">处理建议</h3>
            <div class="suggestions-list">
              <div v-for="(suggestion, idx) in state.recommendation.suggestions" :key="idx" class="suggestion-item">
                <span class="suggestion-number">{{ idx + 1 }}</span>
                <div class="suggestion-content">
                  <span class="suggestion-title">{{ suggestion.title }}</span>
                  <span class="suggestion-desc">{{ suggestion.description }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <p class="empty-text">暂无分析结果，请先完成智能分析</p>
        </div>
      </div>

      <!-- Dify 智能分析结果 -->
      <div v-if="hasAnalysis" class="dify-analysis-container">
        <div class="dify-analysis-title">
          <div class="dify-icon-wrapper">
            <span class="dify-icon">🤖</span>
          </div>
          <span class="dify-title-text">Dify智能分析</span>
        </div>
        <div v-if="hasDifyResult" class="markdown-content" v-html="parseMarkdown(difyAnalysisText)"></div>
        <div v-else class="no-dify-data">
          <p style="text-align: center; color: #94a3b8; padding: 20px;">暂无Dify分析数据，请先在视频处理页点击"Send To Dify"</p>
        </div>
      </div>

      <!-- 规则依据展示 -->
      <div class="rule-basis card-surface" v-if="state.ruleBasis.selectedRules.length > 0">
        <h2 class="section-title">引用规则依据 ({{ state.ruleBasis.selectedRules.length }})</h2>
        <div class="rules-list">
          <div v-for="rule in state.ruleBasis.selectedRules" :key="rule.code" class="rule-item">
            <div class="rule-code-badge">{{ rule.code }}</div>
            <div class="rule-content-wrapper">
              <div class="rule-title">{{ rule.title }}</div>
              <div class="rule-desc">{{ rule.content }}</div>
              <div class="rule-meta">
                <span class="rule-source">{{ rule.category }}</span>
                <span class="rule-scenario">适用场景：{{ rule.scenario }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="state.ruleBasis.legalBasis" class="legal-note">
          <h4 class="note-title">法律依据补充</h4>
          <p class="note-text">{{ state.ruleBasis.legalBasis }}</p>
        </div>
      </div>

      <!-- 审核操作区域 -->
      <div class="review-form card-surface" v-if="!state.manualReview.submitted">
        <h2 class="section-title">复核操作</h2>
        
        <div class="decision-group">
          <label class="form-label">复核决定</label>
          <div class="decision-options">
            <label 
              class="decision-option" 
              :class="{ active: state.manualReview.decision === '确认系统建议' }"
            >
              <input 
                type="radio" 
                name="decision" 
                value="确认系统建议" 
                :checked="state.manualReview.decision === '确认系统建议'"
                @change="handleDecisionChange('确认系统建议')"
              >
              <span class="option-icon">✓</span>
              <span class="option-text">
                <strong>确认系统建议</strong>
                <span class="option-desc">直接采纳智能分析的责任认定结果</span>
              </span>
            </label>
            
            <label 
              class="decision-option" 
              :class="{ active: state.manualReview.decision === '调整责任' }"
            >
              <input 
                type="radio" 
                name="decision" 
                value="调整责任" 
                :checked="state.manualReview.decision === '调整责任'"
                @change="handleDecisionChange('调整责任')"
              >
              <span class="option-icon">✎</span>
              <span class="option-text">
                <strong>调整责任</strong>
                <span class="option-desc">对系统建议的责任比例进行调整</span>
              </span>
            </label>
            
            <label 
              class="decision-option" 
              :class="{ active: state.manualReview.decision === '驳回重审' }"
            >
              <input 
                type="radio" 
                name="decision" 
                value="驳回重审" 
                :checked="state.manualReview.decision === '驳回重审'"
                @change="handleDecisionChange('驳回重审')"
              >
              <span class="option-icon">✗</span>
              <span class="option-text">
                <strong>驳回重审</strong>
                <span class="option-desc">结果不符合预期，需要重新分析</span>
              </span>
            </label>
          </div>
        </div>
        
        <!-- 责任调整区域 -->
        <div v-if="state.manualReview.decision === '调整责任' && hasAnalysis" class="adjustment-area">
          <label class="form-label">调整责任分配</label>
          <div class="adjustment-list">
            <div v-for="(liability, idx) in state.analysis.vehicleLiabilities" :key="idx" class="adjustment-item">
              <div class="vehicle-info">
                <div class="vehicle-label">{{ liability.role }}</div>
                <div class="vehicle-plate">{{ liability.plate || '无车牌' }}</div>
              </div>
              <div class="slider-bar-container">
                <div class="slider-bar-track">
                  <div 
                    class="slider-bar-fill" 
                    :style="{ width: (editingLiabilities[idx]?.percentage || liability.percentage) + '%' }"
                  ></div>
                </div>
                <input 
                  type="range" 
                  :value="editingLiabilities[idx]?.percentage || liability.percentage"
                  min="0" 
                  max="100"
                  @input="handlePercentageChange(idx, $event.target.value)"
                  class="merged-slider"
                >
              </div>
              <div class="percentage-input-wrapper">
                <input 
                  type="number" 
                  :value="editingLiabilities[idx]?.percentage || liability.percentage"
                  min="0" 
                  max="100"
                  @input="handlePercentageInput(idx, $event.target.value)"
                  class="percentage-input"
                >
                <span class="percentage-suffix">%</span>
              </div>
            </div>
          </div>
          <div class="total-check" :class="{ error: !isTotalValid }">
            责任总和：{{ calculateTotal() }}% (应为 100%)
          </div>
        </div>
        
        <div class="form-group">
          <label class="form-label">复核说明</label>
          <textarea 
            v-model="reviewNote" 
            class="form-textarea" 
            placeholder="请输入复核意见或补充说明..."
            @input="updateReviewNote"
          ></textarea>
        </div>
        
        <div class="form-actions">
          <button class="btn btn-secondary" @click="handleViewLogs">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
            查看日志
          </button>
          <button 
            class="btn btn-primary" 
            @click="handleSubmitReview"
            :disabled="!canSubmit"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            提交复核
          </button>
        </div>
      </div>

      <!-- 历史复核记录 -->
      <div class="card-surface review-history" v-if="reviews.length > 0 && !state.manualReview.submitted">
        <h2 class="section-title">历史复核记录 ({{ reviews.length }})</h2>
        <div class="review-list">
          <div v-for="(rev, idx) in reviews" :key="rev.review_id || idx" class="review-item">
            <div class="review-header">
              <span class="review-reviewer">{{ rev.reviewer || '未知用户' }}</span>
              <span class="review-time">{{ rev.review_time }}</span>
            </div>
            <div class="review-body">
              <div class="review-field"><span class="field-label">系统建议</span> {{ rev.system_suggestion }}</div>
              <div class="review-field"><span class="field-label">最终结论</span> {{ rev.final_result }}</div>
              <div class="review-field" v-if="rev.review_comment"><span class="field-label">复核说明</span> {{ rev.review_comment }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 已提交状态 -->
      <div class="submitted-section card-surface" v-if="state.manualReview.submitted">
        <div class="submitted-content">
          <div class="success-icon">✓</div>
          <h3 class="success-title">复核已提交</h3>
          <p class="success-text">案件已成功归档，等待后续处理</p>
          
          <div class="submitted-details">
            <div class="detail-row">
              <span class="detail-label">复核决定</span>
              <span class="detail-value">{{ state.manualReview.decision }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">复核时间</span>
              <span class="detail-value">{{ state.manualReview.reviewedAt }}</span>
            </div>
            <div class="detail-row" v-if="state.manualReview.note">
              <span class="detail-label">复核说明</span>
              <span class="detail-value note-value">{{ state.manualReview.note }}</span>
            </div>
          </div>
        </div>
        
        <div class="submitted-actions">
          <button class="btn btn-secondary" @click="handleReset">
            开始新案件
          </button>
        </div>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import { CasesAPI, getCurrentUser } from '../api/index.js'
import NavigationButtons from '../components/NavigationButtons.vue'

const router = useRouter()
const route = useRoute()

const {
  state,
  goStep,
  updateManualReview,
  submitManualReview,
  resetFlow,
  getLogs,
  logMessage,
  LOG_LEVELS
} = useAccidentFlow()

goStep('manual-review')

const reviewNote = ref(state.manualReview.note || '')
const editingLiabilities = ref([])
const reviews = ref([])
const submitting = ref(false)

// 获取历史复核记录
async function fetchReviews() {
  const caseId = route.query.caseId || state.caseId
  if (!caseId) return
  try {
    const result = await CasesAPI.getReviews(caseId)
    if (result.success && Array.isArray(result.data)) {
      reviews.value = result.data
    }
  } catch (err) {
    console.warn('获取复核记录失败:', err)
  }
}

onMounted(() => {
  fetchReviews()
})

const hasAnalysis = computed(() => {
  return state.analysis.confidence !== null && state.analysis.confidence !== ''
})

const hasDifyResult = computed(() => {
  return state.analysis.difyResult !== null && state.analysis.difyResult !== undefined
})

const canSubmit = computed(() => {
  if (state.manualReview.decision === '调整责任' && !isTotalValid.value) {
    return false
  }
  return true
})

const isTotalValid = computed(() => {
  if (editingLiabilities.value.length === 0) return true
  return calculateTotal() === 100
})

function calculateTotal() {
  if (editingLiabilities.value.length === 0) {
    return state.analysis.vehicleLiabilities.reduce((sum, l) => sum + (l.percentage || 0), 0)
  }
  return editingLiabilities.value.reduce((sum, l) => sum + (l?.percentage || 0), 0)
}

function handleDecisionChange(decision) {
  if (decision === '调整责任') {
    editingLiabilities.value = state.analysis.vehicleLiabilities.map(l => ({
      ...l
    }))
  } else {
    editingLiabilities.value = []
  }
  
  updateManualReview({
    decision,
    adjustments: decision === '调整责任' ? {
      modifiedLiabilities: editingLiabilities.value
    } : null
  })
  
  logMessage(LOG_LEVELS.INFO, 'manual-review', 'DECISION', `选择复核决定：${decision}`)
  notify({ title: '复核决定', message: `已选择：${decision}` })
}

function handlePercentageChange(idx, value) {
  if (!editingLiabilities.value[idx]) {
    editingLiabilities.value[idx] = { ...state.analysis.vehicleLiabilities[idx] }
  }
  editingLiabilities.value[idx].percentage = parseInt(value)
  
  updateManualReview({
    adjustments: {
      modifiedLiabilities: editingLiabilities.value
    }
  })
}

function handlePercentageInput(idx, value) {
  const numValue = parseInt(value) || 0
  const clampedValue = Math.min(Math.max(numValue, 0), 100)
  
  if (!editingLiabilities.value[idx]) {
    editingLiabilities.value[idx] = { ...state.analysis.vehicleLiabilities[idx] }
  }
  editingLiabilities.value[idx].percentage = clampedValue
  
  updateManualReview({
    adjustments: {
      modifiedLiabilities: editingLiabilities.value
    }
  })
}

function updateReviewNote() {
  updateManualReview({
    note: reviewNote.value
  })
}

function getConfidenceClass() {
  if (!hasAnalysis.value) return ''
  const conf = state.analysis.confidence
  if (conf >= 80) return 'high'
  if (conf >= 60) return 'medium'
  return 'low'
}

function getLiabilityClass(liability) {
  if (liability.includes('主责')) return 'primary'
  if (liability.includes('次责')) return 'secondary'
  if (liability.includes('无责')) return 'none'
  return 'equal'
}

function getReasoningText() {
  const accidentType = state.form.accidentType
  const liabilities = state.analysis.vehicleLiabilities
  const liabilityText = liabilities.map(l => `${l.role || l.vehicleType}${l.plate ? '(' + l.plate + ')' : ''}：${l.liability}（${l.percentage}%）`).join('；')
  
  if (accidentType === '追尾事故') {
    return `经分析，该事故为追尾事故。责任分配：${liabilityText}。根据《道路交通安全法》第四十三条规定，同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。`
  } else if (accidentType === '变道碰撞') {
    return `经分析，该事故为变道碰撞事故。责任分配：${liabilityText}。根据《道路交通安全法》第四十四条规定，机动车变更车道时，应当提前开启转向灯，确认安全后再变更车道。`
  } else {
    return `经分析，该事故涉及交通违法行为。责任分配：${liabilityText}。根据《道路交通安全法》相关规定，驾驶员应遵守交通规则，确保行车安全。`
  }
}

function handleSubmitReview() {
  if (state.manualReview.decision === '调整责任' && !isTotalValid.value) {
    notify({ title: '提示', message: '责任总和应为100%', type: 'warning' })
    logMessage(LOG_LEVELS.WARNING, 'manual-review', 'VALIDATION', '责任总和验证失败')
    return
  }
  
  updateManualReview({
    note: reviewNote.value
  })
  
  logMessage(LOG_LEVELS.INFO, 'manual-review', 'SUBMIT', '提交复核', {
    decision: state.manualReview.decision,
    note: state.manualReview.note
  })

  // Save review to backend
  const caseId = route.query.caseId || state.caseId
  const currentUserObj = getCurrentUser()
  const reviewer = currentUserObj?.display_name || currentUserObj?.username || '未知用户'
  const systemSuggestion = state.analysis.reasoningText || state.recommendation.summary || ''
  const finalResult = state.manualReview.decision || ''
  const reviewComment = reviewNote.value || ''

  submitting.value = true
  CasesAPI.addReview(caseId, {
    reviewer,
    system_suggestion: systemSuggestion,
    final_result: finalResult,
    review_comment: reviewComment,
  }).then(result => {
    if (result.success) {
      // Update case status to completed
      CasesAPI.update(caseId, { status: '已完成' }).catch(() => {})
      notify({ title: '提交成功', message: '复核记录已保存，案件已完成', type: 'success' })
      updateManualReview({ submitted: true, reviewedAt: new Date().toLocaleString() })
    } else {
      notify({ title: '提交失败', message: result.message || '后端保存失败', type: 'error' })
    }
  }).catch(err => {
    console.error('[handleSubmitReview] Error:', err)
    notify({ title: '提交失败', message: err.message || '网络错误', type: 'error' })
  }).finally(() => {
    submitting.value = false
  })
}

function handleViewLogs() {
  const logs = getLogs()
  // console.log('系统日志:', logs)
  notify({ title: '查看日志', message: `共${logs.length}条日志，已输出到控制台` })
}

function handleReset() {
  resetFlow()
  router.push('/')
  logMessage(LOG_LEVELS.INFO, 'manual-review', 'RESET', '开始新案件')
  notify({ title: '新案件', message: '已重置流程，开始新案件登记' })
}

const difyAnalysisText = computed(() => {
  return state.analysis.difyAnalysisText || '暂无分析结果'
})

const formatJsonToHtml = (jsonObj) => {
  if (!jsonObj || typeof jsonObj !== 'object') return ''
  
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
    'applicability': '适用度'
  }
  
  let html = ''
  
  const renderSection = (key, value, level = 0) => {
    const label = labels[key] || key
    const indent = '  '.repeat(level)
    
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
      
      return `<div class="analysis-section">
        <div class="section-header">
          <span class="section-icon">📋</span>
          <span class="section-title">${label}</span>
        </div>
        <div class="section-content">${itemsHtml}</div>
      </div>`
    }
    
    if (typeof value === 'object') {
      return `<div class="analysis-section">
        <div class="section-header">
          <span class="section-icon">📊</span>
          <span class="section-title">${label}</span>
        </div>
        <div class="section-content">${renderNestedObject(value, level + 1)}</div>
      </div>`
    }
    
    const cleanValue = typeof value === 'string' 
      ? value.replace(/\\n/g, '').replace(/\\"/g, '"').trim()
      : (typeof value === 'number' ? (value * 100).toFixed(1) + '%' : value)
    
    return `<div class="analysis-section">
      <div class="section-header">
        <span class="section-icon">📝</span>
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
  
  for (const [key, value] of Object.entries(jsonObj)) {
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
    
    if (parsed.final && typeof parsed.final === 'string') {
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
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
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
</script>

<style scoped>
.manual-review-page {
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
  justify-content: space-between;
  align-items: flex-start;
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

.header-badge {
  padding: 6px 16px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 600;
}

.header-badge.pending {
  background: rgba(245, 158, 11, 0.1);
  color: var(--warning-500);
}

.header-badge.submitted {
  background: rgba(34, 197, 94, 0.1);
  color: var(--success-500);
}

.review-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.card-surface {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  padding: var(--space-6);
  transition: box-shadow var(--transition-normal);
}

.card-surface:hover { box-shadow: var(--shadow-md); }

.section-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-5);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  transition: all var(--transition-fast);
}

.summary-item:hover { border-color: var(--primary-200); transform: translateY(-1px); }

.summary-label {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.summary-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
}

.summary-value.high { color: var(--success-500); }
.summary-value.medium { color: var(--warning-500); }
.summary-value.low { color: var(--danger-500); }

.liability-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.liability-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-4);
  display: flex;
  gap: var(--space-3);
  transition: all var(--transition-normal);
}

.liability-card:hover {
  border-color: var(--primary-200);
  transform: translateY(-2px);
}

.vehicle-avatar {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  background: var(--primary-gradient);
  color: white;
  font-size: var(--text-lg);
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.vehicle-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.vehicle-role {
  font-weight: 700;
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.vehicle-plate {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.vehicle-type {
  font-size: 11px;
  color: var(--text-muted);
}

.liability-info {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-2);
}

.liability-badge {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 700;
}

.liability-badge.primary {
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger-500);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.liability-badge.secondary {
  background: rgba(245, 158, 11, 0.1);
  color: var(--warning-500);
  border: 1px solid rgba(245, 158, 11, 0.2);
}

.liability-badge.none {
  background: rgba(34, 197, 94, 0.1);
  color: var(--success-500);
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.liability-badge.equal {
  background: rgba(139, 92, 246, 0.1);
  color: #8b5cf6;
  border: 1px solid rgba(139, 92, 246, 0.2);
}

.liability-percentage {
  font-size: var(--text-xl);
  font-weight: 800;
  color: var(--text-primary);
}

.reasoning-section {
  background: var(--primary-soft);
  border-radius: var(--radius-xl);
  padding: var(--space-4);
  border-left: 3px solid var(--primary);
}

.reasoning-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.reasoning-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
}

.suggestions-section {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  padding: var(--space-4);
  margin-top: var(--space-4);
}

.suggestions-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.suggestion-item {
  display: flex;
  gap: var(--space-3);
}

.suggestion-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--primary);
  color: white;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.suggestion-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.suggestion-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.suggestion-desc {
  font-size: 11px;
  color: var(--text-secondary);
}

.empty-state {
  padding: var(--space-8);
  text-align: center;
}

.empty-text {
  font-size: var(--text-sm);
  color: var(--text-muted);
  margin: 0;
}

.rules-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.rule-item {
  display: flex;
  gap: var(--space-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  border: 1px solid var(--border-light);
}

.rule-code-badge {
  padding: 6px 12px;
  background: var(--primary-soft);
  color: var(--primary);
  border-radius: var(--radius-md);
  font-size: 11px;
  font-weight: 800;
  flex-shrink: 0;
}

.rule-content-wrapper {
  flex: 1;
}

.rule-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.rule-desc {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin-bottom: var(--space-2);
}

.rule-meta {
  display: flex;
  gap: var(--space-3);
}

.rule-source, .rule-scenario {
  font-size: 11px;
  color: var(--text-muted);
}

.legal-note {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  border: 1px dashed var(--primary-300);
}

.note-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.note-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
}

.decision-group {
  margin-bottom: var(--space-6);
}

.form-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}

.decision-options {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.decision-option {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border: 2px solid var(--border-light);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-fast);
  align-items: flex-start;
}

.decision-option:hover {
  border-color: var(--primary-300);
}

.decision-option.active {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.decision-option input {
  display: none;
}

.option-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-lg);
  border: 2px solid var(--border-light);
  flex-shrink: 0;
}

.decision-option.active .option-icon {
  background: var(--primary-gradient);
  color: white;
  border-color: transparent;
}

.option-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-text strong {
  color: var(--text-primary);
}

.option-desc {
  font-size: 11px;
  color: var(--text-muted);
}

.adjustment-area {
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.adjustment-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-bottom: var(--space-3);
}

.adjustment-item {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}

.vehicle-info {
  min-width: 100px;
}

.vehicle-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.vehicle-plate {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.slider-bar-container {
  flex: 1;
  position: relative;
  height: 12px;
}

.slider-bar-track {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  height: 12px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.slider-bar-fill {
  height: 100%;
  background: var(--primary-gradient);
  border-radius: var(--radius-full);
  transition: width var(--transition-normal);
}

.merged-slider {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  cursor: pointer;
  outline: none;
}

.merged-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  background: var(--primary-500);
  border-radius: 50%;
  cursor: pointer;
  border: 3px solid white;
  box-shadow: var(--shadow-md);
  transition: all var(--transition-fast);
  margin-top: -4px;
}

.merged-slider::-webkit-slider-thumb:hover {
  transform: scale(1.15);
  box-shadow: var(--shadow-lg);
}

.merged-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  background: var(--primary-500);
  border-radius: 50%;
  cursor: pointer;
  border: 3px solid white;
  box-shadow: var(--shadow-md);
  transition: all var(--transition-fast);
}

.percentage-input-wrapper {
  position: relative;
  width: 75px;
}

.percentage-input {
  width: 100%;
  padding: 6px 22px 6px 8px;
  font-size: var(--text-sm);
  font-weight: 600;
  text-align: center;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--primary-600);
  outline: none;
  transition: all var(--transition-fast);
}

.percentage-input:focus {
  border-color: var(--primary-500);
  box-shadow: var(--shadow-focus);
}

.percentage-suffix {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--primary-600);
  pointer-events: none;
}

.percentage-input::-webkit-outer-spin-button,
.percentage-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.percentage-input[type=number] {
  -moz-appearance: textfield;
}

.percentage-display {
  min-width: 50px;
  text-align: right;
  font-weight: 700;
  font-size: var(--text-lg);
  color: var(--text-primary);
}

.total-check {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 600;
  padding-top: var(--space-2);
  border-top: 1px solid var(--border-light);
}

.total-check.error {
  color: var(--danger-500);
}

.form-group {
  margin-bottom: var(--space-6);
}

.form-textarea {
  width: 100%;
  min-height: 120px;
  padding: 10px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  color: var(--text-primary);
  resize: vertical;
  outline: none;
  transition: all var(--transition-fast);
  background: var(--bg-secondary);
  font-family: var(--font-sans);
  line-height: var(--leading-relaxed);
}

.form-textarea:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
  background: var(--bg-primary);
}

.form-actions {
  display: flex;
  gap: var(--space-4);
  justify-content: flex-end;
  padding-top: var(--space-2);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: 9px 18px;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  font-family: var(--font-sans);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none !important;
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
  border-color: var(--border-light);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--primary-soft);
  border-color: var(--primary-300);
  color: var(--primary);
  transform: translateY(-1px);
}

.btn-primary {
  background: var(--primary-gradient);
  color: white;
  border: none;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-gradient-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.submitted-content {
  text-align: center;
  padding: var(--space-6);
}

.success-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: rgba(34, 197, 94, 0.1);
  color: var(--success-500);
  font-size: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto var(--space-4);
}

.success-title {
  font-size: var(--text-xl);
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.success-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-6);
}

.submitted-details {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
}

.detail-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

.detail-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
  text-align: right;
}

.note-value {
  max-width: 400px;
  line-height: var(--leading-relaxed);
}

.submitted-actions {
  display: flex;
  justify-content: center;
  gap: var(--space-4);
}

.dify-analysis-section {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.03) 0%, rgba(139, 92, 246, 0.03) 100%);
  border: 1px solid rgba(99, 102, 241, 0.15);
}

.dify-header {
  margin-bottom: var(--space-4);
}

.dify-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dify-badge-icon {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
}

.dify-content {
  padding: 4px;
}

.dify-formatted {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dify-item {
  background: rgba(255, 255, 255, 0.8);
  border-radius: 10px;
  padding: 12px 16px;
  border-left: 4px solid #6366f1;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.dify-nested-item {
  border-left: 3px solid #a5b4fc;
  padding: 8px 12px;
  margin-left: 12px;
  background: rgba(99, 102, 241, 0.03);
}

.dify-item-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 6px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.dify-item-value {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
  padding: 8px 12px;
  background: rgba(99, 102, 241, 0.05);
  border-radius: 8px;
}

.dify-item-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dify-list-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 6px;
  border-left: 3px solid #8b5cf6;
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
}

.dify-bullet {
  color: #8b5cf6;
  font-weight: 700;
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.dify-nested {
  margin-left: 16px;
  padding-left: 12px;
  border-left: 2px dashed #cbd5e1;
}

.dify-text-output {
  font-size: 13px;
  line-height: 1.7;
  color: #475569;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  border-left: 3px solid #6366f1;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: var(--space-3);
  }
  
  .summary-grid {
    grid-template-columns: 1fr;
  }
  
  .liability-cards {
    grid-template-columns: 1fr;
  }
  
  .adjustment-item {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .form-actions {
    flex-direction: column;
  }
  
  .btn {
    width: 100%;
  }
}
</style>
