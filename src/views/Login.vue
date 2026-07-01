<template>
  <div class="login-page">
    <!-- 左侧品牌区域 -->
    <aside class="login-brand" aria-label="平台介绍">
      <!-- 背景装饰层 -->
      <div class="bg-layer">
        <div class="bg-gradient"></div>
        <div class="bg-grid"></div>
        <div class="bg-orb orb-1"></div>
        <div class="bg-orb orb-2"></div>
        <div class="bg-orb orb-3"></div>
      </div>

      <!-- 品牌内容 -->
      <div class="brand-body">
        <div class="brand-logo-wrap">
          <div class="brand-logo">
            <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
              <defs>
                <linearGradient id="shield-grad" x1="32" y1="4" x2="32" y2="60" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stop-color="#fff" stop-opacity="0.95"/>
                  <stop offset="100%" stop-color="#fff" stop-opacity="0.7"/>
                </linearGradient>
              </defs>
              <path d="M32 4L8 14v18c0 16 10 26 24 28 14-2 24-12 24-28V14L32 4z" stroke="url(#shield-grad)" stroke-width="1.8" fill="rgba(255,255,255,0.08)"/>
              <circle cx="32" cy="23" r="9" stroke="url(#shield-grad)" stroke-width="1.8" fill="rgba(255,255,255,0.06)"/>
              <path d="M23 39l5.5-9h7l5.5 9" stroke="url(#shield-grad)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="32" y1="28" x2="32" y2="41" stroke="url(#shield-grad)" stroke-width="1.8" stroke-linecap="round"/>
              <line x1="27" y1="41" x2="37" y2="41" stroke="url(#shield-grad)" stroke-width="1.8" stroke-linecap="round"/>
              <line x1="22" y1="47" x2="42" y2="47" stroke="url(#shield-grad)" stroke-width="1.3" stroke-dasharray="3 3"/>
              <line x1="20" y1="51" x2="44" y2="51" stroke="url(#shield-grad)" stroke-width="1.3" stroke-dasharray="3 3"/>
            </svg>
          </div>
        </div>

        <h1 class="brand-title">交通事故智能处理平台</h1>
        <p class="brand-desc">AI 驱动的全流程事故分析与责任认定系统</p>

        <div class="brand-features">
          <div class="ft-item" v-for="(ft, i) in features" :key="i" :style="{ animationDelay: `${0.6 + i * 0.12}s` }">
            <span class="ft-icon" v-html="ft.icon"></span>
            <span class="ft-text">{{ ft.label }}</span>
          </div>
        </div>
      </div>

      <!-- 底部版权 -->
      <p class="brand-copy">Traffic Accident Intelligent Platform v2.0</p>
    </aside>

    <!-- 右侧登录区域 -->
    <main class="login-main">
      <!-- 移动端专用顶部标题（仅手机显示） -->
      <div class="mobile-header">
        <div class="mobile-logo">
          <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
            <path d="M32 4L8 14v18c0 16 10 26 24 28 14-2 24-12 24-28V14L32 4z" stroke="#007AFF" stroke-width="2.5" fill="rgba(0,122,255,0.08)"/>
            <circle cx="32" cy="23" r="9" stroke="#007AFF" stroke-width="2.5" fill="rgba(0,122,255,0.06)"/>
            <path d="M23 39l5.5-9h7l5.5 9" stroke="#007AFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h1 class="mobile-title">交通事故智能处理平台</h1>
        <p class="mobile-subtitle">现场采证端</p>
      </div>

      <div class="login-card">
        <!-- 头部 -->
        <div class="card-head">
          <div class="head-badge">
            <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd"/></svg>
            <span>安全登录</span>
          </div>
          <h2 class="card-title">欢迎回来</h2>
          <p class="card-sub">登录您的警务账号以继续工作</p>
        </div>

        <!-- 表单 -->
        <form class="login-form" @submit.prevent="handleLogin" novalidate autocomplete="on">
          <!-- 用户名 -->
          <div class="field">
            <label class="field-label" for="username">用户名</label>
            <div class="field-input" :class="{ 'is-error': errors.username, 'is-focus': activeField === 'username' }">
              <span class="fi-icon" v-html="icons.user"></span>
              <input
                id="username"
                ref="usernameRef"
                v-model.trim="form.username"
                type="text"
                placeholder="输入用户名"
                autocomplete="username"
                :disabled="loading"
                @focus="activeField = 'username'"
                @blur="onBlur('username')"
                @input="onInput('username')"
              />
            </div>
            <transition name="msg-slide">
              <p v-if="errors.username" class="field-msg"><span class="msg-dot"></span>{{ errors.username }}</p>
            </transition>
          </div>

          <!-- 密码 -->
          <div class="field">
            <label class="field-label" for="password">密码</label>
            <div class="field-input" :class="{ 'is-error': errors.password, 'is-focus': activeField === 'password' }">
              <span class="fi-icon" v-html="icons.lock"></span>
              <input
                id="password"
                ref="passwordRef"
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="输入密码"
                autocomplete="current-password"
                :disabled="loading"
                @focus="activeField = 'password'"
                @blur="onBlur('password')"
                @input="onInput('password')"
                @keydown.enter="focusNext"
              />
              <button type="button" class="fi-toggle" :disabled="loading" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword" tabindex="-1">
                <span v-html="showPassword ? icons.eyeOff : icons.eyeOn"></span>
              </button>
            </div>
            <transition name="msg-slide">
              <p v-if="errors.password" class="field-msg"><span class="msg-dot"></span>{{ errors.password }}</p>
            </transition>
          </div>

          <!-- 选项行 -->
          <div class="options-row">
            <label class="remember">
              <input v-model="form.remember" type="checkbox" :disabled="loading" />
              <span class="remember-mark"></span>
              <span class="remember-text">记住我</span>
            </label>
            <button type="button" class="forgot-link" @click="handleForgotPassword" :disabled="loading">忘记密码？</button>
          </div>

          <!-- 提交按钮 -->
          <button type="submit" class="submit-btn" :class="{ 'is-loading': loading }" :disabled="loading">
            <span class="btn-content" :class="{ 'is-hidden': loading }">登 录</span>
            <span class="btn-loader" :class="{ 'is-visible': loading }">
              <span class="loader-dot"></span>
              <span class="loader-dot"></span>
              <span class="loader-dot"></span>
            </span>
          </button>

          <!-- 通用错误 -->
          <transition name="msg-slide">
            <div v-if="generalError" class="alert-error">
              <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
              <span>{{ generalError }}</span>
            </div>
          </transition>
        </form>

        <!-- 游客登录 -->
        <div class="guest-section">
          <button
            type="button"
            class="guest-btn"
            :disabled="loading || guestLoading"
            @click="handleGuestLogin"
          >
            <span v-if="!guestLoading" class="guest-btn-text">
              <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"/></svg>
              游客登录
            </span>
            <span v-else class="guest-loader">
              <span class="loader-dot"></span>
              <span class="loader-dot"></span>
              <span class="loader-dot"></span>
            </span>
          </button>
        </div>

        <!-- 分隔线 -->
        <div class="divider"><span class="divider-text">其他登录方式</span></div>

        <!-- 第三方登录 -->
        <div class="social-row">
          <button type="button" class="social-btn social-btn-wechat" title="微信" :disabled="loading" @click="handleSocialLogin('wechat')">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 3C4.91 3 2 5.42 2 8.44c0 1.71.96 3.23 2.47 4.22l-.7 2.1 2.42-1.21c.7.2 1.44.3 2.22.3.13 0 .27 0 .41-.02-.26-.7-.41-1.44-.41-2.22C8.41 8.92 11.2 6 14.78 6h.64C14.4 4.23 11.65 3 8.5 3zm-2.25 2.9a.85.85 0 110 1.7.85.85 0 010-1.7zm4.5 0a.85.85 0 110 1.7.85.85 0 010-1.7zm4.1 3.2c-3.45 0-6.25 2.42-6.25 5.4 0 1.72.96 3.25 2.47 4.23l-.7 2.11 2.42-1.21c.7.21 1.44.31 2.22.31 3.58 0 6.49-2.42 6.49-5.4 0-2.99-2.91-5.44-6.49-5.44l-.16 0zm-2.25 2.9a.85.85 0 110 1.7.85.85 0 010-1.7zm4.5 0a.85.85 0 110 1.7.85.85 0 010-1.7z"/></svg>
          </button>
          <button type="button" class="social-btn social-btn-phone" title="手机验证" :disabled="loading" @click="handleSocialLogin('phone')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="3" width="10" height="18" rx="2"/><line x1="12" y1="17" x2="12" y2="18"/></svg>
          </button>
          <button type="button" class="social-btn social-btn-qrcode" title="扫码登录" :disabled="loading" @click="handleSocialLogin('qrcode')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="5" y="5" width="3" height="3" fill="currentColor" stroke="none"/><rect x="14" y="3" width="7" height="7"/><rect x="16" y="5" width="3" height="3" fill="currentColor" stroke="none"/><rect x="3" y="14" width="7" height="7"/><rect x="5" y="16" width="3" height="3" fill="currentColor" stroke="none"/><rect x="14" y="14" width="3" height="3" fill="currentColor" stroke="none"/><rect x="18" y="14" width="3" height="3"/><rect x="14" y="18" width="3" height="3"/><rect x="18" y="18" width="3" height="3" fill="currentColor" stroke="none"/></svg>
          </button>
        </div>

        <!-- 底部 -->
        <p class="card-footer">
          还没有账号？<button type="button" class="register-link" @click="handleRegister" :disabled="loading">联系管理员</button>
        </p>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { notify } from '../composables/useToast.js'
import { AuthAPI } from '../api/index.js'

const router = useRouter()

// ── DOM 引用 ──
const usernameRef = ref(null)
const passwordRef = ref(null)

// ── 表单 ──
const form = reactive({ username: '', password: '', remember: false })

// ── 状态 ──
const loading = ref(false)
const guestLoading = ref(false)
const showPassword = ref(false)
const activeField = ref('')
const errors = reactive({ username: '', password: '' })
const generalError = ref('')

// ── 图标 ──
const icons = {
  user: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"/></svg>`,
  lock: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd"/></svg>`,
  eyeOn: `<svg viewBox="0 0 20 20" fill="currentColor"><path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/><path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"/></svg>`,
  eyeOff: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3.707 2.293a1 1 0 00-1.414 1.414l14 14a1 1 0 001.414-1.414l-1.473-1.473A10.014 10.014 0 0019.542 10C18.268 5.943 14.478 3 10 3a9.958 9.958 0 00-4.512 1.074l-1.78-1.781zm4.261 4.26l1.514 1.515a2.003 2.003 0 012.45 2.45l1.514 1.514a4 4 0 00-5.478-5.478z" clip-rule="evenodd"/><path d="M12.454 16.697L9.75 13.992a4 4 0 01-3.742-3.741L2.335 6.578A9.98 9.98 0 00.458 10c1.274 4.057 5.065 7 9.542 7 .847 0 1.669-.105 2.454-.303z"/></svg>`
}

// ── 左侧功能亮点 ──
const features = [
  { label: '视频关键帧智能提取', icon: `<svg viewBox="0 0 20 20" fill="currentColor"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 11h4M8 14h4"/></svg>` },
  { label: 'AI 多模型融合事故分析', icon: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 5a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2h-2.22l.123.489.804.804A1 1 0 0113 18H7a1 1 0 01-.707-1.707l.804-.804L7.22 15H5a2 2 0 01-2-2V5zm5.771 7H5V5h10v7H8.771z" clip-rule="evenodd"/></svg>` },
  { label: '法规依据自动匹配', icon: `<svg viewBox="0 0 20 20" fill="currentColor"><path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z"/></svg>` },
  { label: '公正智能责任认定', icon: `<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l6-6z" clip-rule="evenodd"/></svg>` },
]

// ── 验证 ──
const rules = {
  username: (v) => !v ? '请输入用户名' : v.length < 2 ? '用户名至少需要 2 个字符' : '',
  password: (v) => !v ? '请输入密码' : v.length < 6 ? '密码至少需要 6 个字符' : '',
}

const validateField = (name) => { errors[name] = rules[name](form[name]) }
const onBlur = (name) => { activeField.value = ''; validateField(name) }
const onInput = (name) => { if (errors[name]) errors[name] = ''; if (generalError.value) generalError.value = '' }

const focusNext = () => {
  if (activeField.value === 'username' && form.username) { activeField.value = ''; nextTick(() => passwordRef.value?.focus()) }
}

// ── 登录 ──
const handleLogin = async () => {
  generalError.value = ''
  validateField('username')
  validateField('password')
  if (errors.username || errors.password) return
  loading.value = true
  try {
    const result = await AuthAPI.login(form.username, form.password)
    if (result.success && result.data) {
      localStorage.setItem('auth-token', result.data.token)
      localStorage.setItem('auth-user', JSON.stringify(result.data.user))
      if (form.remember) {
        localStorage.setItem('accident-platform-remembered-user', form.username)
      } else {
        localStorage.removeItem('accident-platform-remembered-user')
      }
      window.dispatchEvent(new CustomEvent('auth-change', { detail: { loggedIn: true } }))
      // 根据设备类型跳转：移动端去采证页，桌面端去总览
      const ua = navigator.userAgent || ''
      const isMobile = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile/i.test(ua)
        || (window.innerWidth <= 768 && 'ontouchstart' in window)
      router.push(isMobile ? '/mobile-capture' : '/overview')
      notify({ title: '登录成功', message: `欢迎回来，${result.data.user.display_name || form.username}`, type: 'success' })
    } else {
      generalError.value = result.message || '登录失败，请检查用户名或密码'
    }
  } catch (err) {
    generalError.value = err.message || '网络错误，请检查后端服务是否运行'
  } finally {
    loading.value = false
  }
}

const handleForgotPassword = () => notify({ title: '提示', message: '请联系系统管理员重置密码', type: 'info' })
const handleSocialLogin = (p) => notify({ title: '提示', message: { wechat: '微信扫码', phone: '短信验证', qrcode: '扫码登录' }[p] + '功能开发中', type: 'info' })
const handleRegister = () => notify({ title: '提示', message: '请联系系统管理员创建账号', type: 'info' })

// ── 游客登录 ──
const handleGuestLogin = async () => {
  guestLoading.value = true
  try {
    const result = await AuthAPI.guestLogin()
    if (result.success && result.data) {
      localStorage.setItem('auth-token', result.data.token)
      localStorage.setItem('auth-user', JSON.stringify(result.data.user))
      window.dispatchEvent(new CustomEvent('auth-change', { detail: { loggedIn: true } }))
      const ua = navigator.userAgent || ''
      const isMobile = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile/i.test(ua)
        || (window.innerWidth <= 768 && 'ontouchstart' in window)
      router.push(isMobile ? '/mobile-capture' : '/overview')
      notify({ title: '游客登录成功', message: '您已进入演示模式，部分功能可能受限', type: 'info' })
    } else {
      generalError.value = result.message || '游客登录失败'
    }
  } catch (err) {
    generalError.value = err.message || '网络错误，请检查后端服务是否运行'
  } finally {
    guestLoading.value = false
  }
}

// 恢复记住的用户名
;(() => {
  const u = localStorage.getItem('accident-platform-remembered-user')
  if (u) { form.username = u; form.remember = true }
})()
</script>

<style scoped>
/* ============================================================
   登录页面 - 现代设计
   ============================================================ */

/* ── 页面 ── */
.login-page {
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-base);
  overflow: hidden;
}

/* ============================================================
   左侧品牌区
   ============================================================ */
.login-brand {
  flex: 0 0 46%;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--slate-900);
  isolation: isolate;
}

/* ── 背景层 ── */
.bg-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
}

.bg-gradient {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 30% 20%, #1d4ed8 0%, transparent 50%),
    radial-gradient(ellipse 60% 50% at 70% 80%, #7c3aed 0%, transparent 50%),
    radial-gradient(ellipse 50% 40% at 50% 50%, #0f172a 0%, transparent 70%);
}

.bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse 70% 70% at 50% 50%, black 30%, transparent 70%);
}

/* ── 浮动光球 ── */
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
  animation: orb-float 14s ease-in-out infinite;
}

.orb-1 {
  width: 360px; height: 360px;
  background: rgba(37, 99, 235, 0.5);
  top: -10%; left: -15%;
  animation-delay: 0s;
}

.orb-2 {
  width: 280px; height: 280px;
  background: rgba(124, 58, 237, 0.4);
  bottom: -10%; right: -10%;
  animation-delay: -5s;
}

.orb-3 {
  width: 200px; height: 200px;
  background: rgba(59, 130, 246, 0.45);
  top: 50%; left: 60%;
  animation-delay: -9s;
}

@keyframes orb-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(30px, -25px) scale(1.08); }
  50% { transform: translate(-15px, 20px) scale(0.95); }
  75% { transform: translate(-25px, -15px) scale(1.05); }
}

/* ── 品牌内容 ── */
.brand-body {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: var(--space-10) var(--space-8);
  max-width: 420px;
  animation: fade-up 0.8s var(--ease-default) both;
}

@keyframes fade-up {
  from { opacity: 0; transform: translateY(24px); }
  to { opacity: 1; transform: translateY(0); }
}

.brand-logo-wrap {
  display: inline-block;
  margin-bottom: var(--space-8);
  position: relative;
}

.brand-logo-wrap::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 26px;
  background: conic-gradient(from 0deg, rgba(255,255,255,0.3), rgba(59,130,246,0.5), rgba(124,58,237,0.3), rgba(255,255,255,0.3));
  animation: logo-spin 6s linear infinite;
  z-index: -1;
  filter: blur(2px);
}

@keyframes logo-spin {
  to { transform: rotate(360deg); }
}

.brand-logo {
  width: 80px;
  height: 80px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 22px;
  backdrop-filter: blur(16px);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255,255,255,0.1);
}

.brand-logo svg { width: 48px; height: 48px; }

.brand-title {
  font-size: 1.75rem;
  font-weight: 800;
  color: #fff;
  letter-spacing: -0.02em;
  line-height: 1.25;
  margin-bottom: var(--space-3);
}

.brand-desc {
  font-size: var(--text-sm);
  color: rgba(255, 255, 255, 0.6);
  line-height: var(--leading-relaxed);
  margin-bottom: var(--space-10);
}

/* ── 功能亮点 ── */
.brand-features {
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: left;
  max-width: 300px;
  margin: 0 auto;
}

.ft-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: rgba(255, 255, 255, 0.75);
  font-size: var(--text-sm);
  padding: 9px 12px;
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
  animation: fade-up 0.6s var(--ease-default) both;
}

.ft-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.95);
  transform: translateX(4px);
}

.ft-icon {
  width: 30px; height: 30px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-sm);
}

.ft-icon svg { width: 15px; height: 15px; }

.ft-text { font-weight: 500; }

/* ── 版权 ── */
.brand-copy {
  position: absolute;
  bottom: var(--space-6);
  left: 0; right: 0;
  text-align: center;
  font-size: var(--text-xs);
  color: rgba(255, 255, 255, 0.3);
  letter-spacing: 0.03em;
  z-index: 1;
}

/* ============================================================
   右侧登录区
   ============================================================ */
.login-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-10) var(--space-8);
  background: var(--bg-base);
}

.login-card {
  width: 100%;
  max-width: 400px;
  animation: fade-up 0.6s var(--ease-default) 0.2s both;
}

/* ── 头部 ── */
.card-head {
  text-align: center;
  margin-bottom: var(--space-8);
}

.head-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 14px;
  border-radius: var(--radius-full);
  background: var(--primary-50);
  color: var(--primary-700);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.03em;
  margin-bottom: var(--space-5);
}

.head-badge svg { width: 14px; height: 14px; }

[data-theme="dark"] .head-badge {
  background: rgba(59, 130, 246, 0.12);
  color: var(--primary-300);
}

.card-title {
  font-size: var(--text-3xl);
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.03em;
  line-height: 1.2;
  margin-bottom: var(--space-1);
}

.card-sub {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

/* ============================================================
   表单字段
   ============================================================ */
.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.field { display: flex; flex-direction: column; gap: 6px; }

.field-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  padding-left: 2px;
}

.field-input {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--bg-primary);
  border: 1.5px solid var(--border-medium);
  border-radius: var(--radius-lg);
  padding: 0 14px;
  transition: all var(--transition-fast);
  position: relative;
}

.field-input:focus-within,
.field-input.is-focus {
  border-color: var(--primary-400);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1);
}

.field-input.is-error {
  border-color: var(--danger-500);
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.08);
  animation: shake 0.4s var(--ease-default);
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-4px); }
  40% { transform: translateX(4px); }
  60% { transform: translateX(-3px); }
  80% { transform: translateX(2px); }
}

.field-input input {
  flex: 1;
  border: none; background: transparent;
  padding: 13px 0;
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  color: var(--text-primary);
  outline: none;
  line-height: var(--leading-normal);
}

.field-input input::placeholder { color: var(--text-muted); }
.field-input input:disabled { opacity: 0.5; cursor: not-allowed; }

.fi-icon {
  width: 18px; height: 18px;
  flex-shrink: 0;
  color: var(--text-muted);
  display: flex; align-items: center;
  transition: color var(--transition-fast);
}

.fi-icon svg { width: 18px; height: 18px; }

.field-input:focus-within .fi-icon,
.field-input.is-focus .fi-icon { color: var(--primary-500); }

.fi-toggle {
  width: 32px; height: 32px;
  border: none; background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted);
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.fi-toggle:hover { background: var(--bg-secondary); color: var(--text-secondary); }
.fi-toggle:disabled { opacity: 0.4; cursor: not-allowed; }
.fi-toggle span { width: 18px; height: 18px; display: flex; }
.fi-toggle svg { width: 18px; height: 18px; }

/* ── 字段错误信息 ── */
.field-msg {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--danger);
  padding-left: 4px;
}

.msg-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--danger);
  flex-shrink: 0;
}

/* ── 消息滑入动画 ── */
.msg-slide-enter-active { transition: all var(--transition-fast); }
.msg-slide-leave-active { transition: all 100ms var(--ease-default); }
.msg-slide-enter-from,
.msg-slide-leave-to { opacity: 0; transform: translateY(-4px); }

/* ============================================================
   选项行
   ============================================================ */
.options-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ── 自定义 checkbox ── */
.remember {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  user-select: none;
  position: relative;
}

.remember input {
  position: absolute;
  opacity: 0;
  width: 0; height: 0;
}

.remember-mark {
  width: 18px; height: 18px;
  border: 1.5px solid var(--border-medium);
  border-radius: 5px;
  background: var(--bg-primary);
  flex-shrink: 0;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
}

.remember input:checked + .remember-mark {
  background: var(--primary-600);
  border-color: var(--primary-600);
}

.remember input:checked + .remember-mark::after {
  content: '';
  width: 5px; height: 9px;
  border: solid white;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg) translateY(-1px);
}

.remember input:focus-visible + .remember-mark {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
}

.remember-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* ── 忘记密码 ── */
.forgot-link {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--primary-600);
  background: none;
  border: none;
  cursor: pointer;
  font-family: var(--font-sans);
  padding: 0;
  transition: color var(--transition-fast);
}

.forgot-link:hover { color: var(--primary-700); }
.forgot-link:disabled { opacity: 0.5; cursor: not-allowed; }

/* ============================================================
   提交按钮
   ============================================================ */
.submit-btn {
  width: 100%;
  height: 48px;
  position: relative;
  border: none;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--primary-700) 0%, var(--primary-500) 100%);
  color: white;
  font-size: var(--text-base);
  font-weight: 700;
  font-family: var(--font-sans);
  letter-spacing: 0.08em;
  cursor: pointer;
  overflow: hidden;
  transition: all var(--transition-normal);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.3), inset 0 1px 0 rgba(255,255,255,0.15);
  margin-top: var(--space-1);
}

.submit-btn::before {
  content: '';
  position: absolute;
  top: 0; left: -100%;
  width: 100%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent);
  transition: left 0.6s ease;
}

.submit-btn:hover::before { left: 100%; }

.submit-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 25px rgba(37, 99, 235, 0.4), inset 0 1px 0 rgba(255,255,255,0.15);
}

.submit-btn:active { transform: translateY(0); }

.submit-btn.is-loading {
  cursor: not-allowed;
  background: linear-gradient(135deg, var(--primary-600) 0%, var(--primary-400) 100%);
}

.submit-btn.is-loading::before { display: none; }
.submit-btn:disabled { transform: none; }

/* ── 按钮内容 ── */
.btn-content {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity var(--transition-fast);
}

.btn-content.is-hidden { opacity: 0; pointer-events: none; }

/* ── Three-dot loader ── */
.btn-loader {
  position: absolute;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn-loader.is-visible { display: flex; }

.loader-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  animation: dot-bounce 1.2s ease-in-out infinite;
}

.loader-dot:nth-child(1) { animation-delay: 0s; }
.loader-dot:nth-child(2) { animation-delay: 0.15s; }
.loader-dot:nth-child(3) { animation-delay: 0.3s; }

@keyframes dot-bounce {
  0%, 50%, 100% { transform: translateY(0); opacity: 0.5; }
  25% { transform: translateY(-8px); opacity: 1; }
}

/* ============================================================
   通用错误提示
   ============================================================ */
.alert-error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 11px 14px;
  border-radius: var(--radius-md);
  background: var(--danger-50);
  border: 1px solid var(--danger-100);
  font-size: var(--text-sm);
  color: var(--danger-700);
  animation: shake 0.4s var(--ease-default);
}

.alert-error svg { width: 16px; height: 16px; flex-shrink: 0; color: var(--danger-500); }

[data-theme="dark"] .alert-error {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.15);
}

/* ============================================================
   游客登录
   ============================================================ */
.guest-section {
  margin-top: var(--space-3);
}

.guest-btn {
  width: 100%;
  height: 44px;
  position: relative;
  border: 1.5px solid var(--border-medium);
  border-radius: var(--radius-lg);
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 600;
  font-family: var(--font-sans);
  cursor: pointer;
  overflow: hidden;
  transition: all var(--transition-normal);
  display: flex;
  align-items: center;
  justify-content: center;
}

.guest-btn:hover {
  border-color: var(--primary-400);
  color: var(--primary-600);
  background: var(--primary-50);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

[data-theme="dark"] .guest-btn:hover {
  background: rgba(59, 130, 246, 0.06);
}

.guest-btn:active { transform: translateY(0); }
.guest-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

.guest-btn-text {
  display: flex;
  align-items: center;
  gap: 8px;
}

.guest-btn-text svg {
  width: 16px;
  height: 16px;
  opacity: 0.7;
}

.guest-loader {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

/* ============================================================
   分隔线
   ============================================================ */
.divider {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin: var(--space-6) 0;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border-light);
}

.divider-text {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
  font-weight: 500;
}

/* ============================================================
   第三方登录
   ============================================================ */
.social-row {
  display: flex;
  justify-content: center;
  gap: var(--space-4);
}

.social-btn {
  width: 48px; height: 48px;
  border: 1.5px solid var(--border-medium);
  border-radius: var(--radius-lg);
  background: var(--bg-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
}

.social-btn:hover {
  box-shadow: var(--shadow-sm);
  transform: translateY(-2px);
}

.social-btn:active { transform: translateY(0); }
.social-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
.social-btn svg { width: 22px; height: 22px; }

/* 微信 - 绿色 */
.social-btn-wechat:hover {
  border-color: #07C160;
  color: #07C160;
  background: #ecfdf5;
}
[data-theme="dark"] .social-btn-wechat:hover {
  background: rgba(7, 193, 96, 0.1);
}

/* 手机验证 - 蓝色 */
.social-btn-phone:hover {
  border-color: var(--primary-400);
  color: var(--primary-600);
  background: var(--primary-50);
}
[data-theme="dark"] .social-btn-phone:hover {
  background: rgba(59, 130, 246, 0.1);
}

/* 扫码 - 紫色 */
.social-btn-qrcode:hover {
  border-color: #7c3aed;
  color: #7c3aed;
  background: #f5f3ff;
}
[data-theme="dark"] .social-btn-qrcode:hover {
  background: rgba(124, 58, 237, 0.1);
}

/* ============================================================
   底部
   ============================================================ */
.card-footer {
  margin-top: var(--space-8);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.register-link {
  color: var(--primary-600);
  font-weight: 600;
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: color var(--transition-fast);
}

.register-link:hover { color: var(--primary-700); text-decoration: underline; }
.register-link:disabled { opacity: 0.5; cursor: not-allowed; }

/* ============================================================
   响应式
   ============================================================ */

/* 移动端专用顶部标题：默认隐藏，900px 以下显示 */
.mobile-header { display: none; }

@media (max-width: 900px) {
  .login-brand { display: none; }
  .login-main {
    flex: 1;
    padding: var(--space-8) var(--space-6);
  }
  .login-card { max-width: 440px; }

  /* 移动端显示顶部标题 */
  .mobile-header {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 32px;
  }
  .mobile-logo {
    width: 64px;
    height: 64px;
    margin-bottom: 12px;
  }
  .mobile-logo svg { width: 100%; height: 100%; }
  .mobile-title {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary, #1c1c1e);
    margin: 0 0 4px;
    text-align: center;
  }
  .mobile-subtitle {
    font-size: 14px;
    color: #007AFF;
    font-weight: 500;
    margin: 0;
  }
}

@media (max-width: 480px) {
  .login-main {
    padding: 40px 20px 24px;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .login-card { max-width: 100%; }
  .card-head { margin-bottom: var(--space-6); }
  .card-title { font-size: var(--text-2xl); }
  .field-input { padding: 0 12px; }
  .field-input input { padding: 13px 0; font-size: 16px; /* 防止 iOS 缩放 */ }
  .submit-btn {
    height: 48px; /* 触摸友好 */
    font-size: 16px;
  }
  .guest-btn {
    height: 48px; /* 触摸友好 */
    font-size: 15px;
  }
  .social-btn { width: 44px; height: 44px; }

  /* 移动端顶部标题优化 */
  .mobile-header { margin-bottom: 28px; }
  .mobile-logo { width: 56px; height: 56px; }
  .mobile-title { font-size: 18px; }
  .mobile-subtitle { font-size: 13px; }
}
</style>