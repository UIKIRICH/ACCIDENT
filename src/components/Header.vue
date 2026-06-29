<template>
  <header class="top-header">
    <div class="header-left">
      <nav class="breadcrumb">
        <span class="breadcrumb-item" @click="goHome" style="cursor: pointer;">
          <span class="breadcrumb-icon" v-html="icons.home"></span>首页
        </span>
        <span class="breadcrumb-separator">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </span>
        <span class="breadcrumb-item active">{{ pageTitles[currentPage] || '首页总览' }}</span>
      </nav>
    </div>
    <div class="header-right">
      <div class="search-box">
        <span class="search-icon" v-html="icons.search"></span>
        <input type="text" class="search-input" placeholder="搜索案件、规则或文档...">
      </div>
      <div class="header-actions">
        <button class="icon-button" @click="$emit('theme-toggle')" title="切换主题">
          <span v-html="theme === 'dark' ? icons.sun : icons.moon"></span>
        </button>
        <button class="icon-button notification-btn" title="通知">
          <span v-html="icons.bell"></span>
          <span class="notification-badge">3</span>
        </button>
        <button class="icon-button" @click="showSettings = true" title="设置">
          <span v-html="icons.settings"></span>
        </button>
      </div>
    </div>
  </header>

  <!-- 设置模态框 -->
  <div v-if="showSettings" class="modal-overlay" @click.self="showSettings = false">
    <div class="modal-container">
      <div class="modal-header">
        <h2 class="modal-title">系统设置</h2>
        <button class="modal-close" @click="showSettings = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <div class="settings-section">
          <h3 class="settings-section-title">外观设置</h3>
          <div class="settings-item">
            <div class="settings-item-label">深色模式</div>
            <label class="toggle-switch">
              <input type="checkbox" :checked="theme === 'dark'" @change="toggleTheme">
              <span class="slider"></span>
            </label>
          </div>
        </div>

        <div class="settings-section">
          <h3 class="settings-section-title">通知设置</h3>
          <div class="settings-item">
            <div class="settings-item-label">推送通知</div>
            <label class="toggle-switch">
              <input type="checkbox" v-model="settings.pushNotification">
              <span class="slider"></span>
            </label>
          </div>
          <div class="settings-item">
            <div class="settings-item-label">声音提醒</div>
            <label class="toggle-switch">
              <input type="checkbox" v-model="settings.soundNotification">
              <span class="slider"></span>
            </label>
          </div>
        </div>

        <div class="settings-section">
          <h3 class="settings-section-title">系统信息</h3>
          <div class="settings-item">
            <div class="settings-item-label">版本号</div>
            <span class="settings-item-value">v2.0.0</span>
          </div>
          <div class="settings-item">
            <div class="settings-item-label">构建时间</div>
            <span class="settings-item-value">2025-07-15</span>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="modal-btn secondary" @click="showSettings = false">关闭</button>
        <button class="modal-btn primary" @click="saveSettings">保存设置</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const showSettings = ref(false)
const settings = ref({
  pushNotification: true,
  soundNotification: false
})

const props = defineProps({
  currentPage: {
    type: String,
    default: 'overview'
  },
  theme: {
    type: String,
    default: 'light'
  }
})

const emit = defineEmits(['theme-toggle'])

const pageTitles = {
  overview: '首页总览',
  accidentEntry: '事故录入',
  intelligentAnalysis: '智能分析',
  liability: '责任建议',
  ruleBasis: '规则依据',
  manualReview: '人工复核',
  historyCases: '历史案例',
  workQueue: '任务中心',
  ruleLibrary: '规则库',
  videoProcessing: '视频处理',
  imageEvidence: '图片侧证'
}

const icons = {
  home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="22" height="22"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,
  moon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="22" height="22"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`,
  sun: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="22" height="22"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>`,
  bell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="22" height="22"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>`,
  settings: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="22" height="22"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`
}

const goHome = () => {
  router.push('/')
}

const toggleTheme = () => {
  emit('theme-toggle')
}

const saveSettings = () => {
  localStorage.setItem('appSettings', JSON.stringify(settings.value))
  showSettings.value = false
  alert('设置已保存！')
}

// 从本地存储加载设置
const loadSettings = () => {
  const saved = localStorage.getItem('appSettings')
  if (saved) {
    settings.value = JSON.parse(saved)
  }
}

loadSettings()
</script>

<style scoped>
.top-header {
  height: 72px;
  background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-base) 100%);
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-5);
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: 16px;
}

.breadcrumb-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-tertiary);
  transition: color var(--transition-fast);
  font-weight: 500;
}

.breadcrumb-item:hover {
  color: var(--text-primary);
}

.breadcrumb-icon {
  width: 20px;
  height: 20px;
  opacity: 0.7;
}

.breadcrumb-item.active {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 17px;
}

.breadcrumb-separator {
  width: 18px;
  height: 18px;
  color: var(--text-muted);
  opacity: 0.6;
}

.breadcrumb-separator svg {
  width: 100%;
  height: 100%;
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.search-box {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 10px 16px;
  width: 340px;
  transition: all var(--transition-fast);
}

.search-box:focus-within {
  background: var(--bg-primary);
  border-color: var(--primary-500);
  box-shadow: var(--shadow-focus);
}

.search-icon {
  width: 20px;
  height: 20px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.search-box:focus-within .search-icon {
  color: var(--primary-600);
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 15px;
  color: var(--text-primary);
  outline: none;
  font-family: var(--font-sans);
}

.search-input::placeholder {
  color: var(--text-muted);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.icon-button {
  width: 44px;
  height: 44px;
  border: 1px solid var(--border-light);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  position: relative;
}

.icon-button:hover {
  border-color: var(--primary-500);
  color: var(--primary-600);
  background: var(--primary-50);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.notification-btn {
  position: relative;
}

.notification-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  min-width: 18px;
  height: 18px;
  background: var(--danger-500);
  color: white;
  font-size: 11px;
  font-weight: 700;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  z-index: 2;
  box-shadow: 0 2px 6px rgba(220, 38, 38, 0.3);
}

/* 模态框样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background: var(--bg-primary);
  border-radius: 16px;
  box-shadow: var(--shadow-2xl);
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-light);
}

.modal-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  width: 36px;
  height: 36px;
  border: none;
  background: var(--bg-secondary);
  border-radius: 8px;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.modal-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.settings-section {
  margin-bottom: 24px;
}

.settings-section:last-child {
  margin-bottom: 0;
}

.settings-section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 12px;
}

.settings-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
}

.settings-item-label {
  font-size: 15px;
  color: var(--text-primary);
  font-weight: 500;
}

.settings-item-value {
  font-size: 14px;
  color: var(--text-muted);
}

/* 切换开关样式 */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 52px;
  height: 28px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--border-medium);
  transition: all 0.3s;
  border-radius: 28px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 22px;
  width: 22px;
  left: 3px;
  bottom: 3px;
  background: var(--bg-primary);
  transition: all 0.3s;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
}

input:checked + .slider {
  background: var(--primary-500);
}

input:checked + .slider:before {
  transform: translateX(24px);
}

.modal-footer {
  display: flex;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-light);
}

.modal-btn {
  flex: 1;
  height: 44px;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  font-family: var(--font-sans);
}

.modal-btn.secondary {
  background: var(--bg-base);
  color: var(--text-secondary);
}

.modal-btn.secondary:hover {
  background: var(--bg-secondary);
  border-color: var(--border-medium);
}

.modal-btn.primary {
  background: var(--primary-gradient);
  color: white;
  border: none;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.modal-btn.primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
}
</style>
