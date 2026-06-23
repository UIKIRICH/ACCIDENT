<template>
  <div class="video-processing-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">视频处理</h1>
        <p class="page-subtitle">事故视频分析与处理</p>
      </div>
    </div>

    <div class="processing-container">
      <div class="video-upload card-surface">
        <div class="upload-card" @click="fileInput?.click()">
          <div class="upload-icon">
            <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="6" width="16" height="12" rx="3" fill-opacity="0.15" />
              <path d="m22 8-6 4 6 4V8Z" fill-opacity="0.8" />
            </svg>
          </div>
          <h3 class="upload-title">上传事故视频</h3>
          <p class="upload-desc">支持 MP4、AVI、MOV 格式，最大 200MB</p>
          <input
            ref="fileInput"
            type="file"
            class="file-input"
            accept="video/*"
            @change="handleFile"
          />
          <p v-if="videoMeta.name" class="upload-desc">当前文件：{{ videoMeta.name }}</p>
        </div>
      </div>

      <div class="video-analysis card-surface">
        <h2 class="section-title">视频分析</h2>
        <div class="analysis-card">
          <div class="left-section">
            <div class="video-player">
              <div class="player-placeholder">
                <video
                  v-if="videoUrl"
                  ref="videoPlayer"
                  :src="videoUrl"
                  controls
                  class="preview-video"
                ></video>
                <img
                  v-else
                  :src="videoPosterUrl"
                  alt="视频播放器"
                >
              </div>
            </div>

            <div class="analysis-controls">
            <div class="control-group">
              <button 
                class="control-btn" 
                :class="{ 'active': activeButton === 'intelligent' }"
                @click="setActiveButton('intelligent'); runAnalysis()">
                智能分析
              </button>
              <button 
                class="control-btn" 
                :class="{ 'active': activeButton === 'extract' }"
                @click="setActiveButton('extract'); extractFrames()" 
                :disabled="extracting">
                <span v-if="extracting" class="loading-spinner"></span>
                {{ extracting ? '提取中...' : '关键帧提取' }}
              </button>
              <button 
                class="control-btn" 
                :class="{ 'active': activeButton === 'mainframe' }"
                @click="setActiveButton('mainframe'); setSelectedAsMainFrame()" 
                :disabled="!selectedFrame">
                设为主分析帧
              </button>
              <button 
                class="control-btn" 
                :class="{ 'active': activeButton === 'linkage' }"
                @click="setActiveButton('linkage'); runKeyframeEvidenceLinkage()" 
                :disabled="linkingEvidence || frames.length === 0">
                <span v-if="linkingEvidence" class="loading-spinner"></span>
                {{ linkingEvidence ? '联动中...' : '关键帧侧证联动' }}
              </button>
              <button 
                class="control-btn dify-btn" 
                :class="{ 'active': activeButton === 'dify', 'disabled': sendingToDify || !hasBackendAnalysis }"
                :disabled="sendingToDify || !hasBackendAnalysis"
                @click="setActiveButton('dify'); runDifyWorkflow()">
                <span v-if="sendingToDify" class="loading-spinner"></span>
                {{ sendingToDify ? '发送中...' : 'Send To Dify' }}
              </button>
        </div>
      </div>
      </div>

          <div class="right-section">
            <h3 class="subsection-title">分析结果</h3>
            <div class="results-grid">
              <div class="result-item" v-for="item in results" :key="item.title">
                <h4 class="result-title">{{ item.title }}</h4>
                <p class="result-value">{{ item.value }}</p>
              </div>
            </div>
            <div class="liability-suggestion" style="margin-top: var(--space-4);">
              <h4 class="result-title">责任建议</h4>
              <p class="result-value" style="font-size: var(--text-sm); line-height: var(--leading-normal);">{{ liabilitySuggestion }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="analysis-results card-surface" v-if="imageEvidenceResult">
        <h2 class="section-title">关键帧图片侧证联动</h2>
        <div class="results-grid">
          <div class="result-item">
            <h3 class="result-title">追尾类型匹配度</h3>
            <p class="result-value">{{ imageEvidenceTypeMatch }}</p>
          </div>
          <div class="result-item">
            <h3 class="result-title">单图定责可信度</h3>
            <p class="result-value">{{ imageEvidenceLiabilityTrust }}</p>
          </div>
          <div class="result-item">
            <h3 class="result-title">与视频一致性</h3>
            <p class="result-value">{{ imageEvidenceConsistencyText }}</p>
          </div>
          <div class="result-item">
            <h3 class="result-title">联动结论</h3>
            <p class="result-value">{{ imageEvidenceDecision }}</p>
          </div>
        </div>
      </div>

      <div class="key-frames card-surface">
        <h2 class="section-title">关键帧</h2>
        <div class="frames-grid">
          <div
            v-for="item in frames"
            :key="item.id || item.time"
            class="frame-item"
            :class="{ selected: selectedFrame === item.label, main: item.isMain }"
            @click="selectFrame(item)"
          >
            <div class="frame-badge" v-if="item.isMain">主帧</div>
            <img :src="item.image" :alt="item.label" @error="handleFrameImageError(item, $event)">
            <div class="frame-info">
              <p class="frame-time">{{ item.timeText || item.time }}</p>
              <p class="frame-label">{{ item.label }}</p>
              <div class="frame-quality">
                <span class="quality-item">清晰度: {{ item.clarity }}</span>
                <span class="quality-item">分数: {{ item.qualityScore }}</span>
                <span class="quality-item purpose">{{ item.purpose }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="dify-result card-surface" v-if="difyResult">
        <div class="section-header">
          <div class="dify-title-wrapper">
            <div class="dify-badge">🤖</div>
            <h2 class="section-title">Dify 智能分析结果</h2>
          </div>
          <button class="btn btn-sm btn-outline" @click="difyResult = null">
            关闭
          </button>
        </div>
        <div class="dify-analysis-container">
          <div class="markdown-content" v-html="parseMarkdown(difyAnalysisText)"></div>
        </div>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { notify } from '../composables/useToast'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import NavigationButtons from '../components/NavigationButtons.vue'

const router = useRouter()
const route = useRoute()
const {
  state,
  goStep,
  updateForm,
  updateAnalysis,
  setSelectedFrame,
  completeVideoProcessing,
  setCurrentCase
} = useAccidentFlow()

goStep('video-processing')

// 统一获取 caseId：优先 URL query，fallback store
const currentCaseId = () => route.query.caseId || state.caseId
// 进入页面时同步 caseId 到 store（防止刷新后丢失）
if (route.query.caseId && String(route.query.caseId) !== String(state.caseId)) {
  setCurrentCase(route.query.caseId)
}

// console.log('VideoProcessing.vue loaded successfully')
// console.log('Current step:', state.step)

const fileInput = ref(null)
const videoPlayer = ref(null)
const videoMeta = ref({ name: state.form.fileName || '', size: 0 })
const videoUrl = ref('')
const uploadedFile = ref(state.form.videoFile || null)
const extracting = ref(false)
const extractionAttempted = ref(false)
const linkingEvidence = ref(false)
const imageEvidenceResult = ref(null)
const latestVideoBackendResult = ref(null)
const activeButton = ref('')
const sendingToDify = ref(false)
const difyResult = ref(null)
const difyAnalysisText = computed(() => {
  return state.analysis.difyAnalysisText || '暂无分析结果'
})

const setActiveButton = (buttonName) => {
  activeButton.value = buttonName
}

// 后端主分析结果
const impactTimeText = ref('--')
const vehicleCountText = ref('--')
const accidentTypeText = ref('待分析')
const collisionPositionText = ref('--')
const riskLevelText = ref('unknown')
const typeConfidenceText = ref('')

// 当前选中的“预览帧”
const selectedFrame = computed(() => state.analysis.selectedFrame)

// 从环境变量获取API基础地址
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'
const EXTRACT_TIMEOUT_MS = Number(import.meta.env.VITE_EXTRACT_TIMEOUT_MS || 120000)
const API_BASE_URL_NORMALIZED = String(API_BASE_URL || '/api').replace(/\/+$/, '')

function buildPlaceholderImage(label, size = 'landscape') {
  const isSquare = size === 'square'
  const width = isSquare ? 512 : 1280
  const height = isSquare ? 512 : 720
  const subtitle = isSquare ? 'Keyframe Placeholder' : 'Video Placeholder'
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f2034"/>
      <stop offset="100%" stop-color="#1f4c78"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect x="36" y="36" width="${width - 72}" height="${height - 72}" rx="24" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.24)"/>
  <text x="50%" y="48%" text-anchor="middle" fill="#eaf2ff" font-family="Segoe UI, Arial, sans-serif" font-size="${isSquare ? 32 : 42}" font-weight="700">${label}</text>
  <text x="50%" y="58%" text-anchor="middle" fill="#c5d8f3" font-family="Segoe UI, Arial, sans-serif" font-size="${isSquare ? 18 : 24}">${subtitle}</text>
</svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

const videoPosterUrl = buildPlaceholderImage('Accident Preview', 'landscape')

const results = ref([
  { title: '事故类型', value: state.form.accidentType || '待分析' },
  { title: '估计碰撞时间', value: '--' },
  { title: '车辆数量', value: '--' },
  { title: '碰撞位置', value: '--' }
])

const imageEvidenceTypeMatch = computed(() => {
  const score = Number(imageEvidenceResult.value?.rear_end_type_match_score  ||  0)
  return `${Math.round(score * 100)}%`
})

const imageEvidenceLiabilityTrust = computed(() => {
  const score = Number(imageEvidenceResult.value?.single_image_liability_trust_score  ||  0)
  return `${Math.round(score * 100)}%`
})

const imageEvidenceConsistencyText = computed(() => {
  const c = imageEvidenceResult.value?.consistency
  if (!c) return '未提供视频结果'
  const score = Math.round(Number(c.evidence_consistency_score || 0) * 100)
  if (score >= 75) return `与视频结果基本一致（${score}%）`
  if (score >= 45) return `与视频结果部分一致（${score}%）`
  return `与视频结果存在矛盾（${score}%）`
})

const imageEvidenceDecision = computed(() => {
  const text = String(imageEvidenceResult.value?.decision_text || '')
  return text || '等待联动分析'
})

const liabilitySuggestion = computed(() => {
  const accidentType = accidentTypeText.value
  const consistency = imageEvidenceConsistencyText.value
  
  if (!accidentType || accidentType === '待分析') {
    return '请先上传视频并进行分析，系统将根据事故类型和证据情况给出责任建议。'
  }
  
  if (accidentType.includes('追尾')) {
    if (consistency.includes('基本一致')) {
      return '根据视频和图片证据，后车未保持安全车距，建议后车承担主要责任。'
    } else if (consistency.includes('部分一致')) {
      return '视频与图片证据存在部分差异，建议后车承担主要责任，前车承担次要责任。'
    } else {
      return '证据存在矛盾，建议进一步调查或由交警认定责任。'
    }
  }
  
  if (accidentType.includes('变道')) {
    if (consistency.includes('基本一致')) {
      return '变道车辆未确保安全，建议变道车辆承担全部责任。'
    } else {
      return '建议变道车辆承担主要责任，直行车辆承担次要责任。'
    }
  }
  
  if (accidentType.includes('转弯')) {
    return '转弯车辆应让直行车辆先行，建议转弯车辆承担主要责任。'
  }
  
  return '建议根据现场具体情况，由交警部门进行责任认定。'
})

const defaultFrames = [1, 2, 3, 4].map((n, i) => ({
  id: `default-${n}`,
  label: `关键帧${n}`,
  time: 30 + i * 4,
  timeText: `00:00:${String(30 + i * 4).padStart(2, '0')}`,
  image: buildPlaceholderImage(`Frame ${n}`, 'square'),
  qualityScore: 90 - i * 3,
  clarity: i < 2 ? '清晰' : '较清晰',
  purpose: i === 0 ? '主分析帧' : '辅助证据',
  stage: i === 0 ? 'impact' : 'supplement',
  isMain: i === 0
}))

const frames = computed({
  get() {
    if (state.analysis.keyframes.length > 0) {
      return state.analysis.keyframes
    }
    return []
  },
  set(value) {
    updateAnalysis({ keyframes: value })
  }
})

const hasKeyframes = computed(() => frames.value.length > 0)
const hasBackendAnalysis = computed(() => {
  const vr = latestVideoBackendResult.value
  return Boolean(vr && Array.isArray(vr.keyframes) && vr.keyframes.length > 0)
})

function resolveBackendMediaUrl(rawPath) {
  const path = String(rawPath || '').trim()
  if (!path) return ''
  if (/^https?:\/\//i.test(path) || path.startsWith('data:')) return path
  if (path.startsWith('/api/')) return path
  if (path.startsWith('/')) return `${API_BASE_URL_NORMALIZED}${path}`
  return `${API_BASE_URL_NORMALIZED}/${path}`
}

function candidateFrameUrls(rawPath) {
  const path = String(rawPath || '').trim()
  if (!path) return []
  if (/^https?:\/\//i.test(path) || path.startsWith('data:')) return [path]
  const normalized = path.startsWith('/') ? path : `/${path}`
  const byApi = `${API_BASE_URL_NORMALIZED}${normalized}`
  return Array.from(new Set([byApi, normalized]))
}

function handleFrameImageError(item, event) {
  const img = event?.target
  if (!img || !item) return
  const tried = Array.isArray(item._triedImageUrls) ? item._triedImageUrls : []
  const urls = Array.from(new Set([
    ...candidateFrameUrls(item.imageUrlRaw || ''),
    ...candidateFrameUrls(item.thumbUrlRaw || item.image || '')
  ]))
  const next = urls.find((u) => !tried.includes(u))
  if (next) {
    item._triedImageUrls = [...tried, next]
    item.image = next
    img.src = next
    return
  }
  img.src = buildPlaceholderImage(item.label || '关键帧', 'square')
}

function formatSeconds(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0))
  const hh = String(Math.floor(total / 3600)).padStart(2, '0')
  const mm = String(Math.floor((total % 3600) / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

function updateResultPanel({
  accidentType = state.form.accidentType || '待分析',
  impactTime = '--',
  vehicleCount = '--',
  collisionPosition = '后车前部与前车后部'
} = {}) {
  results.value = [
    { title: '事故类型', value: accidentType },
    { title: '估计碰撞时间', value: impactTime },
    { title: '车辆数量', value: vehicleCount },
    { title: '碰撞位置', value: collisionPosition }
  ]
}

function collisionPositionFromType(typeName) {
  const t = String(typeName || '')
  if (t.includes('追尾')) return '后车前部与前车后部'
  if (t.includes('变道')) return '相邻车道侧向冲突'
  if (t.includes('转弯')) return '路口交汇区冲突'
  return '待判定'
}

function purposeFromStage(stage, fallbackIndex, total) {
  if (stage === 'impact') return '主分析帧'
  if (stage === 'approach') return '冲突形成'
  if (stage === 'pre') return '事故前状态'
  if (stage === 'post') return '事故后状态'
  if (stage === 'evidence' || stage === 'supplement') return '辅助证据'

  // 后端没给 stage 时兜底
  if (fallbackIndex === 0) return '主分析帧'
  if (fallbackIndex === 1) return '碰撞瞬间'
  if (fallbackIndex === total - 1) return '事故后状态'
  return '辅助证据'
}

function buildVideoContextFromBackend(data) {
  if (!data) return null
  return {
    accident_type: data.accident_type,
    type_confidence: data.type_confidence,
    type_topk: data.type_topk || [],
    type_probs: data.evidence?.type_probs || {},
    type_scores: data.evidence?.type_scores_raw || {},
    risk_level: data.risk_level,
    risk_alert_time: data.risk_alert_time,
    lead_time_sec: data.lead_time_sec
  }
}

function normalizeImageEvidenceDecision(evidence) {
  const typeMatch = Number(evidence.rear_end_type_match_score || 0)
  const liabilityTrust = Number(evidence.single_image_liability_trust_score || 0)
  if (typeMatch >= 0.75 && liabilityTrust >= 0.65) {
    return '追尾类型匹配度高，单图可作为较强侧证（仍建议结合视频）。'
  }
  if (typeMatch >= 0.6) {
    return '疑似追尾，单图证据中等，建议结合视频进一步确认。'
  }
  return '当前关键帧对追尾类型支持有限，建议依赖视频时序证据。'
}

function resolveMainFrame(extractedFrames, backendImpactSec) {
  return (
    extractedFrames.find(frame => frame.isMain) ||
    extractedFrames.find(frame => frame.stage === 'impact') ||
    extractedFrames.find(frame => Math.abs(Number(frame.time || 0) - backendImpactSec) < 0.6) ||
    extractedFrames[0]
  )
}

function resetFrameState() {
  extractionAttempted.value = false
  imageEvidenceResult.value = null
  latestVideoBackendResult.value = null
  setSelectedFrame(null)
  updateAnalysis({
    selectedFrame: null,
    selectedFrameInfo: null,
    mainFrameInfo: null,
    impactTime: '--',
    keyframes: []
  })
  impactTimeText.value = '--'
  vehicleCountText.value = '--'
  updateResultPanel()
}

// 初始化函数，从全局状态中读取视频文件信息
const initializeVideo = () => {
  if (state.form.videoFile) {
    uploadedFile.value = state.form.videoFile

    if (videoUrl.value) {
      URL.revokeObjectURL(videoUrl.value)
    }

    videoUrl.value = URL.createObjectURL(state.form.videoFile)
    videoMeta.value = {
      name: state.form.videoFileName || state.form.fileName || '',
      size: state.form.videoFile.size
    }

  notify({
      title: '视频已加载',
      message: state.form.videoFileName || state.form.fileName
    })
  } else if (state.form.videoFileName) {
    mockUploadVideo()
  }
}

initializeVideo()

const handleFile = (e) => {
  const file = e.target.files?.[0]
  if (!file) return

  uploadedFile.value = file

  if (videoUrl.value) {
    URL.revokeObjectURL(videoUrl.value)
  }

  videoUrl.value = URL.createObjectURL(file)
  videoMeta.value = { name: file.name, size: file.size }

  updateForm({
    fileName: file.name,
    fileType: 'video',
    fileSize: `${(file.size / 1024 / 1024).toFixed(2)} MB`,
    videoFileName: file.name,
    videoFile: file
  })

  resetFrameState()
  frames.value = defaultFrames

  notify({
    title: '视频已加载',
    message: file.name
  })
}

// 模拟视频上传，用于测试
const mockUploadVideo = () => {
  const mockFile = new File(['mock video data'], 'accident_video.mp4', { type: 'video/mp4' })
  uploadedFile.value = mockFile

  // 这里只是占位图；真实分析还是走后端
  videoUrl.value = ''

  videoMeta.value = {
    name: 'accident_video.mp4',
    size: 1024 * 1024 * 10
  }

  updateForm({
    fileName: 'accident_video.mp4',
    fileType: 'video',
    fileSize: '10.00 MB',
    videoFileName: 'accident_video.mp4',
    videoFile: mockFile
  })

  resetFrameState()
  frames.value = defaultFrames

  notify({
    title: '视频已加载',
    message: 'accident_video.mp4'
  })
}

const extractFrames = async () => {
  extractionAttempted.value = true
  if (!uploadedFile.value) {
    notify({
      title: '使用模拟数据',
      message: '未检测到上传的视频文件，使用模拟数据进行关键帧提取测试。',
      type: 'info'
    })

    extracting.value = true

    try {
      const mockData = {
        impact_time: 3,
        vehicle_count: 2,
        keyframes: [
          {
            time: '1',
            thumb_url: buildPlaceholderImage('Frame 1', 'square'),
            stage: 'pre',
            purpose: '事故前状态',
            is_main: false,
            score: 0.72
          },
          {
            time: '3',
            thumb_url: buildPlaceholderImage('Frame 2', 'square'),
            stage: 'impact',
            purpose: '主分析帧',
            is_main: true,
            score: 0.95
          },
          {
            time: '5',
            thumb_url: buildPlaceholderImage('Frame 3', 'square'),
            stage: 'post',
            purpose: '事故后状态',
            is_main: false,
            score: 0.83
          },
          {
            time: '7',
            thumb_url: buildPlaceholderImage('Frame 4', 'square'),
            stage: 'evidence',
            purpose: '辅助证据',
            is_main: false,
            score: 0.70
          }
        ]
      }

      await new Promise(resolve => setTimeout(resolve, 1000))
      processKeyframeData(mockData)
    } catch (error) {
      const message = error?.name === 'AbortError'
        ? '关键帧提取超时（120秒），请检查后端是否卡在视频解码或模型加载。'
        : (error?.message || '未知错误')
      notify({
        title: '关键帧提取失败',
        message: `请检查后端是否已启动，或稍后重试。错误信息：${message}`,
        type: 'error'
      })
    } finally {
      extracting.value = false
    }
    return
  }

  extracting.value = true

  try {
    const formData = new FormData()
    formData.append('file', uploadedFile.value)

    notify({
      title: '开始提取关键帧',
      message: '正在分析视频内容，可能需要几秒钟时间...',
      type: 'info'
    })

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), EXTRACT_TIMEOUT_MS)
    let response
    try {
      response = await fetch(`${API_BASE_URL}/upload_video/`, {
        method: 'POST',
        body: formData,
        signal: controller.signal
      })
    } finally {
      clearTimeout(timeoutId)
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `后端返回状态码 ${response.status}`)
    }

    const data = await response.json()
    processKeyframeData(data)
  } catch (error) {
    const message = error?.name === 'AbortError'
      ? '关键帧提取超时（120秒），请检查后端是否卡在视频解码或模型加载。'
      : (error?.message || '未知错误')
    // console.error('关键帧提取失败', error)
    notify({
      title: '关键帧提取失败',
      message: `请检查后端是否已启动，地址是否正确。错误信息：${message}`,
      type: 'error'
    })
  } finally {
    extracting.value = false
  }
}

const processKeyframeData = (data) => {
  latestVideoBackendResult.value = data

  if (!data.keyframes || !Array.isArray(data.keyframes) || data.keyframes.length === 0) {
    frames.value = []
    notify({
      title: '未提取到关键帧',
      message: '后端未返回关键帧，请检查后端响应或视频内容。',
      type: 'error'
    })
    return
  }

  // console.log('后端返回的关键帧数据:', data)

  const backendImpactSec = Number(data.impact_time  ||  0)
  const backendVehicleCount = data.vehicle_count != null ? `${data.vehicle_count} 辆` : '2 辆'
  const backendAccidentType = String(data.accident_type || '待分析')
  const backendTypeConfidence = Number(data.type_confidence  ||  0)
  const backendRiskLevel = String(data.risk_level || 'unknown')
  const backendCollisionPosition = collisionPositionFromType(backendAccidentType)

  const extractedFrames = data.keyframes.map((item, index) => {
    const sec = Number(item.time) || 0

    const qualityScore =
      typeof item.score === 'number'
        ? Math.round(item.score * 100)
        : Math.max(60, 95 - index * 3)

    const clarity =
      qualityScore >= 90 ? '清晰'
        : qualityScore >= 80 ? '较清晰'
          : '一般'

    const stage = item.stage || ''
    const purpose = item.purpose || purposeFromStage(stage, index, data.keyframes.length)
    const isMain = Boolean(item.is_main) || stage === 'impact'

    const thumbUrl = String(item.thumb_url || '').trim()
    const imageUrlRaw = String(item.image_url || item.image || '').trim()
    const candidates = candidateFrameUrls(thumbUrl)
    const imageUrl =
      resolveBackendMediaUrl(imageUrlRaw)
      || candidates[0]
      || resolveBackendMediaUrl(thumbUrl)
      || buildPlaceholderImage(`Frame ${index + 1}`, 'square')

    return {
      id: `frame-${index + 1}`,
      label: `关键帧${index + 1}`,
      time: sec,
      timeText: formatSeconds(sec),
      image: imageUrl,
      imageUrlRaw,
      thumbUrlRaw: thumbUrl,
      _triedImageUrls: imageUrl ? [imageUrl] : [],
      qualityScore,
      clarity,
      purpose,
      stage,
      isMain
    }
  })

  const mainFrame = resolveMainFrame(extractedFrames, backendImpactSec)

  // 只保留一个主分析帧
  const normalizedFrames = extractedFrames.map(frame => ({
    ...frame,
    isMain: frame.id === mainFrame.id
  }))

  frames.value = normalizedFrames

  impactTimeText.value =
    backendImpactSec > 0
      ? formatSeconds(backendImpactSec)
      : (mainFrame?.timeText || '--')

  vehicleCountText.value = backendVehicleCount
  accidentTypeText.value = backendAccidentType
  collisionPositionText.value = backendCollisionPosition
  riskLevelText.value = backendRiskLevel
  typeConfidenceText.value = backendTypeConfidence > 0 ? `${Math.round(backendTypeConfidence * 100)}%` : ''

  updateResultPanel({
    accidentType: typeConfidenceText.value
      ? `${accidentTypeText.value}（置信度 ${typeConfidenceText.value}）`
      : accidentTypeText.value,
    impactTime: impactTimeText.value,
    vehicleCount: vehicleCountText.value,
    collisionPosition: collisionPositionText.value
  })

  // 默认预览主分析帧，但不改动主帧身份
  if (mainFrame) {
    selectFrame(mainFrame, false)
  }

  notify({
    title: '关键帧提取完成',
    message: `共提取 ${normalizedFrames.length} 帧，已按后端主分析帧自动定位`,
    type: 'success'
  })

  // 将关键帧数据保存到store，以便IntelligentAnalysis页面可以访问
  updateAnalysis({
    keyframes: normalizedFrames,
    confidence: backendTypeConfidence * 100,
    riskLevel: backendRiskLevel
  })

  runKeyframeEvidenceLinkage(true)
}

const runKeyframeEvidenceLinkage = async (silent = false) => {
  const mainFrame = frames.value.find(frame => frame.isMain) || frames.value[0]
    if (!mainFrame || !mainFrame.thumbUrlRaw) {
      if (!silent) {
        notify({
          title: '无法联动',
          message: '请先提取关键帧后再进行图片侧证联动。',
          type: 'error'
        })
      }
    return
  }

  linkingEvidence.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/analyze_image_evidence/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        frame_url: mainFrame.thumbUrlRaw,
        video_context: buildVideoContextFromBackend(latestVideoBackendResult.value)
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `后端返回状态码 ${response.status}`)
    }

    const data = await response.json()
    const evidence = data.image_evidence || {}

    imageEvidenceResult.value = {
      ...evidence,
      rear_end_type_match_score: Number(
        evidence.rear_end_type_match_score  ||  evidence.rear_end_likelihood  ||  0
      ),
      single_image_liability_trust_score: Number(
        evidence.single_image_liability_trust_score  ||  evidence.confidence  ||  0
      ),
      decision_text: normalizeImageEvidenceDecision({
        rear_end_type_match_score: Number(
          evidence.rear_end_type_match_score  ||  evidence.rear_end_likelihood  ||  0
        ),
        single_image_liability_trust_score: Number(
          evidence.single_image_liability_trust_score  ||  evidence.confidence  ||  0
        )
      })
    }

    updateAnalysis({
      imageSideEvidence: imageEvidenceResult.value,
      evidenceConsistencyScore: Number(
        imageEvidenceResult.value?.consistency?.evidence_consistency_score  ||  0
      )
    })

    if (!silent) {
      notify({
        title: '联动完成',
        message: '已将关键帧图片侧证与视频关键帧结果完成一致性联动。',
        type: 'success'
      })
    }
  } catch (error) {
    const message = error?.name === 'AbortError'
      ? '关键帧提取超时（120秒），请检查后端是否卡在视频解码或模型加载。'
      : (error?.message || '未知错误')
    if (!silent) {
      notify({
        title: '联动失败',
        message: `关键帧图片侧证联动失败：${message}`,
        type: 'error'
      })
    }
  } finally {
    linkingEvidence.value = false
  }
}

const setSelectedAsMainFrame = () => {
  if (!selectedFrame.value) {
    notify({
      title: '未选择关键帧',
      message: '请先点击一个关键帧，再设为主分析帧。',
      type: 'error'
    })
    return
  }

  const selected = frames.value.find(frame => frame.label === selectedFrame.value)
  if (!selected) return

  const normalized = frames.value.map(frame => ({
    ...frame,
    isMain: frame.label === selected.label
  }))

  frames.value = normalized
  impactTimeText.value = selected.timeText || formatSeconds(Number(selected.time) || 0)

  updateResultPanel({
    accidentType: typeConfidenceText.value
      ? `${accidentTypeText.value}（置信度 ${typeConfidenceText.value}）`
      : accidentTypeText.value,
    impactTime: impactTimeText.value,
    vehicleCount: vehicleCountText.value,
    collisionPosition: collisionPositionText.value
  })

  updateAnalysis({
    selectedFrame: selected.label,
    selectedFrameInfo: selected,
    mainFrameInfo: selected,
    impactTime: impactTimeText.value,
    keyframes: normalized
  })

  notify({
    title: '主分析帧已更新',
    message: `已将 ${selected.label} 设为主分析帧，估计碰撞时间已更新为 ${impactTimeText.value}。`,
    type: 'success'
  })
}

const selectFrame = (item, showToast = true) => {
  setSelectedFrame(item.label)

  updateAnalysis({
    selectedFrame: item.label,
    selectedFrameInfo: item,
    mainFrameInfo: frames.value.find(frame => frame.isMain) || item,
    impactTime: impactTimeText.value,
    keyframes: frames.value
  })

  if (videoPlayer.value && Number.isFinite(Number(item.time))) {
    videoPlayer.value.currentTime = Number(item.time) || 0
  }

  if (showToast) {
    notify({
      title: '已选择关键帧',
      message: `${item.label} | ${item.timeText || item.time} | 清晰度: ${item.clarity} | 分数: ${item.qualityScore}${item.isMain ? ' | 主分析帧' : ''}`
    })
  }
}

const runAnalysis = () => {
  if (!selectedFrame.value) {
    notify({
      title: '请先选择关键帧',
      message: '先提取并选择预览帧，再进入智能分析。',
      type: 'error'
    })
    return
  }

  const selectedFrameObj = frames.value.find(frame => frame.label === selectedFrame.value)
  const mainFrameObj = frames.value.find(frame => frame.isMain) || selectedFrameObj

  if (!selectedFrameObj || !mainFrameObj) {
    notify({
      title: '关键帧信息丢失',
      message: '请重新提取关键帧后再进行分析。',
      type: 'error'
    })
    return
  }

  const confidence = Math.min(95, selectedFrameObj.qualityScore + 5)
  const evidenceIntegrity = Math.min(98, mainFrameObj.qualityScore)

  const weather = state.form.weather || ''
  const roadEnv = state.form.roadEnv || ''
  const accidentType = state.form.accidentType || ''

  const fallbackRiskLevel =
    weather.includes('雨') || roadEnv.includes('路口') || accidentType.includes('碰撞')
      ? '中等'
      : '低'
  const riskLevel = riskLevelText.value && riskLevelText.value !== 'unknown'
    ? riskLevelText.value
    : fallbackRiskLevel

  updateAnalysis({
    selectedFrame: selectedFrame.value,   // 当前预览帧
    selectedFrameInfo: selectedFrameObj,
    mainFrameInfo: mainFrameObj,          // 真正主分析帧
    impactTime: impactTimeText.value,     // 固定碰撞时间
    keyframes: frames.value,
    confidence,
    evidenceIntegrity,
    riskLevel
  })

  updateResultPanel({
    accidentType: typeConfidenceText.value
      ? `${accidentTypeText.value}（置信度 ${typeConfidenceText.value}）`
      : accidentTypeText.value,
    impactTime: impactTimeText.value || mainFrameObj.timeText || '--',
    vehicleCount: vehicleCountText.value || '2 辆',
    collisionPosition: collisionPositionText.value || '待判定'
  })

  const nextRoute = completeVideoProcessing()
  router.push({ path: nextRoute, query: { caseId: currentCaseId() } })

  notify({
    title: '进入智能分析',
    message: `当前预览帧：${selectedFrameObj.label}；主分析帧：${mainFrameObj.label}；碰撞时间：${impactTimeText.value}`,
    type: 'success'
  })
}

const markAnalysis = () => {
  const currentPreview = frames.value.find(frame => frame.label === selectedFrame.value)
  const mainFrame = frames.value.find(frame => frame.isMain)

  const msg = currentPreview
    ? `已对 ${currentPreview.label} 完成重点标记。当前主分析帧：${mainFrame?.label || '未设置'}。`
    : '请先选择一个关键帧。'

  notify({
    title: '标记完成',
    message: msg,
    type: 'info'
  })
}

const runDifyWorkflow = async () => {
  if (sendingToDify.value) return
  
  sendingToDify.value = true
  
  try {
    const backendResult = latestVideoBackendResult.value
    if (!backendResult || !Array.isArray(backendResult.keyframes) || backendResult.keyframes.length === 0) {
      notify({
        title: '错误',
        message: '请先完成关键帧提取（拿到后端真实分析结果）后再发送 Dify。',
        type: 'error'
      })
      sendingToDify.value = false
      return
    }

    notify({
      title: '发送到 Dify',
      message: '正在将事故分析证据发送到 Dify Workflow...',
      type: 'info'
    })

    const videoResult = {
      ...backendResult,
      keyframes: (backendResult.keyframes || []).map((kf) => ({
        time: Number(kf.time) || 0,
        stage: kf.stage || '',
        purpose: kf.purpose || '',
        is_main: Boolean(kf.is_main),
        score: typeof kf.score === 'number' ? kf.score : 0,
        raw_score: typeof kf.raw_score === 'number' ? kf.raw_score : 0,
        thumb_url: kf.thumb_url || '',
        image_url: kf.image_url || ''
      })),
      video_context: buildVideoContextFromBackend(backendResult) || {},
      video_file: videoMeta.value.name || ''
    }

    const requestData = {
      video_result: videoResult,
      image_evidence: imageEvidenceResult.value || {},
      additional_evidence: ''
    }

    const response = await fetch(`${API_BASE_URL}/dify/analyze_accident_case/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData)
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      const errorMsg = errorData.detail?.message || errorData.detail || `请求失败，状态码 ${response.status}`
      throw new Error(errorMsg)
    }

    const data = await response.json()

    const difyOutput = data?.result
       ||  data?.dify_response?.data?.outputs
       ||  data?.dify_response?.data?.answer
       ||  data?.answer_text
       ||  data

    if (difyOutput !== undefined && difyOutput !== null) {
      difyResult.value = difyOutput

      const answerText = normalizeDifyOutputText(difyOutput)
      
      // 基础更新：保存原始Dify数据
      const updates = {
        difyResult: difyOutput,
        difyOutput: JSON.stringify(difyOutput, null, 2),
        difyAnalysisText: answerText
      }
      
      updateAnalysis(updates)

      notify({
        title: 'Dify 分析完成',
        message: '已收到 Dify 返回结果，可在智能分析页查看详细内容',
        type: 'success'
      })
    } else {
      throw new Error('Dify 返回结果格式异常')
    }
  } catch (error) {
    const message = error?.name === 'AbortError'
      ? '关键帧提取超时（120秒），请检查后端是否卡在视频解码或模型加载。'
      : (error?.message || '未知错误')
    // console.error('Dify 请求失败:', error)
    notify({
      title: 'Dify 请求失败',
      message: message || '请检查后端配置和 Dify 服务状态',
      type: 'error'
    })
  } finally {
    sendingToDify.value = false
  }
}

const extractLegalClues = (difyOutput) => {
  const clues = []
  if (!difyOutput) return clues
  
  const text = typeof difyOutput === 'string' ? difyOutput : JSON.stringify(difyOutput)
  
  const legalPatterns = [
    /《[^》]+》/g,
    /第[一二三四五六七八九十百千0-9\d]+条/g,
    /道路交通安全法/g,
    /实施条例/g,
    /法规|法律|条例|规定/g
  ]
  
  legalPatterns.forEach(pattern => {
    const matches = text.match(pattern)
    if (matches) {
      matches.forEach(match => {
        if (!clues.includes(match) && clues.length < 10) {
          clues.push(match)
        }
      })
    }
  })
  
  return clues
}


const normalizeDifyOutputText = (value) => {
  const tryParse = (s) => {
    try {
      return JSON.parse(s)
    } catch {
      return null
    }
  }

  let payload = value

  // 1) 先处理对象结构：优先取 final / answer
  if (payload && typeof payload === 'object') {
    if (typeof payload.final === 'string' && payload.final.trim()) {
      payload = payload.final
    } else if (typeof payload.answer === 'string' && payload.answer.trim()) {
      payload = payload.answer
    }
  }

  // 2) 再处理字符串结构：若是 JSON 字符串，继续解出 final / answer
  if (typeof payload === 'string') {
    const parsed = tryParse(payload)
    if (parsed && typeof parsed === 'object') {
      if (typeof parsed.final === 'string' && parsed.final.trim()) {
        payload = parsed.final
      } else if (typeof parsed.answer === 'string' && parsed.answer.trim()) {
        payload = parsed.answer
      } else {
        payload = JSON.stringify(parsed, null, 2)
      }
    }
  }

  const raw = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2)
  return String(raw || '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/(?<!\n)(【[^】]+】)/g, '\n$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
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
    'applicability': '适用性'
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
    const codeBlockRegex = /```( ? :json) ? \s*([\s\S]* ? )```/i
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
  
  html = html.replace(/```(\w+) ? \n([\s\S]* ? )```/g, '<pre><code class="$1">$2</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  html = html.replace(/### (.+)/g, '<h3>$1</h3>')
  html = html.replace(/## (.+)/g, '<h2>$1</h2>')
  html = html.replace(/# (.+)/g, '<h1>$1</h1>')
  html = html.replace(/^\s*-\s+(.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>[\s\S]* ? <\/li>)/g, '<ul>$1</ul>')
  html = html.replace(/\n\n/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  html = `<div class="clean-text">${html}</div>`
  html = html.replace(/<div class="clean-text"><\/div>/g, '')
  html = html.replace(/<p><\/p>/g, '')
  html = html.replace(/<ul><\/ul>/g, '')
  
  return html
}

onBeforeUnmount(() => {
  if (videoUrl.value && videoUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(videoUrl.value)
  }
})
</script>

<style scoped>
.video-processing-page,
.processing-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.video-processing-page {
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
}

.card-surface,
.video-upload {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  padding: var(--space-6);
  transition: box-shadow var(--transition-normal);
}

.card-surface:hover,
.video-upload:hover { box-shadow: var(--shadow-md); }

.upload-card {
  text-align: center;
  padding: var(--space-8);
  border: 2px dashed var(--border-medium);
  border-radius: var(--radius-2xl);
  background: var(--bg-secondary);
  transition: all var(--transition-normal);
  cursor: pointer;
}

.upload-card:hover {
  border-color: var(--primary-400);
  background: var(--primary-soft);
}

.upload-icon {
  width: 60px; height: 60px;
  margin: 0 auto var(--space-4);
  background: linear-gradient(135deg, var(--primary-soft) 0%, var(--primary-100) 100%);
  border-radius: var(--radius-2xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
  transition: all var(--transition-normal);
}

.upload-card:hover .upload-icon {
  transform: scale(1.08);
  background: var(--primary-gradient);
  color: white;
}

.upload-icon svg { width: 28px; height: 28px; }

.upload-title {
  color: var(--text-primary);
  font-size: var(--text-lg);
  font-weight: 700;
  margin-bottom: var(--space-2);
}

.upload-desc {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-bottom: var(--space-4);
}

.upload-area {
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  flex-wrap: nowrap;
  overflow-x: auto;
  padding-bottom: var(--space-2);
}

.control-group::-webkit-scrollbar {
  height: 4px;
}

.control-group::-webkit-scrollbar-track {
  background: var(--bg-secondary);
  border-radius: 2px;
}

.control-group::-webkit-scrollbar-thumb {
  background: var(--border-light);
  border-radius: 2px;
}

.file-input { display: none; }

.btn,
.control-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 12px 24px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  cursor: pointer;
  font-size: var(--text-base);
  font-weight: 600;
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
}

.btn-icon { width: 15px; height: 15px; }

.btn-primary,
.control-btn.primary,
.control-btn.active {
  background: var(--primary-gradient);
  color: #fff;
  border: none;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-xs);
}

.btn-secondary:hover {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary-300);
  transform: translateY(-1px);
}

.btn-primary:hover,
.control-btn.primary:hover {
  background: var(--primary-gradient-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.control-btn {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.control-btn:hover {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary-300);
  transform: translateY(-1px);
}

.analysis-card {
  display: flex;
  flex-direction: row;
  gap: var(--space-6);
}

.left-section {
  flex: 1.5;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.right-section {
  flex: 1;
  background: var(--bg-secondary);
  padding: var(--space-5);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-light);
}

.subsection-title {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}

.player-placeholder {
  border-radius: var(--radius-2xl);
  overflow: hidden;
  background: linear-gradient(135deg, #0f2034 0%, #13263d 100%);
  box-shadow: var(--shadow-lg);
  max-width: 800px;
  margin: 0 auto;
}

.player-placeholder img,
.preview-video {
  width: 100%;
  display: block;
  aspect-ratio: 16/9;
  object-fit: cover;
}

.section-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-5);
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-4);
}

.right-section .results-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-3);
}

.result-item,
.frame-item {
  background: var(--bg-secondary);
  padding: var(--space-5);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-light);
  transition: all var(--transition-normal);
}

.result-item:hover,
.frame-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--primary-200);
}

.right-section .result-item {
  background: var(--bg-primary);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
}

.result-title {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: var(--space-2);
}

.result-value {
  font-size: var(--text-xl);
  font-weight: 800;
  color: var(--text-primary);
}

.frames-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-4);
}

.frame-item { cursor: pointer; position: relative; }

.frame-item.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18);
  transform: translateY(-2px);
}

.frame-item img {
  width: 100%;
  aspect-ratio: 1/1;
  object-fit: cover;
  border-radius: var(--radius-xl);
  margin-bottom: var(--space-3);
}

.frame-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--primary-gradient);
  color: white;
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  z-index: 1;
}

.frame-info { display: flex; flex-direction: column; gap: 3px; }

.frame-time {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 600;
  text-align: center;
}

.frame-label {
  font-size: var(--text-xs);
  color: var(--text-primary);
  font-weight: 600;
  text-align: center;
}

.frame-quality { display: flex; flex-direction: column; gap: 2px; margin-top: 3px; }

.quality-item {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}

.quality-item.purpose { color: var(--primary); font-weight: 600; }

.frame-item.main {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18);
}

.loading-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(37, 99, 235, 0.3);
  border-radius: 50%;
  border-top-color: var(--primary);
  animation: spin 1s ease-in-out infinite;
  margin-right: var(--space-2);
  vertical-align: middle;
}

.control-btn:disabled .loading-spinner {
  border-color: rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
}

@keyframes spin { to { transform: rotate(360deg); } }

.control-btn.dify-btn {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border-color: transparent;
  color: white;
}

.control-btn.dify-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.control-btn.dify-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.dify-result {
  animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.dify-result .section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.dify-content {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.dify-text {
  padding: var(--space-4);
  max-height: 400px;
  overflow-y: auto;
}

.dify-output {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.dify-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dify-badge {
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

.dify-analysis {
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

</style>