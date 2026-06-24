import { reactive, computed } from 'vue'
import { getRules, saveRules, nextRuleId } from '../composables/usePlatformData'

// 日志系统
const dataLogs = []

// 日志级别
const LOG_LEVELS = {
  INFO: 'INFO',
  WARNING: 'WARNING',
  ERROR: 'ERROR',
  DEBUG: 'DEBUG'
}

// 记录日志函数
function logMessage(level, module, action, message, details = null) {
  const logEntry = {
    timestamp: new Date().toLocaleString(),
    level,
    module,
    action,
    message,
    details,
    caseId: state.caseId
  }
  dataLogs.push(logEntry)
  // console.log(`[${level}] ${module} - ${action}: ${message}`, details)
  // 保留最近50条日志
  if (dataLogs.length > 50) {
    dataLogs.shift()
  }
}

// 数据验证函数
function validateData(module, data, schema) {
  const errors = []
  for (const [field, rules] of Object.entries(schema)) {
    if (rules.required && (data[field] === undefined || data[field] === null || data[field] === '')) {
      errors.push(`${field}: 此字段为必填项`)
    }
    if (rules.type && typeof data[field] !== rules.type && data[field] !== undefined) {
      errors.push(`${field}: 类型错误，应为${rules.type}`)
    }
    if (rules.enum && data[field] && !rules.enum.includes(data[field])) {
      errors.push(`${field}: 值不在允许范围内`)
    }
  }
  if (errors.length > 0) {
    logMessage(LOG_LEVELS.WARNING, module, 'VALIDATION', '数据验证失败', errors)
    return { valid: false, errors }
  }
  return { valid: true }
}

// 数据同步函数
async function syncData(module, action, data) {
  try {
    logMessage(LOG_LEVELS.INFO, module, action, '开始数据同步', data)
    // 模拟异步同步
    await new Promise(resolve => setTimeout(resolve, 100))
    logMessage(LOG_LEVELS.INFO, module, action, '数据同步成功')
    return { success: true }
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, module, action, '数据同步失败', error)
    return { success: false, error: error.message }
  }
}

// 当前案件 ID 持久化 key
const CURRENT_CASE_STORAGE_KEY = 'accident-platform-current-case-id'

// 初始状态
const initialState = () => ({
  // caseId 不再前端随机生成，由后端创建案件后返回；初始为 null
  caseId: null,
  step: 'overview',
  form: {
    time: '',
    location: '',
    accidentType: '',
    vehicleType: 'A车 / B车',
    description: '',
    note: '',
    weather: '',
    roadEnv: '',
    fileName: '',
    fileType: '',
    fileSize: '',
    duration: '',
    images: [],
    imageFiles: [],
    videoFileName: '',
    videoFile: null,
    vehicles: [
      { key: 'A', vehicleType: '小型轿车', plate: '', role: '前车' },
      { key: 'B', vehicleType: '小型轿车', plate: '', role: '后车' }
    ]
  },
  analysis: {
    selectedFrame: '',
    selectedFrameInfo: null,
    keyframes: [],
    confidence: null,
    evidenceIntegrity: null,
    riskLevel: null,
    vehicleLiabilities: [],
    analysisResult: null,
    reasoningText: '',
    matchedRules: [],
    // Dify 相关字段
    difyResult: null,
    difyOutput: '',
    difyLegalClues: [],
    difyAnalysisText: '',
    // 视频语义校验（千问）+ 证据融合 相关字段
    fusedEvidence: null,        // 融合证据包完整数据（fused_evidence_packet）
    semanticCheck: null,        // 千问语义校验结果（快捷访问 = fusedEvidence.qwen_semantic_check）
    fusionResult: null,         // 融合结果（快捷访问 = fusedEvidence.fusion_result）
    cameraContext: null         // 视角上下文（快捷访问 = fusedEvidence.camera_context）
  },
  recommendation: {
    summary: '待生成责任建议',
    ratio: '--',
    hitRules: ['规则待匹配', '规则待匹配', '规则待匹配'],
    vehicleLiabilities: [],
    riskAssessment: null,
    suggestions: []
  },
  ruleBasis: {
    selectedRules: [],
    searchQuery: '',
    selectedCategory: '全部',
    appliedRules: [],
    legalBasis: '',
    confirmed: false,
    confirmedAt: null
  },
  manualReview: {
    decision: '确认系统建议',
    note: '',
    submitted: false,
    reviewer: '',
    reviewedAt: null,
    reviewHistory: [],
    adjustments: {
      modifiedLiabilities: [],
      modifiedConfidence: null,
      modifiedRules: []
    }
  },
  ruleLibrary: {
    rules: [
      {
        id: 'R-001',
        name: '后车未保持安全距离',
        type: '追尾事故',
        scene: '同向行驶',
        content: '后车与前车的距离不足安全距离（至少3秒车距），造成追尾事故，后车负全部责任。',
        status: '启用'
      },
      {
        id: 'R-002',
        name: '变道未打转向灯',
        type: '变道事故',
        scene: '车道变更',
        content: '变更车道时未提前开启转向灯，影响其他车辆正常行驶，变道车辆负主要责任。',
        status: '启用'
      },
      {
        id: 'R-003',
        name: '闯红灯行为',
        type: '路口事故',
        scene: '交叉路口',
        content: '违反交通信号灯指示，闯红灯造成事故，闯红灯车辆负全部责任。',
        status: '启用'
      },
      {
        id: 'R-004',
        name: '倒车未观察',
        type: '倒车事故',
        scene: '停车场/倒车',
        content: '倒车时未仔细观察后方情况，造成碰撞事故，倒车方负全部责任。',
        status: '启用'
      }
    ],
    loading: false
  },
  archivedCases: [
    {
      caseId: 'ACC-20240415-001',
      title: '追尾碰撞事故',
      location: '北京市朝阳区建国路58号',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-04-15 16:30:00',
      note: '后车未保持安全距离，车速过快，负主要责任',
      conclusion: '责任认定：后车全责'
    },
    {
      caseId: 'ACC-20240412-002',
      title: '变道刮擦事故',
      location: '上海市浦东新区张江路28号',
      status: '待复核',
      priority: '高优先级',
      archivedAt: '2024-04-12 11:45:00',
      note: '变道车辆未打转向灯，影响正常行驶车辆',
      conclusion: '责任认定：变道车辆主责'
    },
    {
      caseId: 'ACC-20240408-003',
      title: '十字路口相撞事故',
      location: '广州市天河区天河路150号',
      status: '待分析',
      priority: '高优先级',
      archivedAt: '2024-04-08 19:20:00',
      note: '双方均有抢灯行为，需要进一步查看视频证据',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240405-004',
      title: '倒车碰撞事故',
      location: '深圳市南山区科技园南路',
      status: '已完成',
      priority: '低优先级',
      archivedAt: '2024-04-05 09:15:00',
      note: '倒车时未观察后方情况',
      conclusion: '责任认定：倒车方全责'
    },
    {
      caseId: 'ACC-20240401-005',
      title: '闯红灯事故',
      location: '杭州市西湖区文三路100号',
      status: '待复核',
      priority: '高优先级',
      archivedAt: '2024-04-01 14:40:00',
      note: '有监控录像为证，但当事人提出申诉',
      conclusion: '责任认定：闯红灯方全责'
    },
    {
      caseId: 'ACC-20240328-006',
      title: '行人横穿马路',
      location: '成都市武侯区人民南路四段',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-03-28 17:25:00',
      note: '行人突然从路边冲出，机动车避让不及',
      conclusion: '责任认定：行人主责，机动车次责'
    },
    {
      caseId: 'ACC-20240325-007',
      title: '夜间会车未关远光灯',
      location: '西安市雁塔区南三环辅道',
      status: '待分析',
      priority: '中优先级',
      archivedAt: '2024-03-25 21:10:00',
      note: '对方车辆一直开远光灯，造成我方视野受限',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240320-008',
      title: '路边开门事故',
      location: '武汉市江汉区解放大道',
      status: '已完成',
      priority: '低优先级',
      archivedAt: '2024-03-20 13:35:00',
      note: '乘客下车时开门未观察后方，碰撞到电动车',
      conclusion: '责任认定：开门方全责'
    },
    {
      caseId: 'ACC-20240318-009',
      title: '弯道超车事故',
      location: '重庆市渝北区金开大道',
      status: '待复核',
      priority: '高优先级',
      archivedAt: '2024-03-18 08:50:00',
      note: '在弯道处强行超车，与对向车辆发生碰撞',
      conclusion: '责任认定：超车方全责'
    },
    {
      caseId: 'ACC-20240315-010',
      title: '雨天路滑失控',
      location: '南京市鼓楼区中山北路',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-03-15 10:20:00',
      note: '雨天车速过快，车辆失控撞到护栏',
      conclusion: '责任认定：单方事故，驾驶人全责'
    },
    {
      caseId: 'ACC-20240312-011',
      title: '摩托车与汽车相撞',
      location: '苏州市工业园区金鸡湖大道',
      status: '待分析',
      priority: '高优先级',
      archivedAt: '2024-03-12 16:40:00',
      note: '摩托车在机动车道行驶，与变道汽车碰撞',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240308-012',
      title: '疲劳驾驶追尾',
      location: '天津市和平区南京路',
      status: '已完成',
      priority: '低优先级',
      archivedAt: '2024-03-08 09:15:00',
      note: '司机连续驾驶4小时以上，未保持注意力',
      conclusion: '责任认定：后车全责'
    },
    {
      caseId: 'ACC-20240305-013',
      title: '十字路口抢黄灯',
      location: '青岛市市南区香港中路',
      status: '待复核',
      priority: '中优先级',
      archivedAt: '2024-03-05 18:30:00',
      note: '双方都抢黄灯，在路口中间相撞',
      conclusion: '责任认定：同等责任'
    },
    {
      caseId: 'ACC-20240302-014',
      title: '货车超载追尾',
      location: '大连市甘井子区华北路',
      status: '已完成',
      priority: '高优先级',
      archivedAt: '2024-03-02 14:55:00',
      note: '货车严重超载，制动距离不足导致追尾',
      conclusion: '责任认定：货车全责'
    },
    {
      caseId: 'ACC-20240228-015',
      title: '电动车逆行相撞',
      location: '宁波市鄞州区天童北路',
      status: '待分析',
      priority: '中优先级',
      archivedAt: '2024-02-28 11:20:00',
      note: '电动车在非机动车道逆向行驶，与正常行驶电动车相撞',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240225-016',
      title: '路口不礼让行人',
      location: '福州市鼓楼区五四路',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-02-25 15:30:00',
      note: '机动车在人行横道未停车让行，导致行人受伤',
      conclusion: '责任认定：机动车全责'
    },
    {
      caseId: 'ACC-20240222-017',
      title: '不按规定车道行驶',
      location: '厦门市思明区厦禾路',
      status: '待复核',
      priority: '中优先级',
      archivedAt: '2024-02-22 10:15:00',
      note: '机动车在非机动车道内行驶，与非机动车发生碰撞',
      conclusion: '责任认定：机动车主责'
    },
    {
      caseId: 'ACC-20240220-018',
      title: '违法掉头',
      location: '济南市历下区经十路',
      status: '已完成',
      priority: '低优先级',
      archivedAt: '2024-02-20 09:45:00',
      note: '在禁止掉头路段违法掉头，与正常行驶车辆相撞',
      conclusion: '责任认定：掉头车辆全责'
    },
    {
      caseId: 'ACC-20240218-019',
      title: '违反信号灯通行',
      location: '郑州市二七区中原路',
      status: '待分析',
      priority: '高优先级',
      archivedAt: '2024-02-18 17:20:00',
      note: '车辆违反信号灯通行，与其他方向车辆相撞',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240215-020',
      title: '逆行行驶',
      location: '合肥市蜀山区长江西路',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-02-15 14:10:00',
      note: '机动车逆向行驶，与对向正常行驶车辆相撞',
      conclusion: '责任认定：逆行车辆全责'
    },
    {
      caseId: 'ACC-20240212-021',
      title: '违法停车',
      location: '南昌市东湖区八一大道',
      status: '待复核',
      priority: '低优先级',
      archivedAt: '2024-02-12 11:30:00',
      note: '违法停车在道路中央，被后方车辆追尾',
      conclusion: '责任认定：违法停车方主责'
    },
    {
      caseId: 'ACC-20240210-022',
      title: '跟车过近',
      location: '长沙市天心区芙蓉中路',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-02-10 16:45:00',
      note: '后车跟车距离过近，前车紧急制动导致追尾',
      conclusion: '责任认定：后车全责'
    },
    {
      caseId: 'ACC-20240208-023',
      title: '违法超车',
      location: '南宁市青秀区民族大道',
      status: '待分析',
      priority: '高优先级',
      archivedAt: '2024-02-08 08:30:00',
      note: '在禁止超车路段超车，与对向车辆相撞',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240205-024',
      title: '不按规定会车',
      location: '海口市龙华区龙昆南路',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-02-05 13:20:00',
      note: '会车时未减速靠右，与对向车辆发生刮擦',
      conclusion: '责任认定：同等责任'
    },
    {
      caseId: 'ACC-20240202-025',
      title: '车辆故障未设警示',
      location: '贵阳市云岩区中华北路',
      status: '待复核',
      priority: '高优先级',
      archivedAt: '2024-02-02 09:50:00',
      note: '车辆故障停在道路中央，未设置警示标志，被追尾',
      conclusion: '责任认定：故障车辆主责'
    },
    {
      caseId: 'ACC-20240130-026',
      title: '违法变更车道',
      location: '昆明市五华区东风西路',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-01-30 15:15:00',
      note: '连续变更两条车道，与后方车辆发生碰撞',
      conclusion: '责任认定：变道车辆全责'
    },
    {
      caseId: 'ACC-20240128-027',
      title: '不避让执行任务的车辆',
      location: '西安市雁塔区长安南路',
      status: '待分析',
      priority: '高优先级',
      archivedAt: '2024-01-28 11:40:00',
      note: '未避让执行紧急任务的救护车，导致延误',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240125-028',
      title: '违反禁止标线指示',
      location: '兰州市城关区庆阳路',
      status: '已完成',
      priority: '低优先级',
      archivedAt: '2024-01-25 14:25:00',
      note: '车辆跨越双黄线行驶，与对向车辆相撞',
      conclusion: '责任认定：跨越标线车辆全责'
    },
    {
      caseId: 'ACC-20240122-029',
      title: '超载超限运输',
      location: '西宁市城东区东关大街',
      status: '待复核',
      priority: '高优先级',
      archivedAt: '2024-01-22 10:10:00',
      note: '货车超载运输，导致车辆失控侧翻',
      conclusion: '责任认定：超载车辆全责'
    },
    {
      caseId: 'ACC-20240120-030',
      title: '违法装载货物',
      location: '银川市兴庆区解放西街',
      status: '已完成',
      priority: '中优先级',
      archivedAt: '2024-01-20 16:30:00',
      note: '货物装载超限，脱落砸到后方车辆',
      conclusion: '责任认定：装载车辆全责'
    },
    {
      caseId: 'ACC-20240118-031',
      title: '疲劳驾驶',
      location: '乌鲁木齐市天山区中山路',
      status: '待分析',
      priority: '高优先级',
      archivedAt: '2024-01-18 08:45:00',
      note: '长途驾驶疲劳，车辆失控撞到护栏',
      conclusion: '责任认定：待分析'
    },
    {
      caseId: 'ACC-20240115-032',
      title: '酒后驾驶',
      location: '拉萨市城关区北京中路',
      status: '已完成',
      priority: '高优先级',
      archivedAt: '2024-01-15 21:20:00',
      note: '驾驶员酒后驾驶，与正常行驶车辆相撞',
      conclusion: '责任认定：酒驾车辆全责'
    },
    {
      caseId: 'ACC-20240112-033',
      title: '超速行驶',
      location: '呼和浩特市新城区新华大街',
      status: '待复核',
      priority: '中优先级',
      archivedAt: '2024-01-12 14:55:00',
      note: '严重超速行驶，制动距离不足导致追尾',
      conclusion: '责任认定：超速车辆全责'
    },
    {
      caseId: 'ACC-20240110-034',
      title: '违法占用专用车道',
      location: '长春市朝阳区人民大街',
      status: '已完成',
      priority: '低优先级',
      archivedAt: '2024-01-10 11:40:00',
      note: '社会车辆违法占用公交专用道，与公交车发生刮擦',
      conclusion: '责任认定：违法占用车辆主责'
    },
    {
      caseId: 'ACC-20240108-035',
      title: '违法倒车',
      location: '哈尔滨市南岗区东大直街',
      status: '待分析',
      priority: '中优先级',
      archivedAt: '2024-01-08 15:10:00',
      note: '在道路上违法倒车，与后方正常行驶车辆相撞',
      conclusion: '责任认定：待分析'
    }
  ],
  tasks: {
    pending: []
  }
})

const state = reactive(initialState())

  // 应用启动时从 localStorage 恢复上次的 caseId（后端返回的真实 ID）
  ; (() => {
    try {
      const saved = localStorage.getItem(CURRENT_CASE_STORAGE_KEY)
      if (saved && saved.trim()) {
        state.caseId = saved.trim()
      }
    } catch (e) {
      // 忽略 localStorage 读取错误
    }
  })()

// ── caseId 统一管理 API ──
// 无效的 caseId 值集合（防止 "null"/"undefined" 字符串污染后端）
const INVALID_CASE_ID_VALUES = new Set([null, undefined, '', 'null', 'undefined', 'NaN'])

// 校验 caseId 是否为有效值
function isValidCaseId(caseId) {
  if (caseId === null || caseId === undefined) return false
  const str = String(caseId).trim()
  return str !== '' && !INVALID_CASE_ID_VALUES.has(str)
}

// 设置当前案件 ID（来源：后端创建案件返回 / 历史案件恢复 / URL query）
function setCurrentCase(caseId) {
  // 过滤无效值，防止 "null"/"undefined" 字符串污染
  const id = isValidCaseId(caseId) ? String(caseId).trim() : null
  state.caseId = id
  try {
    if (id) {
      localStorage.setItem(CURRENT_CASE_STORAGE_KEY, id)
    } else {
      localStorage.removeItem(CURRENT_CASE_STORAGE_KEY)
    }
  } catch (e) {
    // 忽略 localStorage 写入错误
  }
  logMessage(LOG_LEVELS.INFO, 'SYSTEM', 'SET_CURRENT_CASE', `当前案件 ID 设为 ${id || 'null'}`)
}

// 获取当前案件 ID（优先 state，fallback localStorage），自动过滤无效值
function getCurrentCase() {
  // 1. 优先从 state 获取
  if (isValidCaseId(state.caseId)) {
    return state.caseId
  }
  // 2. fallback localStorage
  try {
    const saved = localStorage.getItem(CURRENT_CASE_STORAGE_KEY)
    if (isValidCaseId(saved)) {
      state.caseId = saved.trim()
      return state.caseId
    }
  } catch (e) {
    // 忽略
  }
  return null
}

const stepLabelMap = {
  overview: '首页总览',
  'accident-entry': '事故录入',
  'video-processing': '视频处理',
  analysis: '智能分析',
  recommendation: '责任建议',
  'rule-basis': '规则依据',
  'manual-review': '人工复核',
  archived: '已归档'
}

const currentStatusLabel = computed(() => stepLabelMap[state.step] || '处理中')

// 数据验证模式
const dataSchemas = {
  'accident-entry': {
    time: { required: true, type: 'string' },
    location: { required: true, type: 'string' },
    accidentType: { required: true, type: 'string' }
  },
  'manual-review': {
    decision: { required: true, type: 'string', enum: ['确认系统建议', '调整责任', '驳回重审'] }
  }
}

// 更新表单数据
function updateForm(patch) {
  const validation = validateData('accident-entry', { ...state.form, ...patch }, dataSchemas['accident-entry'])
  logMessage(LOG_LEVELS.DEBUG, 'accident-entry', 'UPDATE_FORM', '更新表单数据', patch)
  Object.assign(state.form, patch)
  // 同步数据
  syncData('accident-entry', 'UPDATE_FORM', patch)
  return validation
}

// 更新分析数据
function updateAnalysis(patch) {
  logMessage(LOG_LEVELS.DEBUG, 'analysis', 'UPDATE_ANALYSIS', '更新分析数据', patch)
  Object.assign(state.analysis, patch)
  syncData('analysis', 'UPDATE_ANALYSIS', patch)
}

// 更新推荐数据
function updateRecommendation(patch) {
  logMessage(LOG_LEVELS.DEBUG, 'recommendation', 'UPDATE_RECOMMENDATION', '更新推荐数据', patch)
  Object.assign(state.recommendation, patch)
  syncData('recommendation', 'UPDATE_RECOMMENDATION', patch)
}

// 更新规则依据数据
function updateRuleBasis(patch) {
  logMessage(LOG_LEVELS.DEBUG, 'rule-basis', 'UPDATE_RULE_BASIS', '更新规则依据数据', patch)
  Object.assign(state.ruleBasis, patch)
  syncData('rule-basis', 'UPDATE_RULE_BASIS', patch)
}

// 更新人工复核数据
function updateManualReview(patch) {
  // 如果有调整，记录到历史
  if (patch.adjustments) {
    state.manualReview.reviewHistory.push({
      timestamp: new Date().toLocaleString(),
      adjustments: patch.adjustments,
      previousState: {
        decision: state.manualReview.decision,
        note: state.manualReview.note
      }
    })
  }
  logMessage(LOG_LEVELS.DEBUG, 'manual-review', 'UPDATE_MANUAL_REVIEW', '更新人工复核数据', patch)
  Object.assign(state.manualReview, patch)
  syncData('manual-review', 'UPDATE_MANUAL_REVIEW', patch)
}

function setSelectedFrame(frame) {
  state.analysis.selectedFrame = frame
  logMessage(LOG_LEVELS.INFO, 'analysis', 'SELECT_FRAME', '选择关键帧', frame)
}

function completeIntake() {
  state.step = 'video-processing'
  logMessage(LOG_LEVELS.INFO, 'accident-entry', 'COMPLETE', '事故录入完成')
  return '/video-processing'
}

function completeVideoProcessing() {
  state.step = 'analysis'
  logMessage(LOG_LEVELS.INFO, 'video-processing', 'COMPLETE', '视频处理完成')
  return '/intelligent-analysis'
}

function completeAnalysis() {
  state.step = 'recommendation'
  logMessage(LOG_LEVELS.INFO, 'analysis', 'COMPLETE', '智能分析完成')
  return '/liability-recommendation'
}

function completeRecommendation(data = {}) {
  if (data.summary) {
    state.recommendation.summary = data.summary
  }
  if (data.ratio) {
    state.recommendation.ratio = data.ratio
  }
  if (data.hitRules) {
    state.recommendation.hitRules = data.hitRules
  }
  if (data.suggestions) {
    state.recommendation.suggestions = data.suggestions
  }
  if (data.vehicleLiabilities) {
    state.recommendation.vehicleLiabilities = data.vehicleLiabilities
  }
  state.step = 'rule-basis'
  logMessage(LOG_LEVELS.INFO, 'recommendation', 'COMPLETE', '责任建议完成', data)
  return '/rule-basis'
}

function completeRuleBasis() {
  state.ruleBasis.confirmed = true
  state.ruleBasis.confirmedAt = new Date().toLocaleString()
  state.step = 'manual-review'
  logMessage(LOG_LEVELS.INFO, 'rule-basis', 'COMPLETE', '规则依据确认完成')
  return '/manual-review'
}

function submitManualReview() {
  const validation = validateData('manual-review', state.manualReview, dataSchemas['manual-review'])
  if (!validation.valid) {
    logMessage(LOG_LEVELS.ERROR, 'manual-review', 'SUBMIT', '提交失败', validation.errors)
    return { success: false, errors: validation.errors }
  }

  state.manualReview.submitted = true
  state.manualReview.reviewedAt = new Date().toLocaleString()
  state.step = 'archived'

  const archivedCase = {
    caseId: state.caseId,
    title: state.form.accidentType || '事故案件',
    conclusion: state.manualReview.decision || state.recommendation.summary,
    status: '已归档',
    source: `${state.form.fileType === 'video' ? '视频' : '图片'} + 事故描述`,
    note: state.manualReview.note || '无人工备注',
    archivedAt: new Date().toLocaleString(),
    route: '录入 → 视频处理 → 智能分析 → 责任建议 → 规则依据 → 人工复核 → 归档',
    priority: state.analysis.riskLevel === '高' ? '高' : state.analysis.riskLevel === '中等' ? '中' : '低',
    // 完整数据快照
    snapshot: {
      form: JSON.parse(JSON.stringify(state.form)),
      analysis: JSON.parse(JSON.stringify(state.analysis)),
      recommendation: JSON.parse(JSON.stringify(state.recommendation)),
      ruleBasis: JSON.parse(JSON.stringify(state.ruleBasis)),
      manualReview: JSON.parse(JSON.stringify(state.manualReview))
    }
  }

  state.archivedCases.unshift(archivedCase)
  logMessage(LOG_LEVELS.INFO, 'manual-review', 'SUBMIT', '人工复核提交完成，案件已归档', archivedCase)
  return { success: true, route: '/history-cases' }
}

function resetFlow() {
  const archivedCases = [...state.archivedCases]
  const fresh = initialState()
  Object.keys(state).forEach((key) => {
    state[key] = fresh[key]
  })
  state.archivedCases = archivedCases
  logMessage(LOG_LEVELS.INFO, 'SYSTEM', 'RESET', '流程已重置')
}

// 清除无效的案件ID
function clearInvalidCase() {
  // 重置为 null，不再随机生成
  setCurrentCase(null)
  state.step = 'overview'
  // 清除 localStorage 和 sessionStorage 中的旧版 caseId 缓存（历史残留）
  try {
    const keysToRemove = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key !== CURRENT_CASE_STORAGE_KEY && (key.includes('caseId') || key.includes('case_id') || key === 'currentCase')) {
        keysToRemove.push(key)
      }
    }
    keysToRemove.forEach(key => localStorage.removeItem(key))

    const sessionKeysToRemove = []
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i)
      if (key && (key.includes('caseId') || key.includes('case_id') || key === 'currentCase')) {
        sessionKeysToRemove.push(key)
      }
    }
    sessionKeysToRemove.forEach(key => sessionStorage.removeItem(key))
  } catch (e) {
    // 忽略存储清除错误
  }
  logMessage(LOG_LEVELS.WARNING, 'SYSTEM', 'CLEAR_INVALID_CASE', '已清除无效案件ID及相关缓存')
}

function goStep(step) {
  state.step = step
  logMessage(LOG_LEVELS.DEBUG, 'SYSTEM', 'GO_STEP', `切换到${step}步骤`)
}

// 初始化规则库数据
function initRuleLibrary() {
  try {
    state.ruleLibrary.rules = getRules()
    logMessage(LOG_LEVELS.INFO, 'rule-library', 'INIT', '规则库数据初始化完成')
    return true
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'rule-library', 'INIT', '规则库数据初始化失败', error)
    return false
  }
}

// 获取规则库数据
function getRuleLibrary() {
  if (state.ruleLibrary.rules.length === 0) {
    initRuleLibrary()
  }
  return [...state.ruleLibrary.rules]
}

// 获取启用的规则
function getActiveRules() {
  if (state.ruleLibrary.rules.length === 0) {
    initRuleLibrary()
  }
  return state.ruleLibrary.rules.filter(rule => rule.status === '启用')
}

// 根据事故类型获取规则
function getRulesByType(accidentType) {
  if (state.ruleLibrary.rules.length === 0) {
    initRuleLibrary()
  }
  return state.ruleLibrary.rules.filter(rule => rule.type === accidentType && rule.status === '启用')
}

// 添加新规则
function addRule(rule) {
  try {
    if (!rule.id) {
      rule.id = nextRuleId(state.ruleLibrary.rules)
    }
    const newRule = { ...rule, status: rule.status || '启用' }
    state.ruleLibrary.rules.unshift(newRule)
    saveRules(state.ruleLibrary.rules)
    logMessage(LOG_LEVELS.INFO, 'rule-library', 'ADD', `添加新规则: ${rule.id}`, newRule)
    syncData('rule-library', 'ADD_RULE', newRule)
    return newRule
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'rule-library', 'ADD', '添加规则失败', error)
    return null
  }
}

// 更新规则
function updateRule(ruleId, updates) {
  try {
    const index = state.ruleLibrary.rules.findIndex(rule => rule.id === ruleId)
    if (index !== -1) {
      state.ruleLibrary.rules[index] = { ...state.ruleLibrary.rules[index], ...updates }
      saveRules(state.ruleLibrary.rules)
      logMessage(LOG_LEVELS.INFO, 'rule-library', 'UPDATE', `更新规则: ${ruleId}`, updates)
      syncData('rule-library', 'UPDATE_RULE', { ruleId, updates })
      return state.ruleLibrary.rules[index]
    }
    return null
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'rule-library', 'UPDATE', '更新规则失败', error)
    return null
  }
}

// 删除规则
function deleteRule(ruleId) {
  try {
    const index = state.ruleLibrary.rules.findIndex(rule => rule.id === ruleId)
    if (index !== -1) {
      const deletedRule = state.ruleLibrary.rules.splice(index, 1)[0]
      saveRules(state.ruleLibrary.rules)
      logMessage(LOG_LEVELS.INFO, 'rule-library', 'DELETE', `删除规则: ${ruleId}`, deletedRule)
      syncData('rule-library', 'DELETE_RULE', { ruleId, deletedRule })
      return true
    }
    return false
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'rule-library', 'DELETE', '删除规则失败', error)
    return false
  }
}

// 从规则库选择规则到规则依据
function selectRuleFromLibrary(rule) {
  try {
    // 检查是否已经选择
    const alreadySelected = state.ruleBasis.selectedRules.some(selected => selected.id === rule.id)
    if (!alreadySelected) {
      const ruleToAdd = {
        id: rule.id,
        code: rule.id,
        name: rule.name,
        title: rule.name,
        category: rule.type,
        type: rule.type,
        scene: rule.scene,
        content: `适用于${rule.scene}场景的责任认定规则。`,
        applied: 1
      }
      updateRuleBasis({
        selectedRules: [...state.ruleBasis.selectedRules, ruleToAdd],
        appliedRules: [...state.ruleBasis.appliedRules, ruleToAdd]
      })
      logMessage(LOG_LEVELS.INFO, 'rule-basis', 'SELECT', `从规则库选择规则: ${rule.id}`)
      return true
    }
    return false
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'rule-basis', 'SELECT', '选择规则失败', error)
    return false
  }
}

// 从规则库中移除选择的规则
function deselectRuleFromLibrary(ruleId) {
  try {
    updateRuleBasis({
      selectedRules: state.ruleBasis.selectedRules.filter(rule => rule.id !== ruleId),
      appliedRules: state.ruleBasis.appliedRules.filter(rule => rule.id !== ruleId)
    })
    logMessage(LOG_LEVELS.INFO, 'rule-basis', 'DESELECT', `取消选择规则: ${ruleId}`)
    return true
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'rule-basis', 'DESELECT', '取消选择规则失败', error)
    return false
  }
}

// 获取规则库分类统计
function getRuleCategories() {
  if (state.ruleLibrary.rules.length === 0) {
    initRuleLibrary()
  }
  const map = new Map()
  state.ruleLibrary.rules.forEach(rule => map.set(rule.type, (map.get(rule.type) || 0) + 1))
  return [...map.entries()].map(([name, count]) => ({ name, count }))
}

// 更新归档案件
function updateArchivedCase(caseId, updates) {
  try {
    const index = state.archivedCases.findIndex(c => c.caseId === caseId)
    if (index !== -1) {
      state.archivedCases.splice(index, 1, { ...state.archivedCases[index], ...updates })
      logMessage(LOG_LEVELS.INFO, 'history-cases', 'UPDATE_CASE', `更新归档案件: ${caseId}`, updates)
      syncData('history-cases', 'UPDATE_CASE', { caseId, updates })
      return true
    }
    return false
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'history-cases', 'UPDATE_CASE', '更新归档案件失败', error)
    return false
  }
}

// 删除归档案件
function deleteArchivedCase(caseId) {
  try {
    const index = state.archivedCases.findIndex(c => c.caseId === caseId)
    if (index !== -1) {
      state.archivedCases.splice(index, 1)
      logMessage(LOG_LEVELS.INFO, 'history-cases', 'DELETE_CASE', `删除归档案件: ${caseId}`)
      syncData('history-cases', 'DELETE_CASE', { caseId })
      return true
    }
    return false
  } catch (error) {
    logMessage(LOG_LEVELS.ERROR, 'history-cases', 'DELETE_CASE', '删除归档案件失败', error)
    return false
  }
}

// 获取待处理任务（只显示归档案例中待分析状态）
function getPendingTasks() {
  const tasks = []

  // 归档案件中需要处理的 - 只显示待分析状态
  state.archivedCases.forEach(caseItem => {
    if (caseItem.status === '待分析') {
      tasks.push({
        id: `T-${caseItem.caseId}`,
        caseId: caseItem.caseId,
        title: `${caseItem.caseId} ${caseItem.title}`,
        type: '智能分析',
        status: '待分析',
        priority: caseItem.priority === '高优先级' ? 'high' : caseItem.priority === '中优先级' ? 'medium' : 'low',
        deadline: caseItem.archivedAt,
        createdAt: caseItem.archivedAt
      })
    }
  })

  state.tasks.pending = tasks
  return tasks
}

// 添加任务
function addTask(task) {
  const newTask = {
    id: `T-${Date.now().toString().slice(-6)}`,
    createdAt: new Date().toLocaleString(),
    ...task
  }
  state.tasks.pending.push(newTask)
  logMessage(LOG_LEVELS.INFO, 'tasks', 'ADD_TASK', '添加新任务', newTask)
  return newTask
}

// 完成任务
function completeTask(taskId) {
  const index = state.tasks.pending.findIndex(t => t.id === taskId)
  if (index !== -1) {
    const task = state.tasks.pending[index]
    state.tasks.pending.splice(index, 1)
    logMessage(LOG_LEVELS.INFO, 'tasks', 'COMPLETE_TASK', '完成任务', task)
    return true
  }
  return false
}

// 获取最近事故记录
function getRecentCases(limit = 5) {
  const cases = []

  // 当前案件
  if (state.step !== 'overview' && state.step !== 'archived') {
    let caseStatus = '处理中'
    switch (state.step) {
      case 'accident-entry':
      case 'video-processing':
        caseStatus = '待分析'
        break
      case 'analysis':
      case 'recommendation':
      case 'rule-basis':
        caseStatus = '待复核'
        break
      case 'manual-review':
        caseStatus = '复核中'
        break
    }
    cases.push({
      id: state.caseId,
      caseId: state.caseId,
      type: state.form.accidentType || '未命名案件',
      status: caseStatus,
      location: state.form.location || '未记录',
      time: new Date().toLocaleString(),
      hasVideo: !!state.form.videoFile
    })
  }

  // 归档案件
  state.archivedCases.forEach(caseItem => {
    cases.push({
      id: caseItem.caseId,
      caseId: caseItem.caseId,
      type: caseItem.title || '未命名案件',
      status: caseItem.status || '已完成',
      location: caseItem.location || '未记录',
      time: caseItem.archivedAt,
      hasVideo: caseItem.hasVideo || false
    })
  })

  // 按时间倒序，取最近的
  return cases.sort((a, b) => new Date(b.time) - new Date(a.time)).slice(0, limit)
}

// 获取日志
function getLogs() {
  return [...dataLogs]
}

// 导出数据
function exportData() {
  return {
    caseId: state.caseId,
    state: JSON.parse(JSON.stringify(state)),
    logs: getLogs(),
    exportedAt: new Date().toLocaleString()
  }
}

export function useAccidentFlow() {
  return {
    state,
    currentStatusLabel,
    // caseId 统一管理
    setCurrentCase,
    getCurrentCase,
    isValidCaseId,
    updateForm,
    updateAnalysis,
    updateRecommendation,
    updateRuleBasis,
    updateManualReview,
    setSelectedFrame,
    completeIntake,
    completeVideoProcessing,
    completeAnalysis,
    completeRecommendation,
    completeRuleBasis,
    submitManualReview,
    resetFlow,
    clearInvalidCase,
    goStep,
    getLogs,
    exportData,
    validateData,
    syncData,
    logMessage,
    LOG_LEVELS,
    // 规则库相关
    initRuleLibrary,
    getRuleLibrary,
    getActiveRules,
    getRulesByType,
    addRule,
    updateRule,
    deleteRule,
    selectRuleFromLibrary,
    deselectRuleFromLibrary,
    getRuleCategories,
    // 历史案件相关
    updateArchivedCase,
    deleteArchivedCase,
    // 任务管理相关
    getPendingTasks,
    addTask,
    completeTask,
    getRecentCases
  }
}