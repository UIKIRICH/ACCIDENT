import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { standalone: true }
  },
  {
    path: '/overview',
    name: 'Overview',
    component: () => import('../views/Overview.vue')
  },
  {
    path: '/dashboard',
    name: 'DashboardScreen',
    component: () => import('../views/DashboardScreen.vue')
  },
  {
    path: '/accident-entry',
    name: 'AccidentEntry',
    component: () => import('../views/AccidentEntry.vue')
  },
  {
    path: '/video-processing',
    name: 'VideoProcessing',
    component: () => import('../views/VideoProcessing.vue')
  },
  {
    path: '/image-evidence',
    name: 'ImageEvidence',
    component: () => import('../views/ImageEvidenceV2.vue')
  },
  {
    path: '/intelligent-analysis',
    name: 'IntelligentAnalysis',
    component: () => import('../views/IntelligentAnalysis.vue')
  },
  {
    path: '/liability-recommendation',
    name: 'LiabilityRecommendation',
    component: () => import('../views/Liability.vue')
  },
  {
    path: '/report-detail',
    name: 'ReportDetail',
    component: () => import('../views/ReportDetail.vue')
  },
  {
    path: '/rule-basis',
    name: 'RuleBasis',
    component: () => import('../views/RuleBasis.vue')
  },
  {
    path: '/manual-review',
    name: 'ManualReview',
    component: () => import('../views/ManualReview.vue')
  },
  {
    path: '/history-cases',
    name: 'HistoryCases',
    component: () => import('../views/HistoryCases.vue')
  },
  {
    path: '/accident-timeline',
    name: 'AccidentTimeline',
    component: () => import('../views/AccidentTimeline.vue')
  },
  {
    path: '/evidence-chain',
    name: 'EvidenceChain',
    component: () => import('../views/EvidenceChain.vue')
  },
  {
    path: '/rule-graph',
    name: 'RuleGraph',
    component: () => import('../views/RuleGraph.vue')
  },
  {
    path: '/rule-library',
    name: 'RuleLibrary',
    component: () => import('../views/RuleLibrary.vue')
  },
  {
    path: '/work-queue',
    name: 'WorkQueue',
    component: () => import('../views/WorkQueue.vue')
  },
  {
    path: '/review-priority',
    name: 'ReviewPriority',
    component: () => import('../views/ReviewPriority.vue')
  },
  {
    path: '/test',
    name: 'Test',
    component: () => import('../views/TestPage.vue')
  },
  {
    path: '/mobile-capture',
    name: 'MobileCapture',
    component: () => import('../views/MobileCapture.vue'),
    meta: { standalone: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 移动端设备检测：通过 User-Agent 判断
const isMobileDevice = () => {
  const ua = navigator.userAgent || navigator.vendor || window.opera
  return /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile/i.test(ua)
    || (window.innerWidth <= 768 && 'ontouchstart' in window)
}

// 移动端允许访问的路径（独立页面，不重定向）
const MOBILE_ALLOWED_PATHS = ['/mobile-capture', '/login']

router.beforeEach((to, from) => {
  const token = localStorage.getItem('auth-token')

  // 认证检查
  if (to.path !== '/login' && !token) {
    return '/login'
  } else if (to.path === '/login' && token) {
    // 已登录用户访问登录页：移动端去采证页，桌面端去总览
    return isMobileDevice() ? '/mobile-capture' : '/overview'
  }

  // 双端分离：移动端访问桌面页面时，自动重定向到移动端采证页
  if (token && isMobileDevice() && !MOBILE_ALLOWED_PATHS.includes(to.path)) {
    return '/mobile-capture'
  }

  // 桌面端访问移动端采证页时，重定向到总览（采证是手机专用功能）
  if (token && !isMobileDevice() && to.path === '/mobile-capture') {
    return '/overview'
  }

  return true
})

export default router