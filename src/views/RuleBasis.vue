<template>
  <div class="rule-basis-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">规则依据</h1>
        <p class="page-subtitle">事故责任认定的法律依据</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goToRuleLibrary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
            <polyline points="2 17 12 22 22 17"></polyline>
            <polyline points="2 12 12 17 22 12"></polyline>
          </svg>
          打开规则库
        </button>
      </div>
    </div>

    <div class="rule-basis-container">
      <div class="case-info card-surface">
        <h2 class="section-title">案件信息</h2>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">案件编号</span>
            <span class="info-value">{{ state.caseId }}</span>
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

      <div class="analysis-result card-surface">
        <h2 class="section-title">分析结果</h2>
        <div class="result-card">
          <div class="result-item">
            <span class="result-label">责任建议</span>
            <span class="result-value">{{ getLiabilitySummary() }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">车辆数量</span>
            <span class="result-value">{{ state.form.vehicles.length }}辆</span>
          </div>
          <div class="result-item">
            <span class="result-label">置信度</span>
            <span class="result-value confidence-high">{{ state.analysis.confidence }}%</span>
          </div>
          <div class="result-item">
            <span class="result-label">证据完整性</span>
            <span class="result-value">{{ state.analysis.evidenceIntegrity }}%</span>
          </div>
        </div>
        
        <div v-if="hasAnalysis && state.analysis.vehicleLiabilities.length > 0" class="liability-preview">
          <h3 class="preview-title">责任分配预览</h3>
          <div class="liability-cards">
            <div v-for="(liability, idx) in state.analysis.vehicleLiabilities" :key="idx" class="liability-card-mini">
              <span class="vehicle-tag">{{ liability.role || liability.vehicleType }}</span>
              <span class="plate-number">{{ liability.plate || '未知车牌' }}</span>
              <span class="liability-tag" :class="getLiabilityClass(liability.liability)">
                {{ liability.liability }} ({{ liability.percentage }}%)
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="rule-search card-surface">
        <div class="search-box">
          <input 
            type="text" 
            v-model="searchQuery" 
            placeholder="搜索规则或法律法规" 
            class="search-input"
            @input="handleSearch"
          >
          <button class="search-button" @click="handleSearch">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"></path>
            </svg>
            搜索
          </button>
        </div>
      </div>

      <div class="rule-categories card-surface">
        <h2 class="section-title">规则分类</h2>
        <div class="categories-list">
          <button 
            v-for="cat in categories" 
            :key="cat"
            class="category-item" 
            :class="{ active: selectedCategory === cat }" 
            @click="handleCategorySelect(cat)"
          >
            {{ cat }}
          </button>
        </div>
      </div>

      <div class="rule-list card-surface">
        <div class="list-header">
          <h2 class="section-title">规则库规则</h2>
          <span class="rule-count">{{ ruleLibrary.length }} 条</span>
        </div>
        <div class="rules-grid">
          <div v-for="rule in filteredRules" :key="rule.id" class="rule-card" :class="{ selected: isRuleSelected(rule.id) }">
            <div class="rule-header">
              <span class="rule-code">{{ rule.id }}</span>
              <span class="rule-category">{{ rule.type }}</span>
              <button class="select-rule-btn" @click="toggleRuleSelect(rule)" v-if="!isRuleSelected(rule.id)">
                选择
              </button>
              <button class="deselect-rule-btn" @click="toggleRuleSelect(rule)" v-else>
                取消
              </button>
            </div>
            <h3 class="rule-title">{{ rule.name }}</h3>
            <p class="rule-content">{{ rule.content || `适用于${rule.scene}场景的责任认定规则。` }}</p>
            <div class="rule-meta">
              <span class="rule-scenario">适用场景: {{ rule.scene }}</span>
              <span class="rule-status" :class="rule.status === '启用' ? 'status-active' : 'status-inactive'">
                {{ rule.status }}
              </span>
            </div>
          </div>
        </div>
        <div v-if="ruleLibrary.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
              <polyline points="2 17 12 22 22 17"></polyline>
              <polyline points="2 12 12 17 22 12"></polyline>
            </svg>
          </div>
          <p class="empty-text">规则库为空，请先前往规则库添加规则</p>
        </div>
      </div>

      <div class="default-rules card-surface">
        <h2 class="section-title">标准规则</h2>
        <div class="rules-grid">
          <div v-for="rule in defaultRules" :key="rule.code" class="rule-card" :class="{ selected: isRuleSelected(rule.code) }">
            <div class="rule-header">
              <span class="rule-code">{{ rule.code }}</span>
              <span class="rule-category">{{ rule.category }}</span>
              <button class="select-rule-btn" @click="toggleDefaultRuleSelect(rule)" v-if="!isRuleSelected(rule.code)">
                选择
              </button>
              <button class="deselect-rule-btn" @click="toggleDefaultRuleSelect(rule)" v-else>
                取消
              </button>
            </div>
            <h3 class="rule-title">{{ rule.title }}</h3>
            <p class="rule-content">{{ rule.content }}</p>
            <div class="rule-meta">
              <span class="rule-scenario">适用场景: {{ rule.scenario }}</span>
              <span class="rule-applied">应用次数: {{ rule.applied }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="state.ruleBasis.selectedRules.length > 0" class="selected-rules card-surface">
        <h2 class="section-title">已选择的规则 ({{ state.ruleBasis.selectedRules.length }})</h2>
        <div class="selected-rules-list">
          <div v-for="rule in state.ruleBasis.selectedRules" :key="rule.id || rule.code" class="selected-rule-item">
            <span class="rule-code-small">{{ rule.id || rule.code }}</span>
            <span class="rule-title-small">{{ rule.name || rule.title }}</span>
            <button class="remove-btn" @click="removeRule(rule)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div class="legal-basis card-surface">
        <h2 class="section-title">法律依据说明</h2>
        <textarea 
          v-model="legalBasis" 
          class="legal-basis-textarea" 
          placeholder="请输入法律依据说明..."
          @input="updateLegalBasis"
        ></textarea>
      </div>

      <!-- 后端命中规则展示 -->
      <div class="card-surface matched-rules-section">
        <h2 class="section-title">命中规则（来自智能分析）</h2>
        <div v-if="loadingRules" class="empty-state">
          <p class="empty-text">加载中...</p>
        </div>
        <div v-else-if="loadError" class="empty-state">
          <p class="empty-text" style="color:#ef4444;">加载失败: {{ loadError }}</p>
        </div>
        <div v-else-if="matchedRules.length === 0" class="empty-state">
          <p class="empty-text">未匹配到规则，建议人工复核</p>
        </div>
        <div v-else class="rules-grid">
          <div v-for="(rule, idx) in matchedRules" :key="rule.match_id || idx" class="rule-card selected">
            <div class="rule-header">
              <span class="rule-code">{{ rule.rule_id || 'N/A' }}</span>
              <span class="rule-category">匹配规则</span>
            </div>
            <h3 class="rule-title">{{ rule.rule_name || '未命名规则' }}</h3>
            <div class="rule-detail-list">
              <div class="rule-detail-item">
                <span class="detail-label">触发条件</span>
                <span class="detail-value">{{ rule.trigger_condition || '无' }}</span>
              </div>
              <div class="rule-detail-item">
                <span class="detail-label">推理说明</span>
                <span class="detail-value">{{ rule.trigger_reason || '无' }}</span>
              </div>
              <div class="rule-detail-item">
                <span class="detail-label">法律依据</span>
                <span class="detail-value">{{ rule.legal_basis || '无' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="dify-analysis-container" v-if="hasDifyResult">
        <div class="dify-analysis-title">
          <div class="dify-icon-wrapper">
            <span class="dify-icon">🤖</span>
          </div>
          <span class="dify-title-text">Dify智能分析</span>
        </div>
        <div class="markdown-content" v-html="parseMarkdown(difyAnalysisText)"></div>
      </div>
      <div v-if="!hasDifyResult" class="no-dify-data">
        <p style="text-align: center; color: #94a3b8; padding: 20px;">暂无Dify分析数据，请先在视频处理页点击"Send To Dify"</p>
      </div>

      <div class="rule-actions">
        <button class="btn btn-secondary" @click="handleViewLogs">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
          </svg>
          查看日志
        </button>
        <button class="btn btn-primary" @click="handleCompleteRuleBasis" :disabled="state.ruleBasis.confirmed">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          {{ state.ruleBasis.confirmed ? '已确认' : '确认规则依据' }}
        </button>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import { CasesAPI } from '../api/index.js'
import NavigationButtons from '../components/NavigationButtons.vue'

const router = useRouter()
const route = useRoute()

const {
  state,
  goStep,
  completeRuleBasis,
  updateRuleBasis,
  getLogs,
  logMessage,
  LOG_LEVELS,
  initRuleLibrary,
  getRuleLibrary,
  selectRuleFromLibrary,
  deselectRuleFromLibrary,
  setCurrentCase,
  getCurrentCase,
  isValidCaseId
} = useAccidentFlow()

goStep('rule-basis')

// 统一获取 caseId：优先 URL query，fallback store/localStorage，自动过滤无效值
const currentCaseId = () => {
  const queryId = route.query.caseId
  if (isValidCaseId(queryId)) {
    return String(queryId).trim()
  }
  return getCurrentCase()
}

// 从后端加载命中规则
const matchedRules = ref([])
const loadingRules = ref(false)
const loadError = ref('')

async function fetchMatchedRules() {
  const caseId = currentCaseId()
  if (!isValidCaseId(caseId)) return
  // 同步到 store（防止刷新后 store 丢失）
  if (String(caseId) !== String(state.caseId)) setCurrentCase(caseId)
  loadingRules.value = true
  loadError.value = ''
  try {
    const result = await CasesAPI.getMatchedRules(caseId)
    if (result.success && Array.isArray(result.data)) {
      matchedRules.value = result.data
      // Update store with selected rules from matched data
      if (result.data.length > 0) {
        const storeRules = result.data.map(r => ({
          id: r.rule_id,
          code: r.rule_id,
          name: r.rule_name,
          content: r.legal_basis,
          type: '',
          trigger_condition: r.trigger_condition,
          trigger_reason: r.trigger_reason,
        }))
        updateRuleBasis({ selectedRules: storeRules, appliedRules: storeRules })
      }
    } else {
      // 案件不存在
      notify({ title: '案件不存在', message: `案件 ${caseId} 未找到，请从历史案例选择`, type: 'warning' })
      setTimeout(() => router.push('/history-cases'), 1500)
    }
  } catch (err) {
    console.warn('获取命中规则失败:', err)
    loadError.value = err.message || '获取命中规则失败'
    notify({ title: '加载失败', message: '无法加载案件数据，请重试', type: 'error' })
  } finally {
    loadingRules.value = false
  }
}

onMounted(() => {
  fetchMatchedRules()
})

const categories = ['全部', '道路交通安全法', '实施条例', '地方法规', '司法解释']
const selectedCategory = computed(() => state.ruleBasis.selectedCategory)
const searchQuery = computed({
  get: () => state.ruleBasis.searchQuery,
  set: (val) => updateRuleBasis({ searchQuery: val })
})
const legalBasis = computed({
  get: () => state.ruleBasis.legalBasis,
  set: (val) => updateRuleBasis({ legalBasis: val })
})

const ruleLibrary = computed(() => {
  if (state.ruleLibrary.rules.length === 0) {
    initRuleLibrary()
  }
  return state.ruleLibrary.rules
})

const defaultRules = ref([
  { code: 'R-01', category: '道路交通安全法', title: '追尾事故责任认定', content: '后车未保持安全距离导致追尾，后车承担全部责任。', scenario: '同向行驶追尾', applied: 156 },
  { code: 'R-03', category: '实施条例', title: '安全距离规定', content: '同车道行驶应保持足以采取紧急制动措施的安全距离。', scenario: '制动不及', applied: 134 },
  { code: 'R-04', category: '地方法规', title: '路口让行规则', content: '无信号灯路口应让右方来车先行。', scenario: '路口碰撞', applied: 87 },
  { code: 'R-06', category: '道路交通安全法', title: '闯红灯责任规则', content: '违反信号灯通行导致事故，违规方承担全部责任。', scenario: '信号灯路口', applied: 203 },
  { code: 'R-07', category: '实施条例', title: '变更车道规则', content: '变更车道时不得影响相关车道内行驶的机动车的正常行驶。', scenario: '变道碰撞', applied: 98 },
  { code: 'R-08', category: '司法解释', title: '交通事故责任划分', content: '公安机关交通管理部门应当根据当事人的行为对发生道路交通事故所起的作用以及过错的严重程度，确定当事人的责任。', scenario: '综合判定', applied: 312 }
])

const filteredRules = computed(() => {
  let filtered = ruleLibrary.value
  
  if (selectedCategory.value !== '全部') {
    filtered = filtered.filter(rule => rule.type === selectedCategory.value)
  }
  
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(rule => 
      (rule.name && rule.name.toLowerCase().includes(query)) ||
      (rule.type && rule.type.toLowerCase().includes(query)) ||
      (rule.scene && rule.scene.toLowerCase().includes(query)) ||
      (rule.id && rule.id.toLowerCase().includes(query))
    )
  }
  
  return filtered
})

const hasDifyResult = computed(() => {
  return state.analysis.difyResult !== null && state.analysis.difyResult !== undefined
})

const difyAnalysisText = computed(() => {
  return state.analysis.difyAnalysisText || '暂无分析结果'
})

const difyLegalClues = computed(() => {
  return state.analysis.difyLegalClues || []
})

const hasAnalysis = computed(() => {
  return state.analysis.confidence !== null && state.analysis.confidence !== ''
})

function goToRuleLibrary() {
  router.push('/rule-library')
}

function handleSearch() {
  if (!searchQuery.value.trim()) {
    notify({ title: '提示', message: '请输入搜索关键词', type: 'info' })
    return
  }
  logMessage(LOG_LEVELS.INFO, 'rule-basis', 'SEARCH', `搜索规则: ${searchQuery.value}`)
  notify({ title: '搜索规则', message: `正在搜索: ${searchQuery.value}` })
}

function handleCategorySelect(cat) {
  updateRuleBasis({ selectedCategory: cat })
  logMessage(LOG_LEVELS.INFO, 'rule-basis', 'CATEGORY', `切换分类: ${cat}`)
  notify({ title: '分类筛选', message: `已切换到: ${cat}` })
}

function isRuleSelected(idOrCode) {
  return state.ruleBasis.selectedRules.some(r => r.id === idOrCode || r.code === idOrCode)
}

function toggleRuleSelect(rule) {
  if (isRuleSelected(rule.id)) {
    deselectRuleFromLibrary(rule.id)
    notify({ title: '取消选择', message: `已取消选择: ${rule.name}` })
  } else {
    selectRuleFromLibrary(rule)
    notify({ title: '选择规则', message: `已选择: ${rule.name}` })
  }
}

function toggleDefaultRuleSelect(rule) {
  let selectedRules = [...state.ruleBasis.selectedRules]
  if (isRuleSelected(rule.code)) {
    selectedRules = selectedRules.filter(r => r.code !== rule.code)
    logMessage(LOG_LEVELS.INFO, 'rule-basis', 'UNSELECT_RULE', `取消选择规则: ${rule.code}`)
    notify({ title: '取消选择', message: `已取消选择: ${rule.title}` })
  } else {
    const ruleToAdd = {
      id: rule.code,
      code: rule.code,
      name: rule.title,
      title: rule.title,
      category: rule.category,
      type: rule.category,
      content: rule.content,
      applied: rule.applied
    }
    selectedRules.push(ruleToAdd)
    logMessage(LOG_LEVELS.INFO, 'rule-basis', 'SELECT_RULE', `选择规则: ${rule.code}`)
    notify({ title: '选择规则', message: `已选择: ${rule.title}` })
  }
  updateRuleBasis({ selectedRules, appliedRules: selectedRules })
}

function removeRule(rule) {
  if (rule.id) {
    deselectRuleFromLibrary(rule.id)
  } else {
    let selectedRules = state.ruleBasis.selectedRules.filter(r => r.code !== rule.code)
    updateRuleBasis({ selectedRules, appliedRules: selectedRules })
  }
  notify({ title: '移除规则', message: `已移除: ${rule.name || rule.title}` })
}

function updateLegalBasis() {
  // 实时更新到store
}

function getLiabilitySummary() {
  if (!hasAnalysis.value || state.analysis.vehicleLiabilities.length === 0) {
    return '待生成责任建议'
  }
  const liabilities = state.analysis.vehicleLiabilities
  return liabilities.map(l => `${l.role || l.vehicleType}: ${l.liability}`).join('，')
}

function getLiabilityClass(liability) {
  if (liability.includes('主责')) return 'primary'
  if (liability.includes('次责')) return 'secondary'
  return 'none'
}

function handleCompleteRuleBasis() {
  if (state.ruleBasis.selectedRules.length === 0) {
    notify({ title: '提示', message: '请至少选择一条规则', type: 'warning' })
    logMessage(LOG_LEVELS.WARNING, 'rule-basis', 'COMPLETE', '未选择规则，无法确认')
    return
  }
  
  logMessage(LOG_LEVELS.INFO, 'rule-basis', 'COMPLETE', '规则依据确认', {
    selectedRules: state.ruleBasis.selectedRules.length,
    legalBasis: state.ruleBasis.legalBasis
  })
  
  const result = completeRuleBasis()
  router.push({ path: result, query: { caseId: currentCaseId() } })
  notify({ title: '规则依据确认', message: '规则依据已确认，进入人工复核页面' })
}

function handleViewLogs() {
  const logs = getLogs()
  // console.log('系统日志:', logs)
  notify({ title: '查看日志', message: `共${logs.length}条日志，已输出到控制台` })
}

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
.rule-basis-page {
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
  align-items: center;
  gap: var(--space-4);
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

.rule-basis-container {
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

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
}

.rule-count {
  padding: 5px 12px;
  border-radius: var(--radius-full);
  background: var(--primary-soft);
  color: var(--primary);
  font-size: var(--text-xs);
  font-weight: 600;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-4);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  transition: all var(--transition-fast);
}

.info-item:hover { border-color: var(--primary-200); transform: translateY(-1px); }

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

.result-card {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  transition: all var(--transition-fast);
}

.result-item:hover { border-color: var(--primary-200); transform: translateY(-1px); }

.result-label {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.result-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
  line-height: var(--leading-snug);
}

.confidence-high {
  color: var(--success-500);
}

.liability-preview {
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-light);
}

.preview-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}

.liability-cards {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.liability-card-mini {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--space-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
}

.vehicle-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}

.plate-number {
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.liability-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  width: fit-content;
}

.liability-tag.primary { background: rgba(239, 68, 68, 0.15); color: var(--danger-500); }
.liability-tag.secondary { background: rgba(245, 158, 11, 0.15); color: var(--warning-500); }
.liability-tag.none { background: rgba(34, 197, 94, 0.15); color: var(--success-500); }

.search-box {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

.search-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  color: var(--text-primary);
  outline: none;
  background: var(--bg-secondary);
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.search-input:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
  background: var(--bg-primary);
}

.search-button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 10px 18px;
  background: var(--primary-gradient);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.search-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.categories-list {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.category-item {
  padding: 7px 16px;
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.category-item:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-soft);
}

.category-item.active {
  background: var(--primary-gradient);
  color: white;
  border-color: transparent;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.rules-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--space-5);
}

.rule-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  transition: all var(--transition-normal);
  position: relative;
}

.rule-card:hover {
  border-color: var(--primary-300);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.1);
  transform: translateY(-2px);
}

.rule-card.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.rule-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
  gap: var(--space-2);
}

.rule-code {
  font-size: 11px;
  font-weight: 700;
  color: var(--primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 3px 10px;
  border-radius: var(--radius-md);
}

.rule-category {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 3px 10px;
  border-radius: var(--radius-md);
  flex: 1;
}

.select-rule-btn, .deselect-rule-btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: var(--radius-md);
  border: 1px solid;
  cursor: pointer;
  font-weight: 600;
  transition: all var(--transition-fast);
}

.select-rule-btn {
  background: var(--bg-primary);
  color: var(--primary);
  border-color: var(--primary-300);
}

.select-rule-btn:hover {
  background: var(--primary);
  color: white;
}

.deselect-rule-btn {
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger-500);
  border-color: rgba(239, 68, 68, 0.3);
}

.deselect-rule-btn:hover {
  background: var(--danger-500);
  color: white;
}

.rule-title {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}

.rule-content {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin-bottom: var(--space-4);
}

.rule-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--text-muted);
}

.rule-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

.status-active { background: rgba(34, 197, 94, 0.1); color: var(--success-500); }
.status-inactive { background: rgba(107, 114, 128, 0.1); color: var(--text-muted); }

.selected-rules-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.selected-rule-item {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-3);
  background: var(--primary-soft);
  border: 1px solid var(--primary-300);
  border-radius: var(--radius-lg);
}

.rule-code-small {
  font-size: 11px;
  font-weight: 700;
  color: var(--primary);
}

.rule-title-small {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.remove-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(239, 68, 68, 0.1);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--danger-500);
  transition: all var(--transition-fast);
}

.remove-btn:hover {
  background: var(--danger-500);
  color: white;
}

.empty-state {
  padding: 48px var(--space-6);
  text-align: center;
}

.empty-icon {
  width: 60px;
  height: 60px;
  margin: 0 auto var(--space-4);
  color: var(--text-muted);
  opacity: 0.5;
}

.empty-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.legal-basis-textarea {
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

.legal-basis-textarea:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
}

.rule-actions {
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

.dify-legal-content {
  padding: 4px;
}

.dify-formatted {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dify-item {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(139, 92, 246, 0.03) 100%);
  border-radius: 10px;
  padding: 12px 16px;
  border-left: 4px solid #6366f1;
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
  background: rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
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
  background: rgba(255, 255, 255, 0.8);
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
  .page-header { flex-direction: column; align-items: stretch; }
  .header-actions { width: 100%; }
  .search-box { flex-direction: column; align-items: stretch; }
  .search-button { width: 100%; }
  .categories-list { justify-content: center; }
  .rules-grid { grid-template-columns: 1fr; }
  .rule-actions { flex-direction: column; }
  .btn { width: 100%; }
}
</style>