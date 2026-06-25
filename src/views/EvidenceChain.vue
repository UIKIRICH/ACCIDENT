<template>
  <div class="evidence-chain-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">证据链可视化</h1>
        <p class="page-subtitle">证据 → 事实 → 规则 → 建议 → 复核 → 报告 完整链路追踪</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="refreshCases">
          <span class="btn-icon">↻</span>
          刷新案件
        </button>
      </div>
    </div>

    <!-- 案件选择器 -->
    <div class="case-selector card-surface">
      <div class="selector-row">
        <label class="selector-label">选择案件</label>
        <select v-model="selectedCaseId" class="case-select" @change="onCaseChange">
          <option value="" disabled>请选择案件查看证据链</option>
          <option v-for="c in cases" :key="c.caseId" :value="c.caseId">
            {{ c.caseId }} · {{ c.title }} · {{ c.status }}
          </option>
        </select>
      </div>
      <div v-if="caseDetail" class="case-meta">
        <span class="meta-item"><span class="meta-label">事故类型</span>{{ caseDetail.accident_type || caseDetail.title || '未命名' }}</span>
        <span class="meta-item"><span class="meta-label">发生地点</span>{{ caseDetail.location || '未记录' }}</span>
        <span class="meta-item"><span class="meta-label">案件状态</span>{{ caseDetail.status || '处理中' }}</span>
      </div>
    </div>

    <!-- 横向流程图 -->
    <div class="flowchart-container card-surface">
      <div v-if="loading" class="flowchart-loading">
        <div class="loading-spinner"></div>
        <p>正在加载证据链数据...</p>
      </div>
      <div v-else-if="!selectedCaseId" class="empty-flowchart">
        <div class="empty-icon">🔗</div>
        <p>请先选择案件以查看证据链</p>
      </div>
      <div v-else class="flowchart">
        <template v-for="(node, index) in nodes" :key="node.id">
          <div
            class="flow-node"
            :class="[`node-${node.category}`, { active: selectedNodeId === node.id, empty: !node.hasData }]"
            @click="selectNode(node)"
          >
            <div class="node-badge" v-html="node.icon"></div>
            <div class="node-info">
              <div class="node-title">{{ node.title }}</div>
              <div class="node-subtitle" v-if="node.subtitle">{{ node.subtitle }}</div>
              <div class="node-count" :class="{ 'no-data': !node.hasData }">{{ node.countText }}</div>
            </div>
          </div>
          <div v-if="index < nodes.length - 1" class="flow-arrow" :class="`arrow-${node.category}`">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"></line>
              <polyline points="12 5 19 12 12 19"></polyline>
            </svg>
          </div>
        </template>
      </div>
    </div>

    <!-- 遮罩层 -->
    <transition name="fade">
      <div v-if="selectedNodeId" class="panel-mask" @click="selectedNodeId = null"></div>
    </transition>

    <!-- 详情面板（右侧滑入） -->
    <transition name="slide">
      <div v-if="selectedNodeId && currentNode" class="detail-panel" :class="`panel-${currentNode.category}`">
        <div class="panel-header">
          <div class="panel-title-wrap">
            <span class="panel-badge" v-html="currentNode.icon"></span>
            <div>
              <h3 class="panel-title">{{ currentNode.title }}</h3>
              <p class="panel-subtitle" v-if="currentNode.subtitle">{{ currentNode.subtitle }}</p>
            </div>
          </div>
          <button class="panel-close" @click="selectedNodeId = null" title="关闭">✕</button>
        </div>
        <div class="panel-body">
          <!-- 视频证据 -->
          <template v-if="selectedNodeId === 'video-evidence'">
            <div v-if="videoEvidences.length" class="detail-list">
              <div v-for="(ev, i) in videoEvidences" :key="i" class="detail-item">
                <div class="item-name">{{ ev.file_name || ev.name || `视频证据 ${i + 1}` }}</div>
                <div class="item-meta" v-if="ev.content || ev.description">{{ ev.content || ev.description }}</div>
                <div class="item-path" v-if="ev.file_path">路径：{{ ev.file_path }}</div>
                <div class="item-time" v-if="ev.created_at">{{ ev.created_at }}</div>
                <!-- 视频关联的关键帧图片预览 -->
                <div v-if="ev.keyframe_url" class="keyframe-thumb">
                  <img :src="ev.keyframe_url" alt="关键帧预览" class="thumb-img" @error="e => e.target.style.display='none'" />
                </div>
              </div>
            </div>
            <!-- 同时展示 imageEvidences 中的关键帧图片 -->
            <div v-if="imageEvidences.length" class="detail-list" style="margin-top: 12px;">
              <div class="block-label" style="margin-bottom: 8px;">视频关键帧</div>
              <div v-for="(ev, i) in imageEvidences" :key="'kf-'+i" class="detail-item">
                <div class="item-name">{{ ev.file_name || ev.name || `关键帧 ${i + 1}` }}</div>
                <div class="keyframe-thumb" v-if="ev.preview_url">
                  <img :src="ev.preview_url" alt="关键帧" class="thumb-img" @error="e => { e.target.style.display='none'; e.target.nextElementSibling.style.display='block'; }" />
                  <span class="thumb-fallback" style="display:none; font-size:12px; color:var(--text-muted); margin-top:8px;">图片加载失败</span>
                </div>
              </div>
            </div>
            <p v-if="!videoEvidences.length && !imageEvidences.length" class="empty-text">暂无视频证据</p>
          </template>

          <!-- 视频语义校验（千问 + 融合门控） -->
          <template v-else-if="selectedNodeId === 'video-semantic-check'">
            <div v-if="fusedEvidence" class="semantic-check-detail">
              <!-- 视角与车辆上下文 -->
              <div class="detail-block">
                <div class="block-label">视角与车辆上下文</div>
                <div class="semantic-grid">
                  <div class="semantic-row">
                    <span class="semantic-label">视角类型</span>
                    <span class="semantic-value">{{ mapValue(CAMERA_VIEW_MAP, fusedEvidence.camera_context?.camera_view) }}</span>
                  </div>
                  <div class="semantic-row">
                    <span class="semantic-label">自车状态</span>
                    <span class="semantic-value">{{ fusedEvidence.camera_context?.ego_vehicle_present ? '隐式参与' : '未参与' }}</span>
                  </div>
                  <div class="semantic-row">
                    <span class="semantic-label">画面可见外部车辆数</span>
                    <span class="semantic-value">{{ fusedEvidence.camera_context?.visible_external_vehicle_count ?? '—' }}</span>
                  </div>
                  <div class="semantic-row">
                    <span class="semantic-label">估计涉事车辆数</span>
                    <span class="semantic-value">{{ fusedEvidence.camera_context?.estimated_involved_vehicle_count ?? '—' }}</span>
                  </div>
                  <div class="semantic-row">
                    <span class="semantic-label">外部车辆行为</span>
                    <span class="semantic-value">{{ mapValue(BEHAVIOR_MAP, fusedEvidence.vehicle_evidence?.external_vehicle_behavior) }}</span>
                  </div>
                  <div class="semantic-row">
                    <span class="semantic-label">自车-外部车辆关系</span>
                    <span class="semantic-value">{{ mapValue(EGO_RELATION_MAP, fusedEvidence.vehicle_evidence?.ego_external_relation) }}</span>
                  </div>
                </div>
              </div>

              <!-- 检测模型 vs 语义校验 对比 -->
              <div class="detail-block">
                <div class="block-label">事故类型判定（双通道）</div>
                <div class="dual-channel">
                  <div class="channel-item channel-detector">
                    <div class="channel-title">检测模型候选</div>
                    <div class="channel-type">{{ mapValue(ACCIDENT_TYPE_MAP, fusedEvidence.detector_output?.candidate_accident_type_from_detector) }}</div>
                    <div class="channel-conf">置信度 {{ formatConfidence(fusedEvidence.detector_output?.detector_type_confidence) }}</div>
                  </div>
                  <div class="channel-item channel-qwen">
                    <div class="channel-title">千问语义校验</div>
                    <div class="channel-type">{{ mapValue(ACCIDENT_TYPE_MAP, fusedEvidence.qwen_semantic_check?.semantic_accident_type_from_qwen) }}</div>
                    <div class="channel-conf">置信度 {{ formatConfidence(fusedEvidence.qwen_semantic_check?.semantic_confidence) }}</div>
                  </div>
                </div>
                <div class="final-type">
                  <span class="final-label">最终事故类型</span>
                  <span class="final-value" :class="{ 'is-unknown': fusedEvidence.fusion_result?.accepted_accident_type === 'unknown' }">
                    {{ mapValue(ACCIDENT_TYPE_MAP, fusedEvidence.fusion_result?.accepted_accident_type) }}
                  </span>
                </div>
              </div>

              <!-- 系统结论 -->
              <div class="detail-block">
                <div class="block-label">系统结论</div>
                <div class="conclusion-box" :class="{ 'has-conflict': fusedEvidence.fusion_result?.conflict_detected }">
                  <div class="conclusion-row">
                    <span class="conclusion-label">系统状态</span>
                    <span class="conclusion-value">{{ mapValue(FINAL_STATUS_MAP, fusedEvidence.fusion_result?.final_status) }}</span>
                  </div>
                  <div class="conclusion-row">
                    <span class="conclusion-label">系统动作</span>
                    <span class="conclusion-value">{{ mapValue(SYSTEM_ACTION_MAP, fusedEvidence.fusion_result?.system_action) }}</span>
                  </div>
                  <div class="conclusion-row" v-if="fusedEvidence.fusion_result?.status_reason">
                    <span class="conclusion-label">状态原因</span>
                    <span class="conclusion-value">{{ fusedEvidence.fusion_result.status_reason }}</span>
                  </div>
                  <div class="conclusion-row">
                    <span class="conclusion-label">是否冲突</span>
                    <span class="conclusion-value" :class="{ 'text-danger': fusedEvidence.fusion_result?.conflict_detected, 'text-success': !fusedEvidence.fusion_result?.conflict_detected }">
                      {{ fusedEvidence.fusion_result?.conflict_detected ? '存在冲突' : '无冲突' }}
                    </span>
                  </div>
                  <div class="conclusion-row">
                    <span class="conclusion-label">需人工复核</span>
                    <span class="conclusion-value" :class="{ 'text-danger': fusedEvidence.fusion_result?.manual_review_required }">
                      {{ fusedEvidence.fusion_result?.manual_review_required ? '是' : '否' }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- 追尾特征支持 -->
              <div class="detail-block" v-if="fusedEvidence.fusion_result?.rear_end_support">
                <div class="block-label">追尾特征支持</div>
                <div class="rear-end-box">
                  <div class="rear-end-status" :class="'status-' + fusedEvidence.fusion_result.rear_end_support.status">
                    {{ mapValue(REAR_END_STATUS_MAP, fusedEvidence.fusion_result.rear_end_support.status) }}
                    <span class="rear-end-score">（评分 {{ fusedEvidence.fusion_result.rear_end_support.score }}）</span>
                  </div>
                  <div class="rear-end-reason" v-if="fusedEvidence.fusion_result.rear_end_support.reason">
                    {{ fusedEvidence.fusion_result.rear_end_support.reason }}
                  </div>
                </div>
              </div>

              <!-- 冲突原因列表 -->
              <div class="detail-block" v-if="fusedEvidence.qwen_semantic_check?.conflict_reasons?.length">
                <div class="block-label">冲突原因</div>
                <ul class="reason-list">
                  <li v-for="(reason, i) in fusedEvidence.qwen_semantic_check.conflict_reasons" :key="i">{{ reason }}</li>
                </ul>
              </div>

              <!-- 缺失证据列表 -->
              <div class="detail-block" v-if="fusedEvidence.qwen_semantic_check?.missing_evidence?.length">
                <div class="block-label">缺失证据</div>
                <ul class="reason-list missing-list">
                  <li v-for="(item, i) in fusedEvidence.qwen_semantic_check.missing_evidence" :key="i">{{ item }}</li>
                </ul>
              </div>

              <!-- 证据一致性 -->
              <div class="detail-block" v-if="fusedEvidence.fusion_result?.keyframe_video_consistency">
                <div class="block-label">证据一致性</div>
                <div class="consistency-box">
                  <div class="consistency-score" :class="'level-' + fusedEvidence.fusion_result.keyframe_video_consistency.level">
                    {{ mapValue(CONSISTENCY_LEVEL_MAP, fusedEvidence.fusion_result.keyframe_video_consistency.level) }}
                    <span class="consistency-num">{{ fusedEvidence.fusion_result.keyframe_video_consistency.score }}</span>
                  </div>
                  <div v-if="fusedEvidence.fusion_result.keyframe_video_consistency.matched_items?.length" class="consistency-sub">
                    <div class="sub-label">一致项</div>
                    <ul class="reason-list"><li v-for="(m, i) in fusedEvidence.fusion_result.keyframe_video_consistency.matched_items" :key="i">{{ m }}</li></ul>
                  </div>
                  <div v-if="fusedEvidence.fusion_result.keyframe_video_consistency.conflict_items?.length" class="consistency-sub">
                    <div class="sub-label">冲突项</div>
                    <ul class="reason-list"><li v-for="(c, i) in fusedEvidence.fusion_result.keyframe_video_consistency.conflict_items" :key="i">{{ c }}</li></ul>
                  </div>
                  <div v-if="fusedEvidence.fusion_result.keyframe_video_consistency.missing_items?.length" class="consistency-sub">
                    <div class="sub-label">缺失项</div>
                    <ul class="reason-list"><li v-for="(m, i) in fusedEvidence.fusion_result.keyframe_video_consistency.missing_items" :key="i">{{ m }}</li></ul>
                  </div>
                </div>
              </div>
            </div>
            <p v-else class="empty-text">暂无视频语义校验数据<br><span class="empty-hint">请先在视频处理页完成千问语义校验与证据融合</span></p>
          </template>

          <!-- 图片证据 -->
          <template v-else-if="selectedNodeId === 'image-evidence'">
            <div v-if="imageEvidences.length" class="detail-list">
              <div v-for="(ev, i) in imageEvidences" :key="i" class="detail-item">
                <div class="item-name">{{ ev.file_name || ev.name || `图片证据 ${i + 1}` }}</div>
                <div class="item-meta" v-if="ev.content || ev.description">{{ ev.content || ev.description }}</div>
                <div class="item-path" v-if="ev.file_path">路径：{{ ev.file_path }}</div>
                <div class="item-time" v-if="ev.created_at">{{ ev.created_at }}</div>
                <div class="keyframe-thumb" v-if="ev.preview_url">
                  <img :src="ev.preview_url" alt="图片证据" class="thumb-img" @error="e => { e.target.style.display='none'; e.target.nextElementSibling.style.display='block'; }" />
                  <span class="thumb-fallback" style="display:none; font-size:12px; color:var(--text-muted); margin-top:8px;">图片加载失败</span>
                </div>
              </div>
            </div>
            <p v-else class="empty-text">暂无图片证据</p>
          </template>

          <!-- 文本描述 -->
          <template v-else-if="selectedNodeId === 'text-evidence'">
            <div v-if="caseDetail && caseDetail.description" class="detail-block">
              <div class="block-label">案件描述</div>
              <p class="block-text">{{ caseDetail.description }}</p>
            </div>
            <div v-if="textEvidences.length" class="detail-list">
              <div class="block-label" style="margin-top: 16px;">文本证据</div>
              <div v-for="(ev, i) in textEvidences" :key="i" class="detail-item">
                <div class="item-name">{{ ev.file_name || ev.name || `文本证据 ${i + 1}` }}</div>
                <div class="item-meta" v-if="ev.content || ev.description">{{ ev.content || ev.description }}</div>
              </div>
            </div>
            <p v-if="!textEvidences.length && !(caseDetail && caseDetail.description)" class="empty-text">暂无文本描述</p>
          </template>

          <!-- 结构化事实 -->
          <template v-else-if="selectedNodeId === 'structured-facts'">
            <div v-if="facts.length" class="detail-list">
              <div v-for="(f, i) in facts" :key="i" class="detail-item">
                <div class="item-head">
                  <span class="item-tag">{{ f.fact_type || '事实' }}</span>
                  <span v-if="f.confidence != null" class="item-confidence">置信度 {{ f.confidence }}{{ typeof f.confidence === 'number' ? '%' : '' }}</span>
                </div>
                <div class="item-meta">{{ f.fact_content || f.fact_value || f.content || '无内容' }}</div>
                <div class="item-time" v-if="f.source_type">来源：{{ f.source_type }}</div>
              </div>
            </div>
            <p v-else class="empty-text">暂无结构化事实</p>
          </template>

          <!-- 命中规则 -->
          <template v-else-if="selectedNodeId === 'matched-rules'">
            <div v-if="matchedRules.length" class="detail-list">
              <div v-for="(r, i) in matchedRules" :key="i" class="detail-item">
                <div class="item-head">
                  <span class="item-tag">{{ r.rule_id || `规则 ${i + 1}` }}</span>
                </div>
                <div class="item-name">{{ r.rule_name || r.name || '未命名规则' }}</div>
                <div class="item-meta" v-if="r.trigger_reason">触发原因：{{ r.trigger_reason }}</div>
                <div class="item-legal" v-if="r.legal_basis || r.basis">法律依据：{{ r.legal_basis || r.basis }}</div>
              </div>
            </div>
            <p v-else class="empty-text">暂无命中规则</p>
          </template>

          <!-- 责任建议 -->
          <template v-else-if="selectedNodeId === 'liability'">
            <div v-if="liability" class="liability-detail">
              <div v-if="liability.summary" class="detail-block">
                <div class="block-label">责任概述</div>
                <p class="block-text">{{ liability.summary }}</p>
              </div>
              <div v-if="liabilityVehicles.length" class="detail-block">
                <div class="block-label">责任分配</div>
                <div class="liability-rows">
                  <div v-for="(v, i) in liabilityVehicles" :key="i" class="liability-row">
                    <span class="liability-role">{{ v.role || v.vehicleType || `车辆 ${i + 1}` }}</span>
                    <div class="liability-bar">
                      <div class="liability-bar-fill" :style="{ width: (v.percentage || 0) + '%' }"></div>
                    </div>
                    <span class="liability-pct">{{ v.liability || '未认定' }} {{ v.percentage || 0 }}%</span>
                  </div>
                </div>
              </div>
              <p v-if="!liability.summary && !liabilityVehicles.length" class="empty-text">暂无责任建议详情</p>
            </div>
            <p v-else class="empty-text">暂无责任建议</p>
          </template>

          <!-- 人工复核 -->
          <template v-else-if="selectedNodeId === 'reviews'">
            <div v-if="reviews.length" class="detail-list">
              <div v-for="(rv, i) in reviews" :key="i" class="detail-item">
                <div class="item-head">
                  <span class="item-name" style="margin: 0;">{{ rv.reviewer || rv.reviewer_name || '未知复核人' }}</span>
                  <span class="item-time" v-if="rv.reviewed_at || rv.created_at">{{ rv.reviewed_at || rv.created_at }}</span>
                </div>
                <div class="item-meta" v-if="rv.final_result || rv.conclusion">
                  <span class="item-tag">{{ rv.final_result || rv.conclusion }}</span>
                </div>
                <div class="item-meta" v-if="rv.review_comment || rv.opinion || rv.review_opinion">
                  {{ rv.review_comment || rv.opinion || rv.review_opinion }}
                </div>
              </div>
            </div>
            <p v-else class="empty-text">暂无复核记录</p>
          </template>

          <!-- 报告归档 -->
          <template v-else-if="selectedNodeId === 'report'">
            <div v-if="caseDetail" class="report-detail">
              <div class="detail-block">
                <div class="block-label">案件状态</div>
                <p class="block-text">{{ caseDetail.status || '处理中' }}</p>
              </div>
              <div class="detail-block">
                <div class="block-label">案件编号</div>
                <p class="block-text">{{ selectedCaseId }}</p>
              </div>
              <div class="detail-block">
                <div class="block-label">事故类型</div>
                <p class="block-text">{{ caseDetail.accident_type || caseDetail.title || '未命名' }}</p>
              </div>
              <div class="detail-block">
                <div class="block-label">归档信息</div>
                <p class="block-text">{{ caseDetail.status === '已完成' || caseDetail.status === '已归档' ? '该案件已归档，可导出报告' : '案件尚未归档' }}</p>
              </div>
              <button class="btn btn-primary export-btn" @click="exportReport">
                <span class="btn-icon">⬇</span>
                导出报告
              </button>
            </div>
            <p v-else class="empty-text">暂无案件报告信息</p>
          </template>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { CasesAPI, StatsAPI } from '../api/index.js'
import { notify } from '../composables/useToast'
import { useAccidentFlow } from '../stores/useAccidentFlow'

const router = useRouter()
const route = useRoute()
const { getCurrentCase, isValidCaseId, setCurrentCase } = useAccidentFlow()

// 案件列表与选中状态
const cases = ref([])
const selectedCaseId = ref('')
const loading = ref(false)
const selectedNodeId = ref(null)

// 各节点数据
const caseDetail = ref(null)
const evidences = ref([])
const facts = ref([])
const matchedRules = ref([])
const liability = ref(null)
const reviews = ref([])
// 视频语义校验（千问）+ 证据融合 数据
const fusedEvidence = ref(null)

// ── 字段中文映射（避免裸露英文枚举值） ──
const CAMERA_VIEW_MAP = {
  dashcam_ego_view: '行车记录仪视角',
  roadside_view: '路侧监控视角',
  surveillance_view: '交通监控视角',
  unknown: '未知视角'
}
const BEHAVIOR_MAP = {
  lane_change: '变道',
  cut_in: '切入',
  braking: '急停',
  straight: '直行',
  unknown: '未知'
}
const ACCIDENT_TYPE_MAP = {
  rear_end: '追尾',
  side_collision: '侧向碰撞',
  lane_change_or_cut_in: '变道/切入',
  head_on: '正面碰撞',
  unknown: '暂不直接认定'
}
const EGO_RELATION_MAP = {
  external_vehicle_moves_into_ego_path: '外部车辆驶入自车路径',
  ego_rear_ends_front_vehicle: '自车追尾前车',
  side_collision: '侧向碰撞',
  unknown: '未知'
}
const FINAL_STATUS_MAP = {
  evidence_ready: '证据就绪',
  needs_manual_review: '需人工复核',
  insufficient_evidence: '证据不足'
}
const SYSTEM_ACTION_MAP = {
  manual_review_required: '需人工复核',
  proceed_to_liability: '进入责任推理'
}
const REAR_END_STATUS_MAP = {
  supported: '支持',
  partially_supported: '部分支持',
  not_supported: '不支持'
}
const CONSISTENCY_LEVEL_MAP = {
  high: '高',
  medium: '中',
  low: '低'
}

// 通用映射函数：找不到时返回原值或默认值
function mapValue(map, value, fallback = '—') {
  if (value == null || value === '') return fallback
  return map[value] || value
}

// 格式化置信度（0~1 → 百分比）
function formatConfidence(val) {
  if (val == null || val === '') return '—'
  const num = Number(val)
  if (isNaN(num)) return String(val)
  return (num <= 1 ? num * 100 : num).toFixed(1) + '%'
}

// ── 将证据 file_path 转换为可访问的 URL ──
// 后端静态文件映射:
//   /keyframes       -> backend/keyframes/
//   /uploaded_videos -> backend/uploaded_videos/
//   /uploads         -> uploads/
function filePathToUrl(filePath) {
  if (!filePath) return null
  const p = String(filePath).replace(/\\/g, '/')
  if (p.startsWith('http://') || p.startsWith('https://') || p.startsWith('/')) {
    return p
  }
  // uploads/cases/... 保留完整相对路径
  if (p.startsWith('uploads/')) {
    return `/${p}`
  }
  const basename = p.split('/').pop()
  if (!basename) return null
  // backend/uploaded_videos/... -> /uploaded_videos/...
  if (p.includes('uploaded_videos')) {
    return `/uploaded_videos/${basename}`
  }
  if (p.includes('keyframe') || p.includes('keyframes') || /\.(jpg|jpeg|png|webp|gif|bmp)$/i.test(p)) {
    return `/keyframes/${basename}`
  }
  if (p.includes('uploaded_images') || p.includes('uploaded')) {
    return `/uploaded_images/${basename}`
  }
  if (/\.(jpg|jpeg|png|webp|gif|bmp)$/i.test(p)) {
    return `/keyframes/${basename}`
  }
  return `/${p}`
}

// ── 证据分类辅助函数 ──
const getEvidenceType = (e) => String(e.evidence_type || e.type || '').toLowerCase()
const isVideoEvidence = (e) => {
  const t = getEvidenceType(e)
  const fp = String(e.file_path || '')
  return t.includes('video') || t.includes('视频') || /\.(mp4|avi|mov|webm|mkv|flv)$/i.test(fp)
}
const isImageEvidence = (e) => {
  const t = getEvidenceType(e)
  const fp = String(e.file_path || '')
  return t.includes('image') || t.includes('图片') || t.includes('photo') ||
    t.includes('keyframe') || t.includes('关键帧') || t.includes('frame') ||
    /\.(jpg|jpeg|png|webp|gif|bmp)$/i.test(fp)
}
const isTextEvidence = (e) => {
  const t = getEvidenceType(e)
  return t.includes('text') || t.includes('文本') || t.includes('描述')
}

// 按类型分类的证据（附加预览 URL）
const videoEvidences = computed(() =>
  evidences.value.filter(isVideoEvidence).map(e => ({
    ...e,
    keyframe_url: filePathToUrl(e.keyframe_path || e.thumbnail_path || '')
  }))
)
const imageEvidences = computed(() =>
  evidences.value.filter(isImageEvidence).map(e => ({
    ...e,
    preview_url: filePathToUrl(e.file_path)
  }))
)
const textEvidences = computed(() => evidences.value.filter(isTextEvidence))

// 责任建议中的车辆责任分配
const liabilityVehicles = computed(() => {
  if (!liability.value) return []
  const details = liability.value.details || {}
  return details.vehicles || liability.value.vehicles || []
})

// ── 流程图节点定义（依据已加载数据动态计算） ──
const nodes = computed(() => {
  if (!selectedCaseId.value) return []
  const videoCount = videoEvidences.value.length
  const hasFused = !!fusedEvidence.value
  const hasConflict = !!fusedEvidence.value?.fusion_result?.conflict_detected
  const imageCount = imageEvidences.value.length
  const hasText = textEvidences.value.length > 0 || !!(caseDetail.value && caseDetail.value.description)
  const factCount = facts.value.length
  const ruleCount = matchedRules.value.length
  const hasLiability = !!liability.value
  const reviewCount = reviews.value.length
  const hasReport = !!caseDetail.value

  return [
    {
      id: 'video-evidence',
      title: '视频证据',
      subtitle: '关键帧 / 分析',
      category: 'evidence',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="15" height="16" rx="2"/><path d="m22 8-5 4 5 4V8z"/></svg>`,
      hasData: videoCount > 0,
      countText: videoCount > 0 ? `${videoCount} 条` : '暂无'
    },
    {
      id: 'video-semantic-check',
      title: '视频语义校验',
      subtitle: '千问 · 融合门控',
      category: 'semantic',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v1a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M5 8h14l-1 12H6L5 8z"/><circle cx="9.5" cy="14" r="1"/><circle cx="14.5" cy="14" r="1"/></svg>`,
      hasData: hasFused,
      countText: hasFused ? (hasConflict ? '存在冲突' : '已通过') : '暂无'
    },
    {
      id: 'image-evidence',
      title: '图片证据',
      subtitle: '图片分析',
      category: 'evidence',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>`,
      hasData: imageCount > 0,
      countText: imageCount > 0 ? `${imageCount} 条` : '暂无'
    },
    {
      id: 'text-evidence',
      title: '文本描述',
      subtitle: '文本事实',
      category: 'evidence',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
      hasData: hasText,
      countText: hasText ? `${textEvidences.value.length || 1} 条` : '暂无'
    },
    {
      id: 'structured-facts',
      title: '结构化事实',
      subtitle: '事实抽取',
      category: 'fact',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
      hasData: factCount > 0,
      countText: factCount > 0 ? `${factCount} 条` : '暂无'
    },
    {
      id: 'matched-rules',
      title: '命中规则',
      subtitle: '规则匹配',
      category: 'rule',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M5 8l7-5 7 5"/><path d="M5 16l7 5 7-5"/></svg>`,
      hasData: ruleCount > 0,
      countText: ruleCount > 0 ? `${ruleCount} 条` : '暂无'
    },
    {
      id: 'liability',
      title: '责任建议',
      subtitle: '责任认定',
      category: 'liability',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-5"/></svg>`,
      hasData: hasLiability,
      countText: hasLiability ? '已生成' : '暂无'
    },
    {
      id: 'reviews',
      title: '人工复核',
      subtitle: '复核记录',
      category: 'review',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/></svg>`,
      hasData: reviewCount > 0,
      countText: reviewCount > 0 ? `${reviewCount} 条` : '暂无'
    },
    {
      id: 'report',
      title: '报告归档',
      subtitle: '案件报告',
      category: 'report',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>`,
      hasData: hasReport,
      countText: hasReport ? (caseDetail.value.status || '查看') : '暂无'
    }
  ]
})

// 当前选中的节点对象
const currentNode = computed(() => nodes.value.find(n => n.id === selectedNodeId.value))

// ── 加载案件列表 ──
async function loadCases() {
  try {
    const result = await StatsAPI.getHistoryCases({ limit: 100 })
    if (result.success && Array.isArray(result.data)) {
      cases.value = result.data.map(c => ({
        caseId: String(c.id),
        title: c.title || c.accident_type || '未命名案件',
        status: c.status || '待处理',
        location: c.location || '未记录'
      }))
    }
  } catch (err) {
    console.warn('获取案件列表失败:', err)
    cases.value = []
  }
}

// ── 选中案件后并行加载所有链路数据 ──
async function loadChainData(caseId) {
  loading.value = true
  // 重置数据
  caseDetail.value = null
  evidences.value = []
  facts.value = []
  matchedRules.value = []
  liability.value = null
  reviews.value = []
  fusedEvidence.value = null
  selectedNodeId.value = null

  try {
    const [
      detailRes, evidencesRes, factsRes, rulesRes, reviewsRes, liabilityRes, fusedRes
    ] = await Promise.allSettled([
      CasesAPI.getDetail(caseId),
      CasesAPI.getEvidences(caseId),
      CasesAPI.getFacts(caseId),
      CasesAPI.getMatchedRules(caseId),
      CasesAPI.getReviews(caseId),
      CasesAPI.getLiabilityLatest(caseId),
      CasesAPI.getFusedEvidence(caseId)
    ])

    // 案件基本信息
    if (detailRes.status === 'fulfilled' && detailRes.value?.success) {
      caseDetail.value = detailRes.value.data
    }

    // 证据列表
    if (evidencesRes.status === 'fulfilled' && evidencesRes.value?.success) {
      evidences.value = evidencesRes.value.data || []
    }

    // 结构化事实
    if (factsRes.status === 'fulfilled' && factsRes.value?.success) {
      facts.value = factsRes.value.data || []
    }

    // 命中规则
    if (rulesRes.status === 'fulfilled' && rulesRes.value?.success) {
      matchedRules.value = rulesRes.value.data || []
    }

    // 复核记录
    if (reviewsRes.status === 'fulfilled' && reviewsRes.value?.success) {
      reviews.value = reviewsRes.value.data || []
    }

    // 责任建议
    if (liabilityRes.status === 'fulfilled' && liabilityRes.value?.success) {
      liability.value = liabilityRes.value.data
    } else if (caseDetail.value && caseDetail.value.liability) {
      // 从案件详情中提取责任数据
      liability.value = caseDetail.value.liability
    }

    // 视频语义校验 + 证据融合数据
    if (fusedRes.status === 'fulfilled' && fusedRes.value?.success) {
      const packet = fusedRes.value.data?.fused_evidence_packet
      // 后端在无数据时返回空对象 {}，这里过滤掉空包
      fusedEvidence.value = (packet && Object.keys(packet).length > 0) ? packet : null
    }
  } catch (err) {
    console.error('加载证据链数据失败:', err)
    notify({ title: '加载失败', message: '无法加载证据链数据，请重试', type: 'error' })
  } finally {
    loading.value = false
  }
}

// ── 案件选择变化 ──
async function onCaseChange() {
  if (!selectedCaseId.value) return
  // 同步到全局 store
  setCurrentCase(selectedCaseId.value)
  await loadChainData(selectedCaseId.value)
}

// ── 点击节点展开详情 ──
function selectNode(node) {
  selectedNodeId.value = node.id
}

// ── 刷新案件列表 ──
async function refreshCases() {
  await loadCases()
  notify({ title: '刷新成功', message: '案件列表已更新', type: 'success' })
}

// ── 导出报告 ──
async function exportReport() {
  if (!selectedCaseId.value) return
  try {
    const blob = await CasesAPI.exportReport(selectedCaseId.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `证据链报告_${selectedCaseId.value}_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    notify({ title: '导出成功', message: '报告已下载到本地' })
  } catch (err) {
    notify({ title: '导出失败', message: err.message || '请稍后重试', type: 'error' })
  }
}

// ── 页面初始化 ──
onMounted(async () => {
  await loadCases()
  // 优先使用 URL query 中的 caseId，其次使用 store 中当前案件
  const queryId = route.query.caseId
  let initialId = ''
  if (isValidCaseId(queryId)) {
    initialId = String(queryId).trim()
  } else {
    const current = getCurrentCase()
    if (isValidCaseId(current)) {
      initialId = String(current).trim()
    }
  }
  if (initialId) {
    selectedCaseId.value = initialId
    await loadChainData(initialId)
  }
})
</script>

<style scoped>
.evidence-chain-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  animation: pageIn 0.4s var(--ease-default);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── 页面头部 ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
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
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 400;
}

.header-actions { display: flex; gap: var(--space-3); }

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 9px 18px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 600;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.btn-icon { font-size: 14px; line-height: 1; }

.btn-primary {
  background: var(--primary-gradient);
  color: white;
  border: none;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.btn-primary:hover {
  background: var(--primary-gradient-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.btn-secondary:hover {
  background: var(--primary-soft);
  color: var(--primary);
  border-color: var(--primary-300);
  transform: translateY(-1px);
}

/* ── 卡片表面 ── */
.card-surface {
  padding: var(--space-6);
  border-radius: var(--radius-2xl);
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-normal);
}

.card-surface:hover { box-shadow: var(--shadow-md); }

/* ── 案件选择器 ── */
.case-selector { display: flex; flex-direction: column; gap: var(--space-4); }

.selector-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.selector-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
}

.case-select {
  flex: 1;
  padding: 10px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  outline: none;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.case-select:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
  background: var(--bg-primary);
}

.case-meta {
  display: flex;
  gap: var(--space-6);
  flex-wrap: wrap;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-light);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.meta-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── 流程图容器 ── */
.flowchart-container { min-height: 200px; }

.flowchart-loading,
.empty-flowchart {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: 60px 0;
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.empty-icon { font-size: 48px; opacity: 0.5; }

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-light);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* ── 横向流程图 ── */
.flowchart {
  display: flex;
  align-items: stretch;
  gap: var(--space-2);
  overflow-x: auto;
  padding: var(--space-3) 0;
}

/* ── 节点卡片 ── */
.flow-node {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: 12px;
  background: var(--bg-primary);
  border: 2px solid var(--border-light);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: all var(--transition-normal);
  min-width: 160px;
  flex-shrink: 0;
  position: relative;
}

.flow-node:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}

.flow-node.empty {
  opacity: 0.6;
}

.flow-node.empty .node-count {
  color: var(--text-muted);
}

/* 节点颜色分类 */
.node-evidence { --node-color: #007AFF; }
.node-semantic { --node-color: #00C7BE; }
.node-fact { --node-color: #34C759; }
.node-rule { --node-color: #FF9500; }
.node-liability { --node-color: #5856D6; }
.node-review { --node-color: #FF3B30; }
.node-report { --node-color: #8E8E93; }

.flow-node:hover {
  border-color: var(--node-color);
}

.flow-node.active {
  border-color: var(--node-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--node-color) 20%, transparent), var(--shadow-lg);
  background: color-mix(in srgb, var(--node-color) 5%, var(--bg-primary));
}

.node-badge {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--node-color) 12%, transparent);
  flex-shrink: 0;
  color: var(--node-color);
}

.node-badge svg {
  width: 22px;
  height: 22px;
}

.node-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.node-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}

.node-subtitle {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.node-count {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--node-color);
  margin-top: 2px;
}

.node-count.no-data {
  color: var(--text-muted);
  font-weight: 500;
}

/* ── 箭头连线 ── */
.flow-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--border-medium);
  transition: color var(--transition-fast);
}

.flow-arrow svg {
  width: 22px;
  height: 22px;
}

.arrow-evidence { color: #007AFF; }
.arrow-semantic { color: #00C7BE; }
.arrow-fact { color: #34C759; }
.arrow-rule { color: #FF9500; }
.arrow-liability { color: #5856D6; }
.arrow-review { color: #FF3B30; }
.arrow-report { color: #8E8E93; }

/* ── 遮罩层 ── */
.panel-mask {
  position: fixed;
  inset: 0;
  background: rgba(3, 10, 20, 0.4);
  z-index: 1000;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* ── 详情面板（右侧滑入） ── */
.detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: min(440px, calc(100vw - 32px));
  height: 100vh;
  background: var(--bg-primary);
  box-shadow: var(--shadow-2xl);
  z-index: 1001;
  display: flex;
  flex-direction: column;
  border-left: 4px solid var(--node-color, var(--primary));
}

.panel-evidence { --node-color: #007AFF; }
.panel-semantic { --node-color: #00C7BE; }
.panel-fact { --node-color: #34C759; }
.panel-rule { --node-color: #FF9500; }
.panel-liability { --node-color: #5856D6; }
.panel-review { --node-color: #FF3B30; }
.panel-report { --node-color: #8E8E93; }

.slide-enter-active, .slide-leave-active {
  transition: transform 0.35s var(--ease-default), opacity 0.35s ease;
}
.slide-enter-from, .slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--node-color) 5%, var(--bg-primary));
}

.panel-title-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.panel-badge {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--node-color) 15%, transparent);
  color: var(--node-color);
  flex-shrink: 0;
}

.panel-badge svg {
  width: 20px;
  height: 20px;
}

.panel-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.panel-subtitle {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin: 2px 0 0 0;
}

.panel-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-md);
  font-size: 16px;
  transition: all var(--transition-fast);
}

.panel-close:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
}

/* ── 详情列表项 ── */
.detail-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.detail-item {
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border-left: 3px solid var(--node-color, var(--primary));
}

.item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.item-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
  word-break: break-all;
}

.item-meta {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin-top: 2px;
}

.item-path {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  margin-top: 4px;
  word-break: break-all;
}

.item-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.item-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  background: color-mix(in srgb, var(--node-color, var(--primary)) 12%, transparent);
  color: var(--node-color, var(--primary));
}

.item-confidence {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.item-legal {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 4px;
  line-height: var(--leading-relaxed);
}

/* ── 详情区块 ── */
.detail-block {
  margin-bottom: var(--space-4);
}

.block-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}

.block-text {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: var(--leading-relaxed);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

/* ── 责任分配 ── */
.liability-rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.liability-row {
  display: grid;
  grid-template-columns: 100px 1fr 90px;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.liability-role {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-primary);
}

.liability-bar {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.liability-bar-fill {
  height: 100%;
  background: var(--node-color, var(--primary));
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
}

.liability-pct {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
}

/* ── 报告导出按钮 ── */
.export-btn {
  width: 100%;
  margin-top: var(--space-4);
  justify-content: center;
}

/* ── 视频语义校验详情面板 ── */
.semantic-check-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.semantic-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.semantic-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  gap: var(--space-3);
}

.semantic-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  flex-shrink: 0;
}

.semantic-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
  text-align: right;
  word-break: break-word;
}

/* 双通道对比 */
.dual-channel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.channel-item {
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
}

.channel-detector {
  border-left: 3px solid #007AFF;
}

.channel-qwen {
  border-left: 3px solid #00C7BE;
}

.channel-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.channel-type {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.channel-conf {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.final-type {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border-left: 3px solid var(--node-color, var(--primary));
}

.final-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
}

.final-value {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
}

.final-value.is-unknown {
  color: #FF9500;
}

/* 系统结论 */
.conclusion-box {
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
}

.conclusion-box.has-conflict {
  background: rgba(255, 149, 0, 0.06);
  border-color: rgba(255, 149, 0, 0.3);
}

.conclusion-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px dashed var(--border-light);
  gap: var(--space-3);
}

.conclusion-row:last-child {
  border-bottom: none;
}

.conclusion-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  flex-shrink: 0;
}

.conclusion-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
  text-align: right;
  word-break: break-word;
}

.text-danger {
  color: #FF3B30 !important;
}

.text-success {
  color: #34C759 !important;
}

/* 追尾特征支持 */
.rear-end-box {
  padding: var(--space-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.rear-end-status {
  font-size: var(--text-sm);
  font-weight: 700;
  margin-bottom: 4px;
}

.rear-end-status.status-supported {
  color: #34C759;
}

.rear-end-status.status-partially_supported {
  color: #FF9500;
}

.rear-end-status.status-not_supported {
  color: #FF3B30;
}

.rear-end-score {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
}

.rear-end-reason {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
}

/* 原因/缺失列表 */
.reason-list {
  margin: 0;
  padding-left: 20px;
  list-style: disc;
}

.reason-list li {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  padding: 4px 0;
}

.reason-list.missing-list li {
  color: var(--text-tertiary);
}

/* 证据一致性 */
.consistency-box {
  padding: var(--space-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.consistency-score {
  font-size: var(--text-sm);
  font-weight: 700;
  margin-bottom: var(--space-2);
}

.consistency-score.level-high {
  color: #34C759;
}

.consistency-score.level-medium {
  color: #FF9500;
}

.consistency-score.level-low {
  color: #FF3B30;
}

.consistency-num {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  margin-left: 6px;
}

.consistency-sub {
  margin-top: var(--space-2);
}

.sub-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 4px;
}

/* 空状态提示 */
.empty-hint {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 8px;
}

/* ── 空状态文本 ── */
.empty-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
  text-align: center;
  padding: var(--space-8) 0;
}

/* 关键帧缩略图 */
.keyframe-thumb {
  margin-top: var(--space-3);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #1a1a1a;
  border: 1px solid var(--border-light);
}

.thumb-img {
  width: 100%;
  display: block;
  object-fit: cover;
  max-height: 240px;
  border-radius: var(--radius-md);
  transition: opacity 0.3s ease;
}

.thumb-fallback {
  display: block;
  padding: var(--space-4);
  text-align: center;
}

/* ── 响应式：小屏幕纵向排列 ── */
@media (max-width: 1024px) {
  .flowchart {
    flex-direction: column;
    align-items: stretch;
  }

  .flow-node {
    min-width: auto;
    width: 100%;
  }

  .flow-arrow {
    transform: rotate(90deg);
    padding: var(--space-1) 0;
  }

  .case-meta {
    flex-direction: column;
    gap: var(--space-2);
  }

  .selector-row {
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-2);
  }

  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 640px) {
  .detail-panel {
    width: 100vw;
  }

  .liability-row {
    grid-template-columns: 80px 1fr 80px;
    gap: var(--space-2);
  }
}
</style>
