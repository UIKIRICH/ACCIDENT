<template>
  <div class="rule-library-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">规则库</h1>
        <p class="page-subtitle">事故责任认定规则管理</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="exportRules">
          <span class="btn-icon" v-html="icons.download"></span>
          导出规则
        </button>
        <input ref="importInput" type="file" accept="application/json" class="hidden-input" @change="handleImport">
        <button class="btn btn-secondary" @click="openImport">
          <span class="btn-icon" v-html="icons.upload"></span>
          导入规则
        </button>
        <button class="btn btn-primary" @click="openCreateModal">
          <span class="btn-icon" v-html="icons.plus"></span>
          新增规则
        </button>
      </div>
    </div>

    <div class="library-container">
      <div class="rule-categories">
        <div class="section-header">
          <h2 class="section-title">规则分类</h2>
        </div>
        <div class="categories-grid">
          <div class="category-card" v-for="item in categorySummary" :key="item.name" :class="getCategoryClass(item.name)">
            <div class="category-icon" v-html="getCategoryIcon(item.name)"></div>
            <h3 class="category-title">{{ item.name }}</h3>
            <p class="category-count">{{ item.count }} 条规则</p>
          </div>
        </div>
      </div>

      <div class="rule-management card-surface">
        <div class="table-head">
          <div class="table-head-left">
            <span class="section-icon" v-html="icons.layers"></span>
            <h2 class="section-title">规则管理</h2>
          </div>
          <span class="summary-pill">共 {{ rules.length }} 条</span>
        </div>
        <div class="rules-table">
          <table>
            <thead>
              <tr>
                <th>规则ID</th>
                <th>规则名称</th>
                <th>事故类型</th>
                <th>适用场景</th>
                <th>状态</th>
                <th>选择</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr class="rule-row" v-for="rule in rules" :key="rule.id">
                <td><span class="rule-id">{{ rule.id }}</span></td>
                <td><span class="rule-name">{{ rule.name }}</span></td>
                <td><span class="type-tag">{{ rule.type }}</span></td>
                <td>{{ rule.scene }}</td>
                <td>
                  <span class="status-badge" :class="rule.status === '启用' ? 'status-active' : 'status-inactive'">
                    <span class="status-dot"></span>
                    {{ rule.status }}
                  </span>
                </td>
                <td>
                  <button class="btn btn-xs" :class="isRuleSelected(rule.id) ? 'btn-primary' : 'btn-secondary'" @click="toggleSelectRule(rule)">
                    {{ isRuleSelected(rule.id) ? '已选择' : '选择' }}
                  </button>
                </td>
                <td>
                  <div class="action-buttons">
                    <button class="action-btn edit-btn icon-only" @click="openEditModal(rule)" title="编辑">
                      <span v-html="icons.edit"></span>
                    </button>
                    <button class="action-btn delete-btn icon-only" @click="deleteRule(rule.id)" title="删除">
                      <span v-html="icons.trash"></span>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="rules.length === 0" class="empty-state">
          <div class="empty-icon" v-html="icons.layers"></div>
          <p class="empty-text">暂无规则，点击"新增规则"添加</p>
        </div>
      </div>
    </div>

    <div v-if="showModal" class="modal-mask" @click.self="closeModal">
      <div class="modal-card">
        <div class="modal-header">
          <h3 class="modal-title">
            <span class="modal-icon" v-html="form.id ? icons.edit : icons.plus"></span>
            {{ form.id ? '编辑规则' : '新增规则' }}
          </h3>
          <button class="modal-close" @click="closeModal" title="关闭">
            <span v-html="icons.close"></span>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">规则名称 <span class="required">*</span></label>
              <input v-model.trim="form.name" class="form-input" placeholder="请输入规则名称">
            </div>
            <div class="form-group">
              <label class="form-label">事故类型 <span class="required">*</span></label>
              <input v-model.trim="form.type" class="form-input" placeholder="如：追尾事故">
            </div>
            <div class="form-group">
              <label class="form-label">适用场景 <span class="required">*</span></label>
              <input v-model.trim="form.scene" class="form-input" placeholder="如：同向行驶">
            </div>
            <div class="form-group">
              <label class="form-label">状态</label>
              <select v-model="form.status" class="form-select">
                <option>启用</option>
                <option>停用</option>
              </select>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="closeModal">
            <span class="btn-icon" v-html="icons.close"></span>
            取消
          </button>
          <button class="btn btn-primary" @click="saveRule">
            <span class="btn-icon" v-html="icons.save"></span>
            保存
          </button>
        </div>
      </div>
    </div>
    <NavigationButtons />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAccidentFlow } from '../stores/useAccidentFlow'
import NavigationButtons from '../components/NavigationButtons.vue'
import { notify } from '../composables/useToast'
import { RulesAPI } from '../api/index.js'

const { 
  state,
  selectRuleFromLibrary, 
  deselectRuleFromLibrary 
} = useAccidentFlow()

const icons = {
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`,
  edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>`,
  download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" fill="none"/><polyline points="7 10 12 15 17 10" fill="none" stroke-width="2"/><line x1="12" y1="15" x2="12" y2="3" fill="none" stroke-width="2"/></svg>`,
  upload: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" fill="none"/><path d="M17 8l-5-5-5 5" fill="none" stroke-width="2"/><path d="M12 3v12" fill="none" stroke-width="2"/></svg>`,
  rearEnd: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2" fill-opacity="0.2"/><path d="M5 17v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" fill="none"/><path d="M8 14h8" fill="none"/><path d="M8 10h8" fill="none"/><path d="M8 6h8" fill="none"/></svg>`,
  laneChange: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h18" fill="none"/><path d="M16 8l4 4-4 4" fill="none"/><path d="M8 8l-4 4 4 4" fill="none"/><circle cx="12" cy="12" r="3" fill-opacity="0.3"/></svg>`,
  intersection: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18" fill="none"/><path d="M3 12h18" fill="none"/><circle cx="12" cy="12" r="4" fill-opacity="0.3"/><path d="M12 8l-2-3h4l-2 3z" fill-opacity="0.5"/><path d="M16 12l3-2v4l-3-2z" fill-opacity="0.5"/></svg>`,
  general: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18" fill="none"/><path d="M5 7h14" fill="none"/><path d="M4 21h16" fill="none"/><path d="M8 7l4-4 4 4" fill="none"/></svg>`,
  layers: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2" fill-opacity="0.2"/><polyline points="2 17 12 22 22 17" fill="none"/><polyline points="2 12 12 17 22 12" fill="none"/></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
  save: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" fill-opacity="0.2"/><polyline points="17 21 17 13 7 13 7 21" fill="none"/><polyline points="7 3 7 8 15 8" fill="none"/></svg>`
}

const categoryIcons = {
  '追尾事故': icons.rearEnd,
  '变道事故': icons.laneChange,
  '路口事故': icons.intersection,
  '一般事故': icons.general
}

const importInput = ref(null)
const showModal = ref(false)
const form = ref({ id: '', name: '', type: '', scene: '', status: '启用' })
const rules = ref([])
const loading = ref(false)

// 从后端API获取规则列表
async function fetchRules() {
  loading.value = true
  try {
    const result = await RulesAPI.getList()
    if (result.success && Array.isArray(result.data)) {
      rules.value = result.data
    }
  } catch (err) {
    console.warn('获取规则列表失败:', err)
    rules.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchRules()
})

// 分类统计
const categorySummary = computed(() => {
  const map = new Map()
  rules.value.forEach(rule => {
    const type = rule.type || '一般事故'
    map.set(type, (map.get(type) || 0) + 1)
  })
  return [...map.entries()].map(([name, count]) => ({ name, count }))
})

const getCategoryIcon = (name) => categoryIcons[name] || icons.general

const getCategoryClass = (name) => {
  const classMap = {
    '追尾事故': 'category-rear-end',
    '变道事故': 'category-lane-change',
    '路口事故': 'category-intersection',
    '一般事故': 'category-general'
  }
  return classMap[name] || 'category-general'
}

const isRuleSelected = (ruleId) => {
  return state.ruleBasis.selectedRules.some(r => r.id === ruleId)
}

const resetForm = () => { form.value = { id: '', name: '', type: '', scene: '', status: '启用' } }
const openCreateModal = () => { resetForm(); showModal.value = true }
const openEditModal = (rule) => { form.value = { ...rule }; showModal.value = true }
const closeModal = () => { showModal.value = false; resetForm() }
const openImport = () => importInput.value?.click()

const saveRule = async () => {
  if (!form.value.name || !form.value.type || !form.value.scene) {
    notify({ title: '保存失败', message: '请填写完整规则信息。', type: 'warning' })
    return
  }
  try {
    if (form.value.id) {
      // 编辑 → PUT /api/rules/:id
      const result = await RulesAPI.update(form.value.id, form.value)
      if (result.success) {
        notify({ title: '规则已更新', message: `${form.value.id} 已保存修改。` })
        await fetchRules() // 刷新列表
      }
    } else {
      // 新增 → POST /api/rules
      const result = await RulesAPI.create(form.value)
      if (result.success && result.data) {
        notify({ title: '规则已新增', message: `${result.data.id} 已加入规则库。` })
        await fetchRules() // 刷新列表
      }
    }
    closeModal()
  } catch (err) {
    notify({ title: '保存失败', message: err.message || '操作失败', type: 'error' })
  }
}

const deleteRule = async (id) => {
  try {
    const result = await RulesAPI.delete(id)
    if (result.success) {
      notify({ title: '规则已删除', message: `${id} 已从规则库移除。`, type: 'success' })
      await fetchRules() // 刷新列表
    }
  } catch (err) {
    notify({ title: '删除失败', message: err.message || '操作失败', type: 'error' })
  }
}

const exportRules = () => {
  const blob = new Blob([JSON.stringify(rules.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'rule-library.json'
  link.click()
  URL.revokeObjectURL(url)
  notify({ title: '导出成功', message: '规则文件已开始下载。' })
}

const handleImport = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const payload = JSON.parse(await file.text())
    if (!Array.isArray(payload)) throw new Error('invalid')
    for (const rule of payload) {
      try {
        await RulesAPI.create(rule)
      } catch (e) {
        console.warn(`导入规则失败:`, rule, e)
      }
    }
    await fetchRules()
    notify({ title: '导入成功', message: `已完成导入 ${payload.length} 条规则。` })
  } catch {
    notify({ title: '导入失败', message: '请上传有效的 JSON 规则文件。', type: 'error' })
  } finally {
    event.target.value = ''
  }
}

const toggleSelectRule = (rule) => {
  if (isRuleSelected(rule.id)) {
    deselectRuleFromLibrary(rule.id)
    notify({ title: '取消选择', message: `已取消选择: ${rule.name}` })
  } else {
    selectRuleFromLibrary(rule)
    notify({ title: '选择规则', message: `已选择: ${rule.name}` })
  }
}
</script>

<style scoped>
.rule-library-page, .library-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.rule-library-page {
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
  margin-bottom: var(--space-2);
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

.header-actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 9px 18px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-size: var(--text-sm);
  font-weight: 600;
  font-family: var(--font-sans);
  white-space: nowrap;
}

.btn-xs {
  padding: 5px 12px;
  font-size: var(--text-xs);
}

.btn-icon { width: 15px; height: 15px; }

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
  border-color: var(--primary-400);
  transform: translateY(-1px);
}

.hidden-input { display: none; }

.card-surface, .category-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-normal);
}

.card-surface:hover, .category-card:hover { box-shadow: var(--shadow-md); }

.rule-categories, .rule-management {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.section-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.section-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
}

.categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-4);
}

.category-card {
  padding: var(--space-6);
  text-align: center;
  transition: all var(--transition-normal);
}

.category-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
  border-color: var(--primary-200);
}

.category-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto var(--space-3);
  background: var(--primary-soft);
  color: var(--primary);
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-normal);
}

.category-icon span { width: 28px; height: 28px; }

.category-rear-end .category-icon {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  color: white;
  box-shadow: 0 3px 10px rgba(245, 158, 11, 0.3);
}

.category-rear-end:hover .category-icon { transform: scale(1.08) rotate(-3deg); }

.category-lane-change .category-icon {
  background: var(--primary-gradient);
  color: white;
  box-shadow: 0 3px 10px rgba(59, 130, 246, 0.3);
}

.category-lane-change:hover .category-icon { transform: scale(1.08) rotate(3deg); }

.category-intersection .category-icon {
  background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
  color: white;
  box-shadow: 0 3px 10px rgba(139, 92, 246, 0.3);
}

.category-intersection:hover .category-icon { transform: scale(1.08) rotate(-2deg); }

.category-general .category-icon {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  color: white;
  box-shadow: 0 3px 10px rgba(34, 197, 94, 0.3);
}

.category-general:hover .category-icon { transform: scale(1.08) rotate(2deg); }

.category-title {
  color: var(--text-primary);
  margin-bottom: var(--space-2);
  font-size: var(--text-base);
  font-weight: 700;
}

.category-count {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border-light);
}

.table-head-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.summary-pill {
  padding: 5px 12px;
  border-radius: var(--radius-full);
  background: var(--primary-soft);
  color: var(--primary);
  font-size: var(--text-xs);
  font-weight: 600;
}

.rule-management { padding: 0; overflow: hidden; }
.rules-table { overflow: auto; }
.rules-table table { width: 100%; border-collapse: collapse; }

.rules-table th, .rules-table td {
  padding: 14px;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
  color: var(--text-primary);
  background: transparent;
}

.rules-table th {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  background: var(--bg-secondary);
}

.rule-row { transition: background var(--transition-fast); }
.rule-row:hover { background: var(--primary-soft); }

.rule-id {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 3px 10px;
  border-radius: var(--radius-md);
}

.rule-name { font-weight: 600; color: var(--text-primary); }

.type-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

.status-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.status-active { background: rgba(34, 197, 94, 0.1); color: var(--success-500); }
.status-inactive { background: rgba(107, 114, 128, 0.1); color: var(--text-muted); }

.action-buttons { display: flex; gap: var(--space-2); }

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  font-size: var(--text-xs);
  font-weight: 500;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.action-btn span { width: 13px; height: 13px; }

.action-btn.icon-only {
  width: 30px;
  height: 30px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
}

.action-btn.icon-only span { width: 15px; height: 15px; }

.edit-btn { background: rgba(139, 92, 246, 0.1); color: #8b5cf6; }
.edit-btn:hover { background: #8b5cf6; color: white; transform: translateY(-1px); }

.delete-btn { background: rgba(239, 68, 68, 0.1); color: var(--danger-500); }
.delete-btn:hover { background: var(--danger-500); color: white; transform: translateY(-1px); }

.empty-state { padding: 48px var(--space-6); text-align: center; }
.empty-icon { width: 60px; height: 60px; margin: 0 auto var(--space-4); color: var(--text-muted); opacity: 0.5; }
.empty-text { color: var(--text-muted); font-size: var(--text-sm); }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(3, 10, 20, 0.55);
  display: grid;
  place-items: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.modal-card {
  width: min(560px, calc(100vw - 48px));
  background: var(--bg-primary);
  padding: 0;
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-2xl);
  overflow: hidden;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--border-light);
}

.modal-title {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.modal-icon { width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; color: var(--primary); }

.modal-close {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.modal-close:hover { background: var(--bg-secondary); color: var(--text-primary); }
.modal-close span { width: 16px; height: 16px; }

.modal-body { padding: var(--space-6); }

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
}

.form-group { display: flex; flex-direction: column; }

.form-label {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: 600;
}

.required { color: var(--danger); }

.form-input, .form-select {
  width: 100%;
  padding: 10px 14px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
  outline: none;
}

.form-input:focus, .form-select:focus {
  border-color: var(--primary-400);
  box-shadow: var(--shadow-focus);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--border-light);
}

@media (max-width: 768px) {
  .page-header { flex-direction: column; align-items: flex-start; }
  .header-actions { width: 100%; }
  .header-actions .btn { flex: 1; justify-content: center; }
  .form-grid { grid-template-columns: 1fr; }
  .categories-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
