<template>
  <div class="liability-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">责任建议</h1>
        <p class="page-subtitle">基于智能分析的责任认定建议</p>
      </div>
      <div class="header-actions">
        <span class="analysis-status" :class="hasAnalysis ? 'status-completed' : 'status-pending'">
          {{ hasAnalysis ? '分析已完成' : '待分析' }}
        </span>
      </div>
    </div>

    <div class="liability-container">
      <div class="case-overview card-surface">
        <h2 class="section-title">案件概览</h2>
        <div class="overview-grid">
          <div class="overview-item">
            <span class="overview-label">案件编号</span>
            <span class="overview-value">{{ state.caseId }}</span>
          </div>
          <div class="overview-item">
            <span class="overview-label">事故类型</span>
            <span class="overview-value">{{ state.form.accidentType || '待填写' }}</span>
          </div>
          <div class="overview-item">
            <span class="overview-label">涉事车辆</span>
            <span class="overview-value">{{ state.form.vehicles.length }}辆</span>
          </div>
          <div class="overview-item">
            <span class="overview-label">分析置信度</span>
            <span class="overview-value">{{ hasAnalysis ? state.analysis.confidence + '%' : '--' }}</span>
          </div>
        </div>
      </div>

      <div v-if="!hasAnalysis" class="pending-section card-surface">
        <div class="pending-content">
          <div class="pending-icon">
            <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10" fill-opacity="0.15"/>
              <path d="M12 6v6l4 2" stroke-linecap="round"/>
            </svg>
          </div>
          <h3>数据待分析</h3>
          <p>请先前往'智能分析'页面完成分析，分析完成后将自动生成责任建议</p>
        </div>
      </div>

      <div v-else class="liability-result card-surface">
        <h2 class="section-title">责任认定结果</h2>
        <div class="result-card">
          <div class="result-header">
            <div class="result-icon">
              <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10" fill-opacity="0.15"/><polyline points="8 12 11 15 16 9" fill="none" stroke-width="2"/></svg>
            </div>
            <div class="result-title">
              <h3>责任认定</h3>
              <p class="result-confidence">置信度: {{ state.analysis.confidence }}%</p>
            </div>
          </div>
          <div class="liability-details">
            <div v-for="(liability, index) in vehicleLiabilities" :key="liability.key" class="liability-party">
              <div class="party-header">
                <div class="party-info">
                  <span class="party-role">{{ liability.role || liability.vehicleType }}</span>
                  <span v-if="liability.plate" class="party-plate">{{ liability.plate }}</span>
                </div>
              </div>
              <div class="party-liability">
                <span class="liability-level" :class="getLiabilityClass(liability.liability)">{{ liability.liability }}</span>
                <span class="liability-percentage">{{ liability.percentage }}%</span>
              </div>
            </div>
          </div>
          <div class="liability-reasoning">
            <h4>认定理由</h4>
            <p>{{ getReasoningText() }}</p>
          </div>
        </div>
      </div>

      <div v-if="hasAnalysis" class="suggestion-section card-surface">
        <h2 class="section-title">处理建议</h2>
        <div class="suggestion-grid">
          <div class="suggestion-item">
            <div class="suggestion-icon">
              <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5">
                <path d="M12 2l3 7h7l-5.5 4 2 7-6.5-4.5L5.5 20l2-7L2 9h7l3-7z" fill-opacity="0.15"/>
              </svg>
            </div>
            <h4>快速处理</h4>
            <p>责任明确的事故，建议优先选择快速处理程序，节省时间</p>
          </div>
          <div class="suggestion-item">
            <div class="suggestion-icon">
              <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5">
                <path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 00-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" fill-opacity="0.15"/>
              </svg>
            </div>
            <h4>保险理赔</h4>
            <p>责任认定后，及时联系保险公司进行理赔，保留好相关证据</p>
          </div>
          <div class="suggestion-item">
            <div class="suggestion-icon">
              <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5">
                <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" fill-opacity="0.15"/>
                <circle cx="9" cy="7" r="4" fill-opacity="0.15"/>
                <path d="M23 21v-2a4 4 0 00-3-3.87"/>
                <circle cx="16" cy="3" r="4" fill-opacity="0.15"/>
              </svg>
            </div>
            <h4>安全教育</h4>
            <p>建议驾驶人参加交通安全学习，提高安全意识，避免类似事故</p>
          </div>
        </div>
      </div>

      <div v-if="hasAnalysis" class="risk-section card-surface">
        <h2 class="section-title">风险评估</h2>
        <div class="risk-content">
          <div class="risk-level">
            <span class="risk-label">风险等级</span>
            <span class="risk-value" :class="getRiskClass()">
              {{ getRiskLevel() }}
            </span>
          </div>
          <div class="risk-details">
            <div class="risk-item">
              <span class="risk-item-label">事故严重程度</span>
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: getSeverity() + '%' }"></div>
              </div>
            </div>
            <div class="risk-item">
              <span class="risk-item-label">责任清晰程度</span>
              <div class="progress-bar">
                <div class="progress-fill progress-high" :style="{ width: state.analysis.confidence + '%' }"></div>
              </div>
            </div>
            <div class="risk-item">
              <span class="risk-item-label">证据完整程度</span>
              <div class="progress-bar">
                <div class="progress-fill progress-medium" :style="{ width: state.analysis.evidenceIntegrity + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

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

      <div v-if="hasAnalysis" class="note-section card-surface">
        <h2 class="section-title">重要提示</h2>
        <div class="note-content">
          <ul class="note-list">
            <li>本责任建议基于智能分析结果，仅供参考，最终责任以交警部门认定为准</li>
            <li>若对责任认定有异议，可申请人工复核或向上级部门申诉</li>
            <li>事故处理过程中，请注意保留好相关证据（照片、视频、证人联系方式等）</li>
            <li>建议在事故处理完毕后，及时更新车辆保险信息</li>
          </ul>
        </div>
      </div>

      <div class="liability-actions">
        <button class="btn btn-secondary" :disabled="!hasAnalysis" @click="viewReport">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          详细报告
        </button>
        <button class="btn btn-primary" :disabled="!hasAnalysis" @click="submitReview">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          提交复核
        </button>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import { CasesAPI } from '../api/index.js'
import NavigationButtons from '../components/NavigationButtons.vue'

const router = useRouter()

const {
  state,
  goStep,
  completeRecommendation
} = useAccidentFlow()

goStep('recommendation')

async function loadCaseLiability() {
  try {
    const result = await CasesAPI.getDetail(state.caseId)
    if (result.success && result.data) {
      const liability = result.data.liability
      if (liability) {
        state.analysis.vehicleLiabilities = liability.details?.vehicles || []
        state.analysis.confidence = liability.details?.confidence || state.analysis.confidence
        state.analysis.reasoningText = liability.summary || ''
      }
    } else {
      // 案件不存在
      notify({ title: '案件不存在', message: `案件 ${state.caseId} 未找到，请从历史案例选择`, type: 'warning' })
      setTimeout(() => router.push('/history-cases'), 1500)
    }
  } catch (e) {
    console.warn('加载责任结果失败:', e)
    notify({ title: '加载失败', message: '无法加载案件数据，请重试', type: 'error' })
  }
}

onMounted(() => {
  loadCaseLiability()
})

const hasAnalysis = computed(() => {
  return state.analysis.confidence !== null && 
         state.analysis.confidence !== undefined &&
         state.analysis.confidence !== ''
})

const hasDifyResult = computed(() => {
  return state.analysis.difyResult !== null && state.analysis.difyResult !== undefined
})

const vehicleLiabilities = computed(() => {
  if (state.analysis.vehicleLiabilities && state.analysis.vehicleLiabilities.length > 0) {
    return state.analysis.vehicleLiabilities
  }
  
  const vehicles = state.form.vehicles || []
  const accidentType = state.form.accidentType
  
  if (vehicles.length === 0) return []
  
  let liabilities = []
  
  if (accidentType === '追尾事故') {
    if (vehicles.length === 2) {
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
    if (vehicles.length === 2) {
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
      const changingIndex = vehicles.findIndex(v => v.role === '变道车辆')
      vehicles.forEach((vehicle, index) => {
        if (vehicle.role === '变道车辆' || (changingIndex === -1 && index === 0)) {
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
            percentage = 15 / (vehicles.length - 2)
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
    if (vehicles.length === 2) {
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
  
  return liabilities
})

const getLiabilityClass = (liability) => {
  if (liability === '主责') return 'primary'
  if (liability === '次责') return 'secondary'
  if (liability === '无责') return 'none'
  return ''
}

const getReasoningText = () => {
  // 优先使用Dify解析出的真实理由
  if (state.analysis.reasoningText) {
    return state.analysis.reasoningText
  }
  
  // 如果Dify没有提供理由，使用默认模板
  const accidentType = state.form.accidentType
  const liabilities = vehicleLiabilities.value
  const liabilityText = liabilities.map(l => `${l.role || l.vehicleType}${l.plate ? '(' + l.plate + ')' : ''}：${l.liability}（${l.percentage}%）`).join('；')
  
  if (accidentType === '追尾事故') {
    return `经分析，该事故为追尾事故。责任分配：${liabilityText}。根据《道路交通安全法》第四十三条规定，同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。本次分析置信度为${state.analysis.confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  } else if (accidentType === '变道碰撞') {
    return `经分析，该事故为变道碰撞事故。责任分配：${liabilityText}。根据《道路交通安全法》第四十四条规定，机动车变更车道时，应当提前开启转向灯，确认安全后再变更车道。本次分析置信度为${state.analysis.confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  } else {
    return `经分析，该事故涉及交通违法行为。责任分配：${liabilityText}。根据《道路交通安全法》相关规定，驾驶员应遵守交通规则，确保行车安全。本次分析置信度为${state.analysis.confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  }
}

const getRiskLevel = () => {
  const confidence = state.analysis.confidence || 0
  if (confidence >= 90) return '低风险'
  if (confidence >= 70) return '中风险'
  return '高风险'
}

const getRiskClass = () => {
  const confidence = state.analysis.confidence || 0
  if (confidence >= 90) return 'risk-low'
  if (confidence >= 70) return 'risk-medium'
  return 'risk-high'
}

const getSeverity = () => {
  return Math.min(85, 30 + state.form.vehicles.length * 10)
}

const handleConfirmLiability = () => {
  const nextRoute = completeRecommendation()
  router.push(nextRoute)
  notify({ title: '责任确认', message: '责任认定已确认，进入规则依据页面' })
}

const handlePrintReport = () => {
  const printContent = document.querySelector('.liability-result')
  if (printContent) {
    const printWindow = window.open('', '_blank')
    printWindow.document.write(`
      <html>
        <head>
          <title>责任认定报告 - ${state.caseId}</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 40px; }
            h2 { color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }
            .result-card { background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }
            .liability-party { background: #fff; padding: 15px; border-radius: 6px; margin: 10px 0; border: 1px solid #eee; }
            .party-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
            .party-role { font-weight: bold; font-size: 16px; }
            .party-plate { color: #666; background: #eee; padding: 4px 12px; border-radius: 8px; }
            .party-liability { display: flex; align-items: center; gap: 12px; }
            .liability-level { padding: 6px 16px; border-radius: 20px; font-weight: bold; }
            .liability-level.primary { background: #fee; color: #c00; }
            .liability-level.secondary { background: #fff3e0; color: #ed6c02; }
            .liability-level.none { background: #efe; color: #090; }
            .liability-percent { font-size: 18px; font-weight: bold; }
            .liability-reasoning { background: #f8f9fa; padding: 15px; border-radius: 6px; margin-top: 15px; }
            .liability-reasoning h4 { margin-bottom: 10px; }
            .liability-reasoning p { line-height: 1.6; color: #555; }
            .result-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
            .result-title h3 { font-size: 20px; margin-bottom: 4px; }
            .result-confidence { color: #090; font-weight: 600; }
          </style>
        </head>
        <body>
          <h1 style="text-align: center; margin-bottom: 30px;">事故责任认定报告</h1>
          <p><strong>案件编号:</strong> ${state.caseId}</p>
          <p><strong>事故类型:</strong> ${state.form.accidentType || '待分析'}</p>
          <p><strong>生成时间:</strong> ${new Date().toLocaleString()}</p>
          ${printContent.innerHTML}
          <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #999; font-size: 12px;">
            <p>本报告由交通事故智能分析平台自动生成，仅供参考。</p>
          </div>
        </body>
      </html>
    `)
    printWindow.document.close()
    printWindow.print()
  }
  notify({ title: '打印报告', message: '责任认定报告已生成，正在打印' })
}

const viewReport = () => {
  router.push('/report-detail')
}

const submitReview = () => {
  const liabilitySummary = vehicleLiabilities.value.map(l => `${l.role || l.vehicleType}${l.plate ? '(' + l.plate + ')' : ''}：${l.liability}(${l.percentage}%)`).join('，')
  
  const suggestions = [
    { title: '快速处理', description: '责任明确的事故，建议优先选择快速处理程序，节省时间' },
    { title: '保险理赔', description: '责任认定后，及时联系保险公司进行理赔，保留好相关证据' },
    { title: '安全教育', description: '建议驾驶人参加交通安全学习，提高安全意识，避免类似事故' }
  ]
  
  completeRecommendation({
    summary: liabilitySummary,
    ratio: vehicleLiabilities.value[0]?.percentage + '%' || '0%',
    hitRules: [],
    suggestions: suggestions,
    vehicleLiabilities: vehicleLiabilities.value
  })

  router.push('/manual-review')
  notify({ title: '提交成功', message: '案件已提交到复核队列' })
}

const difyAnalysisText = computed(() => {
  return state.analysis.difyAnalysisText || '暂无分析结果'
})

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
</script>

<style scoped>
.liability-page {
  padding: 0;
  animation: pageIn 0.4s var(--ease-default);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.analysis-status {
  padding: 5px 14px;
  border-radius: var(--radius-full);
  font-size: 13px;
  font-weight: 600;
}

.status-pending {
  background: rgba(148, 163, 184, 0.1);
  color: #64748b;
}

.status-completed {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.liability-container {
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
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-5);
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-4);
}

.overview-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-light);
  transition: all var(--transition-fast);
}

.overview-item:hover { border-color: var(--primary-300); transform: translateY(-1px); }

.overview-label {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.overview-value {
  font-size: var(--text-base);
  color: var(--text-primary);
  font-weight: 700;
}

.pending-section {
  text-align: center;
}

.pending-content {
  padding: var(--space-10);
}

.pending-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto var(--space-5);
  color: #64748b;
}

.pending-content h3 {
  font-size: var(--text-xl);
  color: var(--text-primary);
  margin-bottom: var(--space-3);
  font-weight: 700;
}

.pending-content p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  max-width: 500px;
  margin: 0 auto;
  line-height: var(--leading-relaxed);
}

.result-card {
  background: var(--primary-soft);
  border-radius: var(--radius-2xl);
  padding: var(--space-6);
  border-left: 4px solid var(--primary);
}

.result-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.result-icon {
  width: 52px;
  height: 52px;
  border-radius: var(--radius-2xl);
  background: var(--primary-gradient);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.25);
}

.result-icon svg { width: 26px; height: 26px; }

.result-title h3 {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 3px;
}

.result-confidence {
  font-size: var(--text-sm);
  color: #22c55e;
  font-weight: 600;
}

.liability-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.liability-party {
  background: var(--bg-primary);
  border-radius: var(--radius-2xl);
  padding: var(--space-5);
  border: 2px solid var(--border-light);
  position: relative;
  overflow: hidden;
  transition: all var(--transition-normal);
}

.liability-party:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }

.party-header {
  margin-bottom: var(--space-4);
}

.party-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.party-role {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
}

.party-plate {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
}

.party-liability {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.liability-level {
  display: inline-block;
  width: fit-content;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 700;
}

.liability-level.primary { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
.liability-level.secondary { background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
.liability-level.none { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.3); }

.liability-percentage {
  font-size: var(--text-2xl);
  font-weight: 800;
  color: var(--text-primary);
}

.liability-reasoning {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  border: 1px solid var(--border-light);
}

.liability-reasoning h4 {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}

.liability-reasoning p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
}

.suggestion-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--space-5);
}

.suggestion-item {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  border: 1px solid var(--border-light);
  transition: all var(--transition-normal);
}

.suggestion-item:hover {
  border-color: var(--primary-300);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.suggestion-icon {
  width: 44px;
  height: 44px;
  margin-bottom: var(--space-4);
  color: var(--primary);
}

.suggestion-item h4 {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.suggestion-item p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
}

.risk-content {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-5);
}

.risk-level {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
}

.risk-label {
  font-size: var(--text-base);
  color: var(--text-secondary);
  font-weight: 600;
}

.risk-value {
  font-size: var(--text-lg);
  font-weight: 700;
  padding: 5px 14px;
  border-radius: var(--radius-full);
}

.risk-low {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.risk-medium {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.risk-high {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.risk-details {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.risk-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.risk-item-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--border-light);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: var(--radius-full);
  transition: width 0.5s var(--ease-default);
}

.progress-high {
  background: var(--success-500);
}

.progress-medium {
  background: var(--warning-500);
}

.note-content {
  background: rgba(59, 130, 246, 0.05);
  border: 1px dashed var(--primary-300);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
}

.note-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.note-list li {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  padding: var(--space-2) 0 var(--space-2) 24px;
  position: relative;
}

.note-list li:before {
  content: '•';
  position: absolute;
  left: 8px;
  color: var(--primary);
  font-weight: bold;
}

.liability-actions {
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
  padding: 10px 20px;
  border-radius: var(--radius-xl);
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

.btn-icon {
  width: 18px;
  height: 18px;
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
    align-items: flex-start;
    gap: var(--space-3);
  }
  
  .overview-grid { grid-template-columns: 1fr; }
  .liability-details { grid-template-columns: 1fr; }
  .suggestion-grid { grid-template-columns: 1fr; }
  .liability-actions { flex-direction: column; }
  .btn { width: 100%; }
}
</style>