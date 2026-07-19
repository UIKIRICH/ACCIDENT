const KEYS = {
  rules: 'accident-platform-rules',
  cases: 'accident-platform-cases',
  draft: 'accident-platform-entry-draft',
  video: 'accident-platform-video-meta'
}

const defaultRules = [
  { id: 'R-001', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-002', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-003', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-004', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-005', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-006', name: '开门未观察后方', type: '刮擦事故', scene: '路边停车', status: '启用' },
  { id: 'R-007', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-008', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-009', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-010', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-011', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-012', name: '开门未观察后方', type: '刮擦事故', scene: '路边停车', status: '启用' },
  { id: 'R-013', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-014', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-015', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-016', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-017', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-018', name: '未按规定让行', type: '路口事故', scene: '无信号灯路口', status: '启用' },
  { id: 'R-019', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-020', name: '逆行', type: '一般事故', scene: '单行道', status: '启用' },
  { id: 'R-021', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-022', name: '变道未让行', type: '变道事故', scene: '变道过程', status: '启用' },
  { id: 'R-023', name: '开门未观察后方', type: '刮擦事故', scene: '路边停车', status: '启用' },
  { id: 'R-024', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-025', name: '酒后驾驶', type: '重大事故', scene: '夜间道路', status: '启用' },
  { id: 'R-026', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-027', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-028', name: '机动车占用非机动车道', type: '一般事故', scene: '城市道路', status: '启用' },
  { id: 'R-029', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-030', name: '变道未让行', type: '变道事故', scene: '变道过程', status: '启用' },
  { id: 'R-031', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-032', name: '开门未观察后方', type: '刮擦事故', scene: '路边停车', status: '启用' },
  { id: 'R-033', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-034', name: '非机动车逆行', type: '非机动车事故', scene: '非机动车道', status: '启用' },
  { id: 'R-035', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-036', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-037', name: '酒后驾驶', type: '重大事故', scene: '夜间道路', status: '启用' },
  { id: 'R-038', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-039', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-040', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-041', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-042', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-043', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-044', name: '开门未观察后方', type: '刮擦事故', scene: '路边停车', status: '启用' },
  { id: 'R-045', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-046', name: '机动车占用非机动车道', type: '一般事故', scene: '城市道路', status: '启用' },
  { id: 'R-047', name: '变道未让行', type: '变道事故', scene: '变道过程', status: '启用' },
  { id: 'R-048', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-049', name: '行人闯红灯', type: '行人事故', scene: '城市路口', status: '启用' },
  { id: 'R-050', name: '酒后驾驶', type: '重大事故', scene: '夜间道路', status: '启用' },
  { id: 'R-051', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-052', name: '逆行', type: '一般事故', scene: '单行道', status: '启用' },
  { id: 'R-053', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-054', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-055', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-056', name: '闯红灯', type: '路口事故', scene: '信号灯路口', status: '启用' },
  { id: 'R-057', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-058', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-059', name: '非机动车逆行', type: '非机动车事故', scene: '非机动车道', status: '启用' },
  { id: 'R-060', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-061', name: '开门未观察后方', type: '刮擦事故', scene: '路边停车', status: '启用' },
  { id: 'R-062', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-063', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-064', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-065', name: '非机动车逆行', type: '非机动车事故', scene: '非机动车道', status: '启用' },
  { id: 'R-066', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-067', name: '非机动车逆行', type: '非机动车事故', scene: '非机动车道', status: '启用' },
  { id: 'R-068', name: '开门未观察后方', type: '刮擦事故', scene: '路边停车', status: '启用' },
  { id: 'R-069', name: '闯红灯', type: '路口事故', scene: '信号灯路口', status: '启用' },
  { id: 'R-070', name: '未按规定让行', type: '路口事故', scene: '无信号灯路口', status: '启用' },
  { id: 'R-071', name: '变道未让行', type: '变道事故', scene: '变道过程', status: '启用' },
  { id: 'R-072', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-073', name: '行人闯红灯', type: '行人事故', scene: '城市路口', status: '启用' },
  { id: 'R-074', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-075', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-076', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-077', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-078', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-079', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-080', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-081', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-082', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-083', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-084', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-085', name: '机动车占用非机动车道', type: '一般事故', scene: '城市道路', status: '启用' },
  { id: 'R-086', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-087', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-088', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-089', name: '行人闯红灯', type: '行人事故', scene: '城市路口', status: '启用' },
  { id: 'R-090', name: '逆行', type: '一般事故', scene: '单行道', status: '启用' },
  { id: 'R-091', name: '违法掉头', type: '路口事故', scene: '禁止掉头路段', status: '启用' },
  { id: 'R-092', name: '逆行', type: '一般事故', scene: '单行道', status: '启用' },
  { id: 'R-093', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-094', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-095', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-096', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-097', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-098', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-099', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-100', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-101', name: '夜间未开灯', type: '一般事故', scene: '夜间道路', status: '启用' },
  { id: 'R-102', name: '夜间未开灯', type: '一般事故', scene: '夜间道路', status: '启用' },
  { id: 'R-103', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-104', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-105', name: '违法掉头', type: '路口事故', scene: '禁止掉头路段', status: '启用' },
  { id: 'R-106', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-107', name: '机动车占用非机动车道', type: '一般事故', scene: '城市道路', status: '启用' },
  { id: 'R-108', name: '违规并线', type: '变道事故', scene: '高峰车流', status: '启用' },
  { id: 'R-109', name: '违规并线', type: '变道事故', scene: '高峰车流', status: '启用' },
  { id: 'R-110', name: '机动车占用非机动车道', type: '一般事故', scene: '城市道路', status: '启用' },
  { id: 'R-111', name: '逆行', type: '一般事故', scene: '单行道', status: '启用' },
  { id: 'R-112', name: '行人闯红灯', type: '行人事故', scene: '城市路口', status: '启用' },
  { id: 'R-113', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-114', name: '机动车占用非机动车道', type: '一般事故', scene: '城市道路', status: '启用' },
  { id: 'R-115', name: '违规并线', type: '变道事故', scene: '高峰车流', status: '启用' },
  { id: 'R-116', name: '违规并线', type: '变道事故', scene: '高峰车流', status: '启用' },
  { id: 'R-117', name: '夜间未开灯', type: '一般事故', scene: '夜间道路', status: '启用' },
  { id: 'R-118', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-119', name: '非机动车逆行', type: '非机动车事故', scene: '非机动车道', status: '启用' },
  { id: 'R-120', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-121', name: '违规并线', type: '变道事故', scene: '高峰车流', status: '启用' },
  { id: 'R-122', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-123', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-124', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-125', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-126', name: '雨天未减速', type: '追尾事故', scene: '雨天道路', status: '启用' },
  { id: 'R-127', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-128', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-129', name: '闯红灯', type: '路口事故', scene: '信号灯路口', status: '启用' },
  { id: 'R-130', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-131', name: '夜间未开灯', type: '一般事故', scene: '夜间道路', status: '启用' },
  { id: 'R-132', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-133', name: '违法掉头', type: '路口事故', scene: '禁止掉头路段', status: '启用' },
  { id: 'R-134', name: '高速出口急刹', type: '追尾事故', scene: '高速出口', status: '启用' },
  { id: 'R-135', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-136', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-137', name: '违法掉头', type: '路口事故', scene: '禁止掉头路段', status: '启用' },
  { id: 'R-138', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-139', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
  { id: 'R-140', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-141', name: '违规并线', type: '变道事故', scene: '高峰车流', status: '启用' },
  { id: 'R-142', name: '高速出口急刹', type: '追尾事故', scene: '高速出口', status: '启用' },
  { id: 'R-143', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-144', name: '违规并线', type: '变道事故', scene: '高峰车流', status: '启用' },
  { id: 'R-145', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-146', name: '酒后驾驶', type: '重大事故', scene: '夜间道路', status: '启用' },
  { id: 'R-147', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-148', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-149', name: '行人闯红灯', type: '行人事故', scene: '城市路口', status: '启用' },
  { id: 'R-150', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-151', name: '雨天未减速', type: '追尾事故', scene: '雨天道路', status: '启用' },
  { id: 'R-152', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-153', name: '违法超车', type: '碰撞事故', scene: '双向车道', status: '启用' },
  { id: 'R-154', name: '行人闯红灯', type: '行人事故', scene: '城市路口', status: '启用' },
  { id: 'R-155', name: '夜间未开灯', type: '一般事故', scene: '夜间道路', status: '启用' },
  { id: 'R-156', name: '违法掉头', type: '路口事故', scene: '禁止掉头路段', status: '启用' },
  { id: 'R-157', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-158', name: '疲劳驾驶', type: '一般事故', scene: '长时间驾驶', status: '启用' },
  { id: 'R-159', name: '未打转向灯', type: '变道事故', scene: '车道变更', status: '启用' },
  { id: 'R-160', name: '未观察盲区', type: '碰撞事故', scene: '转弯路口', status: '启用' },
  { id: 'R-161', name: '夜间未开灯', type: '一般事故', scene: '夜间道路', status: '启用' },
  { id: 'R-162', name: '压实线变道', type: '变道事故', scene: '道路实线区域', status: '启用' },
  { id: 'R-163', name: '后车未保持安全距离', type: '追尾事故', scene: '同向行驶', status: '启用' },
  { id: 'R-164', name: '超速行驶', type: '一般事故', scene: '城市快速路', status: '启用' },
  { id: 'R-165', name: '未按导向车道行驶', type: '路口事故', scene: '多车道路口', status: '启用' },
  { id: 'R-166', name: '占用应急车道', type: '一般事故', scene: '高速公路', status: '启用' },
  { id: 'R-167', name: '未观察盲区', type: '碰撞事故', scene: '转弯路口', status: '启用' },
  { id: 'R-168', name: '未礼让行人', type: '行人事故', scene: '人行横道', status: '启用' },
  { id: 'R-169', name: '逆行', type: '一般事故', scene: '单行道', status: '启用' },
  { id: 'R-170', name: '违规停车', type: '刮擦事故', scene: '路边停车区域', status: '启用' },
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
