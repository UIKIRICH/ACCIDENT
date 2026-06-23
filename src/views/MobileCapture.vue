<template>
  <div class="mobile-capture">
    <!-- 左侧抽屉遮罩 -->
    <div v-if="drawerOpen" class="drawer-overlay" @click="toggleDrawer"></div>

    <!-- 左侧抽屉栏 -->
    <div class="drawer-panel" :class="{ open: drawerOpen }">
      <div class="drawer-header">
        <div class="drawer-avatar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </div>
        <div class="drawer-user">
          <div class="drawer-name">张警官</div>
          <div class="drawer-role">事故处理专员</div>
        </div>
      </div>

      <nav class="drawer-menu">
        <button class="drawer-item" @click="toggleDrawer">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
          <span>首页总览</span>
        </button>
        <button class="drawer-item" @click="handleExport">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          <span>导出采证记录</span>
        </button>
        <button class="drawer-item" @click="goHome">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          <span>返回后台</span>
        </button>
        <button class="drawer-item danger" @click="handleClose">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <path d="M9 9l6 6M15 9l-6 6"/>
          </svg>
          <span>关闭采证</span>
        </button>
        <button class="drawer-item danger" @click="handleLogout">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
          <span>退出登录</span>
        </button>
      </nav>

      <div class="drawer-footer">
        <div class="drawer-version">版本 v1.0.0</div>
        <div class="drawer-copyright">事故处理平台</div>
      </div>
    </div>

    <!-- 顶部导航栏 -->
    <header class="top-bar">
      <button class="menu-btn" @click="toggleDrawer" aria-label="菜单">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="3" y1="6" x2="21" y2="6"/>
          <line x1="3" y1="12" x2="21" y2="12"/>
          <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>
      <h1 class="top-title">现场采证</h1>
      <span class="top-spacer"></span>
    </header>

    <!-- 表单视图 -->
    <main v-if="!submitted" class="form-wrap">
      <section class="card">
        <h2 class="card-title">事故基本信息</h2>

        <div class="field">
          <label class="label">事故地点 <span class="req">*</span></label>
          <input
            v-model="form.location"
            class="input"
            type="text"
            placeholder="如：建国路与文化路交叉口"
          />
        </div>

        <div class="field">
          <label class="label">事故类型</label>
          <select v-model="form.accidentType" class="select">
            <option>追尾</option>
            <option>变道碰撞</option>
            <option>转弯未让行</option>
            <option>多车事故</option>
            <option>其他</option>
          </select>
        </div>

        <div class="field">
          <label class="label">事故时间</label>
          <input v-model="form.accidentTime" class="input" type="datetime-local" />
        </div>

        <div class="field">
          <label class="label">事故描述 <span class="req">*</span></label>
          <textarea
            v-model="form.description"
            class="textarea"
            rows="4"
            placeholder="请简要描述事故发生经过..."
          ></textarea>
        </div>
      </section>

      <section class="card">
        <div class="card-head-row">
          <h2 class="card-title">现场图片</h2>
          <button class="add-btn" @click="imageInput?.click()">+ 添加</button>
          <input
            ref="imageInput"
            type="file"
            accept="image/*"
            multiple
            class="hidden-input"
            @change="onImagesChange"
          />
        </div>

        <div v-if="images.length === 0" class="empty-hint">点击“添加”上传现场照片（可多选）</div>
        <div v-else class="image-grid">
          <div v-for="(img, idx) in images" :key="idx" class="image-cell">
            <img :src="img.preview" class="thumb" alt="现场图片" />
            <button class="del-btn" @click="removeImage(idx)" aria-label="删除">×</button>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head-row">
          <h2 class="card-title">行车视频 <span class="optional">（可选）</span></h2>
          <button v-if="!videoFile" class="add-btn" @click="videoInput?.click()">+ 选择</button>
          <button v-else class="add-btn" @click="removeVideo">移除</button>
          <input
            ref="videoInput"
            type="file"
            accept="video/*"
            class="hidden-input"
            @change="onVideoChange"
          />
        </div>

        <div v-if="!videoFile" class="empty-hint">上传行车记录仪视频（MP4 / MOV）</div>
        <div v-else class="video-preview">
          <video :src="videoPreview" class="video-el" controls></video>
          <p class="file-name">{{ videoFile.name }}</p>
        </div>
      </section>

      <section class="card">
        <h2 class="card-title">补充说明</h2>
        <textarea
          v-model="form.remark"
          class="textarea"
          rows="3"
          placeholder="其他需要补充的文字说明..."
        ></textarea>
      </section>

      <button class="submit-btn" :disabled="submitting" @click="handleSubmit">
        <span v-if="!submitting">一键提交采证</span>
        <span v-else class="loading-row">
          <span class="spinner"></span>
          提交中...
        </span>
      </button>
    </main>

    <!-- 成功视图 -->
    <main v-else class="success-wrap">
      <div class="check-circle">
        <svg viewBox="0 0 52 52" class="check-svg">
          <circle class="check-circle-bg" cx="26" cy="26" r="24" />
          <path class="check-path" d="M14 27 l8 8 l16 -16" />
        </svg>
      </div>
      <h2 class="success-title">采证提交成功</h2>
      <p class="success-sub">您的现场证据已成功上传</p>

      <div class="result-card">
        <div class="result-row">
          <span class="result-label">案件编号</span>
          <span class="result-value highlight">{{ caseId }}</span>
        </div>
        <div class="result-row">
          <span class="result-label">证据状态</span>
          <span class="result-value">已上传至后端</span>
        </div>
        <div class="result-row">
          <span class="result-label">研判平台</span>
          <span class="result-value">案件已创建</span>
        </div>
      </div>

      <div class="success-actions">
        <button class="action-btn primary" @click="resetAll">再录一单</button>
        <button class="action-btn ghost" @click="goHome">返回首页</button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { CasesAPI } from '../api/index.js'
import { notify } from '../composables/useToast'

const router = useRouter()

const drawerOpen = ref(false)
const submitting = ref(false)
const submitted = ref(false)
const caseId = ref('')

const pad = (n) => String(n).padStart(2, '0')
const nowStr = () => {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const form = reactive({
  location: '',
  description: '',
  accidentType: '追尾',
  accidentTime: nowStr(),
  remark: ''
})

const images = ref([])
const videoFile = ref(null)
const videoPreview = ref('')
const imageInput = ref(null)
const videoInput = ref(null)

const getToken = () => localStorage.getItem('auth-token') || ''

const toggleDrawer = () => {
  drawerOpen.value = !drawerOpen.value
}

const onImagesChange = (e) => {
  const files = [...(e.target.files || [])]
  let count = 0
  files.forEach((file) => {
    if (!file.type.startsWith('image/')) return
    images.value.push({
      file,
      preview: URL.createObjectURL(file)
    })
    count++
  })
  e.target.value = ''
  if (count) notify({ title: '已添加图片', message: `本次新增 ${count} 张` })
}

const removeImage = (idx) => {
  const img = images.value[idx]
  if (img?.preview) URL.revokeObjectURL(img.preview)
  images.value.splice(idx, 1)
}

const onVideoChange = (e) => {
  const file = e.target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('video/')) {
    notify({ title: '格式错误', message: '请选择视频文件', type: 'warning' })
    return
  }
  if (videoPreview.value) URL.revokeObjectURL(videoPreview.value)
  videoFile.value = file
  videoPreview.value = URL.createObjectURL(file)
  e.target.value = ''
}

const removeVideo = () => {
  if (videoPreview.value) URL.revokeObjectURL(videoPreview.value)
  videoFile.value = null
  videoPreview.value = ''
  if (videoInput.value) videoInput.value.value = ''
}

const uploadFile = async (url, file) => {
  const formData = new FormData()
  formData.append('file', file)
  const options = { method: 'POST', body: formData }
  const token = getToken()
  if (token) options.headers = { Authorization: `Bearer ${token}` }

  const res = await fetch(url, options)
  if (!res.ok) {
    let detail = `上传失败: ${res.status}`
    try {
      const err = await res.json()
      detail = err.detail || err.message || detail
    } catch { }
    throw new Error(detail)
  }
  return res.json().catch(() => ({}))
}

const uploadTextEvidence = async (cid, content) => {
  const token = getToken()
  const res = await fetch(`/api/cases/${cid}/evidences`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({ type: 'text', content })
  })
  if (!res.ok) {
    let detail = `文本证据上传失败: ${res.status}`
    try {
      const err = await res.json()
      detail = err.detail || err.message || detail
    } catch { }
    throw new Error(detail)
  }
  return res.json().catch(() => ({}))
}

const handleSubmit = async () => {
  if (!form.location.trim()) {
    notify({ title: '请完善信息', message: '请填写事故地点', type: 'warning' })
    return
  }
  if (!form.description.trim()) {
    notify({ title: '请完善信息', message: '请填写事故描述', type: 'warning' })
    return
  }

  submitting.value = true
  try {
    const accidentTime = form.accidentTime ? form.accidentTime.replace('T', ' ') : ''
    const result = await CasesAPI.create({
      accident_type: form.accidentType,
      location: form.location.trim(),
      description: form.description.trim(),
      accident_time: accidentTime
    })

    if (!result.success || !result.data) {
      throw new Error(result.message || '创建案件失败')
    }
    const cid = result.data.case_id || result.data.id
    if (!cid) throw new Error('未获取到案件编号')

    const textContent = [form.description.trim(), form.remark.trim()].filter(Boolean).join('\n\n')
    if (textContent) {
      try {
        await uploadTextEvidence(cid, textContent)
      } catch (err) {
        console.warn('文本证据上传失败:', err)
      }
    }

    for (const img of images.value) {
      try {
        await uploadFile('/api/analyze_image_file_evidence/', img.file)
      } catch (err) {
        console.warn('图片上传失败:', err)
      }
    }

    if (videoFile.value) {
      try {
        await uploadFile('/api/upload_video/', videoFile.value)
      } catch (err) {
        console.warn('视频上传失败:', err)
      }
    }

    caseId.value = cid
    submitted.value = true
    notify({ title: '提交成功', message: `案件 ${cid} 已提交` })
  } catch (err) {
    console.error('提交采证失败:', err)
    notify({ title: '提交失败', message: err.message || '请稍后重试', type: 'error' })
  } finally {
    submitting.value = false
  }
}

const handleExport = async () => {
  toggleDrawer()
  if (!caseId.value) {
    notify({ title: '提示', message: '请先提交采证后再导出', type: 'warning' })
    return
  }
  try {
    const token = getToken()
    const res = await fetch(`/api/cases/${caseId.value}/report/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (!res.ok) {
      throw new Error('导出失败')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `采证记录_${caseId.value}.html`
    a.click()
    URL.revokeObjectURL(url)
    notify({ title: '导出成功', message: '采证记录已下载' })
  } catch (err) {
    console.error('导出失败:', err)
    notify({ title: '导出失败', message: err.message || '请稍后重试', type: 'error' })
  }
}

const handleClose = () => {
  toggleDrawer()
  if (window.confirm('确定要关闭采证吗？未提交的数据将会丢失。')) {
    router.push('/overview')
  }
}

const handleLogout = () => {
  toggleDrawer()
  if (window.confirm('确定要退出登录吗？')) {
    // 清除登录态
    localStorage.removeItem('auth-token')
    localStorage.removeItem('auth-user')
    notify({ title: '已退出登录', message: '请重新登录', type: 'success' })
    router.push('/login')
  }
}

const resetAll = () => {
  images.value.forEach((img) => img.preview && URL.revokeObjectURL(img.preview))
  if (videoPreview.value) URL.revokeObjectURL(videoPreview.value)

  images.value = []
  videoFile.value = null
  videoPreview.value = ''
  form.location = ''
  form.description = ''
  form.accidentType = '追尾'
  form.remark = ''
  form.accidentTime = nowStr()
  caseId.value = ''
  submitted.value = false
}

const goHome = () => {
  // 移动端留在采证页，桌面端返回总览
  const ua = navigator.userAgent || ''
  const isMobile = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile/i.test(ua)
    || (window.innerWidth <= 768 && 'ontouchstart' in window)
  if (isMobile) {
    toggleDrawer()
    resetAll()
  } else {
    router.push('/overview')
  }
}
const goBack = () => {
  if (window.history.length > 1) router.back()
  else router.push('/overview')
}

onBeforeUnmount(() => {
  images.value.forEach((img) => img.preview && URL.revokeObjectURL(img.preview))
  if (videoPreview.value) URL.revokeObjectURL(videoPreview.value)
})
</script>

<style scoped>
.mobile-capture {
  max-width: 480px;
  margin: 0 auto;
  min-height: 100vh;
  min-height: 100dvh;
  background: #F2F2F7;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.drawer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 100;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.drawer-panel {
  position: fixed;
  top: 0;
  left: 0;
  width: 260px;
  height: 100vh;
  background: #fff;
  z-index: 101;
  transform: translateX(-100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  box-shadow: 4px 0 20px rgba(0, 0, 0, 0.1);
}

.drawer-panel.open {
  transform: translateX(0);
}

.drawer-header {
  padding: 32px 20px 24px;
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 0.5px solid #e5e5ea;
  background: linear-gradient(135deg, #007AFF 0%, #0051D5 100%);
}

.drawer-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.drawer-avatar svg {
  width: 28px;
  height: 28px;
}

.drawer-user {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.drawer-name {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}

.drawer-role {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.drawer-menu {
  flex: 1;
  padding: 12px 0;
}

.drawer-item {
  width: 100%;
  padding: 14px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  background: transparent;
  border: none;
  color: #1c1c1e;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}

.drawer-item svg {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  color: #8e8e93;
}

.drawer-item:hover {
  background: #f2f2f7;
}

.drawer-item:active {
  background: #e5e5ea;
}

.drawer-item.danger {
  color: #FF3B30;
}

.drawer-item.danger svg {
  color: #FF3B30;
}

.drawer-footer {
  padding: 16px 20px;
  border-top: 0.5px solid #e5e5ea;
  text-align: center;
}

.drawer-version {
  font-size: 12px;
  color: #8e8e93;
}

.drawer-copyright {
  font-size: 12px;
  color: #8e8e93;
  margin-top: 4px;
}

.top-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 8px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
}

.menu-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  color: #007AFF;
  border-radius: 10px;
}

.menu-btn:active {
  background: rgba(0, 0, 0, 0.05);
}

.menu-btn svg {
  width: 22px;
  height: 22px;
}

.top-title {
  flex: 1;
  text-align: center;
  font-size: 17px;
  font-weight: 600;
  color: #1c1c1e;
  margin: 0;
}

.top-spacer {
  width: 40px;
}

.form-wrap {
  flex: 1;
  padding: 16px 16px 32px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.card {
  background: #fff;
  border-radius: 16px;
  padding: 18px 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 4px 12px rgba(0, 0, 0, 0.03);
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1c1c1e;
  margin: 0 0 14px;
}

.card-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.card-head-row .card-title {
  margin: 0;
}

.optional {
  font-size: 13px;
  font-weight: 400;
  color: #8e8e93;
}

.field {
  margin-bottom: 14px;
}

.field:last-child {
  margin-bottom: 0;
}

.label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #6b6b70;
  margin-bottom: 7px;
}

.req {
  color: #FF3B30;
}

.input,
.select,
.textarea {
  width: 100%;
  border: 1px solid #e5e5ea;
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 15px;
  font-family: inherit;
  color: #1c1c1e;
  background: #f9f9fb;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

.input:focus,
.select:focus,
.textarea:focus {
  border-color: #007AFF;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}

.textarea {
  resize: vertical;
  min-height: 88px;
  line-height: 1.5;
}

.select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%238e8e93'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 18px;
  padding-right: 38px;
}

.add-btn {
  border: none;
  background: rgba(0, 122, 255, 0.1);
  color: #007AFF;
  font-size: 14px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: 999px;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
}

.add-btn:active {
  background: rgba(0, 122, 255, 0.18);
}

.hidden-input {
  display: none;
}

.empty-hint {
  font-size: 13px;
  color: #8e8e93;
  padding: 18px 0;
  text-align: center;
  border: 1px dashed #dcdce0;
  border-radius: 12px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.image-cell {
  position: relative;
  width: 100%;
  padding-top: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: #f2f2f7;
}

.thumb {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.del-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.del-btn:active {
  background: rgba(0, 0, 0, 0.75);
}

.video-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.video-el {
  width: 100%;
  border-radius: 12px;
  background: #000;
  max-height: 260px;
}

.file-name {
  margin: 0;
  font-size: 13px;
  color: #8e8e93;
  word-break: break-all;
}

.submit-btn {
  margin-top: 6px;
  height: 52px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #007AFF 0%, #0051D5 100%);
  color: #fff;
  font-size: 17px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(0, 81, 213, 0.32);
  transition: transform 0.15s, box-shadow 0.2s, opacity 0.2s;
}

.submit-btn:active {
  transform: translateY(1px);
  box-shadow: 0 3px 10px rgba(0, 81, 213, 0.28);
}

.submit-btn:disabled {
  opacity: 0.75;
  cursor: not-allowed;
}

.loading-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.success-wrap {
  flex: 1;
  padding: 48px 24px 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.check-circle {
  width: 96px;
  height: 96px;
  margin-bottom: 20px;
}

.check-svg {
  width: 100%;
  height: 100%;
}

.check-circle-bg {
  fill: none;
  stroke: #34C759;
  stroke-width: 3;
  stroke-dasharray: 151;
  stroke-dashoffset: 151;
  animation: draw-circle 0.6s ease forwards;
}

.check-path {
  fill: none;
  stroke: #34C759;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 34;
  stroke-dashoffset: 34;
  animation: draw-check 0.4s 0.5s ease forwards;
}

@keyframes draw-circle {
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes draw-check {
  to {
    stroke-dashoffset: 0;
  }
}

.success-title {
  font-size: 22px;
  font-weight: 700;
  color: #1c1c1e;
  margin: 0 0 6px;
}

.success-sub {
  font-size: 14px;
  color: #8e8e93;
  margin: 0 0 28px;
}

.result-card {
  width: 100%;
  background: #fff;
  border-radius: 16px;
  padding: 4px 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 4px 12px rgba(0, 0, 0, 0.03);
}

.result-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 0;
  border-bottom: 0.5px solid #e5e5ea;
}

.result-row:last-child {
  border-bottom: none;
}

.result-label {
  font-size: 15px;
  color: #6b6b70;
}

.result-value {
  font-size: 15px;
  color: #1c1c1e;
  font-weight: 500;
}

.result-value.highlight {
  color: #007AFF;
  font-weight: 700;
  font-size: 16px;
}

.success-actions {
  width: 100%;
  margin-top: 28px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-btn {
  height: 50px;
  border: none;
  border-radius: 14px;
  font-size: 16px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.15s;
}

.action-btn.primary {
  background: linear-gradient(135deg, #007AFF 0%, #0051D5 100%);
  color: #fff;
  box-shadow: 0 6px 18px rgba(0, 81, 213, 0.28);
}

.action-btn.ghost {
  background: #fff;
  color: #007AFF;
  border: 1px solid #dcdce0;
}

.action-btn:active {
  transform: translateY(1px);
}
</style>