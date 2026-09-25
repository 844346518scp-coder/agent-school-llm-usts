/** A 端接入 B 模块第三阶段能力（分层提示 / 图形批注 / 语音纠错确认）时共用的纯逻辑。
 *
 * 为什么单独成文件：这些函数不依赖 Vue 运行时，可以用原生 Node 直接测
 * （见 tests/test_agent_tools.mjs），做法与 courseChapters.ts 一致。
 *
 * 硬约束：
 * - 所有长度与取值上限都抄自后端契约（docs/contracts/README.md 的「智能体接口 v0.4」一节
 *   与 backend/app/ai/{hints,plotting,voice}.py），前端只做「提前拦截 + 如实说明」，
 *   不代替后端判定，也**不静默截断**：截断必须回传 truncated 标记由界面告知用户。
 * - 语音转写与拍照识别一样只是草稿，必须由学生确认后才进入 /api/conversations；
 *   本模块不提供任何绕过确认的路径。
 */
import type { Role } from './api'

/* SECTION: 后端契约常量（与 backend 保持一致，改动需同步契约文档） */
export const HINT_QUESTION_MAX = 1000        // HintInput.question 上限
export const HINT_LEVEL_MAX = 3              // hints.MAX_LEVEL
export const PLOT_QUESTION_MAX = 1000        // PlotInput.question 上限
export const PLOT_EXPR_MAX = 200             // MAX_EXPR
export const PLOT_SAMPLES_MIN = 2
export const PLOT_SAMPLES_MAX = 241
export const PLOT_AXIS_LIMIT = 1e4           // x_min / x_max 的 ge / le
export const AUDIO_MEDIA_TYPES: readonly string[] = [
  'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/webm',
  'audio/ogg', 'audio/mp4', 'audio/m4a', 'audio/x-m4a',
]
export const AUDIO_MIN_BYTES = 512
export const AUDIO_MAX_BYTES = 20 * 1024 * 1024
export const AUDIO_MAX_DURATION = 120

/* SECTION: 主题选项（单一来源，避免模板里硬编码的列表与后端建议值对不上） */
export function topicOptions(role: Role): string[] {
  return role === 'teacher'
    ? ['函数与极限', '导数与微分', '费曼练习', '教学设计']
    : ['函数与极限', '导数与微分', '费曼练习']
}

/** 沿用原 AgentView 的关键词兜底推断；教师端不猜主题。 */
export function guessTopic(text: string, role: Role): string {
  if (role === 'teacher') return ''
  const value = text || ''
  if (value.includes('费曼')) return '费曼练习'
  if (/导数|微分|dy\/dx|f'\(/.test(value)) return '导数与微分'
  if (/极限|lim|连续/.test(value)) return '函数与极限'
  return ''
}

export interface TopicDecision {
  /** 要写入主题下拉框的值；applied=false 时为空字符串，表示不要改动下拉框 */
  topic: string
  /** 是否真的改变了主题（false 时界面必须把建议值显示出来，不能静默丢弃） */
  applied: boolean
  /** 建议的主题原文，用于界面提示 */
  suggested: string
}

/**
 * 后端 suggest_topic 可能返回下拉框里没有的主题（例如「一元函数积分学」「无穷级数」）。
 * 直接写进 v-model 会让 select 显示空白，所以只有落在 allowed 里才应用，
 * 否则保留原主题并把建议值交给界面如实展示。
 */
export function decideTopic(role: Role, suggested: string | null | undefined, text: string, allowed: readonly string[]): TopicDecision {
  const suggestedText = (suggested || '').trim()
  const fallback = guessTopic(text, role)
  const candidate = suggestedText || fallback
  if (candidate && allowed.includes(candidate)) return { topic: candidate, applied: true, suggested: suggestedText }
  return { topic: '', applied: false, suggested: suggestedText || fallback }
}

/* SECTION: 分层提示 */
export interface ClampedText { text: string; truncated: boolean }

/** 对话问题最长 2000 字，提示接口只收 1000 字：超限时截断并回传标记，由界面说明。 */
export function clampForHint(question: string, max = HINT_QUESTION_MAX): ClampedText {
  const trimmed = (question || '').trim()
  if (trimmed.length <= max) return { text: trimmed, truncated: false }
  return { text: trimmed.slice(0, max), truncated: true }
}

/**
 * 下一级提示只认后端给的 next_level；为 null / 越界 / 不递增时一律返回 null（按钮禁用）。
 * 前端绝不自己拼接三级提示，也不猜测层级。
 */
export function nextHintLevel(current: number, next: number | null | undefined, total = HINT_LEVEL_MAX): number | null {
  if (typeof next !== 'number' || !Number.isFinite(next)) return null
  const level = Math.trunc(next)
  if (level <= current || level > total || level < 1) return null
  return level
}

/* SECTION: 图形批注画布 */
export interface PlotViewport { x_min: number; x_max: number; y_min: number; y_max: number }
export type PlotSample = [number, number | null]
export interface PlotPadding { top: number; right: number; bottom: number; left: number }
export interface Projection {
  x(value: number): number
  y(value: number): number
  innerWidth: number
  innerHeight: number
  padding: PlotPadding
}

export const PLOT_PADDING: PlotPadding = { top: 16, right: 18, bottom: 26, left: 42 }

/** 视窗坐标 → 画布像素；y 轴翻转（数学坐标向上为正）。 */
export function createProjection(viewport: PlotViewport, width: number, height: number, padding: PlotPadding = PLOT_PADDING): Projection {
  const spanX = viewport.x_max - viewport.x_min
  const spanY = viewport.y_max - viewport.y_min
  const innerWidth = Math.max(1, width - padding.left - padding.right)
  const innerHeight = Math.max(1, height - padding.top - padding.bottom)
  const safeX = Number.isFinite(spanX) && spanX !== 0 ? spanX : 1
  const safeY = Number.isFinite(spanY) && spanY !== 0 ? spanY : 1
  return {
    x: value => padding.left + ((value - viewport.x_min) / safeX) * innerWidth,
    y: value => padding.top + (1 - (value - viewport.y_min) / safeY) * innerHeight,
    innerWidth,
    innerHeight,
    padding,
  }
}

/**
 * 采样点里 y 可能是 null（函数在该点无定义，见 mathcheck.sample_curve）。
 * 这些点必须断开折线，不能连成一条直线穿过间断点。
 */
export function toPolylineSegments(samples: PlotSample[], projection: Pick<Projection, 'x' | 'y'>): Array<Array<[number, number]>> {
  const segments: Array<Array<[number, number]>> = []
  let current: Array<[number, number]> = []
  for (const sample of samples || []) {
    if (!Array.isArray(sample)) continue
    const vx = Number(sample[0])
    const vy = sample[1]
    if (!Number.isFinite(vx) || typeof vy !== 'number' || !Number.isFinite(vy)) {
      if (current.length) { segments.push(current); current = [] }
      continue
    }
    current.push([projection.x(vx), projection.y(vy)])
  }
  if (current.length) segments.push(current)
  return segments
}

/** 坐标轴刻度：取 4 等分，保留到小数点后 2 位并去掉多余的 0。 */
export function axisTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return []
  return Array.from({ length: count + 1 }, (_, index) => min + ((max - min) * index) / count)
}

export function formatTick(value: number): string {
  if (!Number.isFinite(value)) return ''
  if (Math.abs(value) < 1e-9) return '0'
  const rounded = Math.round(value * 100) / 100
  return String(rounded)
}

/** 绘图区校验：区间非法或采样数越界时给出原因，不发请求（后端也会 422）。 */
export function checkPlotParams(xMin: number, xMax: number, samples: number): string {
  if (!Number.isFinite(xMin) || !Number.isFinite(xMax)) return '区间需要是数字。'
  if (Math.abs(xMin) > PLOT_AXIS_LIMIT || Math.abs(xMax) > PLOT_AXIS_LIMIT) return `区间需在 ±${PLOT_AXIS_LIMIT} 以内。`
  if (xMin >= xMax) return '区间左端点必须小于右端点。'
  if (!Number.isFinite(samples)) return '采样点数需要是数字。'
  const count = Math.trunc(samples)
  if (count < PLOT_SAMPLES_MIN || count > PLOT_SAMPLES_MAX) return `采样点数需在 ${PLOT_SAMPLES_MIN}–${PLOT_SAMPLES_MAX} 之间。`
  return ''
}

/* SECTION: 语音（服务端转写 + 浏览器原生兜底） */
/**
 * MediaRecorder 给的是 `audio/webm;codecs=opus` 这类带参数的 MIME，
 * 后端只按主类型白名单校验，不剥参数会直接 422。
 */
export function normalizeAudioMediaType(mime: string | null | undefined): string | null {
  const base = (mime || '').split(';')[0].trim().toLowerCase()
  return AUDIO_MEDIA_TYPES.includes(base) ? base : null
}

/** base64 长度 → 原始字节数（与后端解码后的判断口径一致）。 */
export function audioBase64Bytes(base64: string): number {
  const cleaned = (base64 || '').replace(/\s/g, '')
  if (!cleaned) return 0
  const padding = cleaned.endsWith('==') ? 2 : cleaned.endsWith('=') ? 1 : 0
  return Math.max(0, Math.floor((cleaned.length * 3) / 4) - padding)
}

export interface AudioClipCheck { ok: boolean; reason: string }

/** 上传前自检，避免把必然被 422 的载荷发给后端；reason 直接展示给用户。 */
export function checkAudioClip(base64: string, mediaType: string | null, durationSeconds: number | null): AudioClipCheck {
  if (!mediaType) {
    return { ok: false, reason: `浏览器录制的音频格式不在后端支持范围内（仅支持 ${AUDIO_MEDIA_TYPES.join(' / ')}）。` }
  }
  const bytes = audioBase64Bytes(base64)
  if (bytes < AUDIO_MIN_BYTES) return { ok: false, reason: '录音太短或数据过小，请重新录一段。' }
  if (bytes > AUDIO_MAX_BYTES) return { ok: false, reason: '音频超过 20 MB，请分段或缩短后重试。' }
  if (durationSeconds !== null && Number.isFinite(durationSeconds) && durationSeconds > AUDIO_MAX_DURATION) {
    return { ok: false, reason: `单段语音请控制在 ${AUDIO_MAX_DURATION} 秒以内。` }
  }
  return { ok: true, reason: '' }
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

/** 分块转 base64，避免一次性展开大数组导致调用栈溢出。 */
export function arrayBufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)
  let binary = ''
  const chunk = 0x2000
  for (let start = 0; start < bytes.length; start += chunk) {
    const part = Array.from(bytes.subarray(start, start + chunk))
    binary += String.fromCharCode.apply(null, part)
  }
  return btoa(binary)
}

/** 后端 corrections[] → 一行可读文本，让学生看见「改了什么」。 */
export function describeCorrections(corrections: Array<{ from?: unknown; to?: unknown; count?: unknown }> | null | undefined): string {
  if (!Array.isArray(corrections) || !corrections.length) return ''
  return corrections
    .map(item => {
      const from = typeof item?.from === 'string' ? item.from : ''
      const to = typeof item?.to === 'string' ? item.to : ''
      const count = typeof item?.count === 'number' && item.count > 1 ? `（${item.count} 次）` : ''
      if (!from && !to) return ''
      return `${from} → ${to}${count}`
    })
    .filter(Boolean)
    .join('；')
}

/* SECTION: 浏览器原生语音（Web Speech API 不在标准 DOM 类型里，这里只声明用到的部分） */
export interface BrowserSpeechLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  abort(): void
  onstart: (() => void) | null
  onresult: ((event: unknown) => void) | null
  onerror: ((event: unknown) => void) | null
  onend: (() => void) | null
}

export function createBrowserSpeech(): BrowserSpeechLike | null {
  if (typeof window === 'undefined') return null
  const holder = window as unknown as {
    SpeechRecognition?: new () => BrowserSpeechLike
    webkitSpeechRecognition?: new () => BrowserSpeechLike
  }
  const Ctor = holder.SpeechRecognition ?? holder.webkitSpeechRecognition
  if (!Ctor) return null
  try {
    return new Ctor()
  } catch {
    return null
  }
}

/** 把浏览器给的 results 结构读成「已确定文本 + 临时文本」，任何异常结构都当空处理。 */
export function readSpeechTranscript(event: unknown): { final: string; interim: string } {
  const results = (event as { results?: unknown } | null)?.results
  const list = results as ArrayLike<Record<string, unknown>> | undefined
  if (!list || typeof list.length !== 'number') return { final: '', interim: '' }
  let final = ''
  let interim = ''
  for (let index = 0; index < list.length; index++) {
    const result = list[index]
    if (!result) continue
    const alternative = result[0] as { transcript?: unknown } | undefined
    const transcript = typeof alternative?.transcript === 'string' ? alternative.transcript : ''
    if (!transcript) continue
    if (result.isFinal === true) final += transcript
    else interim += transcript
  }
  return { final: final.trim(), interim: interim.trim() }
}

export function readSpeechError(event: unknown): string {
  const error = (event as { error?: unknown } | null)?.error
  return typeof error === 'string' ? error : ''
}

const SPEECH_ERRORS: Record<string, [string, string]> = {
  'not-allowed': ['麦克风权限被拒绝', '请在浏览器地址栏左侧的站点设置里把「麦克风」改为允许后重试。'],
  'service-not-allowed': ['浏览器语音服务不可用', '当前浏览器或系统策略不允许调用在线语音识别，请改用键盘输入。'],
  'no-speech': ['没有听到有效语音', '请靠近麦克风再说一次，或检查系统输入设备是否被占用。'],
  'audio-capture': ['没有找到可用麦克风', '这台设备可能没有麦克风或驱动未就绪，请改用键盘输入。'],
  network: ['语音识别网络不可用', '浏览器原生识别需要联网访问识别服务，请检查网络后重试。'],
  aborted: ['识别被中断', '本次识别已取消，可重新开始录音。'],
}

export function describeSpeechError(code: string): { title: string; detail: string } {
  const known = SPEECH_ERRORS[code]
  if (known) return { title: known[0], detail: known[1] }
  return { title: '语音识别失败', detail: code ? `浏览器返回的错误代码是「${code}」，可重试或改用键盘输入。` : '未知原因，可重试或改用键盘输入。' }
}
