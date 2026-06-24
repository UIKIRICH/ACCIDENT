<template>
  <div class="rule-graph-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">规则依据图谱</h1>
        <p class="page-subtitle">视频检测 → 语义校验 → 融合门控 → 事实 → 规则 → 责任 → 复核 的可解释推导链路</p>
      </div>
    </div>

    <!-- 顶部案件选择器 -->
    <div class="case-selector card-surface">
      <div class="selector-left">
        <span class="selector-label">选择案件</span>
        <select
          v-model="selectedCaseId"
          class="case-select"
          :disabled="loadingCases"
          @change="handleCaseChange"
        >
          <option value="" disabled>{{ loadingCases ? '加载案件中...' : '请选择案件' }}</option>
          <option v-for="c in cases" :key="c.caseId" :value="c.caseId">
            {{ c.caseId }} · {{ c.title }}
          </option>
        </select>
      </div>
      <div v-if="selectedCaseId" class="selector-right">
        <span class="case-meta-item">
          <span class="meta-label">事故类型</span>
          <span class="meta-value">{{ currentCaseMeta.accidentType || '—' }}</span>
        </span>
        <span class="case-meta-item">
          <span class="meta-label">发生地点</span>
          <span class="meta-value">{{ currentCaseMeta.location || '—' }}</span>
        </span>
        <span class="case-meta-item">
          <span class="meta-label">状态</span>
          <span class="meta-value">{{ currentCaseMeta.status || '—' }}</span>
        </span>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-state card-surface">
      <div class="loading-spinner"></div>
      <p class="loading-text">正在加载推导链路...</p>
    </div>

    <!-- 图谱主体 -->
    <div v-else-if="selectedCaseId" class="graph-wrapper card-surface">
      <!-- 流向图例 -->
      <div class="flow-legend">
        <div class="legend-item">
          <span class="legend-dot" style="background:#007AFF"></span>
          <span class="legend-text">视频检测</span>
        </div>
        <span class="legend-arrow">→</span>
        <div class="legend-item">
          <span class="legend-dot" style="background:#00C7BE"></span>
          <span class="legend-text">语义校验</span>
        </div>
        <span class="legend-arrow">→</span>
        <div class="legend-item">
          <span class="legend-dot" style="background:#AF52DE"></span>
          <span class="legend-text">融合门控</span>
        </div>
        <span class="legend-arrow">→</span>
        <div class="legend-item">
          <span class="legend-dot" style="background:#34C759"></span>
          <span class="legend-text">事实</span>
        </div>
        <span class="legend-arrow">→</span>
        <div class="legend-item">
          <span class="legend-dot" style="background:#FF9500"></span>
          <span class="legend-text">规则</span>
        </div>
        <span class="legend-arrow">→</span>
        <div class="legend-item">
          <span class="legend-dot" style="background:#5856D6"></span>
          <span class="legend-text">责任</span>
        </div>
        <span class="legend-arrow">→</span>
        <div class="legend-item">
          <span class="legend-dot" style="background:#FF3B30"></span>
          <span class="legend-text">复核</span>
        </div>
      </div>

      <!-- 7 列节点图谱 -->
      <div class="graph-container">
        <!-- 第 1 列：视频检测模型 -->
        <div class="graph-column detector">
          <div class="column-header" style="--col-color:#007AFF">
            <span class="column-dot"></span>
            <span class="column-title">视频检测</span>
            <span class="column-count">{{ fusedEvidence ? 1 : 0 }}</span>
          </div>
          <div class="column-body">
            <div
              v-if="fusedEvidence"
              class="node-card detector-node"
              :class="{ selected: isNodeSelected('detector', 0) }"
              @click="selectNode('detector', fusedEvidence, 0)"
            >
              <div class="node-tag">检测模型</div>
              <div class="node-title">{{ mapAccidentType(fusedEvidence.detector_output?.candidate_accident_type_from_detector) }}</div>
              <div class="node-desc">置信度 {{ formatConfidence(fusedEvidence.detector_output?.detector_type_confidence) }}</div>
              <div v-if="fusedEvidence.fusion_result?.rear_end_support" class="node-confidence">
                追尾支持 {{ formatConfidence(fusedEvidence.fusion_result.rear_end_support.score) }}
              </div>
            </div>
            <div v-else class="empty-node">暂无</div>
          </div>
        </div>

        <!-- 连线 1 -->
        <div class="graph-connector"><span class="connector-arrow">→</span></div>

        <!-- 第 2 列：千问语义校验 -->
        <div class="graph-column semantic">
          <div class="column-header" style="--col-color:#00C7BE">
            <span class="column-dot"></span>
            <span class="column-title">语义校验</span>
            <span class="column-count">{{ fusedEvidence?.qwen_semantic_check ? 1 : 0 }}</span>
          </div>
          <div class="column-body">
            <div
              v-if="fusedEvidence?.qwen_semantic_check"
              class="node-card semantic-node"
              :class="{ selected: isNodeSelected('semantic', 0) }"
              @click="selectNode('semantic', fusedEvidence, 0)"
            >
              <div class="node-tag">千问</div>
              <div class="node-title">{{ mapAccidentType(fusedEvidence.qwen_semantic_check.semantic_accident_type_from_qwen) }}</div>
              <div class="node-desc">{{ mapCameraView(fusedEvidence.camera_context?.camera_view) }}</div>
              <div class="node-confidence">
                置信度 {{ formatConfidence(fusedEvidence.qwen_semantic_check.semantic_confidence) }}
              </div>
            </div>
            <div v-else class="empty-node">暂无</div>
          </div>
        </div>

        <!-- 连线 2 -->
        <div class="graph-connector"><span class="connector-arrow">→</span></div>

        <!-- 第 3 列：证据融合门控 -->
        <div class="graph-column fusion">
          <div class="column-header" style="--col-color:#AF52DE">
            <span class="column-dot"></span>
            <span class="column-title">融合门控</span>
            <span class="column-count">{{ fusedEvidence?.fusion_result ? 1 : 0 }}</span>
          </div>
          <div class="column-body">
            <div
              v-if="fusedEvidence?.fusion_result"
              class="node-card fusion-node"
              :class="{ 'has-conflict': fusedEvidence.fusion_result.conflict_detected, selected: isNodeSelected('fusion', 0) }"
              @click="selectNode('fusion', fusedEvidence, 0)"
            >
              <div class="node-tag">融合</div>
              <div class="node-title">{{ mapAccidentType(fusedEvidence.fusion_result.accepted_accident_type) }}</div>
              <div class="node-desc">{{ mapFinalStatus(fusedEvidence.fusion_result.final_status) }}</div>
              <div class="node-confidence" :class="{ 'text-danger': fusedEvidence.fusion_result.manual_review_required }">
                {{ fusedEvidence.fusion_result.manual_review_required ? '需人工复核' : '可进入责任推理' }}
              </div>
            </div>
            <div v-else class="empty-node">暂无</div>
          </div>
        </div>

        <!-- 连线 3 -->
        <div class="graph-connector"><span class="connector-arrow">→</span></div>

        <!-- 第 4 列：事实 -->
        <div class="graph-column facts">
          <div class="column-header" style="--col-color:#34C759">
            <span class="column-dot"></span>
            <span class="column-title">事实</span>
            <span class="column-count">{{ facts.length }}</span>
          </div>
          <div class="column-body">
            <div
              v-for="(f, idx) in facts"
              :key="'fact-' + idx"
              class="node-card fact-node"
              :class="{ selected: isNodeSelected('fact', idx) }"
              @click="selectNode('fact', f, idx)"
            >
              <div class="node-tag">事实</div>
              <div class="node-title">{{ f.fact_type || '未分类事实' }}</div>
              <div class="node-desc">{{ f.fact_content || f.fact_value || '—' }}</div>
              <div v-if="f.confidence != null" class="node-confidence">
                置信度 {{ formatConfidence(f.confidence) }}
              </div>
            </div>
            <div v-if="facts.length === 0" class="empty-node">暂无</div>
          </div>
        </div>

        <!-- 连线 1 -->
        <div class="graph-connector"><span class="connector-arrow">→</span></div>

        <!-- 第 2 列：规则 -->
        <div class="graph-column rules">
          <div class="column-header" style="--col-color:#FF9500">
            <span class="column-dot"></span>
            <span class="column-title">规则</span>
            <span class="column-count">{{ matchedRules.length }}</span>
          </div>
          <div class="column-body">
            <div
              v-for="(r, idx) in matchedRules"
              :key="'rule-' + idx"
              class="node-card rule-node"
              :class="{ selected: isNodeSelected('rule', idx) }"
              @click="selectNode('rule', r, idx)"
            >
              <div class="node-tag">规则</div>
              <div class="node-title">{{ r.rule_name || r.rule_id || '未命名规则' }}</div>
              <div class="node-desc">{{ r.legal_basis || '—' }}</div>
              <div v-if="r.confidence != null" class="node-confidence">
                置信度 {{ formatConfidence(r.confidence) }}
              </div>
            </div>
            <div v-if="matchedRules.length === 0" class="empty-node">暂无</div>
          </div>
        </div>

        <!-- 连线 2 -->
        <div class="graph-connector"><span class="connector-arrow">→</span></div>

        <!-- 第 3 列：责任 -->
        <div class="graph-column liability">
          <div class="column-header" style="--col-color:#5856D6">
            <span class="column-dot"></span>
            <span class="column-title">责任</span>
            <span class="column-count">{{ liability ? 1 : 0 }}</span>
          </div>
          <div class="column-body">
            <div
              v-if="liability"
              class="node-card liability-node selected-only"
              :class="{ selected: isNodeSelected('liability', 0) }"
              @click="selectNode('liability', liability, 0)"
            >
              <div class="node-tag">责任</div>
              <div class="node-title">{{ liability.summary || '责任认定结果' }}</div>
              <div class="node-desc">
                {{ formatVehicles(liability.vehicles) || '—' }}
              </div>
              <div v-if="liability.confidence != null" class="node-confidence">
                置信度 {{ formatConfidence(liability.confidence) }}
              </div>
            </div>
            <div v-else class="empty-node">暂无</div>
          </div>
        </div>

        <!-- 连线 3 -->
        <div class="graph-connector"><span class="connector-arrow">→</span></div>

        <!-- 第 4 列：复核 -->
        <div class="graph-column reviews">
          <div class="column-header" style="--col-color:#FF3B30">
            <span class="column-dot"></span>
            <span class="column-title">复核</span>
            <span class="column-count">{{ reviews.length }}</span>
          </div>
          <div class="column-body">
            <div
              v-for="(rv, idx) in reviews"
              :key="'review-' + idx"
              class="node-card review-node"
              :class="{ selected: isNodeSelected('review', idx) }"
              @click="selectNode('review', rv, idx)"
            >
              <div class="node-tag">复核</div>
              <div class="node-title">{{ rv.reviewer || '复核人未知' }}</div>
              <div class="node-desc">{{ rv.final_result || '—' }}</div>
              <div v-if="rv.created_at" class="node-confidence">{{ rv.created_at }}</div>
            </div>
            <div v-if="reviews.length === 0" class="empty-node">暂无</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 未选择案件占位 -->
    <div v-else class="empty-state card-surface">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="11" cy="11" r="8"></circle>
          <path d="m21 21-4.35-4.35"></path>
        </svg>
      </div>
      <p class="empty-text">请在上方选择案件以查看推导链路</p>
    </div>

    <!-- 详情面板（右侧滑入） -->
    <transition name="slide">
      <div v-if="selectedNode" class="detail-panel">
        <div class="detail-header" :style="{ '--detail-color': detailColor }">
          <span class="detail-type">{{ detailTypeLabel }}</span>
          <button class="detail-close" @click="selectedNode = null">×</button>
        </div>
        <div class="detail-body">
          <!-- 视频检测模型详情 -->
          <template v-if="selectedNode.type === 'detector'">
            <div class="detail-row">
              <span class="detail-label">候选事故类型</span>
              <span class="detail-value">{{ mapAccidentType(selectedNode.data.detector_output?.candidate_accident_type_from_detector) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">检测置信度</span>
              <span class="detail-value">{{ formatConfidence(selectedNode.data.detector_output?.detector_type_confidence) }}</span>
            </div>
            <div v-if="selectedNode.data.fusion_result?.rear_end_support" class="detail-row">
              <span class="detail-label">追尾特征支持</span>
              <span class="detail-value">
                {{ mapRearEndStatus(selectedNode.data.fusion_result.rear_end_support.status) }}
                （评分 {{ selectedNode.data.fusion_result.rear_end_support.score }}）
              </span>
            </div>
            <div v-if="selectedNode.data.fusion_result?.rear_end_support?.reason" class="detail-row">
              <span class="detail-label">说明</span>
              <span class="detail-value">{{ selectedNode.data.fusion_result.rear_end_support.reason }}</span>
            </div>
            <div class="detail-tip">
              检测模型负责"看到了什么"，输出车辆目标、关键帧与事故类型候选，但不直接定责。
            </div>
          </template>

          <!-- 千问语义校验详情 -->
          <template v-else-if="selectedNode.type === 'semantic'">
            <div class="detail-row">
              <span class="detail-label">视角类型</span>
              <span class="detail-value">{{ mapCameraView(selectedNode.data.camera_context?.camera_view) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">自车状态</span>
              <span class="detail-value">{{ selectedNode.data.camera_context?.ego_vehicle_present ? '隐式参与' : '未参与' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">画面可见外部车辆数</span>
              <span class="detail-value">{{ selectedNode.data.camera_context?.visible_external_vehicle_count ?? '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">估计涉事车辆数</span>
              <span class="detail-value">{{ selectedNode.data.camera_context?.estimated_involved_vehicle_count ?? '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">外部车辆行为</span>
              <span class="detail-value">{{ mapBehavior(selectedNode.data.vehicle_evidence?.external_vehicle_behavior) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">语义事故类型</span>
              <span class="detail-value">{{ mapAccidentType(selectedNode.data.qwen_semantic_check?.semantic_accident_type_from_qwen) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">语义置信度</span>
              <span class="detail-value">{{ formatConfidence(selectedNode.data.qwen_semantic_check?.semantic_confidence) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">与检测模型冲突</span>
              <span class="detail-value" :class="{ 'text-danger': selectedNode.data.qwen_semantic_check?.conflict_with_detector }">
                {{ selectedNode.data.qwen_semantic_check?.conflict_with_detector ? '是' : '否' }}
              </span>
            </div>
            <div v-if="selectedNode.data.qwen_semantic_check?.conflict_reasons?.length" class="detail-list-block">
              <div class="detail-sub-label">冲突原因</div>
              <ul class="detail-reason-list">
                <li v-for="(r, i) in selectedNode.data.qwen_semantic_check.conflict_reasons" :key="i">{{ r }}</li>
              </ul>
            </div>
            <div v-if="selectedNode.data.qwen_semantic_check?.missing_evidence?.length" class="detail-list-block">
              <div class="detail-sub-label">缺失证据</div>
              <ul class="detail-reason-list">
                <li v-for="(m, i) in selectedNode.data.qwen_semantic_check.missing_evidence" :key="i">{{ m }}</li>
              </ul>
            </div>
            <div class="detail-tip">
              千问语义校验负责"这段视频在发生什么"，识别视角、自车隐式参与和车辆行为语义，不直接定责。
            </div>
          </template>

          <!-- 证据融合门控详情 -->
          <template v-else-if="selectedNode.type === 'fusion'">
            <div class="detail-row">
              <span class="detail-label">最终事故类型</span>
              <span class="detail-value" :class="{ 'text-warning': selectedNode.data.fusion_result?.accepted_accident_type === 'unknown' }">
                {{ mapAccidentType(selectedNode.data.fusion_result?.accepted_accident_type) }}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">系统状态</span>
              <span class="detail-value">{{ mapFinalStatus(selectedNode.data.fusion_result?.final_status) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">系统动作</span>
              <span class="detail-value">{{ mapSystemAction(selectedNode.data.fusion_result?.system_action) }}</span>
            </div>
            <div v-if="selectedNode.data.fusion_result?.status_reason" class="detail-row">
              <span class="detail-label">状态原因</span>
              <span class="detail-value">{{ selectedNode.data.fusion_result.status_reason }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">是否冲突</span>
              <span class="detail-value" :class="{ 'text-danger': selectedNode.data.fusion_result?.conflict_detected }">
                {{ selectedNode.data.fusion_result?.conflict_detected ? '存在冲突' : '无冲突' }}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">需人工复核</span>
              <span class="detail-value" :class="{ 'text-danger': selectedNode.data.fusion_result?.manual_review_required }">
                {{ selectedNode.data.fusion_result?.manual_review_required ? '是' : '否' }}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">可进入责任推理</span>
              <span class="detail-value" :class="{ 'text-success': selectedNode.data.fusion_result?.should_enter_liability_reasoning }">
                {{ selectedNode.data.fusion_result?.should_enter_liability_reasoning ? '是' : '否' }}
              </span>
            </div>
            <div v-if="selectedNode.data.fusion_result?.keyframe_video_consistency" class="detail-list-block">
              <div class="detail-sub-label">证据一致性</div>
              <div class="detail-row">
                <span class="detail-label">一致性评分</span>
                <span class="detail-value">
                  {{ mapConsistencyLevel(selectedNode.data.fusion_result.keyframe_video_consistency.level) }}
                  （{{ selectedNode.data.fusion_result.keyframe_video_consistency.score }}）
                </span>
              </div>
              <div v-if="selectedNode.data.fusion_result.keyframe_video_consistency.conflict_items?.length" class="detail-list-block">
                <div class="detail-sub-label">冲突项</div>
                <ul class="detail-reason-list">
                  <li v-for="(c, i) in selectedNode.data.fusion_result.keyframe_video_consistency.conflict_items" :key="i">{{ c }}</li>
                </ul>
              </div>
              <div v-if="selectedNode.data.fusion_result.keyframe_video_consistency.missing_items?.length" class="detail-list-block">
                <div class="detail-sub-label">缺失项</div>
                <ul class="detail-reason-list">
                  <li v-for="(m, i) in selectedNode.data.fusion_result.keyframe_video_consistency.missing_items" :key="i">{{ m }}</li>
                </ul>
              </div>
            </div>
            <div class="detail-tip">
              融合层负责"这些证据能不能进入责任推理"，根据规则门控决定是否采纳、修正或转人工复核。
            </div>
          </template>

          <!-- 事实详情 -->
          <template v-else-if="selectedNode.type === 'fact'">
            <div class="detail-row">
              <span class="detail-label">事实类型</span>
              <span class="detail-value">{{ selectedNode.data.fact_type || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">事实内容</span>
              <span class="detail-value">{{ selectedNode.data.fact_content || selectedNode.data.fact_value || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">置信度</span>
              <span class="detail-value">{{ formatConfidence(selectedNode.data.confidence) }}</span>
            </div>
            <div v-if="selectedNode.data.source_type" class="detail-row">
              <span class="detail-label">来源</span>
              <span class="detail-value">{{ selectedNode.data.source_type }}</span>
            </div>
          </template>

          <!-- 规则详情 -->
          <template v-else-if="selectedNode.type === 'rule'">
            <div class="detail-row">
              <span class="detail-label">规则编号</span>
              <span class="detail-value">{{ selectedNode.data.rule_id || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">规则名称</span>
              <span class="detail-value">{{ selectedNode.data.rule_name || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">法律依据</span>
              <span class="detail-value">{{ selectedNode.data.legal_basis || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">触发条件</span>
              <span class="detail-value">{{ selectedNode.data.trigger_condition || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">推理说明</span>
              <span class="detail-value">{{ selectedNode.data.trigger_reason || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">置信度</span>
              <span class="detail-value">{{ formatConfidence(selectedNode.data.confidence) }}</span>
            </div>
          </template>

          <!-- 责任详情 -->
          <template v-else-if="selectedNode.type === 'liability'">
            <div class="detail-row">
              <span class="detail-label">责任摘要</span>
              <span class="detail-value">{{ selectedNode.data.summary || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">责任比例</span>
              <span class="detail-value">{{ formatVehicles(selectedNode.data.vehicles) || '—' }}</span>
            </div>
            <div v-if="selectedNode.data.vehicles && selectedNode.data.vehicles.length" class="detail-vehicles">
              <div v-for="(v, i) in selectedNode.data.vehicles" :key="i" class="vehicle-bar">
                <span class="vehicle-name">{{ v.role || v.vehicle_type || v.vehicleType || ('车辆' + (i + 1)) }}</span>
                <div class="vehicle-progress">
                  <div
                    class="vehicle-progress-inner"
                    :style="{ width: (v.percentage || v.ratio || 0) + '%' }"
                  ></div>
                </div>
                <span class="vehicle-percent">{{ v.percentage || v.ratio || 0 }}%</span>
              </div>
            </div>
            <div class="detail-row">
              <span class="detail-label">置信度</span>
              <span class="detail-value">{{ formatConfidence(selectedNode.data.confidence) }}</span>
            </div>
          </template>

          <!-- 复核详情 -->
          <template v-else-if="selectedNode.type === 'review'">
            <div class="detail-row">
              <span class="detail-label">复核人</span>
              <span class="detail-value">{{ selectedNode.data.reviewer || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">最终结果</span>
              <span class="detail-value">{{ selectedNode.data.final_result || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">复核意见</span>
              <span class="detail-value">{{ selectedNode.data.review_comment || '—' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">复核时间</span>
              <span class="detail-value">{{ selectedNode.data.created_at || '—' }}</span>
            </div>
          </template>
        </div>
      </div>
    </transition>

    <!-- 遮罩层（点击关闭详情） -->
    <transition name="fade">
      <div v-if="selectedNode" class="detail-mask" @click="selectedNode = null"></div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { CasesAPI, StatsAPI } from '../api/index.js'
import { notify } from '../composables/useToast'
import { useAccidentFlow } from '../stores/useAccidentFlow'

const router = useRouter()
const route = useRoute()
const { getCurrentCase, isValidCaseId, setCurrentCase } = useAccidentFlow()

// 案件列表与选择
const cases = ref([])
const selectedCaseId = ref('')
const loadingCases = ref(false)

// 各列节点数据
const facts = ref([])
const matchedRules = ref([])
const liability = ref(null)
const reviews = ref([])
// 视频语义校验 + 证据融合 数据
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

function mapCameraView(val) { return CAMERA_VIEW_MAP[val] || val || '—' }
function mapBehavior(val) { return BEHAVIOR_MAP[val] || val || '—' }
function mapAccidentType(val) { return ACCIDENT_TYPE_MAP[val] || val || '—' }
function mapFinalStatus(val) { return FINAL_STATUS_MAP[val] || val || '—' }
function mapSystemAction(val) { return SYSTEM_ACTION_MAP[val] || val || '—' }
function mapRearEndStatus(val) { return REAR_END_STATUS_MAP[val] || val || '—' }
function mapConsistencyLevel(val) { return CONSISTENCY_LEVEL_MAP[val] || val || '—' }

// 加载与选中状态
const loading = ref(false)
const selectedNode = ref(null) // { type, data, index }

// 当前案件元信息
const currentCaseMeta = computed(() => {
  const c = cases.value.find(item => item.caseId === selectedCaseId.value)
  return c || {}
})

// 详情面板颜色与标题
const detailColor = computed(() => {
  const map = {
    detector: '#007AFF',
    semantic: '#00C7BE',
    fusion: '#AF52DE',
    fact: '#34C759',
    rule: '#FF9500',
    liability: '#5856D6',
    review: '#FF3B30'
  }
  return map[selectedNode.value?.type] || '#007AFF'
})

const detailTypeLabel = computed(() => {
  const map = {
    detector: '视频检测节点',
    semantic: '语义校验节点',
    fusion: '融合门控节点',
    fact: '事实节点',
    rule: '规则节点',
    liability: '责任节点',
    review: '复核节点'
  }
  return map[selectedNode.value?.type] || '节点详情'
})

// 格式化置信度（兼容 0~1 与 0~100）
function formatConfidence(val) {
  if (val == null || val === '') return '—'
  const num = Number(val)
  if (isNaN(num)) return String(val)
  return (num <= 1 ? num * 100 : num).toFixed(1) + '%'
}

// 格式化车辆责任比例摘要
function formatVehicles(vehicles) {
  if (!vehicles || !vehicles.length) return ''
  return vehicles.map(v => {
    const name = v.role || v.vehicle_type || v.vehicleType || '车辆'
    const pct = v.percentage != null ? v.percentage : (v.ratio != null ? v.ratio : '')
    return pct !== '' ? `${name} ${pct}%` : name
  }).join('，')
}

// 判断节点是否被选中
function isNodeSelected(type, index) {
  return selectedNode.value && selectedNode.value.type === type && selectedNode.value.index === index
}

// 点击节点显示详情
function selectNode(type, data, index) {
  selectedNode.value = { type, data, index }
}

// 加载案件列表
async function loadCases() {
  loadingCases.value = true
  try {
    const result = await StatsAPI.getHistoryCases({ limit: 100 })
    if (result.success && Array.isArray(result.data)) {
      cases.value = result.data.map(c => ({
        caseId: c.id,
        title: c.title || c.accident_type || '未命名案件',
        accidentType: c.accident_type || '',
        location: c.location || '',
        status: c.status || ''
      }))
    } else {
      cases.value = []
    }
  } catch (err) {
    console.warn('获取案件列表失败:', err)
    cases.value = []
    notify({ title: '加载失败', message: '案件列表获取失败', type: 'error' })
  } finally {
    loadingCases.value = false
  }
}

// 从 liability-latest 原始数据中提取责任信息（兼容多种结构）
function extractLiability(data) {
  if (!data) return null
  // 直接字段结构：{ summary, details: { vehicles, confidence } }
  if (data.summary) {
    const details = data.details || {}
    return {
      summary: data.summary,
      vehicles: details.vehicles || data.vehicles || [],
      confidence: details.confidence != null ? details.confidence : data.confidence
    }
  }
  // AnalysisVersion 行结构：含 suggestion_json
  if (data.suggestion_json) {
    try {
      const sug = typeof data.suggestion_json === 'string'
        ? JSON.parse(data.suggestion_json)
        : data.suggestion_json
      return {
        summary: sug.summary || sug.liability_suggestion || '责任分析结果',
        vehicles: sug.vehicles || sug.vehicle_liabilities || sug.details?.vehicles || [],
        confidence: sug.confidence != null ? sug.confidence : sug.confidence_score
      }
    } catch {
      // 解析失败则走兜底
    }
  }
  // 兜底
  return {
    summary: data.summary || data.liability_suggestion || '责任分析结果',
    vehicles: data.vehicles || data.vehicle_liabilities || [],
    confidence: data.confidence
  }
}

// 选中案件后并行加载所有数据
async function loadGraphData(caseId) {
  loading.value = true
  selectedNode.value = null
  // 重置数据
  facts.value = []
  matchedRules.value = []
  liability.value = null
  reviews.value = []
  fusedEvidence.value = null

  try {
    // 并行调用 5 个接口（新增 getFusedEvidence）
    const [factsRes, rulesRes, liabilityRes, reviewsRes, fusedRes] = await Promise.all([
      CasesAPI.getFacts(caseId).catch(err => ({ _error: err.message })),
      CasesAPI.getMatchedRules(caseId).catch(err => ({ _error: err.message })),
      CasesAPI.getLiabilityLatest(caseId).catch(err => ({ _error: err.message })),
      CasesAPI.getReviews(caseId).catch(err => ({ _error: err.message })),
      CasesAPI.getFusedEvidence(caseId).catch(err => ({ _error: err.message }))
    ])

    // 事实节点
    if (factsRes && factsRes.success && Array.isArray(factsRes.data)) {
      facts.value = factsRes.data
    }

    // 规则节点
    if (rulesRes && rulesRes.success && Array.isArray(rulesRes.data)) {
      matchedRules.value = rulesRes.data
    }

    // 责任节点（单个）
    if (liabilityRes && liabilityRes.success && liabilityRes.data) {
      liability.value = extractLiability(liabilityRes.data)
    }

    // 复核节点
    if (reviewsRes && reviewsRes.success && Array.isArray(reviewsRes.data)) {
      reviews.value = reviewsRes.data
    }

    // 视频语义校验 + 证据融合数据
    if (fusedRes && fusedRes.success) {
      const packet = fusedRes.data?.fused_evidence_packet
      // 后端在无数据时返回空对象 {}，这里过滤掉空包
      fusedEvidence.value = (packet && Object.keys(packet).length > 0) ? packet : null
    }

    // 全部为空时提示
    if (!facts.value.length && !matchedRules.value.length && !liability.value && !reviews.value.length && !fusedEvidence.value) {
      notify({ title: '提示', message: '该案件暂无推导链路数据', type: 'warning' })
    }
  } catch (err) {
    console.warn('加载图谱数据失败:', err)
    notify({ title: '加载失败', message: '推导链路数据获取失败', type: 'error' })
  } finally {
    loading.value = false
  }
}

// 案件选择变化
function handleCaseChange() {
  if (!selectedCaseId.value) return
  // 同步到全局 store
  setCurrentCase(selectedCaseId.value)
  loadGraphData(selectedCaseId.value)
}

onMounted(async () => {
  await loadCases()
  // 优先使用 URL query 中的 caseId，其次 store 中的当前案件
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
  if (initialId && cases.value.some(c => c.caseId === initialId)) {
    selectedCaseId.value = initialId
    loadGraphData(initialId)
  }
})
</script>

<style scoped>
/* ── 页面容器 ── */
.rule-graph-page {
  padding: 0;
  animation: pageIn 0.4s var(--ease-default);
}

@keyframes pageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-header {
  margin-bottom: var(--space-6);
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

/* ── 通用卡片 ── */
.card-surface {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  padding: var(--space-6);
  transition: box-shadow var(--transition-normal);
}

/* ── 案件选择器 ── */
.case-selector {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-6);
  margin-bottom: var(--space-6);
  flex-wrap: wrap;
}

.selector-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.selector-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
}

.case-select {
  min-width: 320px;
  padding: 10px 14px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: var(--bg-secondary);
  outline: none;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.case-select:focus {
  border-color: #007AFF;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.15);
  background: var(--bg-primary);
}

.case-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.selector-right {
  display: flex;
  gap: var(--space-6);
  flex-wrap: wrap;
}

.case-meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.meta-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.meta-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 600;
}

/* ── 加载状态 ── */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px var(--space-6);
  gap: var(--space-4);
}

.loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border-light);
  border-top-color: #007AFF;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

/* ── 图谱容器 ── */
.graph-wrapper {
  background: #F2F2F7;
}

/* ── 流向图例 ── */
.flow-legend {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-6);
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border-light);
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-text {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.legend-arrow {
  color: var(--text-muted);
  font-size: var(--text-base);
  font-weight: 700;
}

/* ── 7 列图谱布局 ── */
.graph-container {
  display: grid;
  grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr auto 1fr auto 1fr auto 1fr;
  gap: 0;
  align-items: stretch;
}

.graph-column {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ── 列标题 ── */
.column-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  border-left: 4px solid var(--col-color, #007AFF);
}

.column-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--col-color, #007AFF);
  flex-shrink: 0;
}

.column-title {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  flex: 1;
}

.column-count {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

/* ── 列主体 ── */
.column-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0 var(--space-2);
}

/* ── 节点卡片 ── */
.node-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: var(--space-4);
  cursor: pointer;
  transition: all var(--transition-fast);
  border-left: 4px solid transparent;
}

.node-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* 选中高亮：边框加粗 + 阴影加深 */
.node-card.selected {
  border-width: 2px;
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

/* 各列节点配色（浅色背景 + 对应色边框） */
.detector-node {
  background: rgba(0, 122, 255, 0.08);
  border-left-color: #007AFF;
}
.detector-node.selected {
  border-color: #007AFF;
  background: rgba(0, 122, 255, 0.14);
}

.semantic-node {
  background: rgba(0, 199, 190, 0.08);
  border-left-color: #00C7BE;
}
.semantic-node.selected {
  border-color: #00C7BE;
  background: rgba(0, 199, 190, 0.14);
}

.fusion-node {
  background: rgba(175, 82, 222, 0.08);
  border-left-color: #AF52DE;
}
.fusion-node.selected {
  border-color: #AF52DE;
  background: rgba(175, 82, 222, 0.14);
}
.fusion-node.has-conflict {
  background: rgba(255, 149, 0, 0.10);
  border-left-color: #FF9500;
}

.fact-node {
  background: rgba(52, 199, 89, 0.08);
  border-left-color: #34C759;
}
.fact-node.selected {
  border-color: #34C759;
  background: rgba(52, 199, 89, 0.14);
}

.rule-node {
  background: rgba(255, 149, 0, 0.08);
  border-left-color: #FF9500;
}
.rule-node.selected {
  border-color: #FF9500;
  background: rgba(255, 149, 0, 0.14);
}

.liability-node {
  background: rgba(88, 86, 214, 0.08);
  border-left-color: #5856D6;
}
.liability-node.selected {
  border-color: #5856D6;
  background: rgba(88, 86, 214, 0.14);
}

.review-node {
  background: rgba(255, 59, 48, 0.08);
  border-left-color: #FF3B30;
}
.review-node.selected {
  border-color: #FF3B30;
  background: rgba(255, 59, 48, 0.14);
}

.node-tag {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.node-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
  line-height: var(--leading-snug);
  word-break: break-word;
}

.node-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: var(--leading-snug);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.node-confidence {
  margin-top: var(--space-2);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
}

/* ── 空节点 ── */
.empty-node {
  padding: var(--space-6) var(--space-4);
  text-align: center;
  color: var(--text-muted);
  font-size: var(--text-sm);
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px dashed var(--border-medium);
}

/* ── 列间连线 ── */
.graph-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  min-width: 32px;
}

.connector-arrow {
  font-size: 22px;
  font-weight: 800;
  color: var(--text-muted);
  line-height: 1;
  opacity: 0.7;
}

/* ── 空状态 ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px var(--space-6);
  gap: var(--space-4);
}

.empty-icon {
  width: 56px;
  height: 56px;
  color: var(--text-muted);
  opacity: 0.5;
}

.empty-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

/* ── 详情面板（右侧滑入） ── */
.detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 420px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-primary);
  box-shadow: var(--shadow-2xl);
  z-index: 1001;
  display: flex;
  flex-direction: column;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border-light);
  border-left: 4px solid var(--detail-color, #007AFF);
}

.detail-type {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.detail-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 20px;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
}

.detail-close:hover {
  background: var(--danger-light);
  color: var(--danger-500);
}

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.detail-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.detail-value {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 500;
  line-height: var(--leading-relaxed);
  word-break: break-word;
}

/* 详情面板辅助色（冲突/警告/成功） */
.text-danger {
  color: #FF3B30 !important;
  font-weight: 600;
}

.text-warning {
  color: #FF9500 !important;
  font-weight: 600;
}

.text-success {
  color: #34C759 !important;
  font-weight: 600;
}

/* 详情提示框 */
.detail-tip {
  margin-top: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: rgba(0, 122, 255, 0.06);
  border-left: 3px solid #007AFF;
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
}

/* 详情子列表块 */
.detail-list-block {
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.detail-sub-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}

.detail-reason-list {
  margin: 0;
  padding-left: 20px;
  list-style: disc;
}

.detail-reason-list li {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  padding: 3px 0;
  word-break: break-word;
}

/* 责任车辆进度条 */
.detail-vehicles {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.vehicle-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.vehicle-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 60px;
}

.vehicle-progress {
  flex: 1;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.vehicle-progress-inner {
  height: 100%;
  background: linear-gradient(90deg, #5856D6, #8b5cf6);
  border-radius: var(--radius-full);
  transition: width 0.4s var(--ease-default);
}

.vehicle-percent {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
  min-width: 40px;
  text-align: right;
}

/* ── 遮罩层 ── */
.detail-mask {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(15, 23, 42, 0.4);
  z-index: 1000;
}

/* ── 过渡动画 ── */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s var(--ease-default);
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s var(--ease-default);
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ── 响应式：小屏幕 1 列纵向排列 ── */
@media (max-width: 1024px) {
  .graph-container {
    grid-template-columns: 1fr;
    gap: var(--space-2);
  }

  .graph-column {
    width: 100%;
  }

  /* 连线改为向下箭头 */
  .graph-connector {
    padding: var(--space-2) 0;
  }
  .connector-arrow {
    transform: rotate(90deg);
  }

  .column-body {
    padding: 0;
  }
}

@media (max-width: 768px) {
  .case-selector {
    flex-direction: column;
    align-items: stretch;
  }
  .case-select {
    min-width: 0;
    width: 100%;
  }
  .selector-right {
    gap: var(--space-4);
  }
  .detail-panel {
    width: 100vw;
    max-width: 100vw;
  }
}
</style>
