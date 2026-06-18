<template>
  <div class="toast-container">
    <div 
      v-for="toast in toasts" 
      :key="toast.id"
      class="toast"
      :class="toast.type"
    >
      <div class="toast-icon" v-html="icons.check"></div>
      <div class="toast-content">
        <div class="toast-title">{{ toast.title }}</div>
        <div class="toast-message">{{ toast.message }}</div>
      </div>
      <button class="toast-close" @click="$emit('close', toast.id)">
        <span v-html="icons.x"></span>
      </button>
    </div>
  </div>
</template>

<script setup>


// Props
const props = defineProps({
  toasts: {
    type: Array,
    default: () => []
  }
})

// Emits
const emit = defineEmits(['close'])

// SVG 图标库
const icons = {
  check: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" fill-opacity="0.15"/><polyline points="8 12 11 15 16 9" fill="none" stroke-width="2"/></svg>`,
  x: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" fill-opacity="0.15"/><line x1="9" y1="9" x2="15" y2="15" fill="none" stroke-width="2"/><line x1="15" y1="9" x2="9" y2="15" fill="none" stroke-width="2"/></svg>`
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  background: var(--bg-primary);
  border-left: 4px solid;
  min-width: 300px;
  max-width: 400px;
  animation: slideIn 0.3s ease;
}

.toast.success {
  border-left-color: var(--success-500);
}

.toast.error {
  border-left-color: var(--danger-500);
}

.toast.warning {
  border-left-color: var(--warning-500);
}

.toast.info {
  border-left-color: var(--primary-500);
}

.toast-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}

.toast.success .toast-icon {
  color: var(--success-500);
}

.toast.error .toast-icon {
  color: var(--danger-500);
}

.toast.warning .toast-icon {
  color: var(--warning-500);
}

.toast.info .toast-icon {
  color: var(--primary-500);
}

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.toast-message {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.toast-close {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s ease;
  flex-shrink: 0;
}

.toast-close:hover {
  background: var(--bg-secondary);
}

.toast-close span {
  width: 16px;
  height: 16px;
  color: var(--text-muted);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>