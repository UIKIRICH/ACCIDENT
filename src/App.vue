<template>
  <!-- 独立页面（登录页等）→ 仅渲染路由内容 -->
  <template v-if="isStandalonePage">
    <router-view v-slot="{ Component }">
      <component :is="Component" />
    </router-view>
    <Toast v-if="toasts.length > 0" :toasts="toasts" @close="removeToast" />
  </template>

  <!-- 正常后台布局 -->
  <div v-else class="app" :class="{ 'dark-theme': theme === 'dark' }">
    <Sidebar :currentPage="currentPage" @page-change="handlePageChange" :user="currentUser" :isLoggedIn="isLoggedIn" @logout="handleLogout" @go-login="handleGoLogin" />
    <div class="main-content">
      <Header :currentPage="currentPage" :theme="theme" @theme-toggle="toggleTheme" />
      <div class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </div>
    <Toast v-if="toasts.length > 0" :toasts="toasts" @close="removeToast" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import Header from './components/Header.vue'
import Toast from './components/Toast.vue'

const router = useRouter()
const route = useRoute()
const currentPage = ref(localStorage.getItem('accident-platform-page') || 'overview')

// 判断是否为独立页面（如登录页）
const isStandalonePage = computed(() => route.meta?.standalone === true)
const theme = ref(localStorage.getItem('accident-platform-theme') || 'light')

// ── 登录状态（ref 响应式，路由变化时同步读取 localStorage） ──
const isLoggedIn = ref(false)

const syncLoginState = () => { isLoggedIn.value = !!localStorage.getItem('auth-token') }

const currentUser = computed(() => {
  if (!isLoggedIn.value) {
    return { name: '未登录', role: '请先登录', initials: '?', badge: '' }
  }
  const username = localStorage.getItem('accident-platform-user') || '张警官'
  return {
    name: username,
    role: '事故处理专员',
    initials: username.charAt(0),
    badge: 'PD-20240086'
  }
})

const handleLogout = () => {
  localStorage.removeItem('auth-token')
  localStorage.removeItem('auth-user')
  localStorage.removeItem('accident-platform-logged-in')
  localStorage.removeItem('accident-platform-user')
  localStorage.removeItem('accident-platform-login-time')
  isLoggedIn.value = false
  router.push('/login')
  showToast({ title: '已退出登录', message: '您已成功退出系统', type: 'info' })
}

const handleGoLogin = () => {
  router.push('/login')
}
const toasts = ref([])

const convertToKebabCase = (str) => {
  if (str === 'liability') {
    return 'liability-recommendation'
  }
  if (str === 'reviewPriority') {
    return 'review-priority'
  }
  if (str === 'evidenceChain') {
    return 'evidence-chain'
  }
  if (str === 'accidentTimeline') {
    return 'accident-timeline'
  }
  if (str === 'ruleGraph') {
    return 'rule-graph'
  }
  return str.replace(/([a-z0-9]|(?=[A-Z]))([A-Z])/g, '$1-$2').toLowerCase()
}

const convertToCamelCase = (str) => {
  if (str === 'liability-recommendation') {
    return 'liability'
  }
  if (str === 'review-priority') {
    return 'reviewPriority'
  }
  if (str === 'evidence-chain') {
    return 'evidenceChain'
  }
  if (str === 'accident-timeline') {
    return 'accidentTimeline'
  }
  if (str === 'rule-graph') {
    return 'ruleGraph'
  }
  return str.replace(/-([a-z])/g, (g) => g[1].toUpperCase())
}

const handlePageChange = (page) => {
  currentPage.value = page
  localStorage.setItem('accident-platform-page', page)
  const kebabCasePath = convertToKebabCase(page)
  router.push(`/${kebabCasePath}`)
}

const toggleTheme = () => {
  theme.value = theme.value === 'light' ? 'dark' : 'light'
  localStorage.setItem('acc-platform-theme', theme.value)
  document.documentElement.setAttribute('data-theme', theme.value)
}

const showToast = ({ title, message, type = 'success' }) => {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, title, message, type })
  setTimeout(() => removeToast(id), 3200)
}

const removeToast = (id) => {
  toasts.value = toasts.value.filter((toast) => toast.id !== id)
}

const toastHandler = (event) => showToast(event.detail)

// 防止多个 API 同时 401 时重复弹窗和跳转
let authExpiredHandled = false
const authExpiredHandler = (event) => {
  if (authExpiredHandled) return
  authExpiredHandled = true
  isLoggedIn.value = false
  showToast({
    title: '登录已过期',
    message: '您的登录状态已失效，请重新登录',
    type: 'warning'
  })
  if (route.path !== '/login') {
    router.push('/login')
  }
  // 3 秒后重置标记，允许下次过期检测
  setTimeout(() => { authExpiredHandled = false }, 3000)
}

watch(() => route.path, (newPath) => {
  syncLoginState()
  const pageKey = newPath.replace('/', '')
  if (pageKey) {
    const camelCasePageKey = convertToCamelCase(pageKey)
    currentPage.value = camelCasePageKey
    localStorage.setItem('accident-platform-page', camelCasePageKey)
  }
})

onMounted(() => {
  document.documentElement.setAttribute('data-theme', theme.value)
  window.addEventListener('app-toast', toastHandler)
  window.addEventListener('auth-expired', authExpiredHandler)
  syncLoginState()

  // 检查并清除无效的 caseId 缓存
  try {
    const invalidCaseKeys = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && (key.includes('caseId') || key.includes('case_id') || key === 'currentCase')) {
        const value = localStorage.getItem(key)
        // 检查是否是无效的 caseId（如 ACC-019871, ACC-264816 等）
        if (value && /^ACC-\d+$/.test(value)) {
          invalidCaseKeys.push(key)
        }
      }
    }
    if (invalidCaseKeys.length > 0) {
      invalidCaseKeys.forEach(key => localStorage.removeItem(key))
      showToast({
        title: '数据已清理',
        message: '检测到无效的案件ID，已自动清除',
        type: 'info'
      })
    }
  } catch (e) {
    // 忽略存储检查错误
  }

  // 未登录且不在登录页 → 重定向到登录页
  if (!isLoggedIn.value && route.path !== '/login') {
    router.push('/login')
  }
  // 已登录且访问根路径 → 重定向到首页
  else if (isLoggedIn.value && route.path === '/') {
    router.push('/overview')
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('app-toast', toastHandler)
  window.removeEventListener('auth-expired', authExpiredHandler)
})
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

.app { 
  display: flex; 
  height: 100vh; 
  overflow: hidden;
  position: relative;
}

.main-content {
  flex: 1;
  margin-left: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.content-area { 
  flex: 1; 
  padding: var(--content-padding); 
  overflow-y: auto;
  background: var(--bg-base);
  position: relative;
}

.content-area::-webkit-scrollbar {
  width: 6px;
}

.content-area::-webkit-scrollbar-track {
  background: transparent;
}

.content-area::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
}

[data-theme="dark"] .content-area::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
}

.content-area::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.2);
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.25s var(--ease-default);
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>