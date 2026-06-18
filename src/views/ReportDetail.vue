<template>
  <div class="report-page">
    <div class="report-header">
      <div class="header-left">
        <button class="back-btn" @click="goBack">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 18 9 12 15 6"></polyline>
          </svg>
          返回
        </button>
        <h1 class="report-title">事故分析详细报告</h1>
      </div>
      <button class="download-btn" @click="downloadReport">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        下载报告
      </button>
    </div>

    <div class="report-content">
      <div class="report-section">
        <h2 class="section-title">一、案件基本信息</h2>
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

      <div class="report-section">
        <h2 class="section-title">二、分析结果概览</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ state.analysis.confidence }}%</div>
            <div class="stat-label">分析置信度</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ state.analysis.evidenceIntegrity }}%</div>
            <div class="stat-label">证据完整度</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ state.analysis.keyframes.length }}</div>
            <div class="stat-label">关键帧数量</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ state.form.vehicles.length }}</div>
            <div class="stat-label">涉事车辆</div>
          </div>
        </div>
      </div>

      <div class="report-section">
        <h2 class="section-title">三、责任认定结果</h2>
        <div class="liability-list">
          <div v-for="(liability, index) in vehicleLiabilities" :key="liability.key" class="liability-card" :class="{ primary: liability.liability === '主责' }">
            <div class="liability-header">
              <span class="liability-role">{{ liability.role || liability.vehicleType }}</span>
              <span class="liability-plate">{{ liability.plate }}</span>
            </div>
            <div class="liability-info">
              <span class="liability-degree" :class="liability.liability">{{ liability.liability }}</span>
              <span class="liability-percent">{{ liability.percentage }}%</span>
            </div>
          </div>
        </div>
      </div>

      <div class="report-section">
        <h2 class="section-title">四、认定理由</h2>
        <div class="reasoning-box">
          <p>{{ getReasoningText() }}</p>
        </div>
      </div>

      <div class="report-section">
        <h2 class="section-title">五、处理建议</h2>
        <div class="suggestions-list">
          <div class="suggestion-card">
            <div class="suggestion-content">
              <h3>快速处理</h3>
              <p>责任明确的事故，建议优先选择快速处理程序，节省时间</p>
            </div>
          </div>
          <div class="suggestion-card">
            <div class="suggestion-content">
              <h3>保险理赔</h3>
              <p>责任认定后，及时联系保险公司进行理赔，保留好相关证据</p>
            </div>
          </div>
          <div class="suggestion-card">
            <div class="suggestion-content">
              <h3>安全教育</h3>
              <p>建议驾驶人参加交通安全学习，提高安全意识，避免类似事故</p>
            </div>
          </div>
        </div>
      </div>

      <div class="report-footer">
        <div class="footer-info">
          <span>报告生成时间: {{ new Date().toLocaleString('zh-CN') }}</span>
          <span>分析系统版本: v2.0</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import { CasesAPI } from '../api/index.js'

const router = useRouter()
const { state } = useAccidentFlow()

const goBack = () => {
  router.back()
}

async function loadCaseLiability() {
  try {
    const result = await CasesAPI.getDetail(state.caseId)
    if (result.success && result.data) {
      const liability = result.data.liability
      if (liability) {
        state.analysis.vehicleLiabilities = liability.details?.vehicles || []
        state.analysis.confidence = liability.details?.confidence || state.analysis.confidence
        state.analysis.evidenceIntegrity = liability.details?.evidence_integrity || state.analysis.evidenceIntegrity
        state.analysis.reasoningText = liability.summary || ''
      }
    }
  } catch (e) {
    console.warn('加载责任结果失败:', e)
  }
}

onMounted(() => {
  loadCaseLiability()
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
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '主责', percentage: 100 })
        } else {
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '无责', percentage: 0 })
        }
      })
    } else {
      vehicles.forEach((vehicle, index) => {
        if (index === vehicles.length - 1) {
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '主责', percentage: 100 })
        } else {
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '无责', percentage: 0 })
        }
      })
    }
  } else if (accidentType === '变道碰撞') {
    if (vehicles.length === 2) {
      vehicles.forEach((vehicle, index) => {
        if (vehicle.role === '变道车辆' || index === 0) {
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '主责', percentage: 70 })
        } else {
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '次责', percentage: 30 })
        }
      })
    } else {
      let hasFoundChanging = false
      vehicles.forEach((vehicle, index) => {
        if (vehicle.role === '变道车辆' || (index === 0 && !hasFoundChanging)) {
          hasFoundChanging = true
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '主责', percentage: 60 })
        } else {
          const isFirst = !liabilities.some(l => l.liability === '次责')
          liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '次责', percentage: isFirst ? 25 : 15 })
        }
      })
    }
  } else {
    vehicles.forEach((vehicle, index) => {
      if (index === 0) {
        liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '主责', percentage: 80 })
      } else {
        liabilities.push({ key: vehicle.key, vehicleType: vehicle.vehicleType, plate: vehicle.plate, role: vehicle.role, liability: '次责', percentage: 20 })
      }
    })
  }

  return liabilities
})

const getReasoningText = () => {
  // 优先使用后端返回的分析理由
  if (state.analysis.reasoningText) {
    return state.analysis.reasoningText
  }
  
  const liabilityText = vehicleLiabilities.value.map(l => `${l.role || l.vehicleType}${l.plate ? '(' + l.plate + ')' : ''}：${l.liability}（${l.percentage}%）`).join('；')
  const accidentType = state.form.accidentType

  if (accidentType === '追尾事故') {
    return `经分析，该事故为追尾事故。责任分配：${liabilityText}。根据《道路交通安全法》第四十三条规定，同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。本次分析置信度为${state.analysis.confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  } else if (accidentType === '变道碰撞') {
    return `经分析，该事故为变道碰撞事故。责任分配：${liabilityText}。根据《道路交通安全法》第四十四条规定，机动车变更车道时，应当提前开启转向灯，确认安全后再变更车道。本次分析置信度为${state.analysis.confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  } else {
    return `经分析，该事故涉及交通违法行为。责任分配：${liabilityText}。根据《道路交通安全法》相关规定，驾驶员应遵守交通规则，确保行车安全。本次分析置信度为${state.analysis.confidence}%，证据完整度为${state.analysis.evidenceIntegrity}%。`
  }
}

const downloadReport = () => {
  const divider = '='.repeat(60)
  let report = ''

  report += `${divider}\n`
  report += `事故分析详细报告\n`
  report += `${divider}\n\n`

  report += `一、案件基本信息\n`
  report += `-`.repeat(40) + '\n'
  report += `案件编号: ${state.caseId}\n`
  report += `事故类型: ${state.form.accidentType || '待分析'}\n`
  report += `发生时间: ${state.form.time || '未填写'}\n`
  report += `发生地点: ${state.form.location || '未填写'}\n\n`

  report += `二、分析结果概览\n`
  report += `-`.repeat(40) + '\n'
  report += `分析置信度: ${state.analysis.confidence || 0}%\n`
  report += `证据完整度: ${state.analysis.evidenceIntegrity || 0}%\n`
  report += `关键帧数量: ${state.analysis.keyframes.length || 0}帧\n`
  report += `涉事车辆: ${state.form.vehicles.length || 0}辆\n\n`

  report += `三、责任认定结果\n`
  report += `-`.repeat(40) + '\n'
  vehicleLiabilities.value.forEach(liability => {
    const vehicleInfo = liability.role || liability.vehicleType
    const plateInfo = liability.plate ? `(${liability.plate})` : ''
    report += `${vehicleInfo}${plateInfo}: ${liability.liability} (${liability.percentage}%)\n`
  })
  report += '\n'

  report += `四、认定理由\n`
  report += `-`.repeat(40) + '\n'
  report += `${getReasoningText()}\n\n`

  report += `五、处理建议\n`
  report += `-`.repeat(40) + '\n'
  report += `1. 快速处理：责任明确的事故，建议优先选择快速处理程序，节省时间\n`
  report += `2. 保险理赔：责任认定后，及时联系保险公司进行理赔，保留好相关证据\n`
  report += `3. 安全教育：建议驾驶人参加交通安全学习，提高安全意识，避免类似事故\n\n`

  report += `${divider}\n`
  report += `报告生成时间: ${new Date().toLocaleString('zh-CN')}\n`
  report += `分析系统版本: v2.0\n`
  report += `${divider}\n`

  const blob = new Blob([report], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `事故分析报告_${state.caseId}_${new Date().toISOString().slice(0, 10)}.txt`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  notify({ title: '下载成功', message: '报告已保存到本地' })
}
</script>

<style scoped>
.report-page {
  min-height: 100vh;
  background: var(--bg-secondary);
  padding-bottom: var(--space-8);
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) var(--space-6);
  background: var(--bg-primary);
  box-shadow: var(--shadow-sm);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.back-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--bg-secondary);
  border: none;
  border-radius: var(--radius-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.back-btn:hover {
  background: var(--border-light);
}

.back-btn svg {
  width: 16px;
  height: 16px;
}

.report-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.download-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  background: var(--primary);
  border: none;
  border-radius: var(--radius-lg);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.download-btn:hover {
  background: var(--primary-dark);
  transform: translateY(-1px);
}

.download-btn svg {
  width: 16px;
  height: 16px;
}

.report-content {
  padding: var(--space-6);
  max-width: 900px;
  margin: 0 auto;
}

.report-section {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  padding: var(--space-6);
  margin-bottom: var(--space-6);
  box-shadow: var(--shadow-sm);
}

.section-title {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-5) 0;
  padding-bottom: var(--space-3);
  border-bottom: 2px solid var(--primary-200);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.info-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.info-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

.stat-card {
  background: var(--bg-secondary);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  text-align: center;
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--primary);
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: var(--space-1);
}

.liability-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.liability-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border-left: 4px solid var(--border-light);
}

.liability-card.primary {
  border-left-color: var(--primary);
  background: rgba(37, 99, 235, 0.05);
}

.liability-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.liability-role {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.liability-plate {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 2px 8px;
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
}

.liability-info {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.liability-degree {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-weight: 600;
}

.liability-degree.主责 {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.liability-degree.次责 {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.liability-degree.无责 {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.liability-percent {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
}

.reasoning-box {
  background: var(--bg-secondary);
  padding: var(--space-5);
  border-radius: var(--radius-lg);
}

.reasoning-box p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.suggestion-card {
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.suggestion-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.suggestion-content h3 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.suggestion-content p {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--leading-relaxed);
}

.report-footer {
  padding: var(--space-4);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
}

.footer-info {
  display: flex;
  gap: var(--space-6);
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .report-header {
    padding: var(--space-3);
  }

  .report-title {
    font-size: var(--text-base);
  }

  .report-content {
    padding: var(--space-3);
  }

  .info-grid {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .liability-card {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .liability-info {
    width: 100%;
    justify-content: space-between;
  }

  .footer-info {
    flex-direction: column;
    gap: var(--space-2);
  }
}
</style>