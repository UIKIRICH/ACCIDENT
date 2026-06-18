const KEYS = {
  rules: 'accident-platform-rules',
  cases: 'accident-platform-cases',
  draft: 'accident-platform-entry-draft',
  video: 'accident-platform-video-meta'
}

const defaultRules = [
  { id: 'R-001', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-002', name: '变道未让行', type: '变道事故', scene: '变道过程', status: '启用' },
  { id: 'R-003', name: '闯红灯', type: '路口事故', scene: '信号灯路口', status: '启用' },
  { id: 'R-004', name: '逆行', type: '一般事故', scene: '单行道', status: '启用' },
  { id: 'R-005', name: '超速行驶', type: '一般事故', scene: '限速路段', status: '启用' }
]

const defaultCases = [
  { id: 'E-0422', type: '追尾事故', location: '北京市朝阳区', status: '待处理', submittedAt: '2026-03-24 16:00', eta: '30分钟', reviewer: '', description: '主路同向行驶时发生追尾。', weather: '晴' },
  { id: 'E-0423', type: '交叉路口事故', location: '北京市海淀区', status: '处理中', submittedAt: '2026-03-24 15:30', eta: '20分钟', reviewer: '张警官', description: '路口直行与左转冲突。', weather: '阴' },
  { id: 'E-0424', type: '变道事故', location: '北京市西城区', status: '待处理', submittedAt: '2026-03-24 14:45', eta: '25分钟', reviewer: '', description: '变道车辆未观察后方来车。', weather: '晴' },
  { id: 'E-0425', type: '停车事故', location: '北京市丰台区', status: '待处理', submittedAt: '2026-03-24 14:00', eta: '20分钟', reviewer: '', description: '停车开门引发剐蹭。', weather: '雨' },
  { id: 'E-0426', type: '路口剐蹭', location: '北京市通州区', status: '已完成', submittedAt: '2026-03-23 18:15', eta: '已归档', reviewer: '张警官', description: '两车在无信号路口相撞。', weather: '晴' }
]

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

function write(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function getRules() {
  const rules = read(KEYS.rules, defaultRules)
  if (!localStorage.getItem(KEYS.rules)) write(KEYS.rules, rules)
  return rules
}

export function saveRules(rules) {
  write(KEYS.rules, rules)
}

export function getCases() {
  const cases = read(KEYS.cases, defaultCases)
  if (!localStorage.getItem(KEYS.cases)) write(KEYS.cases, cases)
  return cases
}

export function saveCases(cases) {
  write(KEYS.cases, cases)
}

export function getDraft() {
  return read(KEYS.draft, null)
}

export function saveDraft(draft) {
  write(KEYS.draft, draft)
}

export function clearDraft() {
  localStorage.removeItem(KEYS.draft)
}

export function saveVideoMeta(videoMeta) {
  write(KEYS.video, videoMeta)
}

export function getVideoMeta() {
  return read(KEYS.video, null)
}

export function nextRuleId(rules) {
  const max = rules.reduce((acc, item) => Math.max(acc, Number(item.id.split('-')[1]) || 0), 0)
  return `R-${String(max + 1).padStart(3, '0')}`
}

export function nextCaseId(cases) {
  const max = cases.reduce((acc, item) => Math.max(acc, Number(item.id.split('-')[1]) || 0), 0)
  return `E-${String(max + 1).padStart(4, '0')}`
}
