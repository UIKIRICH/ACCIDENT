<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="brand-logo">
        <span class="logo-icon-inner">智</span>
      </div>
      <div class="brand-text">
        <span class="brand-title">事故处理平台</span>
        <span class="brand-subtitle">Intelligent Platform</span>
      </div>
    </div>
    <nav class="sidebar-nav">
      <div 
        v-for="section in navigation" 
        :key="section.section"
        class="nav-section"
      >
        <div class="nav-section-title">{{ section.section }}</div>
        <button 
          v-for="item in section.items" 
          :key="item.key"
          class="nav-item" 
          :class="{ 'active': currentPage === item.key }"
          @click="$emit('page-change', item.key)"
        >
          <span class="nav-icon" v-html="icons[item.icon]"></span>
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-indicator"></span>
        </button>
      </div>
    </nav>
    <div class="sidebar-footer">
      <div class="user-card" @click="toggleUserPanel">
        <div class="user-avatar">
          <span>{{ user.initials }}</span>
        </div>
        <div class="user-info">
          <div class="user-name">{{ user.name }}</div>
          <div class="user-role">{{ user.role }}</div>
        </div>
        <div class="user-status">
          <span class="status-dot"></span>
        </div>
      </div>
      <div v-if="showUserPanel && isLoggedIn" class="user-panel">
        <button class="user-panel-item" @click.stop="$emit('logout')">
          <span>退出登录</span>
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  currentPage: {
    type: String,
    default: 'overview'
  },
  user: {
    type: Object,
    required: true
  },
  isLoggedIn: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['page-change', 'logout'])

const showUserPanel = ref(false)

const toggleUserPanel = () => {
  showUserPanel.value = !showUserPanel.value
}

const navigation = [
  {
    section: '概览',
    items: [
      { key: 'overview', label: '首页总览', icon: 'home' },
      { key: 'dashboard', label: '态势大屏', icon: 'monitor' }
    ]
  },
  {
    section: '案件处理',
    items: [
      { key: 'accidentEntry', label: '事故录入', icon: 'upload' },
      { key: 'videoProcessing', label: '视频处理', icon: 'video' },
      { key: 'imageEvidence', label: '图片证据', icon: 'image' },
      { key: 'intelligentAnalysis', label: '智能分析', icon: 'brain' },
      { key: 'liability', label: '责任建议', icon: 'fileText' },
      { key: 'ruleBasis', label: '规则依据', icon: 'database' },
      { key: 'manualReview', label: '人工复核', icon: 'checkCircle' }
    ]
  },
  {
    section: '可视化分析',
    items: [
      { key: 'evidenceChain', label: '证据链可视化', icon: 'chain' },
      { key: 'accidentTimeline', label: '事故时间轴', icon: 'clock' },
      { key: 'ruleGraph', label: '规则依据图谱', icon: 'share' }
    ]
  },
  {
    section: '数据管理',
    items: [
      { key: 'historyCases', label: '历史案例', icon: 'folder' },
      { key: 'workQueue', label: '任务中心', icon: 'list' },
      { key: 'ruleLibrary', label: '规则库', icon: 'layers' }
    ]
  }
]

const icons = {
  mobile: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12" y2="18.01"/></svg>`,
  home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
  upload: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`,
  brain: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></svg>`,
  fileText: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>`,
  database: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>`,
  checkCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
  list: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>`,
  layers: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
  video: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="15" height="16" rx="2"/><path d="m22 8-5 4 5 4V8z"/></svg>`,
  image: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>`,
  monitor: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  chain: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  share: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`
}
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  background: var(--sidebar-bg-gradient);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 100;
  overflow: hidden;
}

.sidebar-header {
  padding: var(--space-6) var(--space-6);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  border-bottom: 1px solid var(--sidebar-border);
}

.brand-logo {
  width: 44px;
  height: 44px;
  background: var(--primary-gradient);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35);
}

.logo-icon-inner {
  font-size: 20px;
  font-weight: 800;
  color: white;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--sidebar-text);
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.brand-subtitle {
  font-size: 13px;
  color: var(--sidebar-text-muted);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.sidebar-nav {
  flex: 1;
  padding: var(--space-5) var(--space-4);
  overflow-y: auto;
}

.sidebar-nav::-webkit-scrollbar {
  width: 5px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}

.nav-section {
  margin-bottom: var(--space-6);
}

.nav-section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--sidebar-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 0 var(--space-3) var(--space-3);
}

.nav-item {
  width: 100%;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 14px;
  background: transparent;
  border: none;
  color: var(--sidebar-text-muted);
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  border-radius: var(--radius-lg);
  margin-bottom: 4px;
  position: relative;
  font-family: var(--font-sans);
  line-height: var(--leading-normal);
}

.nav-item:hover {
  color: var(--sidebar-text);
  background: var(--sidebar-hover-bg);
  transform: translateX(2px);
}

.nav-item.active {
  color: var(--sidebar-active-text);
  background: var(--sidebar-active-bg);
  font-weight: 600;
}

.nav-icon {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.75;
  transition: opacity var(--transition-fast);
}

.nav-item:hover .nav-icon {
  opacity: 1;
}

.nav-item.active .nav-icon {
  opacity: 1;
}

.nav-label {
  flex: 1;
  min-width: 0;
}

.nav-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 3px;
  height: 22px;
  background: var(--primary-400);
  border-radius: 0 3px 3px 0;
  transition: transform var(--transition-fast);
}

.nav-item.active .nav-indicator {
  transform: translateY(-50%) scaleY(1);
}

.sidebar-footer {
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--sidebar-border);
}

.user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 12px;
  border-radius: var(--radius-lg);
  transition: background var(--transition-fast);
  cursor: pointer;
}

.user-card:hover {
  background: var(--sidebar-hover-bg);
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--primary-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: white;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.25);
}

.user-info {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--sidebar-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.user-role {
  font-size: 13px;
  color: var(--sidebar-text-muted);
  line-height: 1.3;
  font-weight: 500;
}

.user-status {
  display: flex;
  align-items: center;
  justify-content: center;
}

.status-dot {
  width: 8px;
  height: 8px;
  background: var(--success-500);
  border-radius: 50%;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
}

.user-panel {
  margin-top: var(--space-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-light);
}

.user-panel-item {
  width: 100%;
  padding: 10px 14px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
  text-align: left;
  font-family: var(--font-sans);
}

.user-panel-item:hover {
  background: var(--sidebar-hover-bg);
  color: var(--danger-500);
}
</style>
