<script setup lang="ts">
/* 拍照搜题：相机取景 → 框选裁剪 → 压缩 → POST /agent/recognize → 确认文本回填提问框。
   硬约束：非 live 结果必须明确标注，接口失败如实展示后端原文，不编造识别内容。 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { AlertTriangle, Camera, CheckCircle2, ImagePlus, RefreshCw, ScanLine } from 'lucide-vue-next'
import { api, ApiError, type User } from './api'

interface RecognizeResponse {
  mode?: string
  text?: string
  confidence?: number | null
  warnings?: string[]
  requires_confirmation?: boolean
  suggested_topic?: string | null
}
interface Shot {
  dataUrl: string; base64: string; mediaType: string
  width: number; height: number; bytes: number
  fullW: number; fullH: number; source: string
}
interface Frame { x: number; y: number; w: number; h: number }
type Step = 'camera' | 'crop' | 'result'
type DragMode = 'new' | 'move' | 'nw' | 'n' | 'ne' | 'w' | 'e' | 'sw' | 's' | 'se'

const props = defineProps<{ modelValue: boolean; user: User }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; apply: [string] }>()

const step = ref<Step>('camera')
const busy = ref(false)
const toastText = ref('')
const camError = ref('')
const camErrorDetail = ref('')

/* SECTION: camera-state */
const stageRef = ref<HTMLElement>()
const videoRef = ref<HTMLVideoElement>()
const stillRef = ref<HTMLImageElement>()
const canvasRef = ref<HTMLCanvasElement>()
const fileRef = ref<HTMLInputElement>()
let stream: MediaStream | null = null
let stillUrl = ''
let stillImg: HTMLImageElement | null = null
let torchTrack: MediaStreamTrack | null = null
const torchOn = ref(false)
const torchOk = ref(false)
const facing = ref<'environment' | 'user'>('environment')
const showGrid = ref(true)
const camLive = ref(false)

/* SECTION: frame-state */
const frame = ref<Frame>({ x: 0.1, y: 0.28, w: 0.8, h: 0.32 })
const cssW = ref(0), cssH = ref(0), dpr = ref(1)
let drag: { mode: DragMode; sx: number; sy: number; ox: number; oy: number; ow: number; oh: number } | null = null

/* SECTION: shot-state */
const shot = ref<Shot | null>(null)
let fullCanvas: HTMLCanvasElement | null = null
let fullSource = ''
const maxSide = ref(1280)
const quality = ref(0.82)
const format = ref<'image/jpeg' | 'image/png'>('image/jpeg')
const hint = ref('')

/* SECTION: result-state */
const resultText = ref('')
const resultLive = ref(false)
const confidence = ref<number | null>(null)
const warnings = ref<string[]>([])
const topic = ref('')
const errorText = ref('')
const needsConfirm = ref(true)

const hintPlaceholder = computed(() =>
  props.user.role === 'teacher' ? '例如：教学设计相关的题目文字' : '例如：高等数学 极限 计算题（可留空）')
const sizeLabel = computed(() => {
  const w = Math.round(frame.value.w * cssW.value), h = Math.round(frame.value.h * cssH.value)
  return w > 0 && h > 0 ? `${w} × ${h}` : '—'
})
const confidencePct = computed(() => {
  const c = confidence.value
  if (typeof c !== 'number' || !isFinite(c)) return null
  return Math.round(Math.min(100, Math.max(0, c <= 1 ? c * 100 : c)))
})
const byteText = computed(() => {
  const n = shot.value?.bytes ?? 0
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(2)} MB`
})

const toastErr = ref(false)
function toast(msg: string, isError = false) {
  toastText.value = msg
  toastErr.value = isError
  window.setTimeout(() => { if (toastText.value === msg) toastText.value = '' }, 2400)
}
const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v)

/* SECTION: camera */
const CAM_ERRORS: Record<string, [string, string]> = {
  NotAllowedError: ['相机权限被拒绝', '请在浏览器地址栏左侧的站点设置里把「相机」改为允许，然后重试。无痕窗口和企业策略可能直接拒绝。'],
  NotFoundError: ['没有找到可用摄像头', '这台设备可能没有摄像头或驱动未就绪，可以改用「相册」选择一张题目照片，后续流程完全一致。'],
  NotReadableError: ['摄像头被其他程序占用', '请关闭正在使用相机的应用（视频会议、相机 App、其他标签页）后重试。'],
  OverconstrainedError: ['设备不支持所请求的摄像头参数', '已尝试回退到任意可用摄像头；若仍失败请用「相册」导入。'],
  SecurityError: ['当前环境不是安全上下文', '浏览器只在 https、localhost 下开放相机。若通过局域网 IP（如 http://192.168.x.x）访问，请改用 https 或本机 localhost；也可以先用「相册」导入。'],
  AbortError: ['相机启动被中断', '请重试一次；反复失败时改用「相册」导入。']
}
function stopCamera() {
  if (stream) { stream.getTracks().forEach(t => { try { t.stop() } catch { /* 已停止 */ } }) }
  stream = null; torchTrack = null; torchOk.value = false; torchOn.value = false; camLive.value = false
  if (stillUrl) { URL.revokeObjectURL(stillUrl); stillUrl = '' }
  stillImg = null
  if (stillRef.value) { stillRef.value.hidden = true; stillRef.value.removeAttribute('src') }
  if (videoRef.value) videoRef.value.hidden = false
}
async function startCamera(fallbackAny = false) {
  if (!navigator.mediaDevices?.getUserMedia) {
    camError.value = '当前浏览器不支持 getUserMedia'
    camErrorDetail.value = 'navigator.mediaDevices.getUserMedia 不存在。请使用较新的 Chrome / Edge / Safari，并通过 https 或 localhost 访问。可改用「相册」导入。'
    camLive.value = false
    return
  }
  camError.value = ''; camErrorDetail.value = ''
  stopCamera()
  const video: MediaTrackConstraints = fallbackAny
    ? { width: { ideal: 1920 }, height: { ideal: 1080 } }
    : { facingMode: { ideal: facing.value }, width: { ideal: 1920 }, height: { ideal: 1080 } }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: video })
  } catch (error) {
    const name = (error as DOMException)?.name ?? ''
    if (name === 'OverconstrainedError' && !fallbackAny) return startCamera(true)
    stream = null; camLive.value = false
    const info = CAM_ERRORS[name]
    camError.value = info?.[0] ?? name ?? '相机不可用'
    camErrorDetail.value = info?.[1] ?? ((error as Error)?.message ?? '未知原因，请改用「相册」导入题目照片。')
    return
  }
  const v = videoRef.value
  if (!v) { stopCamera(); return }
  v.hidden = false
  if (stillRef.value) stillRef.value.hidden = true
  v.srcObject = stream
  try { await v.play() } catch { toast('自动播放被拦截，请点击画面一次开始预览') }
  camLive.value = true
  const track = stream.getVideoTracks()[0]
  torchTrack = track ?? null
  torchOk.value = !!(track?.getCapabilities?.() as { torch?: boolean } | undefined)?.torch
  await nextTick()
  resizeCanvas()
}
async function toggleTorch() {
  if (!torchTrack || !torchOk.value) return
  const next = !torchOn.value
  try {
    await torchTrack.applyConstraints({ advanced: [{ torch: next } as unknown as MediaTrackConstraintSet] })
    torchOn.value = next
    toast(next ? '闪光灯已开启' : '闪光灯已关闭')
  } catch { toast('这台设备不支持运行时切换闪光灯', true); torchOk.value = false }
}
async function flip() {
  facing.value = facing.value === 'environment' ? 'user' : 'environment'
  stillImg = null
  await startCamera()
}

/* SECTION: frame-draw */
function resizeCanvas() {
  const cv = canvasRef.value, st = stageRef.value
  if (!cv || !st) return
  const r = st.getBoundingClientRect()
  if (!r.width || !r.height) return
  cssW.value = r.width; cssH.value = r.height
  dpr.value = Math.min(window.devicePixelRatio || 1, 2)
  cv.width = Math.max(1, Math.round(r.width * dpr.value))
  cv.height = Math.max(1, Math.round(r.height * dpr.value))
  draw()
}
function draw() {
  const cv = canvasRef.value
  if (!cv) return
  const ctx = cv.getContext('2d')
  if (!ctx) return
  const w = cssW.value, h = cssH.value
  if (!w || !h) return
  ctx.setTransform(dpr.value, 0, 0, dpr.value, 0, 0)
  ctx.clearRect(0, 0, w, h)
  const f = frame.value
  const x = f.x * w, y = f.y * h, fw = f.w * w, fh = f.h * h

  ctx.save()
  ctx.fillStyle = 'rgba(18,14,28,.55)'
  ctx.beginPath(); ctx.rect(0, 0, w, h); ctx.rect(x, y, fw, fh); ctx.fill('evenodd')
  ctx.restore()

  ctx.save()
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.5
  ctx.strokeRect(x, y, fw, fh)
  if (showGrid.value) {
    ctx.strokeStyle = 'rgba(255,255,255,.30)'; ctx.lineWidth = 1
    for (let i = 1; i <= 2; i++) {
      ctx.beginPath(); ctx.moveTo(x + fw * i / 3, y); ctx.lineTo(x + fw * i / 3, y + fh); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(x, y + fh * i / 3); ctx.lineTo(x + fw, y + fh * i / 3); ctx.stroke()
    }
  }
  const L = Math.min(22, Math.min(fw, fh) * 0.26)
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 3.5; ctx.lineCap = 'round'
  const corners: Array<[number, number, number, number]> = [[x, y, 1, 1], [x + fw, y, -1, 1], [x, y + fh, 1, -1], [x + fw, y + fh, -1, -1]]
  corners.forEach(([cx, cy, dx, dy]) => {
    ctx.beginPath(); ctx.moveTo(cx + dx * L, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + dy * L); ctx.stroke()
  })
  ctx.restore()
}
function hitTest(px: number, py: number): DragMode {
  const f = frame.value, w = cssW.value, h = cssH.value
  const x = f.x * w, y = f.y * h, fw = f.w * w, fh = f.h * h
  const T = 22
  const pts: Record<string, [number, number]> = {
    nw: [x, y], n: [x + fw / 2, y], ne: [x + fw, y], w: [x, y + fh / 2],
    e: [x + fw, y + fh / 2], sw: [x, y + fh], s: [x + fw / 2, y + fh], se: [x + fw, y + fh]
  }
  for (const key of Object.keys(pts)) {
    if (Math.abs(px - pts[key][0]) <= T && Math.abs(py - pts[key][1]) <= T) return key as DragMode
  }
  return px >= x && px <= x + fw && py >= y && py <= y + fh ? 'move' : 'new'
}
const CURSORS: Record<DragMode, string> = {
  nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize',
  n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize', move: 'move', new: 'crosshair'
}
const cursor = ref('crosshair')
function localPoint(ev: PointerEvent) {
  const cv = canvasRef.value
  if (!cv) return { x: 0, y: 0 }
  const r = cv.getBoundingClientRect()
  return { x: ev.clientX - r.left, y: ev.clientY - r.top }
}
function onDown(ev: PointerEvent) {
  if (!hasSource()) return
  const p = localPoint(ev)
  const mode = hitTest(p.x, p.y)
  const f = frame.value
  if (mode === 'new') frame.value = { x: clamp(p.x / cssW.value, 0, 1), y: clamp(p.y / cssH.value, 0, 1), w: 0, h: 0 }
  drag = { mode, sx: p.x, sy: p.y, ox: f.x, oy: f.y, ow: f.w, oh: f.h }
  const target = ev.currentTarget as HTMLElement | null
  target?.setPointerCapture?.(ev.pointerId)
  ev.preventDefault()
  draw()
}
function onMove(ev: PointerEvent) {
  const p = localPoint(ev)
  if (!drag) { cursor.value = hasSource() ? CURSORS[hitTest(p.x, p.y)] : 'default'; return }
  ev.preventDefault()
  const dx = (p.x - drag.sx) / cssW.value, dy = (p.y - drag.sy) / cssH.value
  const MIN = 0.06
  const f = frame.value
  if (drag.mode === 'new') {
    const ax = drag.ox, ay = drag.oy
    const bx = clamp(ax + dx, 0, 1), by = clamp(ay + dy, 0, 1)
    f.x = Math.min(ax, bx); f.y = Math.min(ay, by)
    f.w = Math.max(Math.abs(bx - ax), MIN); f.h = Math.max(Math.abs(by - ay), MIN)
    f.x = clamp(f.x, 0, 1 - f.w); f.y = clamp(f.y, 0, 1 - f.h)
  } else if (drag.mode === 'move') {
    f.w = drag.ow; f.h = drag.oh
    f.x = clamp(drag.ox + dx, 0, 1 - drag.ow)
    f.y = clamp(drag.oy + dy, 0, 1 - drag.oh)
  } else {
    let x1 = drag.ox, y1 = drag.oy, x2 = drag.ox + drag.ow, y2 = drag.oy + drag.oh
    if (drag.mode.includes('w')) x1 = clamp(drag.ox + dx, 0, x2 - MIN)
    if (drag.mode.includes('e')) x2 = clamp(drag.ox + drag.ow + dx, x1 + MIN, 1)
    if (drag.mode.includes('n')) y1 = clamp(drag.oy + dy, 0, y2 - MIN)
    if (drag.mode.includes('s')) y2 = clamp(drag.oy + drag.oh + dy, y1 + MIN, 1)
    f.x = x1; f.y = y1; f.w = x2 - x1; f.h = y2 - y1
  }
  draw()
}
function onUp() {
  if (!drag) return
  drag = null
  if (frame.value.w < 0.05 || frame.value.h < 0.04) {
    frame.value = { x: 0.1, y: 0.28, w: 0.8, h: 0.32 }
    toast('选框太小，已恢复默认范围')
  }
  draw()
}
function fullFrame() { frame.value = { x: 0.03, y: 0.03, w: 0.94, h: 0.94 }; draw(); toast('选框已铺满画面') }

/* SECTION: capture-compress */
function hasSource() { return (camLive.value && !!videoRef.value?.videoWidth) || !!stillImg }
function sourceNode(): { node: CanvasImageSource; vw: number; vh: number; label: string } | null {
  const v = videoRef.value
  if (camLive.value && v && v.videoWidth) return { node: v, vw: v.videoWidth, vh: v.videoHeight, label: '相机实拍' }
  if (stillImg?.naturalWidth) return { node: stillImg, vw: stillImg.naturalWidth, vh: stillImg.naturalHeight, label: '相册导入' }
  return null
}
function capture() {
  const src = sourceNode()
  if (!src) { toast('相机还没准备好，请稍候或改用相册导入', true); return }
  const w = cssW.value, h = cssH.value
  if (!w || !h) return
  const f = frame.value
  const rw = f.w * w, rh = f.h * h
  if (rw < 8 || rh < 8) { toast('选框太小，请重新框选', true); return }

  /* object-fit:cover 反推容器区域对应的源矩形，保证裁剪坐标精确 */
  const scale = Math.max(w / src.vw, h / src.vh)
  const sw0 = w / scale, sh0 = h / scale
  const offX = (src.vw - sw0) / 2, offY = (src.vh - sh0) / 2
  const k = sw0 / w
  const sx = clamp(offX + f.x * w * k, 0, Math.max(0, src.vw - 1))
  const sy = clamp(offY + f.y * h * k, 0, Math.max(0, src.vh - 1))
  const sw = Math.max(1, Math.min(rw * k, src.vw - sx))
  const sh = Math.max(1, Math.min(rh * k, src.vh - sy))

  const mirror = facing.value === 'user' && camLive.value
  const c = document.createElement('canvas')
  c.width = Math.round(sw); c.height = Math.round(sh)
  const g = c.getContext('2d')
  if (!g) { toast('当前浏览器无法创建画布', true); return }
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high'
  if (mirror) { g.translate(c.width, 0); g.scale(-1, 1) }
  g.drawImage(src.node, sx, sy, sw, sh, 0, 0, c.width, c.height)

  fullCanvas = c
  fullSource = src.label
  compress()
  step.value = 'crop'
}
function compress() {
  if (!fullCanvas) return
  const fw = fullCanvas.width, fh = fullCanvas.height
  const long = Math.max(fw, fh)
  const ratio = long > maxSide.value ? maxSide.value / long : 1
  const c = document.createElement('canvas')
  c.width = Math.max(1, Math.round(fw * ratio)); c.height = Math.max(1, Math.round(fh * ratio))
  const g = c.getContext('2d')
  if (!g) return
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high'
  if (format.value === 'image/jpeg') { g.fillStyle = '#ffffff'; g.fillRect(0, 0, c.width, c.height) }
  g.drawImage(fullCanvas, 0, 0, c.width, c.height)
  let dataUrl = ''
  try {
    dataUrl = c.toDataURL(format.value, format.value === 'image/png' ? undefined : quality.value)
  } catch (error) { toast(`导出图片失败：${(error as Error).message}`, true); return }
  const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1)
  shot.value = {
    dataUrl, base64, mediaType: format.value, width: c.width, height: c.height,
    bytes: Math.floor(base64.length * 3 / 4), fullW: fw, fullH: fh, source: fullSource
  }
  toast(`已裁剪 ${c.width}×${c.height}，约 ${(shot.value.bytes / 1024).toFixed(0)} KB`)
}
watch([maxSide, quality, format], () => { if (fullCanvas && step.value !== 'camera') compress() })

function pickFile() { fileRef.value?.click() }
function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) { toast('请选择图片文件', true); return }
  if (file.size > 20 * 1024 * 1024) { toast('图片超过 20 MB，请先压缩后再导入', true); return }
  const url = URL.createObjectURL(file)
  const img = new Image()
  img.onload = () => {
    if (stream) { stream.getTracks().forEach(t => { try { t.stop() } catch { /* 已停止 */ } }); stream = null; camLive.value = false }
    stillImg = img
    if (stillUrl) URL.revokeObjectURL(stillUrl)
    stillUrl = url
    if (stillRef.value) { stillRef.value.src = url; stillRef.value.hidden = false }
    if (videoRef.value) videoRef.value.hidden = true
    camError.value = ''; camErrorDetail.value = ''
    step.value = 'camera'
    nextTick(() => resizeCanvas())
    toast('已载入相册图片，请框选题目区域')
  }
  img.onerror = () => { URL.revokeObjectURL(url); toast('图片解码失败，请换一张再试', true) }
  img.src = url
}

/* SECTION: recognize */
async function recognize() {
  if (!shot.value) { toast('请先拍摄或导入图片', true); return }
  busy.value = true; errorText.value = ''; warnings.value = []; topic.value = ''; confidence.value = null
  try {
    const data = await api<RecognizeResponse>('/agent/recognize', {
      method: 'POST',
      body: JSON.stringify({
        image_base64: shot.value.base64,
        media_type: shot.value.mediaType,
        hint: hint.value.trim().slice(0, 200)
      })
    })
    resultLive.value = data.mode === 'live'
    resultText.value = typeof data.text === 'string' ? data.text : JSON.stringify(data, null, 2)
    confidence.value = typeof data.confidence === 'number' ? data.confidence : null
    warnings.value = Array.isArray(data.warnings) ? data.warnings : []
    topic.value = data.suggested_topic ?? ''
    needsConfirm.value = data.requires_confirmation !== false
    step.value = 'result'
  } catch (error) {
    resultLive.value = false
    resultText.value = ''
    errorText.value = error instanceof ApiError ? `HTTP ${error.status}：${error.message}` : (error as Error).message
    step.value = 'result'
  } finally { busy.value = false }
}
function useText() {
  const text = resultText.value.trim()
  if (!text) { toast('识别文本为空，无法带入提问', true); return }
  emit('apply', text)
  emit('update:modelValue', false)
}
function retake() {
  shot.value = null; fullCanvas = null; errorText.value = ''; resultText.value = ''
  step.value = 'camera'
  if (!camLive.value && !stillImg) void startCamera()
  nextTick(() => resizeCanvas())
}

/* SECTION: lifecycle */
function onResize() { if (props.modelValue && step.value === 'camera') resizeCanvas() }
watch(() => props.modelValue, async open => {
  if (open) {
    step.value = 'camera'
    shot.value = null; fullCanvas = null; errorText.value = ''; resultText.value = ''
    warnings.value = []; confidence.value = null; topic.value = ''
    await nextTick(); await startCamera(); resizeCanvas()
    window.addEventListener('resize', onResize)
  } else {
    window.removeEventListener('resize', onResize)
    stopCamera()
  }
})
onBeforeUnmount(() => { window.removeEventListener('resize', onResize); stopCamera() })
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="拍照搜题"
    width="min(560px, 94vw)"
    align-center
    destroy-on-close
    class="photo-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <!-- SECTION: camera-step -->
    <div v-if="step === 'camera'" class="ps-body">
      <div ref="stageRef" class="ps-stage">
        <video ref="videoRef" class="ps-media" playsinline muted autoplay aria-label="相机实时画面"/>
        <img ref="stillRef" class="ps-media" alt="相册导入的待裁剪图片" hidden>
        <canvas
          ref="canvasRef" class="ps-canvas" :style="{ cursor }"
          @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointercancel="onUp"
        />
        <div v-if="camError" class="ps-fallback">
          <span class="ps-fallback-icon"><AlertTriangle :size="22"/></span>
          <h4>{{ camError }}</h4>
          <p>{{ camErrorDetail }}</p>
          <div class="ps-fallback-actions">
            <button type="button" class="outline-button" @click="startCamera()"><RefreshCw :size="15"/> 重试相机</button>
            <button type="button" class="outline-button" @click="pickFile"><ImagePlus :size="15"/> 从相册选择</button>
          </div>
        </div>
        <div class="ps-stage-top">
          <button v-if="torchOk" type="button" class="ps-icon" :class="{ on: torchOn }" aria-label="切换闪光灯" @click="toggleTorch">
            <ScanLine :size="16"/>
          </button>
          <button type="button" class="ps-icon" :class="{ on: showGrid }" aria-label="切换三分网格" @click="showGrid = !showGrid; draw()">
            <span class="ps-grid-glyph"/>
          </button>
        </div>
        <div class="ps-stage-foot"><span class="ps-size">{{ sizeLabel }}</span></div>
      </div>
      <p class="ps-tip">拖动选框对准题目，拉动四角可调整大小；框外区域会被裁掉。</p>
      <div class="ps-actions">
        <button type="button" class="outline-button" @click="pickFile"><ImagePlus :size="15"/> 相册</button>
        <button type="button" class="primary-button" @click="capture"><Camera :size="16"/> 拍摄并裁剪</button>
        <button type="button" class="outline-button" @click="flip"><RefreshCw :size="15"/> 翻转</button>
      </div>
      <button type="button" class="ps-quiet" @click="fullFrame">选框铺满画面</button>
      <input ref="fileRef" type="file" accept="image/*" class="ps-file" aria-label="从相册选择图片" @change="onFile">
    </div>

    <!-- SECTION: crop-step -->
    <div v-else-if="step === 'crop'" class="ps-body">
      <div class="ps-preview">
        <img v-if="shot" :src="shot.dataUrl" alt="裁剪后的题目图片">
      </div>
      <dl class="ps-meta">
        <div><dt>裁剪前</dt><dd>{{ shot?.fullW }} × {{ shot?.fullH }}</dd></div>
        <div><dt>压缩后</dt><dd>{{ shot?.width }} × {{ shot?.height }}</dd></div>
        <div><dt>图片体积</dt><dd>{{ byteText }}</dd></div>
        <div><dt>来源</dt><dd>{{ shot?.source }}</dd></div>
      </dl>
      <details class="ps-details">
        <summary>压缩参数与提示词</summary>
        <label class="ps-field"><span>题目提示 hint</span>
          <input v-model="hint" type="text" maxlength="200" :placeholder="hintPlaceholder">
        </label>
        <label class="ps-field"><span>最长边 {{ maxSide }} px</span>
          <input v-model.number="maxSide" type="range" min="480" max="2048" step="32">
        </label>
        <label class="ps-field"><span>JPEG 质量 {{ quality.toFixed(2) }}</span>
          <input v-model.number="quality" type="range" min="0.4" max="0.98" step="0.02">
        </label>
        <label class="ps-field"><span>输出格式</span>
          <select v-model="format">
            <option value="image/jpeg">JPEG（体积小）</option>
            <option value="image/png">PNG（更清晰）</option>
          </select>
        </label>
        <p class="ps-note">质量越低体积越小，但公式笔画可能变糊。识别不清时把它调高再拍一次。</p>
      </details>
      <div class="ps-actions">
        <button type="button" class="outline-button" @click="retake"><RefreshCw :size="15"/> 重新框选</button>
        <button type="button" class="primary-button" :disabled="busy || !shot" @click="recognize">
          <ScanLine :size="16"/> {{ busy ? '识别中…' : '提交识别' }}
        </button>
      </div>
    </div>

    <!-- SECTION: result-step -->
    <div v-else class="ps-body">
      <div v-if="errorText" class="form-error" role="alert">
        <strong>后端未返回识别结果</strong><br>{{ errorText }}<br>
        <span class="ps-note">常见原因：未登录（401/403）、后端未配置视觉模型（503）、接口地址不可达。</span>
      </div>
      <div v-else-if="resultLive" class="ps-ok" role="status">
        <CheckCircle2 :size="16"/>
        <span>来自真实接口的识别草稿{{ needsConfirm ? '，需要你确认或修改后才算最终题目文本' : '' }}。</span>
      </div>
      <div v-else class="ps-warn" role="status">
        <AlertTriangle :size="16"/>
        <span>本次返回未标记为 live，下方文本不能当作真实模型识别结果使用。</span>
      </div>

      <img v-if="shot" class="ps-thumb" :src="shot.dataUrl" alt="本次提交的裁剪图片">

      <label class="ps-field"><span>识别文本（可直接修改）</span>
        <textarea v-model="resultText" rows="6" placeholder="识别结果会出现在这里"/>
      </label>

      <div v-if="confidencePct !== null || warnings.length || topic" class="ps-chips">
        <span v-if="topic" class="small-pill">建议知识点：{{ topic }}</span>
        <span v-if="confidencePct !== null" class="small-pill">置信度 {{ confidencePct }}%</span>
        <span v-for="w in warnings" :key="w" class="small-pill warn">{{ w }}</span>
      </div>

      <div class="ps-actions">
        <button type="button" class="outline-button" @click="retake"><RefreshCw :size="15"/> 重新拍照</button>
        <button type="button" class="primary-button" :disabled="!resultText.trim()" @click="useText">
          <CheckCircle2 :size="16"/> 用这段文字提问
        </button>
      </div>
      <p class="ps-note">确认后文本会填入左侧提问框，由你决定是否发送；发送仍走原有的对话保存流程。</p>
    </div>

    <div v-if="toastText" class="ps-toast" role="status">{{ toastText }}</div>
  </el-dialog>
</template>

<style scoped>
.ps-body{display:flex;flex-direction:column;gap:12px}
.ps-stage{position:relative;width:100%;aspect-ratio:3/4;max-height:52vh;border-radius:12px;overflow:hidden;background:#14101f;touch-action:none}
.ps-media{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#14101f}
.ps-canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none}
.ps-stage-top{position:absolute;top:8px;right:8px;display:flex;gap:6px;z-index:2}
.ps-icon{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:rgba(16,12,26,.55);color:#fff;border:1px solid rgba(255,255,255,.22);backdrop-filter:blur(6px)}
.ps-icon.on{background:#fff;color:#3d3550}
.ps-grid-glyph{width:14px;height:14px;border:1.5px solid currentColor;border-radius:2px;background:linear-gradient(currentColor,currentColor) center/1.5px 100% no-repeat,linear-gradient(currentColor,currentColor) center/100% 1.5px no-repeat}
.ps-stage-foot{position:absolute;left:8px;bottom:8px;z-index:2}
.ps-size{font-size:11px;padding:4px 8px;border-radius:6px;background:rgba(16,12,26,.62);color:#fff;font-variant-numeric:tabular-nums}
.ps-fallback{position:absolute;inset:0;z-index:3;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:20px;text-align:center;background:rgba(20,16,31,.94);color:#efeaf7}
.ps-fallback-icon{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2)}
.ps-fallback h4{font-size:14px}
.ps-fallback p{font-size:12px;line-height:1.75;color:#cdc4dd;max-width:38ch}
.ps-fallback-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:4px}
.ps-fallback .outline-button{background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.25);color:#fff;padding:8px 14px;font-size:12px}
.ps-tip{font-size:12px;color:var(--muted);line-height:1.7;text-align:center}
.ps-actions{display:flex;gap:8px;flex-wrap:wrap}
.ps-actions .primary-button,.ps-actions .outline-button{flex:1;min-width:120px;padding:11px 14px;font-size:13px}
.ps-quiet{align-self:center;background:transparent;color:var(--muted);font-size:12px;text-decoration:underline;text-underline-offset:3px}
.ps-file{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.ps-preview{border-radius:12px;overflow:hidden;border:1px solid var(--line);background:#faf9fd;display:grid;place-items:center;min-height:140px}
.ps-preview img{max-width:100%;max-height:44vh;object-fit:contain}
.ps-meta{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:0}
.ps-meta>div{background:var(--soft);border-radius:9px;padding:8px 10px;min-width:0}
.ps-meta dt{font-size:11px;color:var(--muted)}
.ps-meta dd{margin:2px 0 0;font-size:13px;font-weight:600;word-break:break-all}
.ps-details{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:#fff}
.ps-details summary{cursor:pointer;font-size:12.5px;color:var(--primary);font-weight:500}
.ps-details[open]{padding-bottom:12px}
.ps-field{display:block;margin-top:10px}
.ps-field>span{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}
.ps-field input[type=text],.ps-field select,.ps-field textarea{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:9px;background:#fff;font-size:13px}
.ps-field input[type=range]{width:100%;accent-color:var(--primary)}
.ps-field textarea{resize:vertical;line-height:1.75}
.ps-note{font-size:11.5px;color:var(--muted);line-height:1.7;margin-top:8px}
.ps-ok,.ps-warn{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;line-height:1.7;padding:10px 12px;border-radius:9px}
.ps-ok{background:#eaf5ee;color:#4c7f61}
.ps-warn{background:#fff6e6;color:#8a5300}
.ps-thumb{width:100%;max-height:180px;object-fit:contain;border-radius:10px;border:1px solid var(--line);background:#faf9fd}
.ps-chips{display:flex;flex-wrap:wrap;gap:6px}
.ps-chips .warn{background:#fff6e6;color:#8a5300}
.ps-toast{margin-top:4px;text-align:center;font-size:12px;color:var(--muted)}
@media (max-width:700px){.ps-stage{aspect-ratio:3/4;max-height:46vh}.ps-meta{grid-template-columns:1fr 1fr}}
</style>
