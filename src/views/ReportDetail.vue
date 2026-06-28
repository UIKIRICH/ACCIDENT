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
        导出报告
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
            <span class="info-label">视频视角</span>
            <span class="info-value">{{ fusedEvidence ? mapCameraView(fusedEvidence.camera_context?.camera_view) : (state.form.accidentType || '待分析') }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">隐式自车</span>
            <span class="info-value">{{ fusedEvidence ? (fusedEvidence.camera_context?.ego_vehicle_present ? '存在' : '不存在') : '—' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">画面可见外部车辆数</span>
            <span class="info-value">{{ fusedEvidence?.camera_context?.visible_external_vehicle_count ?? '—' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">估计涉事车辆数</span>
            <span class="info-value">{{ fusedEvidence?.camera_context?.estimated_involved_vehicle_count ?? state.form.vehicles.length ?? '—' }}</span>
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
            <div class="stat-value">{{ fusedEvidence ? formatConfidence(fusedEvidence.detector_output?.detector_type_confidence) : (state.analysis.confidence + '%') }}</div>
            <div class="stat-label">检测模型置信度</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ fusedEvidence ? formatConfidence(fusedEvidence.qwen_semantic_check?.semantic_confidence) : '—' }}</div>
            <div class="stat-label">语义校验置信度</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ fusedEvidence ? (fusedEvidence.fusion_result?.keyframe_video_consistency?.score ?? '—') : (state.analysis.evidenceIntegrity + '%') }}</div>
            <div class="stat-label">证据一致性评分</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" :class="{ 'text-warning': fusedEvidence?.fusion_result?.manual_review_required }">
              {{ fusedEvidence ? mapFinalStatus(fusedEvidence.fusion_result?.final_status) : '待分析' }}
            </div>
            <div class="stat-label">系统状态</div>
          </div>
        </div>
      </div>

      <!-- 事故类型判定（三通道对比） -->
      <div class="report-section" v-if="fusedEvidence">
        <h2 class="section-title">三、事故类型判定</h2>
        <div class="type-judgment">
          <div class="type-channel channel-detector">
            <div class="channel-label">检测模型候选</div>
            <div class="channel-value">{{ mapAccidentType(fusedEvidence.detector_output?.candidate_accident_type_from_detector) }}</div>
            <div class="channel-conf">置信度 {{ formatConfidence(fusedEvidence.detector_output?.detector_type_confidence) }}</div>
          </div>
          <div class="type-channel channel-qwen">
            <div class="channel-label">语义校验结果</div>
            <div class="channel-value">{{ mapAccidentType(fusedEvidence.qwen_semantic_check?.semantic_accident_type_from_qwen) }}</div>
            <div class="channel-conf">置信度 {{ formatConfidence(fusedEvidence.qwen_semantic_check?.semantic_confidence) }}</div>
          </div>
          <div class="type-channel channel-final">
            <div class="channel-label">最终事故类型</div>
            <div class="channel-value" :class="{ 'text-warning': fusedEvidence.fusion_result?.accepted_accident_type === 'unknown' }">
              {{ mapAccidentType(fusedEvidence.fusion_result?.accepted_accident_type) }}
            </div>
            <div class="channel-conf">
              {{ fusedEvidence.fusion_result?.conflict_detected ? '证据存在冲突，进入人工复核' : '证据一致，进入责任推理' }}
            </div>
          </div>
        </div>
      </div>

      <div class="report-section">
        <h2 class="section-title">{{ fusedEvidence ? '四' : '三' }}、责任认定结果</h2>
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
        <h2 class="section-title">{{ fusedEvidence ? '五' : '四' }}、认定理由</h2>
        <div class="reasoning-box">
          <!-- 融合说明文案（有融合证据时显示） -->
          <p v-if="fusedEvidence" class="fusion-explain">
            系统未直接采纳单一模型输出，而是结合检测结果与视频语义校验结果进行证据融合。
            {{ fusedEvidence.fusion_result?.conflict_detected
                ? '由于检测候选类型与语义校验结果存在差异，当前案件进入人工复核流程。'
                : '检测候选类型与语义校验结果一致，证据已进入责任推理流程。' }}
          </p>
          <p>{{ getReasoningText() }}</p>
        </div>
      </div>

      <div class="report-section">
        <h2 class="section-title">{{ fusedEvidence ? '六' : '五' }}、处理建议</h2>
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

      <!-- 复核辅助结果 -->
      <div class="report-section" v-if="reviewAssist">
        <h2 class="section-title">{{ fusedEvidence ? '七' : '六' }}、复核辅助结果</h2>
        <div class="review-assist-grid">
          <div class="ra-row">
            <span class="ra-label">系统路由</span>
            <span class="ra-value">{{ reviewAssist.route_type_cn }}</span>
          </div>
          <div class="ra-row">
            <span class="ra-label">复核优先级</span>
            <span class="ra-value ra-priority" :class="'ra-prio-' + reviewAssist.review_priority_level">
              {{ reviewAssist.review_priority_level }}，{{ reviewAssist.review_priority_score }} 分
            </span>
          </div>
          <div class="ra-row">
            <span class="ra-label">复核重点</span>
            <span class="ra-value">{{ reviewAssist.review_focus?.join('、') || '无' }}</span>
          </div>
          <div class="ra-row">
            <span class="ra-label">证据状态</span>
            <span class="ra-value">{{ reviewAssist.evidence_status }}</span>
          </div>
          <div class="ra-row">
            <span class="ra-label">冲突摘要</span>
            <span class="ra-value">{{ reviewAssist.conflict_summary }}</span>
          </div>
          <div class="ra-row" v-if="reviewAssist.evidence_required_items?.length">
            <span class="ra-label">补证建议</span>
            <ul class="ra-list">
              <li v-for="(item, idx) in reviewAssist.evidence_required_items" :key="idx">{{ item }}</li>
            </ul>
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
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import { notify } from '../composables/useToast'
import { CasesAPI, ReviewAssistAPI } from '../api/index.js'

const router = useRouter()
const route = useRoute()
const { state, setCurrentCase, getCurrentCase, isValidCaseId } = useAccidentFlow()

// 视频语义校验 + 证据融合 数据
const fusedEvidence = ref(null)
const reviewAssist = ref(null)

// ── 字段中文映射（避免裸露英文枚举值） ──
const CAMERA_VIEW_MAP = {
  dashcam_ego_view: '行车记录仪视角',
  roadside_view: '路侧监控视角',
  surveillance_view: '交通监控视角',
  unknown: '未知视角'
}
const ACCIDENT_TYPE_MAP = {
  rear_end: '追尾',
  side_collision: '侧向碰撞',
  lane_change_or_cut_in: '变道/切入',
  head_on: '正面碰撞',
  unknown: '暂不直接认定'
}
const FINAL_STATUS_MAP = {
  evidence_ready: '证据就绪',
  needs_manual_review: '需人工复核',
  insufficient_evidence: '证据不足'
}
const CONSISTENCY_LEVEL_MAP = { high: '高', medium: '中', low: '低' }

function mapCameraView(val) { return CAMERA_VIEW_MAP[val] || val || '—' }
function mapAccidentType(val) { return ACCIDENT_TYPE_MAP[val] || val || '—' }
function mapFinalStatus(val) { return FINAL_STATUS_MAP[val] || val || '—' }
function mapConsistencyLevel(val) { return CONSISTENCY_LEVEL_MAP[val] || val || '—' }

// 格式化置信度（0~1 → 百分比）
function formatConfidence(val) {
  if (val == null || val === '') return '—'
  const num = Number(val)
  if (isNaN(num)) return String(val)
  return (num <= 1 ? num * 100 : num).toFixed(1) + '%'
}

// 统一获取 caseId：优先 URL query，fallback store/localStorage，自动过滤无效值
const currentCaseId = () => {
  const queryId = route.query.caseId
  if (isValidCaseId(queryId)) {
    return String(queryId).trim()
  }
  return getCurrentCase()
}

const goBack = () => {
  router.back()
}

async function loadCaseLiability() {
  const caseId = currentCaseId()
  if (!isValidCaseId(caseId)) {
    notify({ title: '无案件', message: '未指定案件，请从历史案例选择', type: 'warning' })
    setTimeout(() => router.push('/history-cases'), 1500)
    return
  }
  // 同步到 store（防止刷新后 store 丢失）
  if (String(caseId) !== String(state.caseId)) setCurrentCase(caseId)
  try {
    // 并行加载案件详情 + 融合证据包
    const [detailResult, fusedResult] = await Promise.all([
      CasesAPI.getDetail(caseId),
      CasesAPI.getFusedEvidence(caseId)
    ])

    if (detailResult.success && detailResult.data) {
      const liability = detailResult.data.liability
      if (liability) {
        state.analysis.vehicleLiabilities = liability.details?.vehicles || []
        state.analysis.confidence = liability.details?.confidence || state.analysis.confidence
        state.analysis.evidenceIntegrity = liability.details?.evidence_integrity || state.analysis.evidenceIntegrity
        state.analysis.reasoningText = liability.summary || ''
      }
    } else {
      // 案件不存在
      notify({ title: '案件不存在', message: `案件 ${caseId} 未找到，请从历史案例选择`, type: 'warning' })
      setTimeout(() => router.push('/history-cases'), 1500)
    }

    // 加载融合证据包
    if (fusedResult.success) {
      const packet = fusedResult.data?.fused_evidence_packet
      fusedEvidence.value = (packet && Object.keys(packet).length > 0) ? packet : null
      // 同步到 store，便于其他页面共享
      state.analysis.fusedEvidence = fusedEvidence.value
      state.analysis.semanticCheck = fusedEvidence.value?.qwen_semantic_check || null
      state.analysis.fusionResult = fusedEvidence.value?.fusion_result || null
      state.analysis.cameraContext = fusedEvidence.value?.camera_context || null
    }
  } catch (e) {
    console.warn('加载责任结果失败:', e)
    notify({ title: '加载失败', message: '无法加载案件数据，请重试', type: 'error' })
  }
}

async function loadReviewAssist() {
  const caseId = currentCaseId()
  if (!isValidCaseId(caseId)) return
  try {
    const result = await ReviewAssistAPI.get(caseId)
    if (result.success && result.data) {
      reviewAssist.value = result.data
      state.reviewAssist = result.data
    }
  } catch (err) {
    console.warn('加载复核辅助失败:', err)
  }
}

onMounted(() => {
  loadCaseLiability()
  loadReviewAssist()
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

const downloadReport = async () => {
  try {
    // 构建案件数据，用前端 state 中的数据直接生成报告
    const caseData = {
      id: currentCaseId() || 'export',
      title: state.form.accidentType ? `${state.form.accidentType}分析报告` : '交通事故分析报告',
      accident_type: state.form.accidentType || '待分析',
      location: state.form.location || '未填写',
      status: '已分析',
      weather: state.form.weather || '未记录',
      road_env: state.form.roadEnv || '未记录',
      vehicle_info: state.form.vehicles || [],
      snapshot: {
        form_data: { time: state.form.time || '' },
        analysis: state.analysis || {}
      },
      liability: {
        details: {
          confidence: state.analysis.confidence || 0,
          evidence_integrity: state.analysis.evidenceIntegrity || 0,
          vehicles: vehicleLiabilities.value
        },
        summary: getReasoningText()
      }
    }

    const blob = await CasesAPI.generateReport(caseData)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `事故分析报告_${currentCaseId() || 'export'}_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    notify({ title: '导出成功', message: 'HTML 报告已下载到本地' })
  } catch (e) {
    console.error('导出报告失败:', e)
    notify({ title: '导出失败', message: e.message || '请稍后重试', type: 'error' })
  }
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

.reasoning-box p + p {
  margin-top: var(--space-3);
}

/* 融合说明文案 */
.fusion-explain {
  padding: var(--space-3) var(--space-4);
  background: rgba(0, 122, 255, 0.06);
  border-left: 3px solid #007AFF;
  border-radius: var(--radius-md);
  color: var(--text-primary) !important;
  font-weight: 500;
}

/* 警告色（人工复核状态） */
.text-warning {
  color: #FF9500 !important;
}

/* 事故类型判定三通道对比 */
.type-judgment {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--space-4);
}

.type-channel {
  padding: var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border-left: 3px solid var(--ch-color, #007AFF);
}

.channel-detector { --ch-color: #007AFF; }
.channel-qwen { --ch-color: #00C7BE; }
.channel-final { --ch-color: #AF52DE; }

.channel-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}

.channel-value {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.channel-conf {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
  line-height: var(--leading-relaxed);
}

@media (max-width: 768px) {
  .type-judgment {
    grid-template-columns: 1fr;
  }
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

/* 复核辅助 */
.review-assist-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.ra-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
}
.ra-label {
  min-width: 80px;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.ra-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.6;
}
.ra-priority { font-weight: 600; }
.ra-prio-高 { color: #ef4444; }
.ra-prio-中 { color: var(--warning-500); }
.ra-prio-低 { color: var(--text-muted); }
.ra-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ra-list li {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding-left: 1em;
  position: relative;
}
.ra-list li::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--primary-500);
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