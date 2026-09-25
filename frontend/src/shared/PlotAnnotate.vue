<script setup lang="ts">
/**
 * 图形批注画布（A 端渲染，B 端算数：POST /api/agent/plot/annotate）。
 *
 * 契约与诚实性约束（docs/contracts/README.md「智能体接口 v0.4」）：
 * - `samples` / `key_points` / `viewport` 全部由后端本地数学工具算出，前端**只负责画**，
 *   不改数值、不自己补点；模型在 live 模式下只写 `explanation` / `step_notes`。
 * - 采样点 y 可能为 null（该点无定义），必须断线，不能连成穿过间断点的直线。
 * - `clipped > 0` 表示有超出视窗的点被裁掉，界面必须说明。
 * - `steps[].detail` 含 LaTeX，走 MathText 渲染。
 * - 画布用 CSS 变量取色，深色主题由既有 dark-theme.css 驱动，无需另写一套配色。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChartSpline, LoaderCircle, RefreshCw } from 'lucide-vue-next'
import { api } from './api'
import { PLOT_EXPR_MAX, PLOT_QUESTION_MAX, PLOT_SAMPLES_MAX, PLOT_SAMPLES_MIN, axisTicks, checkPlotParams, createProjection, formatTick, toPolylineSegments } from './agentTools'
import { isDark } from './theme'
import MathText from './MathText.vue'

interface PlotFunction { expr?: string; latex?: string; derivative?: string | null; derivative_latex?: string | null; derivative_checked?: boolean | null }
interface PlotViewport { x_min: number; x_max: number; y_min: number; y_max: number }
interface PlotKeyPoint { kind?: string; label?: string; x?: number; y?: number | null; slope?: number | null; explain?: string }
interface PlotStep { index?: number; title?: string; detail?: string; points?: Array<[number, number | null]> }
interface PlotResponse {
  mode?: 'demo' | 'live'
  notice?: string | null
  shape?: string
  function?: PlotFunction | null
  viewport?: PlotViewport | null
  samples?: Array<[number, number | null]>
  clipped?: number
  key_points?: PlotKeyPoint[]
  steps?: PlotStep[]
  explanation?: string | null
  step_notes?: string[]
  method?: string
  honesty?: string
}

const props = defineProps<{ question: string; topic: string; disabled?: boolean }>()

const expr = ref('')
const atText = ref('')
const samples = ref(49)
const busy = ref(false)
const error = ref('')
const paramError = ref('')
const data = ref<PlotResponse | null>(null)
const canvasRef = ref<HTMLCanvasElement>()
const boxRef = ref<HTMLDivElement>()
let observer: ResizeObserver | undefined
let dpr = 1

const hasFigure = ref(false)
watch(data, value => { hasFigure.value = !!value?.viewport && !!value?.samples?.length })

function readColor(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

/** 画布是位图，CSS 变量不会自动重绘；主题切换或响应变化时重画一次。 */
function draw() {
  const canvas = canvasRef.value
  const box = boxRef.value
  const payload = data.value
  if (!canvas || !box || !payload?.viewport || !payload.samples?.length) return
  const rect = box.getBoundingClientRect()
  const width = Math.max(200, Math.round(rect.width))
  const height = Math.max(180, Math.round(Math.min(360, width * 0.62)))
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.round(width * dpr)
  canvas.height = Math.round(height * dpr)
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const ink = readColor('--muted', '#80768c')
  const line = readColor('--line', '#eeecf3')
  const primary = readColor('--primary', '#8066c6')
  /* 关键点描边要跟画布底色一致才像“空心点”。--bg 未定义，直接读容器算出来的背景色，
     这样深色主题（由 dark-theme.css 覆盖 .plot-canvas-box）也能自动适配。 */
  const surface = getComputedStyle(box).backgroundColor || '#ffffff'
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)

  const viewport = payload.viewport
  const projection = createProjection(viewport, width, height)
  const zeroX = projection.x(0)
  const zeroY = projection.y(0)
  const showAxisX = viewport.y_min <= 0 && viewport.y_max >= 0
  const showAxisY = viewport.x_min <= 0 && viewport.x_max >= 0

  /* 网格与刻度 */
  ctx.font = '10px Inter, "Segoe UI", sans-serif'
  ctx.lineWidth = 1
  for (const tick of axisTicks(viewport.x_min, viewport.x_max)) {
    const x = projection.x(tick)
    ctx.strokeStyle = line
    ctx.beginPath(); ctx.moveTo(x, projection.padding.top); ctx.lineTo(x, height - projection.padding.bottom); ctx.stroke()
    ctx.fillStyle = ink
    ctx.textAlign = 'center'
    ctx.fillText(formatTick(tick), x, height - projection.padding.bottom + 14)
  }
  for (const tick of axisTicks(viewport.y_min, viewport.y_max)) {
    const y = projection.y(tick)
    ctx.strokeStyle = line
    ctx.beginPath(); ctx.moveTo(projection.padding.left, y); ctx.lineTo(width - projection.padding.right, y); ctx.stroke()
    ctx.fillStyle = ink
    ctx.textAlign = 'right'
    ctx.fillText(formatTick(tick), projection.padding.left - 6, y + 3)
  }
  if (showAxisX) {
    ctx.strokeStyle = ink
    ctx.globalAlpha = 0.55
    ctx.beginPath(); ctx.moveTo(projection.padding.left, zeroY); ctx.lineTo(width - projection.padding.right, zeroY); ctx.stroke()
    ctx.globalAlpha = 1
  }
  if (showAxisY) {
    ctx.strokeStyle = ink
    ctx.globalAlpha = 0.55
    ctx.beginPath(); ctx.moveTo(zeroX, projection.padding.top); ctx.lineTo(zeroX, height - projection.padding.bottom); ctx.stroke()
    ctx.globalAlpha = 1
  }

  /* 曲线：y 为 null 的点断开，不跨间断点连线 */
  ctx.strokeStyle = primary
  ctx.lineWidth = 2.2
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  for (const segment of toPolylineSegments(payload.samples, projection)) {
    if (segment.length < 2) {
      const [px, py] = segment[0]
      ctx.fillStyle = primary
      ctx.beginPath(); ctx.arc(px, py, 2, 0, Math.PI * 2); ctx.fill()
      continue
    }
    ctx.beginPath()
    ctx.moveTo(segment[0][0], segment[0][1])
    for (let index = 1; index < segment.length; index++) ctx.lineTo(segment[index][0], segment[index][1])
    ctx.stroke()
  }

  /* 关键点标注（数值来自后端，前端只做定位） */
  for (const point of payload.key_points || []) {
    if (typeof point.x !== 'number' || typeof point.y !== 'number') continue
    const x = projection.x(point.x)
    const y = projection.y(point.y)
    const accent = point.kind === 'tangent' ? '#c58b3a' : point.kind === 'zero' ? '#5b9a72' : '#a06bc4'
    ctx.fillStyle = accent
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill()
    ctx.strokeStyle = surface
    ctx.lineWidth = 1.5
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.stroke()
    const label = point.label || point.kind || '点'
    ctx.font = '11px Inter, "Segoe UI", sans-serif'
    ctx.textAlign = 'left'
    ctx.fillStyle = ink
    ctx.fillText(`${label} (${formatTick(point.x)}, ${formatTick(point.y)})`, Math.min(x + 8, width - 120), Math.max(12, y - 8))
  }
}

function redraw() { void nextTick(draw) }

async function annotate() {
  if (busy.value || props.disabled) return
  error.value = ''
  paramError.value = ''
  const text = props.question.trim()
  const expression = expr.value.trim()
  if (!text && !expression) {
    paramError.value = '先在下面写下题目，或直接填一个函数表达式（例如 x^2-1）。'
    return
  }
  const param = checkPlotParams(-6, 6, samples.value)
  if (param) { paramError.value = param; return }
  const at = atText.value.trim() === '' ? null : Number(atText.value)
  if (at !== null && !Number.isFinite(at)) { paramError.value = '「在 x = ? 处标切线」需要填数字。'; return }

  busy.value = true
  try {
    data.value = await api<PlotResponse>('/agent/plot/annotate', {
      method: 'POST',
      body: JSON.stringify({
        question: text.slice(0, PLOT_QUESTION_MAX),
        expr: expression ? expression.slice(0, PLOT_EXPR_MAX) : null,
        at,
        topic: props.topic || null,
        samples: Math.trunc(samples.value),
      }),
    })
    redraw()
  } catch (e) {
    error.value = (e as Error).message
    data.value = null
  } finally {
    busy.value = false
  }
}

watch(() => props.question, value => { if (value) expr.value = '' })
watch(hasFigure, redraw)
watch(isDark, redraw)
onMounted(() => {
  if (boxRef.value && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => { if (hasFigure.value) draw() })
    observer.observe(boxRef.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="plot-panel">
    <div class="plot-head">
      <span class="plot-kicker"><ChartSpline :size="15"/> 图形批注</span>
      <p>把题目里的函数画出来，并标出零点、极值与切点；<strong>坐标与关键点全部由后端数学工具算出</strong>，模型只写讲解文字。</p>
    </div>

    <div class="plot-form">
      <label class="plot-field"><span>函数表达式（可留空，自动从题目里解析）</span>
        <input v-model="expr" type="text" :maxlength="PLOT_EXPR_MAX" :disabled="busy || disabled" placeholder="例如 x^2-1 或 sin(x)/x">
      </label>
      <label class="plot-field narrow"><span>在 x = ? 处标切线</span>
        <input v-model="atText" type="text" inputmode="decimal" :disabled="busy || disabled" placeholder="可留空">
      </label>
      <label class="plot-field narrow"><span>采样点数 {{ samples }}</span>
        <input v-model.number="samples" type="range" :min="PLOT_SAMPLES_MIN" :max="PLOT_SAMPLES_MAX" step="4" :disabled="busy || disabled">
      </label>
    </div>

    <div class="plot-actions">
      <button type="button" class="outline-button" :disabled="busy || disabled" @click="annotate">
        <LoaderCircle v-if="busy" :size="15" class="spin"/>
        <ChartSpline v-else :size="15"/>
        {{ busy ? '正在计算图形…' : data ? '重新生成' : '画出这道题的图形' }}
      </button>
      <button v-if="data" type="button" class="subtle-link" :disabled="busy" @click="redraw">
        <RefreshCw :size="14"/> 重绘
      </button>
    </div>

    <p v-if="paramError" class="form-error" role="status">{{ paramError }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>

    <template v-if="data">
      <p v-if="data.notice" class="form-error" role="status">{{ data.notice }}</p>

      <div v-show="hasFigure" ref="boxRef" class="plot-canvas-box">
        <canvas ref="canvasRef" class="plot-canvas" role="img" aria-label="函数图像与关键点标注"/>
      </div>

      <div class="plot-meta">
        <span class="small-pill" :class="data.mode === 'live' ? 'success' : ''">
          {{ data.mode === 'live' ? '模型写讲解 · 数值仍由本地工具算出' : '本地数学工具 · 演示内容' }}
        </span>
        <span v-if="data.shape === 'circle'" class="small-pill">图形：圆</span>
        <span v-if="data.clipped" class="small-pill warn">有 {{ data.clipped }} 个点超出视窗被裁掉，图像不代表全部</span>
        <span v-if="data.viewport" class="small-pill">
          x∈[{{ formatTick(data.viewport.x_min) }}, {{ formatTick(data.viewport.x_max) }}]
          · y∈[{{ formatTick(data.viewport.y_min) }}, {{ formatTick(data.viewport.y_max) }}]
        </span>
        <span v-if="data.samples?.length" class="small-pill">采样 {{ data.samples.length }} 点</span>
      </div>

      <div v-if="data.function" class="plot-function">
        <MathText :text="`$f(x)=${data.function.latex || data.function.expr || ''}$`"/>
        <p v-if="data.function.derivative_latex">
          <MathText :text="`$f'(x)=${data.function.derivative_latex}$`"/>
          <small v-if="data.function.derivative_checked">导数已用中心差商数值复核一致</small>
          <small v-else-if="data.function.derivative_checked === false">导数数值复核未通过，请自行核对</small>
          <small v-else>本次未能对该函数求导，只给出零点与采样图像</small>
        </p>
      </div>

      <ol v-if="data.steps?.length" class="plot-steps">
        <li v-for="step in data.steps" :key="step.index">
          <strong>{{ step.title }}</strong>
          <MathText v-if="step.detail" :text="step.detail"/>
          <span v-if="data.step_notes?.[Number(step.index) - 1]" class="plot-step-note">
            模型补充：{{ data.step_notes[Number(step.index) - 1] }}
          </span>
        </li>
      </ol>

      <div v-if="data.explanation" class="plot-explain">
        <span class="plot-kicker">读图讲解</span>
        <MathText :text="data.explanation"/>
      </div>

      <table v-if="data.key_points?.length" class="plot-points">
        <caption>关键点坐标（由后端算出，可对照你自己的计算）</caption>
        <thead><tr><th>类型</th><th>坐标</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="(point, index) in data.key_points" :key="index">
            <td>{{ point.label || point.kind }}</td>
            <td class="plot-coord">({{ formatTick(point.x ?? 0) }}, {{ point.y === null || point.y === undefined ? '未定义' : formatTick(point.y) }})</td>
            <td>{{ point.explain }}</td>
          </tr>
        </tbody>
      </table>

      <p v-if="data.honesty" class="plot-honesty">{{ data.honesty }}</p>
      <p v-if="data.method" class="plot-method">本次结果来源：{{ data.method }}</p>
    </template>
  </div>
</template>

<style scoped>
.plot-panel{display:flex;flex-direction:column;gap:12px;margin-top:18px;padding:16px 17px;border:1px solid var(--line);border-radius:11px;background:#fdfbff}
.plot-head{display:flex;flex-direction:column;gap:6px}
.plot-kicker{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--primary)}
.plot-head p{font-size:12px;line-height:1.8;color:var(--muted)}
.plot-form{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr) minmax(0,1fr);gap:12px}
.plot-field>span{display:block;font-size:11.5px;color:var(--muted);margin-bottom:5px}
.plot-field input[type=text]{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:#fff;font-size:12.5px}
.plot-field input[type=range]{width:100%;accent-color:var(--primary)}
.plot-actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px}
.plot-actions .outline-button{padding:10px 15px;font-size:12px}
.plot-canvas-box{width:100%;border:1px solid var(--line);border-radius:10px;background:#fff;padding:8px;overflow:hidden}
.plot-canvas{display:block;max-width:100%}
.plot-meta{display:flex;flex-wrap:wrap;gap:7px}
.plot-meta .warn{background:#fff6e6;color:#8a5300}
.plot-function{border:1px solid var(--line);border-radius:9px;padding:11px 13px;background:#fff}
.plot-function p{margin-top:8px;display:flex;flex-wrap:wrap;align-items:baseline;gap:9px}
.plot-function small{font-size:11px;color:var(--muted)}
.plot-steps{margin:0;padding-left:21px;display:flex;flex-direction:column;gap:10px}
.plot-steps li{font-size:12.5px;line-height:1.8;color:#7d6b8c}
.plot-steps strong{display:block;font-size:12.5px;color:#64576f;margin-bottom:3px}
.plot-steps :deep(.math-text){font-size:12.5px;line-height:1.85;color:inherit}
.plot-step-note{display:block;margin-top:5px;font-size:11.5px;color:var(--muted)}
.plot-explain{border-left:2px solid var(--primary);padding-left:11px}
.plot-explain :deep(.math-text){font-size:12.5px;line-height:1.9;color:#7d6b8c}
.plot-points{width:100%;border-collapse:collapse;font-size:12px}
.plot-points caption{text-align:left;font-size:11.5px;color:var(--muted);margin-bottom:7px}
.plot-points th{font-size:11.5px;font-weight:500;color:var(--muted);background:var(--soft);padding:8px 10px;text-align:left}
.plot-points td{padding:9px 10px;border-bottom:1px solid var(--line);color:#7d6b8c;line-height:1.7}
.plot-coord{font-variant-numeric:tabular-nums;white-space:nowrap}
.plot-honesty{font-size:11.5px;line-height:1.8;color:var(--muted);background:var(--soft);border-radius:8px;padding:9px 11px}
.plot-method{font-size:11px;color:var(--muted)}
.spin{animation:plot-spin 1s linear infinite}
@keyframes plot-spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none}}
@media (max-width:700px){.plot-form{grid-template-columns:1fr}.plot-points{font-size:11.5px}.plot-points th,.plot-points td{padding:7px 6px}}
</style>
