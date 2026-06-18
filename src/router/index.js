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
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('auth-token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/overview')
  } else {
    next()
  }
})

export default router