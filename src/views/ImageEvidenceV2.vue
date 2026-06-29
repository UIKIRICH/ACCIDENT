<template>
  <div class="image-evidence-page">
    <div class="card-surface page-header">
      <h1 class="page-title">图片侧证分析</h1>
    </div>

    <div class="content-grid">
      <div class="card-surface upload-panel">
        <h2 class="section-title">选择图片</h2>

        <input ref="fileInput" class="file-input" type="file" accept="image/*" @change="onFileChange">
        
        <div v-if="storedImages.length > 0" class="stored-images-section">
          <div class="section-subtitle">从事故录入页面上传的图片</div>
          <div class="stored-images-grid">
            <div 
              v-for="(img, idx) in storedImages" 
              :key="idx"
              class="stored-image-item"
              :class="{ 'stored-image-selected': selectedStoredImageIndex === idx }"
              @click="selectStoredImage(idx)"
            >
              <img :src="img.preview" :alt="img.name" class="stored-image-thumb">
              <div class="stored-image-name">{{ img.name }}</div>
            </div>
          </div>
        </div>

        <div class="button-row">
          <button class="btn" @click="fileInput?.click()">
            <svg class="btn-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7">
              <path d="M4 13c0-1.657 1.343-3 3-3h6a3 3 0 013 3v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2z" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M6 13l1-3h6l1 3" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="8" cy="14.5" r="1" fill="currentColor"/>
              <circle cx="12" cy="14.5" r="1" fill="currentColor"/>
              <path d="M7 9a2 2 0 012-2h2a2 2 0 012 2v2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            选择事故图片
          </button>
          <button class="btn btn-delete" :disabled="!selectedFile && selectedStoredImageIndex === -1" @click="deleteImage">
            <svg class="btn-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7">
              <path d="M3 6h14M8 6V4a2 2 0 012-2h0a2 2 0 012 2v2M6 6l1 11a2 2 0 002 2h2a2 2 0 002-2l1-11" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M9 9v5M11 9v5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            删除图片
          </button>
          <button class="btn btn-primary" :disabled="!selectedFile && selectedStoredImageIndex === -1 || analyzing" @click="analyzeImage">
            <svg v-if="analyzing" class="btn-icon btn-icon-spin" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7">
              <circle cx="10" cy="10" r="6" stroke-dasharray="20 20"/>
              <path d="M10 4a6 6 0 016 6" stroke-linecap="round"/>
            </svg>
            <svg v-else class="btn-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7">
              <path d="M4.5 4.5l11 5.5-11 5.5 2-5.5-2-5.5z" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            {{ analyzing ? '分析中...' : '开始分析' }}
          </button>
        </div>

        <div v-if="imagePreview" class="preview-wrap">
          <img :src="imagePreview" alt="原始图片" class="preview-image">
        </div>
        <div v-else class="preview-wrap preview-placeholder">
          <div class="placeholder-content">
            <div class="placeholder-icon">
              <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="4" width="18" height="16" rx="3" fill-opacity="0.1"></rect>
                <circle cx="9" cy="10" r="1.5" fill-opacity="0.4"></circle>
                <path d="M4 17l5-5 4 4 3-3 4 4" fill="none" stroke-opacity="0.4"></path>
              </svg>
            </div>
            <div class="placeholder-text">待选择图片</div>
          </div>
        </div>

        <div class="meta-grid">
          <div class="meta-card" :class="{ 'meta-card-pending': !selectedFile && selectedStoredImageIndex === -1 }">
            <div class="meta-label">宽度</div>
            <div class="meta-value">{{ (selectedFile || selectedStoredImageIndex !== -1) ? imageMeta.width + 'px' : '--' }}</div>
          </div>
          <div class="meta-card" :class="{ 'meta-card-pending': !selectedFile && selectedStoredImageIndex === -1 }">
            <div class="meta-label">文件大小</div>
            <div class="meta-value">{{ (selectedFile || selectedStoredImageIndex !== -1) ? imageMeta.sizeText : '--' }}</div>
          </div>
          <div class="meta-card" :class="{ 'meta-card-pending': !selectedFile && selectedStoredImageIndex === -1 }">
            <div class="meta-label">高度</div>
            <div class="meta-value">{{ (selectedFile || selectedStoredImageIndex !== -1) ? imageMeta.height + 'px' : '--' }}</div>
          </div>
          <div class="meta-card" :class="{ 'meta-card-pending': !selectedFile && selectedStoredImageIndex === -1 }">
            <div class="meta-label">格式</div>
            <div class="meta-value">{{ (selectedFile || selectedStoredImageIndex !== -1) ? imageMeta.formatText : '--' }}</div>
          </div>
        </div>

        <div class="left-summary" :class="{ 'summary-pending': !analysisResult }">
          <div class="summary-pill" :class="statusClass">{{ inferenceTitle }}</div>
          <div class="summary-line">车辆角色倾向：{{ roleText }}</div>
        </div>
      </div>

      <div class="card-surface result-panel">
        <h2 class="section-title">分析结果</h2>

        <div class="block-title">事故类型推断</div>
        <div class="inference-banner" :class="statusClass">
          {{ inferenceTitle }}<template v-if="analysisResult">（类型匹配度：{{ percent(typeMatchScore) }}）</template>
        </div>

        <div class="result-kpi-grid">
          <div class="kpi-card" :class="{ 'kpi-card-pending': !selectedFile && selectedStoredImageIndex === -1 }">
            <div class="kpi-label">追尾类型匹配度</div>
            <div class="kpi-value">{{ analysisResult ? percent(typeMatchScore) : '--' }}</div>
          </div>
          <div class="kpi-card" :class="{ 'kpi-card-pending': !analysisResult }">
            <div class="kpi-label">单图定责可信度</div>
            <div class="kpi-value">{{ analysisResult ? percent(liabilityTrustScore) : '--' }}</div>
          </div>
        </div>

        <div class="block-title">图片侧证输出</div>
        <ul class="output-list">
          <li :class="{ 'pending-item': !analysisResult }">追尾侧证综合分：{{ analysisResult ? percent(rearEndLikelihood) : '--' }}</li>
          <li :class="{ 'pending-item': !analysisResult }">追尾类型匹配度：{{ analysisResult ? percent(typeMatchScore) : '--' }}</li>
          <li :class="{ 'pending-item': !analysisResult }">单图定责可信度：{{ analysisResult ? percent(liabilityTrustScore) : '--' }}</li>
          <li :class="{ 'pending-item': !analysisResult }">决策建议：{{ decisionText }}</li>
          <li :class="{ 'pending-item': !analysisResult }">图片可用性：{{ suitableText }}</li>
          <li :class="{ 'pending-item': !analysisResult }">车辆角色倾向：{{ roleText }}</li>
          <li :class="{ 'pending-item': !analysisResult }">可用图片数：{{ suitableCountText }}</li>
          <li :class="{ 'pending-item': !analysisResult }">前车后部受损分：{{ analysisResult ? percent(frontRearDamageScore) : '--' }}</li>
          <li :class="{ 'pending-item': !analysisResult }">后车前部受损分：{{ analysisResult ? percent(rearFrontDamageScore) : '--' }}</li>
          <li :class="{ 'pending-item': !analysisResult }">与视频一致性：{{ consistencyText }}</li>
        </ul>

        <div class="block-title">分项证据面板</div>
        <div class="panel-list">
          <div v-for="item in evidencePanels" :key="item.key" class="panel-row" :class="{ 'panel-row-pending': !analysisResult }">
            <div class="panel-line">
              <span>{{ item.label }}</span>
              <span>{{ analysisResult ? percent(item.value) : '--' }}</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: analysisResult ? percent(item.value) : '0%' }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { notify } from '../composables/useToast'
import NavigationButtons from '../components/NavigationButtons.vue'
import { useAccidentFlow } from '../stores/useAccidentFlow'

const { state, updateAnalysis } = useAccidentFlow()
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

const fileInput = ref(null)
const selectedFile = ref(null)
const imagePreview = ref('')
const analyzing = ref(false)
const analysisResult = ref(null)
const imageMeta = ref({ width: '--', height: '--', sizeText: '--', formatText: '--' })
const selectedStoredImageIndex = ref(-1)

const storedImages = computed(() => state.form.imageFiles || [])

function safeNum(v, d = 0) {
  const n = Number(v)
  return Number.isFinite(n) ? n : d
}

function percent(v) {
  return `${Math.round(safeNum(v) * 100)}%`
}

const rearEndLikelihood = computed(() => safeNum(analysisResult.value?.rear_end_likelihood, analysisResult.value?.confidence))

const featureScores = computed(() => analysisResult.value?.feature_scores || {})

const frontRearDamageScore = computed(() => safeNum(featureScores.value.front_vehicle_rear_damage_score))
const rearFrontDamageScore = computed(() => safeNum(featureScores.value.rear_vehicle_front_damage_score))

const alignScore = computed(() => safeNum(featureScores.value.vehicle_alignment_score))
const distanceScore = computed(() => safeNum(featureScores.value.distance_score))
const longRelScore = computed(() => safeNum(featureScores.value.longitudinal_relation_score))
const contactScore = computed(() => safeNum(featureScores.value.contact_cue_score))
const sidePenalty = computed(() => safeNum(featureScores.value.side_impact_penalty))
const qualityScore = computed(() => safeNum(featureScores.value.quality_score, safeNum(analysisResult.value?.quality?.quality_score)))
const relationVisibility = computed(() => 0.6 * alignScore.value + 0.4 * distanceScore.value)

const typeMatchScore = computed(() => {
  const backendScore = safeNum(analysisResult.value?.rear_end_type_match_score)
  if (backendScore > 0) return Math.max(0, Math.min(1, backendScore))
  const v = 0.28 * frontRearDamageScore.value + 0.28 * rearFrontDamageScore.value + 0.22 * contactScore.value + 0.22 * longRelScore.value
  return Math.max(0, Math.min(1, v - sidePenalty.value))
})

const liabilityTrustScore = computed(() => {
  const backendScore = safeNum(analysisResult.value?.single_image_liability_trust_score)
  if (backendScore > 0) return Math.max(0, Math.min(1, backendScore))
  let v = 0.30 * qualityScore.value + 0.25 * relationVisibility.value + 0.20 * longRelScore.value + 0.25 * Math.min(frontRearDamageScore.value, rearFrontDamageScore.value)
  if (Number(analysisResult.value?.vehicle_count || 0) < 2) v *= 0.7
  return Math.max(0, Math.min(1, v))
})

const suitableText = computed(() => {
  if (!analysisResult.value) return '--'
  if (analysisResult.value?.suitable_for_assessment) return '可用'
  if (analysisResult.value?.assessment_status === 'rejected') return '不适用'
  return '有限可用'
})

const suitableCountText = computed(() => {
  if (!analysisResult.value) return '--'
  const a = analysisResult.value
  if (a.suitable_image_count != null && a.image_count != null) return `${a.suitable_image_count}/${a.image_count}`
  return a.suitable_for_assessment ? '1/1' : '0/1'
})

const consistencyText = computed(() => {
  if (!analysisResult.value) return '--'
  const c = analysisResult.value?.consistency
  if (!c) return '--'
  const score = Math.round(safeNum(c.evidence_consistency_score) * 100)
  if (score >= 75) return `基本一致（${score}%）`
  if (score >= 45) return `部分一致（${score}%）`
  return `存在矛盾（${score}%）`
})

const roleText = computed(() => {
  if (!analysisResult.value) return '--'
  const frontRear = frontRearDamageScore.value
  const rearFront = rearFrontDamageScore.value
  const align = alignScore.value
  const relationVis = relationVisibility.value
  const overall = rearEndLikelihood.value

  if (frontRear >= 0.45 && rearFront >= 0.45 && relationVis >= 0.45) return '两车存在明显前后追尾关系'
  if (relationVis >= 0.75 && overall >= 0.35) return '两车存在明显接触关系，疑似前后追撞'
  if (align < 0.30 || Math.max(frontRear, rearFront) < 0.20) return '车辆前后关系不明确'
  if (frontRear >= rearFront + 0.10) return '疑似前车'
  if (rearFront >= frontRear + 0.10) return '疑似后车'
  if (relationVis >= 0.45 && Math.max(frontRear, rearFront) >= 0.25) return '两车存在前后关系，但主次车辆仍需更多证据确认'
  return '车辆前后关系不明确'
})

const decisionText = computed(() => {
  if (!analysisResult.value) return '--'
  const suitable = Boolean(analysisResult.value?.suitable_for_assessment)
  const l = liabilityTrustScore.value
  if (!suitable) return '单图定责可信度低'
  if (l >= 0.75) return '单图定责可信度较高（仍建议结合视频验证）'
  if (l >= 0.45) return '单图定责可信度中等（建议结合视频确认）'
  return '单图定责可信度较低（不建议单图直接定责）'
})

const inferenceTitle = computed(() => {
  if (!analysisResult.value) return '待分析'
  const t = typeMatchScore.value
  if (!analysisResult.value?.suitable_for_assessment) return '图片不适合用于追尾侧证分析'
  if (t >= 0.75) return '追尾类型匹配度高（追尾侧证较强）'
  if (t >= 0.55) return '追尾类型匹配度中等偏高（疑似追尾）'
  return '追尾类型匹配度不足'
})

const statusClass = computed(() => {
  if (!analysisResult.value) return 'status-pending'
  const t = typeMatchScore.value
  if (!analysisResult.value?.suitable_for_assessment) return 'status-reject'
  if (t >= 0.75) return 'status-high'
  if (t >= 0.55) return 'status-mid'
  return 'status-low'
})

const evidencePanels = computed(() => [
  { key: 'quality', label: '图片可用性', value: qualityScore.value },
  { key: 'view', label: '车辆关系可见性', value: relationVisibility.value },
  { key: 'long', label: '前后纵向关系', value: longRelScore.value },
  { key: 'contact', label: '接触关系线索', value: contactScore.value },
  { key: 'frontRear', label: '前车后部证据', value: frontRearDamageScore.value },
  { key: 'rearFront', label: '后车前部证据', value: rearFrontDamageScore.value },
  { key: 'total', label: '追尾侧证综合分', value: rearEndLikelihood.value },
  { key: 'type', label: '追尾类型匹配度', value: typeMatchScore.value },
  { key: 'liability', label: '单图定责可信度', value: liabilityTrustScore.value }
])

function selectStoredImage(idx) {
  selectedStoredImageIndex.value = idx
  const imgData = storedImages.value[idx]
  
  selectedFile.value = imgData.file
  imagePreview.value = imgData.preview

  imageMeta.value = {
    width: '--',
    height: '--',
    sizeText: `${(imgData.size / 1024).toFixed(1)} KB`,
    formatText: (imgData.type.split('/')[1] || 'unknown').toUpperCase()
  }

  const img = new Image()
  img.onload = () => {
    imageMeta.value.width = img.naturalWidth
    imageMeta.value.height = img.naturalHeight
  }
  img.src = imgData.preview
  
  notify({ title: '已选择', message: `已选择图片: ${imgData.name}`, type: 'success' })
}

function onFileChange(e) {
  const file = e.target.files?.[0]
  if (!file) return
  selectedStoredImageIndex.value = -1
  selectedFile.value = file
  imagePreview.value = URL.createObjectURL(file)

  imageMeta.value = {
    width: '--',
    height: '--',
    sizeText: `${(file.size / 1024).toFixed(1)} KB`,
    formatText: (file.type.split('/')[1] || 'unknown').toUpperCase()
  }

  const img = new Image()
  img.onload = () => {
    imageMeta.value.width = img.naturalWidth
    imageMeta.value.height = img.naturalHeight
  }
  img.src = imagePreview.value
}

function deleteImage() {
  if (!selectedFile.value && selectedStoredImageIndex.value === -1) return
  
  if (imagePreview.value && selectedStoredImageIndex.value === -1) {
    URL.revokeObjectURL(imagePreview.value)
  }
  
  selectedFile.value = null
  selectedStoredImageIndex.value = -1
  imagePreview.value = ''
  analysisResult.value = null
  imageMeta.value = { width: '--', height: '--', sizeText: '--', formatText: '--' }
  
  if (fileInput.value) {
    fileInput.value.value = ''
  }
  
  notify({ title: '已删除', message: '图片已成功删除。', type: 'success' })
}

function buildVideoContext() {
  const imageSide = state.analysis.imageSideEvidence || {}
  return {
    accident_type: state.form.accidentType || '',
    type_confidence: safeNum(state.analysis.confidence) / 100,
    evidence_consistency_score: safeNum(state.analysis.evidenceConsistencyScore),
    rear_end_score: safeNum(imageSide.rear_end_likelihood)
  }
}

async function analyzeImage() {
  if (!selectedFile.value) return
  analyzing.value = true
  try {
    const fd = new FormData()
    fd.append('file', selectedFile.value)
    fd.append('video_context', JSON.stringify(buildVideoContext()))

    const resp = await fetch(`${API_BASE_URL}/analyze_image_file_evidence/`, { method: 'POST', body: fd })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `后端状态码 ${resp.status}`)
    }

    const data = await resp.json()
    
    // 处理后端返回的失败状态（模型不可用等情况）
    if (data.success === false) {
      notify({ title: '分析不可用', message: data.message || '图片分析模型暂不可用', type: 'error' })
      analysisResult.value = null
      return
    }
    
    analysisResult.value = data.image_evidence || null
    updateAnalysis({
      imageSideEvidence: analysisResult.value,
      evidenceConsistencyScore: safeNum(analysisResult.value?.consistency?.evidence_consistency_score)
    })
    notify({ title: '分析完成', message: '图片侧证分析已完成。', type: 'success' })
  } catch (e) {
    notify({ title: '分析失败', message: `图片侧证分析失败：${e.message}`, type: 'error' })
  } finally {
    analyzing.value = false
  }
}
</script>

<style scoped>
.image-evidence-page {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-4);
  animation: pageIn 0.4s var(--ease-default);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.card-surface {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  padding: var(--space-5);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-normal);
}

.card-surface:hover { box-shadow: var(--shadow-md); }

.page-header {
  margin-bottom: 0;
}

.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.03em;
}

.content-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
  align-items: stretch;
}

@media (max-width: 1200px) {
  .content-grid { grid-template-columns: 1fr; }
  .image-evidence-page { padding: var(--space-3); gap: var(--space-4); }
}

@media (max-width: 768px) {
  .image-evidence-page { padding: var(--space-2); gap: var(--space-3); }
  .page-title { font-size: 24px; }
}

.section-title {
  margin: 0 0 var(--space-4);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.4;
}

.section-subtitle {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--space-3);
}

.stored-images-section {
  margin-bottom: var(--space-4);
}

.stored-images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: var(--space-3);
}

.stored-image-item {
  border: 2px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-2);
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--bg-secondary);
}

.stored-image-item:hover {
  border-color: var(--primary-300);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
}

.stored-image-selected {
  border-color: var(--primary);
  background: var(--primary-soft);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.stored-image-thumb {
  width: 100%;
  height: 80px;
  object-fit: cover;
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
}

.stored-image-name {
  font-size: 12px;
  color: var(--text-primary);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.file-input { display: none; }

.button-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.btn {
  flex: 1;
  position: relative;
  overflow: hidden;
  padding: 14px 28px;
  min-height: 48px;
  border-radius: 14px;
  border: 1.5px solid var(--border-medium);
  background: linear-gradient(180deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 15px;
  font-weight: 600;
  font-family: var(--font-sans);
  letter-spacing: -0.01em;
  line-height: 1.4;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  box-shadow: 
    0 1px 2px rgba(0, 0, 0, 0.04),
    0 0 0 1px rgba(0, 0, 0, 0.02) inset;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 50%;
  background: linear-gradient(180deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0) 100%);
  pointer-events: none;
  border-radius: 14px 14px 0 0;
}

.btn-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.btn-icon-spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.btn:hover:not(:disabled) {
  background: linear-gradient(180deg, var(--primary-soft) 0%, rgba(59, 130, 246, 0.08) 100%);
  border-color: var(--primary-300);
  color: var(--primary);
  transform: translateY(-2px);
  box-shadow: 
    0 6px 16px rgba(59, 130, 246, 0.16),
    0 1px 3px rgba(0, 0, 0, 0.06),
    0 0 0 1px rgba(59, 130, 246, 0.08) inset;
}

.btn:active:not(:disabled) {
  transform: translateY(-0.5px) scale(0.99);
  box-shadow: 
    0 3px 10px rgba(59, 130, 246, 0.12),
    0 1px 2px rgba(0, 0, 0, 0.04);
  transition: all 0.1s ease;
}

.btn-primary {
  background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  border-color: transparent;
  box-shadow: 
    0 4px 14px rgba(59, 130, 246, 0.35),
    0 1px 3px rgba(0, 0, 0, 0.12),
    0 0 0 1px rgba(147, 197, 253, 0.4) inset;
}

.btn-primary::before {
  background: linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.04) 100%);
}

.btn-primary:hover:not(:disabled) {
  background: linear-gradient(180deg, #4f8ff8 0%, #2d6bef 100%);
  transform: translateY(-2px);
  box-shadow: 
    0 8px 24px rgba(59, 130, 246, 0.45),
    0 2px 6px rgba(0, 0, 0, 0.15),
    0 0 0 1px rgba(191, 219, 254, 0.5) inset;
}

.btn-primary:active:not(:disabled) {
  transform: translateY(-0.5px) scale(0.99);
  box-shadow: 
    0 4px 14px rgba(59, 130, 246, 0.3),
    0 1px 3px rgba(0, 0, 0, 0.1);
}

.btn-delete {
  background: linear-gradient(180deg, #f87171 0%, #ef4444 100%);
  color: #ffffff;
  border-color: transparent;
  box-shadow: 
    0 4px 14px rgba(239, 68, 68, 0.35),
    0 1px 3px rgba(0, 0, 0, 0.12),
    0 0 0 1px rgba(252, 165, 165, 0.4) inset;
}

.btn-delete::before {
  background: linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.04) 100%);
}

.btn-delete:hover:not(:disabled) {
  background: linear-gradient(180deg, #fca5a5 0%, #f87171 100%);
  transform: translateY(-2px);
  box-shadow: 
    0 8px 24px rgba(239, 68, 68, 0.45),
    0 2px 6px rgba(0, 0, 0, 0.15),
    0 0 0 1px rgba(254, 202, 202, 0.5) inset;
}

.btn-delete:active:not(:disabled) {
  transform: translateY(-0.5px) scale(0.99);
  box-shadow: 
    0 4px 14px rgba(239, 68, 68, 0.3),
    0 1px 3px rgba(0, 0, 0, 0.1);
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  filter: grayscale(0.15);
  transform: none !important;
  box-shadow: 
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 0 0 1px rgba(0, 0, 0, 0.02) inset !important;
}

.btn:disabled::before {
  opacity: 0.5;
}

.preview-wrap {
  width: 100%;
  border-radius: var(--radius-xl);
  overflow: hidden;
  border: 1px solid var(--border-light);
  min-height: 240px;
  background: var(--bg-secondary);
}

.preview-image {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 240px;
  max-height: 420px;
  object-fit: contain;
  background: var(--bg-secondary);
}

.preview-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  min-height: 280px;
}

.placeholder-content {
  text-align: center;
  padding: var(--space-6);
}

.placeholder-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto var(--space-3);
  color: var(--text-muted);
}

.placeholder-icon svg { width: 100%; height: 100%; }

.placeholder-text {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-secondary);
  line-height: 1.5;
}

.meta-grid {
  margin-top: var(--space-4);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.meta-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  transition: all var(--transition-fast);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.meta-card:hover { border-color: var(--primary-200); transform: translateY(-1px); }

.meta-card-pending { border-style: dashed; }
.meta-card-pending .meta-value { color: var(--text-muted); }

.meta-label {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  margin-bottom: var(--space-1);
}

.meta-value {
  color: var(--text-primary);
  font-size: var(--text-2xl);
  font-weight: 800;
  letter-spacing: -0.02em;
}

.left-summary {
  margin-top: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.summary-pending .summary-pill { background: var(--bg-secondary); color: var(--text-muted); border-color: var(--border-light); }
.summary-pending .summary-line { color: var(--text-muted); }

.summary-pill {
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  font-weight: 700;
  font-size: var(--text-sm);
  border: 1px solid transparent;
  line-height: 1.5;
  text-align: center;
}

.summary-line {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.5;
}

.block-title {
  margin-top: var(--space-5);
  margin-bottom: var(--space-3);
  font-weight: 700;
  font-size: var(--text-lg);
  color: var(--text-primary);
  line-height: 1.4;
}

.inference-banner {
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  font-weight: 700;
  font-size: var(--text-base);
  border: 1px solid transparent;
  line-height: 1.5;
  text-align: center;
}

.result-kpi-grid {
  margin-top: var(--space-4);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.kpi-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  transition: all var(--transition-fast);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.kpi-card:hover { border-color: var(--primary-200); transform: translateY(-2px); }

.kpi-card-pending { border-style: dashed; }
.kpi-card-pending .kpi-value { color: var(--text-muted); }

.kpi-label {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  margin-bottom: var(--space-2);
}

.kpi-value {
  font-size: 40px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.output-list {
  margin: var(--space-3) 0 0 var(--space-4);
  padding: 0;
  color: var(--text-primary);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
}

.output-list li {
  margin: var(--space-2) 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  transition: background var(--transition-fast);
}

.output-list li:hover { background: var(--bg-secondary); }
.pending-item { color: var(--text-muted); }

.panel-list {
  margin-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.panel-row { transition: all var(--transition-fast); }
.panel-row-pending .panel-line { color: var(--text-muted); }
.panel-row-pending .progress-track { background: var(--bg-secondary); }
.panel-row-pending .progress-fill { background: var(--border-light); }

.panel-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.5;
}

.progress-track {
  height: 10px;
  border-radius: var(--radius-full);
  background: var(--primary-soft);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary-gradient);
  border-radius: var(--radius-full);
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.status-high { background: rgba(34, 197, 94, 0.1); color: #1a7f37; border-color: rgba(34, 197, 94, 0.2); }
.status-mid { background: rgba(245, 158, 11, 0.1); color: #b45309; border-color: rgba(245, 158, 11, 0.2); }
.status-low, .status-reject { background: rgba(239, 68, 68, 0.1); color: #b91c1c; border-color: rgba(239, 68, 68, 0.2); }
.status-pending { background: var(--bg-secondary); color: var(--text-muted); border-color: var(--border-light); border-style: dashed; }

@media (max-width: 1200px) {
  .page-title { font-size: 26px; }
  .section-title { font-size: var(--text-lg); }
  .kpi-value { font-size: 36px; }
  .meta-grid { gap: var(--space-3); }
  .result-kpi-grid { gap: var(--space-3); }
}

@media (max-width: 768px) {
  .page-title { font-size: 24px; }
  .section-title { font-size: var(--text-base); }
  .btn { 
    padding: 12px 20px; 
    min-height: 44px;
    font-size: 14px;
    border-radius: 12px;
  }
  .btn-icon { width: 16px; height: 16px; }
  .kpi-value { font-size: 32px; }
  .meta-value { font-size: var(--text-xl); }
  .preview-placeholder { min-height: 200px; }
  .placeholder-icon { width: 56px; height: 56px; }
  .placeholder-text { font-size: var(--text-lg); }
  .panel-list { gap: var(--space-3); }
  .progress-track { height: 8px; }
  .output-list { margin-left: var(--space-2); }
  .output-list li { padding: var(--space-1) var(--space-2); }
}
</style>
