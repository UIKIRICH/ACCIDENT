<template>
  <div class="navigation-buttons" v-if="showNavButtons">
    <button 
      class="nav-btn prev-btn"
      :class="{ disabled: !hasPrev }"
      :disabled="!hasPrev"
      @click="goPrev"
    >
      <span class="btn-icon" v-html="icons.chevronLeft"></span>
      <span class="btn-text">上一步</span>
    </button>
    <button 
      class="nav-btn next-btn"
      :class="{ disabled: !hasNext }"
      :disabled="!hasNext"
      @click="goNext"
    >
      <span class="btn-text">下一步</span>
      <span class="btn-icon" v-html="icons.chevronRight"></span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAccidentFlow } from '../stores/useAccidentFlow'

const router = useRouter()
const route = useRoute()
const { state, getCurrentCase, isValidCaseId } = useAccidentFlow()

// 统一获取 caseId：优先 URL query，fallback store/localStorage，自动过滤无效值
const currentCaseId = () => {
  const queryId = route.query.caseId
  if (isValidCaseId(queryId)) {
    return String(queryId).trim()
  }
  return getCurrentCase()
}
// 跳转时携带 caseId 的辅助函数（仅在 caseId 有效时携带）
const pushWithCase = (path) => {
  const cid = currentCaseId()
  router.push(isValidCaseId(cid) ? { path, query: { caseId: cid } } : path)
}

const workflowRoutes = [
  { path: '/overview', name: '首页' },
  { path: '/accident-entry', name: '事故录入' },
  { path: '/video-processing', name: '视频处理' },
  { path: '/image-evidence', name: '图片证据' },
  { path: '/intelligent-analysis', name: '智能分析' },
  { path: '/liability-recommendation', name: '责任建议' },
  { path: '/rule-basis', name: '规则依据' },
  { path: '/manual-review', name: '人工复核' },
  { path: '/history-cases', name: '历史案例' }
]

const icons = {
  chevronLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>`,
  chevronRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`
}

const currentIndex = computed(() => {
  return workflowRoutes.findIndex(r => r.path === route.path)
})

const hasPrev = computed(() => {
  return currentIndex.value > 0
})

const hasNext = computed(() => {
  return currentIndex.value < workflowRoutes.length - 1
})

const showNavButtons = computed(() => {
  return currentIndex.value > 0
})

const goPrev = () => {
  if (hasPrev.value) {
    pushWithCase(workflowRoutes[currentIndex.value - 1].path)
  }
}

const goNext = () => {
  if (hasNext.value) {
    pushWithCase(workflowRoutes[currentIndex.value + 1].path)
  }
}
</script>

<style scoped>
.navigation-buttons {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-5);
  margin-top: var(--space-8);
}

.nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-8);
  border-radius: var(--radius-xl);
  border: none;
  cursor: pointer;
  font-size: var(--text-lg);
  font-weight: 600;
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
  min-width: 140px;
}

.prev-btn {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-light);
}

.prev-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
  border-color: var(--border-color);
}

.next-btn {
  background: var(--primary);
  color: white;
}

.next-btn:hover:not(:disabled) {
  background: var(--primary-dark);
}

.nav-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-icon {
  width: 16px;
  height: 16px;
}

.btn-text {
  line-height: 1;
}

@media (max-width: 768px) {
  .navigation-buttons {
    gap: var(--space-3);
  }
  
  .nav-btn {
    padding: var(--space-3) var(--space-5);
    font-size: var(--text-sm);
    min-width: 100px;
  }
  
  .btn-icon {
    width: 14px;
    height: 14px;
  }
}
</style>