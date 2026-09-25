<script setup lang="ts">
/**
 * 语音输入与纠错确认（A 端接入 B 模块第三阶段语音适配）。
 *
 * 两条路径（契约建议：语音优先用 browser_fallback 的 Web Speech API；启用服务端转写后
 * 把 corrections 展示给学生确认，再走 /api/conversations 保存）：
 *  - browser：浏览器原生 SpeechRecognition，零后端凭据、实时出字，但无术语纠错、Firefox 不支持；
 *  - server ：MediaRecorder 录音 → POST /api/agent/voice/transcribe，返回纠错后的 text + corrections。
 *
 * 诚实性约束（docs/contracts/README.md「智能体接口 v0.4」）：
 *  - 未配置语音服务时 transcribe 返回 503，界面如实展示后端原文并引导改用浏览器原生 / 键盘，
 *    **绝不返回编造文本**；
 *  - 无论哪条路径，识别结果都只是草稿（requires_confirmation=true），必须由学生确认或修正后
 *    才回填提问框；本组件不直接保存对话，发送仍由 AgentView 走 /api/conversations。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { AudioLines, CircleAlert, Mic, MicOff, Square } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, ApiError, type User } from './api'
import { AUDIO_MAX_DURATION, arrayBufferToBase64, audioBase64Bytes, checkAudioClip, createBrowserSpeech, describeCorrections, describeSpeechError, formatBytes, normalizeAudioMediaType, readSpeechError, readSpeechTranscript, type BrowserSpeechLike } from './agentTools'

interface VoiceStatus {
  ready?: boolean
  credential_source?: string
  model?: string | null
  limits?: { formats?: string[]; max_bytes?: number; max_duration_seconds?: number }
  browser_fallback?: { available?: boolean; method?: string; note?: string }
  note?: string
}
interface TranscribeResponse {
  mode?: 'demo' | 'live'
  raw_text?: string
  text?: string
  corrections?: Array<{ from?: string; to?: string; count?: number }>
  warnings?: string[]
  changed?: boolean
  suggested_topic?: string | null
  requires_confirmation?: boolean
  method?: string
}

type Step = 'idle' | 'recording' | 'confirm'
type Method = 'browser' | 'server'

const props = defineProps<{ modelValue: boolean; user: User }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; apply: [text: string, topic: string | null] }>()

const step = ref<Step>('idle')
const method = ref<Method>('browser')
const busy = ref(false)
const status = ref<VoiceStatus | null>(null)
const statusError = ref('')
const liveText = ref('')          // 浏览器实时识别的临时显示
const elapsed = ref(0)

/* confirm step 的草稿与元信息 */
const draft = ref('')
const rawText = ref('')
const correctionsText = ref('')
const warnings = ref<string[]>([])
const changed = ref(false)
const resultMode = ref<'demo' | 'live' | ''>('')
const suggestedTopic = ref<string | null>(null)
const resultMethod = ref('')
const errorText = ref('')

const serverReady = computed(() => status.value?.ready === true)
const browserSupported = ref(false)
const draftEmpty = computed(() => !draft.value.trim())
const byteHint = ref('')

let stream: MediaStream | null = null
let recorder: MediaRecorder | null = null
let chunks: BlobPart[] = []
let speech: BrowserSpeechLike | null = null
let timer: number | undefined
let startedAt = 0

async function loadStatus() {
  statusError.value = ''
  try {
    status.value = await api<VoiceStatus>('/agent/voice/status')
  } catch (e) {
    status.value = null
    statusError.value = (e as Error).message
  }
  browserSupported.value = !!createBrowserSpeech()
  /* 服务端可用就默认走服务端（有术语纠错）；否则默认浏览器原生 */
  method.value = serverReady.value ? 'server' : 'browser'
}

function stopTimer() {
  if (timer !== undefined) { window.clearInterval(timer); timer = undefined }
}
function startTimer() {
  startedAt = Date.now()
  elapsed.value = 0
  stopTimer()
  timer = window.setInterval(() => {
    elapsed.value = Math.round((Date.now() - startedAt) / 1000)
    if (elapsed.value >= AUDIO_MAX_DURATION) {
      ElMessage.warning(`已达单段 ${AUDIO_MAX_DURATION} 秒上限，自动停止录音`)
      if (method.value === 'server') void stopServerRecording()
      else stopBrowserSpeech()
    }
  }, 250)
}

function stopStream() {
  if (stream) { stream.getTracks().forEach(t => { try { t.stop() } catch { /* 已停止 */ } }) }
  stream = null
}

/* SECTION: 服务端录音上传 */
async function startServerRecording() {
  errorText.value = ''
  if (!navigator.mediaDevices?.getUserMedia) {
    errorText.value = '当前浏览器不支持录音（getUserMedia 不可用）。请改用较新的 Chrome / Edge，并通过 https 或 localhost 访问。'
    return
  }
  stopStream()
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    const name = (e as DOMException)?.name ?? ''
    errorText.value = name === 'NotAllowedError'
      ? '麦克风权限被拒绝。请在浏览器地址栏左侧的站点设置里把「麦克风」改为允许后重试。'
      : name === 'NotFoundError'
        ? '没有找到可用麦克风。请检查设备后重试，或改用浏览器实时识别 / 键盘输入。'
        : `无法开始录音：${(e as Error)?.message ?? name}`
    return
  }
  chunks = []
  try {
    recorder = MediaRecorder.isTypeSupported('audio/webm') ? new MediaRecorder(stream, { mimeType: 'audio/webm' }) : new MediaRecorder(stream)
  } catch (e) {
    errorText.value = `当前浏览器不支持 MediaRecorder：${(e as Error)?.message ?? ''}`
    stopStream()
    return
  }
  recorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data) }
  recorder.onstop = () => { stopStream() }
  recorder.start()
  step.value = 'recording'
  startTimer()
}

async function stopServerRecording() {
  stopTimer()
  if (!recorder) { step.value = 'idle'; return }
  const mimeType = recorder.mimeType || (chunks[0] instanceof Blob ? (chunks[0] as Blob).type : '')
  const rec = recorder
  recorder = null
  /* onstop 之后 chunks 才完整，用 Promise 等它落定 */
  const stopped = new Promise<void>(resolve => { rec.onstop = () => { stopStream(); resolve() } })
  try { rec.stop() } catch { /* 已停止 */ }
  await stopped
  step.value = 'recording'
  busy.value = true
  errorText.value = ''
  try {
    const blob = new Blob(chunks, { type: mimeType || 'audio/webm' })
    const buffer = await blob.arrayBuffer()
    const base64 = arrayBufferToBase64(buffer)
    const normalizedType = normalizeAudioMediaType(mimeType || blob.type)
    const duration = startedAt ? Math.min(AUDIO_MAX_DURATION, (Date.now() - startedAt) / 1000) : null
    const preflight = checkAudioClip(base64, normalizedType, duration)
    byteHint.value = formatBytes(audioBase64Bytes(base64))
    if (!preflight.ok) {
      errorText.value = preflight.reason
      step.value = 'idle'
      return
    }
    const data = await api<TranscribeResponse>('/agent/voice/transcribe', {
      method: 'POST',
      body: JSON.stringify({
        audio_base64: base64,
        media_type: normalizedType,
        language: 'zh',
        duration_seconds: duration === null ? null : Math.round(duration * 10) / 10,
      }),
    })
    fillConfirm(data)
  } catch (e) {
    if (e instanceof ApiError && e.status === 503) {
      errorText.value = `${e.message}\n\n服务端未配置语音服务，可切换到「浏览器实时识别」，或直接用键盘输入。`
    } else {
      errorText.value = e instanceof ApiError ? `HTTP ${e.status}：${e.message}` : (e as Error).message
    }
    step.value = 'idle'
  } finally {
    busy.value = false
  }
}

/* SECTION: 浏览器原生实时识别 */
function startBrowserSpeech() {
  errorText.value = ''
  speech = createBrowserSpeech()
  if (!speech) {
    errorText.value = '当前浏览器不支持 Web Speech API（Firefox 暂不支持）。请改用 Chrome / Edge，或用键盘输入。'
    return
  }
  speech.lang = 'zh-CN'
  speech.continuous = true
  speech.interimResults = true
  speech.maxAlternatives = 1
  liveText.value = ''
  speech.onresult = event => {
    const { final, interim } = readSpeechTranscript(event)
    liveText.value = (final + (interim ? ` ${interim}` : '')).trim()
  }
  speech.onerror = event => {
    const info = describeSpeechError(readSpeechError(event))
    errorText.value = `${info.title}：${info.detail}`
    stopBrowserSpeech(false)
  }
  speech.onend = () => {
    stopTimer()
    if (step.value === 'recording' && method.value === 'browser') {
      /* 用户主动停止或识别自然结束 → 把已识别文本带入确认 */
      const text = liveText.value.trim()
      if (text) {
        draft.value = text
        rawText.value = text
        correctionsText.value = ''
        warnings.value = []
        changed.value = false
        resultMode.value = ''
        suggestedTopic.value = null
        resultMethod.value = '浏览器原生识别（Web Speech API），未经服务端术语纠错'
        step.value = 'confirm'
      } else {
        step.value = 'idle'
        if (!errorText.value) errorText.value = '没有识别到语音内容，请靠近麦克风再试一次。'
      }
    }
  }
  try {
    speech.start()
    step.value = 'recording'
    startTimer()
  } catch {
    errorText.value = '浏览器语音识别启动失败，请重试或改用键盘输入。'
    speech = null
  }
}

function stopBrowserSpeech(toConfirm = true) {
  stopTimer()
  if (speech) {
    const s = speech
    speech = null
    try { toConfirm ? s.stop() : s.abort() } catch { /* 已结束 */ }
  }
  if (!toConfirm) step.value = 'idle'
}

/* SECTION: 确认与回填 */
function fillConfirm(data: TranscribeResponse) {
  draft.value = typeof data.text === 'string' ? data.text : ''
  rawText.value = typeof data.raw_text === 'string' ? data.raw_text : ''
  correctionsText.value = describeCorrections(data.corrections)
  warnings.value = Array.isArray(data.warnings) ? data.warnings.filter(w => typeof w === 'string') : []
  changed.value = data.changed === true
  resultMode.value = data.mode === 'live' ? 'live' : 'demo'
  suggestedTopic.value = data.suggested_topic ?? null
  resultMethod.value = data.method || ''
  errorText.value = ''
  step.value = 'confirm'
}

function confirmAndApply() {
  const text = draft.value.trim()
  if (!text) { ElMessage.warning('识别文本为空，无法带入提问'); return }
  emit('apply', text, suggestedTopic.value)
  /* 父组件校验合并后长度；接受后本组件在 apply 回调里关闭 */
}

function reset() {
  draft.value = ''; rawText.value = ''; correctionsText.value = ''; warnings.value = []
  changed.value = false; resultMode.value = ''; suggestedTopic.value = null; resultMethod.value = ''
  errorText.value = ''; liveText.value = ''; byteHint.value = ''
}

function startRecording() {
  reset()
  if (method.value === 'server') void startServerRecording()
  else startBrowserSpeech()
}
function stopRecording() {
  if (method.value === 'server') void stopServerRecording()
  else stopBrowserSpeech(true)
}
function cancelAll() {
  stopTimer()
  if (recorder) { const r = recorder; recorder = null; r.onstop = () => stopStream(); try { r.stop() } catch { stopStream() } }
  if (speech) { const s = speech; speech = null; try { s.abort() } catch { /* 已结束 */ } }
  stopStream()
  step.value = 'idle'
  liveText.value = ''
}

function close() {
  cancelAll()
  reset()
  emit('update:modelValue', false)
}

watch(() => props.modelValue, async open => {
  if (open) { reset(); step.value = 'idle'; await loadStatus() }
  else cancelAll()
})
onBeforeUnmount(cancelAll)
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="语音提问"
    width="min(560px, 94vw)"
    align-center
    destroy-on-close
    class="voice-dialog"
    @update:model-value="close"
  >
    <div class="vc-body">
      <!-- 方式选择（仅 idle 步骤可切换） -->
      <div class="vc-methods" role="radiogroup" aria-label="语音输入方式">
        <button type="button" role="radio" :aria-checked="method === 'browser'" :class="{ active: method === 'browser' }" :disabled="step !== 'idle'" @click="method = 'browser'">
          <Mic :size="16"/>
          <span>浏览器实时识别</span>
          <small>{{ browserSupported ? '本机可用 · 无需服务端凭据' : '本浏览器不支持' }}</small>
        </button>
        <button type="button" role="radio" :aria-checked="method === 'server'" :class="{ active: method === 'server' }" :disabled="step !== 'idle'" @click="method = 'server'">
          <AudioLines :size="16"/>
          <span>录音上传转写</span>
          <small>{{ serverReady ? `服务端已配置（${status?.model || '语音模型'}）· 含术语纠错` : '服务端未配置语音服务' }}</small>
        </button>
      </div>
      <p v-if="statusError" class="vc-status-error">语音能力探针读取失败：{{ statusError }}</p>

      <!-- idle：说明 + 开始 -->
      <template v-if="step === 'idle'">
        <div v-if="method === 'server' && !serverReady" class="vc-warn" role="status">
          <CircleAlert :size="16"/>
          <span>服务端还没有配置语音服务，直接录音上传会返回 503。你可以先试一次看后端原文，或切到「浏览器实时识别」。</span>
        </div>
        <div v-if="method === 'browser' && !browserSupported" class="vc-warn" role="status">
          <CircleAlert :size="16"/>
          <span>当前浏览器不支持 Web Speech API（如 Firefox）。请改用 Chrome / Edge，或用键盘输入。</span>
        </div>
        <p class="vc-tip">
          {{ method === 'server'
            ? '点「开始录音」后说话，再点「停止并转写」；音频不会保存在服务端，只用于本次转写。'
            : '点「开始识别」后说话，浏览器会实时显示文字，说完点「停止」。' }}
        </p>
        <div class="vc-actions">
          <button type="button" class="primary-button" :disabled="busy" @click="startRecording">
            <Mic :size="16"/> 开始{{ method === 'server' ? '录音' : '识别' }}
          </button>
        </div>
        <p v-if="errorText" class="form-error" role="alert">{{ errorText }}</p>
        <p class="vc-note">识别结果只是草稿，下一步需要你确认或修改后才会填入提问框。</p>
      </template>

      <!-- recording：进行中 -->
      <template v-else-if="step === 'recording'">
        <div class="vc-recording" role="status" aria-live="polite">
          <span class="vc-dot"/>
          <strong>{{ busy ? '正在转写…' : method === 'server' ? '正在录音' : '正在聆听' }}</strong>
          <span class="vc-elapsed">{{ elapsed }}s / {{ AUDIO_MAX_DURATION }}s</span>
        </div>
        <p v-if="method === 'browser' && liveText" class="vc-live">{{ liveText }}</p>
        <p v-else-if="busy" class="vc-live muted">请稍候，正在把音频送到服务端转写并做术语纠错。</p>
        <div class="vc-actions">
          <button type="button" class="outline-button" :disabled="busy" @click="cancelAll"><MicOff :size="15"/> 取消</button>
          <button type="button" class="primary-button" :disabled="busy" @click="stopRecording">
            <Square :size="15"/> {{ busy ? '转写中…' : '停止' }}
          </button>
        </div>
      </template>

      <!-- confirm：草稿待确认 -->
      <template v-else>
        <div v-if="resultMode === 'live'" class="vc-ok" role="status">
          <span>来自服务端转写的草稿，已经过术语纠错；请核对后再使用。</span>
        </div>
        <div v-else class="vc-warn" role="status">
          <CircleAlert :size="16"/>
          <span>这是浏览器本地识别的草稿，未经服务端术语纠错，请特别留意公式与专业名词。</span>
        </div>

        <label class="vc-field"><span>识别文本（可直接修改）</span>
          <textarea v-model="draft" rows="5" maxlength="2000" placeholder="识别结果会出现在这里"/>
        </label>

        <div v-if="correctionsText" class="vc-corrections">
          <span>术语纠错</span>
          <p>{{ correctionsText }}</p>
          <p v-if="rawText && changed" class="vc-raw">原始转写：{{ rawText }}</p>
        </div>
        <div v-if="warnings.length || byteHint" class="vc-chips">
          <span v-if="byteHint" class="small-pill">音频约 {{ byteHint }}</span>
          <span v-for="w in warnings" :key="w" class="small-pill warn">{{ w }}</span>
        </div>
        <p v-if="suggestedTopic" class="vc-note">建议知识点：{{ suggestedTopic }}（若不在主题下拉里，会保留你当前主题并单独提示）。</p>

        <div class="vc-actions">
          <button type="button" class="outline-button" :disabled="busy" @click="reset(); step = 'idle'">重新录制</button>
          <button type="button" class="primary-button" :disabled="draftEmpty" @click="confirmAndApply">用这段文字提问</button>
        </div>
        <p v-if="resultMethod" class="vc-note">本次来源：{{ resultMethod }}</p>
        <p class="vc-note">确认后文本会填入左侧提问框，由你决定是否发送；发送仍走原有的对话保存流程。</p>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.vc-body{display:flex;flex-direction:column;gap:13px}
.vc-methods{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.vc-methods button{display:flex;flex-direction:column;align-items:flex-start;gap:5px;text-align:left;padding:13px 14px;border:1px solid var(--line);border-radius:10px;background:#fff;color:#7d6b8c}
.vc-methods button.active{border-color:var(--primary);background:var(--soft);box-shadow:0 0 0 1px var(--primary)}
.vc-methods button>span{font-size:13px;font-weight:600;color:#64576f}
.vc-methods button>small{font-size:11px;color:var(--muted);line-height:1.6}
.vc-status-error{font-size:11.5px;color:#bb574c}
.vc-tip{font-size:12.5px;line-height:1.8;color:var(--muted)}
.vc-note{font-size:11.5px;line-height:1.7;color:var(--muted)}
.vc-actions{display:flex;gap:9px;flex-wrap:wrap}
.vc-actions .primary-button,.vc-actions .outline-button{flex:1;min-width:120px;padding:11px 14px;font-size:13px}
.vc-recording{display:flex;align-items:center;gap:10px;padding:16px;border:1px solid var(--line);border-radius:10px;background:#fff}
.vc-recording strong{font-size:13px;color:#64576f}
.vc-elapsed{margin-left:auto;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.vc-dot{width:10px;height:10px;border-radius:50%;background:#e0574c;animation:vc-pulse 1.1s infinite}
@keyframes vc-pulse{50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.vc-dot{animation:none}}
.vc-live{font-size:13px;line-height:1.85;color:#7d6b8c;background:var(--soft);border-radius:9px;padding:11px 13px;min-height:44px;overflow-wrap:anywhere}
.vc-live.muted{color:var(--muted)}
.vc-ok,.vc-warn{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;line-height:1.7;padding:10px 12px;border-radius:9px}
.vc-ok{background:#eaf5ee;color:#4c7f61}
.vc-warn{background:#fff6e6;color:#8a5300}
.vc-field>span{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}
.vc-field textarea{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:#fff;font-size:13px;line-height:1.8;resize:vertical}
.vc-corrections{border:1px solid var(--line);border-radius:9px;padding:11px 13px;background:#fff}
.vc-corrections>span{font-size:11.5px;color:var(--primary)}
.vc-corrections p{margin:6px 0 0;font-size:12.5px;line-height:1.75;color:#7d6b8c;overflow-wrap:anywhere}
.vc-raw{color:var(--muted)!important;font-size:11.5px!important}
.vc-chips{display:flex;flex-wrap:wrap;gap:7px}
.vc-chips .warn{background:#fff6e6;color:#8a5300}
@media (max-width:700px){.vc-methods{grid-template-columns:1fr}}
</style>
