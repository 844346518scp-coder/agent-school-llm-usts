<script setup lang="ts">
/* 倒计时专注学习模式：纯前端计时，不写库、不发请求。
   关闭弹窗后计时继续，在对话头显示剩余时间；离开本页（组件卸载）计时重置。
   结束时用 WebAudio 轻提示，音频不可用则静默，不影响计时。 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Timer, Play, Pause, RotateCcw, Coffee, CheckCircle2 } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'

type Phase = 'idle' | 'running' | 'paused' | 'done'
const PRESETS = [25, 15, 10, 5]
const MIN_MINUTES = 1, MAX_MINUTES = 120

const open = ref(false)
const phase = ref<Phase>('idle')
const minutes = ref(25)
const total = ref(25 * 60)
const remaining = ref(25 * 60)
const rounds = ref(0)
const focusedSeconds = ref(0)
let deadline = 0
let intervalId = 0

const clampMinutes = (v: number) => Math.min(MAX_MINUTES, Math.max(MIN_MINUTES, Math.floor(v) || 25))
const pad = (v: number) => String(v).padStart(2, '0')
const mmss = (s: number) => `${pad(Math.floor(s / 60))}:${pad(s % 60)}`
const remainingText = computed(() => mmss(Math.max(0, Math.ceil(remaining.value))))
const progress = computed(() => (total.value ? Math.min(1, Math.max(0, 1 - remaining.value / total.value)) : 0))
const RADIUS = 86
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const dashOffset = computed(() => CIRCUMFERENCE * (1 - progress.value))
const statusText = computed(() => {
  if (phase.value === 'running') return '专注中 · 只做眼前这一件事'
  if (phase.value === 'paused') return '已暂停 · 准备好后继续'
  if (phase.value === 'done') return '本轮专注完成，起身放松一下吧'
  return '选好时长，把注意力留给这一道题'
})
const headerClass = computed(() => ({ 'is-running': phase.value === 'running', 'is-paused': phase.value === 'paused', 'is-done': phase.value === 'done' }))
const triggerLabel = computed(() => phase.value === 'idle' ? '打开专注计时' : phase.value === 'done' ? '专注计时已完成，打开详情' : phase.value === 'paused' ? '专注计时已暂停，打开详情' : '专注计时进行中，打开详情')

function stopTimer() { if (intervalId) { window.clearInterval(intervalId); intervalId = 0 } }
function tick() {
  const left = Math.round((deadline - Date.now()) / 1000)
  if (left <= 0) finish()
  else remaining.value = left
}
function start() {
  const m = clampMinutes(minutes.value)
  minutes.value = m
  if (phase.value === 'idle' || phase.value === 'done') { total.value = m * 60; remaining.value = total.value }
  deadline = Date.now() + Math.max(1, remaining.value) * 1000
  phase.value = 'running'
  stopTimer()
  intervalId = window.setInterval(tick, 250)
  ensureAudio()
}
function pause() {
  if (phase.value !== 'running') return
  remaining.value = Math.max(0, Math.round((deadline - Date.now()) / 1000))
  stopTimer()
  if (remaining.value <= 0) finish()
  else phase.value = 'paused'
}
function backToIdle() {
  stopTimer()
  phase.value = 'idle'
  const m = clampMinutes(minutes.value)
  total.value = m * 60; remaining.value = total.value
}
function finish() {
  stopTimer()
  remaining.value = 0
  phase.value = 'done'
  rounds.value += 1
  focusedSeconds.value += total.value
  chime()
  ElMessage.success('本轮专注完成，闭眼休息或远眺 20 秒吧。')
}
function restart() { start() }
watch(minutes, value => {
  const m = clampMinutes(value)
  if (phase.value === 'idle') { total.value = m * 60; remaining.value = total.value }
})
onBeforeUnmount(stopTimer)

let audioCtx: AudioContext | null = null
function ensureAudio() {
  try {
    if (!audioCtx) {
      const ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (ctor) audioCtx = new ctor()
    }
    if (audioCtx?.state === 'suspended') void audioCtx.resume()
  } catch { audioCtx = null }
}
function chime() {
  try {
    ensureAudio()
    const ctx = audioCtx
    if (!ctx) return
    ;[0, 0.3, 0.6].forEach((delay, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = [523.25, 659.25, 783.99][i]
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + delay)
      gain.gain.exponentialRampToValueAtTime(0.16, ctx.currentTime + delay + 0.04)
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + delay + 1.1)
      osc.connect(gain); gain.connect(ctx.destination)
      osc.start(ctx.currentTime + delay); osc.stop(ctx.currentTime + delay + 1.2)
    })
  } catch { /* 提示音不是必要能力，静默完成 */ }
}
</script>

<template>
  <span class="focus-entry">
    <button type="button" class="subtle-link focus-trigger" :class="headerClass" :aria-label="triggerLabel" @click="open = true">
      <Timer :size="15"/>
      <span class="focus-label">{{ phase === 'running' ? remainingText : phase === 'paused' ? `暂停 ${remainingText}` : phase === 'done' ? '专注完成' : '专注模式' }}</span>
      <span v-if="phase === 'running'" class="focus-live-dot" aria-hidden="true"/>
    </button>
    <el-dialog
      v-model="open"
      title="专注学习模式"
      width="min(400px, 94vw)"
      align-center
      append-to-body
      :close-on-click-modal="false"
      class="focus-dialog"
    >
      <div class="ft-body">
        <!-- 配置态 -->
        <template v-if="phase === 'idle'">
          <p class="ft-intro">这一轮只做一件事。选定时长，把搜题页的问题想透，再去看讲解。</p>
          <div class="ft-presets" role="group" aria-label="选择专注时长">
            <button v-for="p in PRESETS" :key="p" type="button" :class="{ active: minutes === p }" @click="minutes = p">{{ p }} 分钟</button>
          </div>
          <label class="ft-custom"><span>自定义时长（{{ MIN_MINUTES }}–{{ MAX_MINUTES }} 分钟）</span>
            <input v-model.number="minutes" type="number" :min="MIN_MINUTES" :max="MAX_MINUTES" step="1">
          </label>
          <button type="button" class="primary-button ft-start" @click="start"><Play :size="16"/> 开始 {{ clampMinutes(minutes) }} 分钟专注</button>
          <p class="ft-note">计时只在当前页面进行，关闭此窗口仍会在顶部显示；离开本页或刷新会重新开始。</p>
        </template>

        <!-- 计时态 -->
        <template v-else-if="phase === 'running' || phase === 'paused'">
          <div class="ft-ring-wrap">
            <svg class="ft-ring" viewBox="0 0 200 200" aria-hidden="true">
              <circle cx="100" cy="100" :r="RADIUS" class="ft-ring-bg"/>
              <circle cx="100" cy="100" :r="RADIUS" class="ft-ring-fg" :stroke-dasharray="CIRCUMFERENCE" :stroke-dashoffset="dashOffset"/>
            </svg>
            <div class="ft-ring-center">
              <strong>{{ remainingText }}</strong>
              <small>{{ phase === 'running' ? '专注中' : '已暂停' }}</small>
            </div>
          </div>
          <p class="ft-status" :class="{ paused: phase === 'paused' }" aria-live="polite">{{ statusText }}</p>
          <div class="ft-actions">
            <button v-if="phase === 'running'" type="button" class="outline-button" @click="pause"><Pause :size="15"/> 暂停</button>
            <button v-else type="button" class="primary-button" @click="start"><Play :size="15"/> 继续</button>
            <button type="button" class="outline-button" @click="backToIdle"><RotateCcw :size="15"/> 结束本轮</button>
          </div>
          <p class="ft-note">可以关闭此窗口继续对着题目思考，剩余时间显示在对话顶部；本页已完成 {{ rounds }} 轮专注。</p>
        </template>

        <!-- 完成态 -->
        <template v-else>
          <div class="ft-done">
            <span class="ft-done-icon"><CheckCircle2 :size="26"/></span>
            <h3>这一轮完成了</h3>
            <p>本页累计 <strong>{{ rounds }}</strong> 轮专注，共 <strong>{{ Math.round(focusedSeconds / 60) }}</strong> 分钟。</p>
          </div>
          <div class="ft-actions">
            <button type="button" class="primary-button" @click="restart"><RotateCcw :size="15"/> 再来一轮</button>
            <button type="button" class="outline-button" @click="open = false"><Coffee :size="15"/> 休息一下</button>
          </div>
        </template>
      </div>
    </el-dialog>
  </span>
</template>

<style scoped>
.focus-entry{display:inline-flex}
.focus-trigger{position:relative;font-variant-numeric:tabular-nums}
.focus-trigger .focus-live-dot{width:5px;height:5px;border-radius:50%;background:var(--primary);animation:ft-breathe 1.6s ease-in-out infinite}
.focus-trigger.is-running{color:var(--primary);font-weight:600}
.focus-trigger.is-paused .focus-live-dot{display:none}
.focus-trigger.is-done{color:#568b6e}
@keyframes ft-breathe{50%{opacity:.3}}
.ft-body{display:flex;flex-direction:column;gap:16px}
.ft-intro{font-size:13px;color:#8a7d99;line-height:1.9}
.ft-presets{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.ft-presets button{background:#fff;border:1px solid var(--line);color:#8f83a0;border-radius:9px;padding:11px 4px;font-size:12px}
.ft-presets button.active{background:var(--soft);border-color:#d9cbee;color:var(--primary);font-weight:600}
.ft-custom{display:flex;flex-direction:column;gap:8px;font-size:12px;color:var(--muted)}
.ft-custom input{border:1px solid var(--line);border-radius:9px;padding:10px 12px;font-size:14px;width:100%}
.ft-start{width:100%;padding:13px}
.ft-note{font-size:11px;color:var(--muted);line-height:1.7;text-align:center}
.ft-ring-wrap{position:relative;width:210px;height:210px;margin:4px auto 0}
.ft-ring{width:100%;height:100%;transform:rotate(-90deg)}
.ft-ring-bg{fill:none;stroke:var(--soft);stroke-width:9}
.ft-ring-fg{fill:none;stroke:var(--primary);stroke-width:9;stroke-linecap:round;transition:stroke-dashoffset .3s linear}
.ft-ring-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px}
.ft-ring-center strong{font-size:38px;font-weight:600;color:#6f5b8f;font-variant-numeric:tabular-nums;letter-spacing:1px}
.ft-ring-center small{font-size:11px;color:var(--muted)}
.ft-status{text-align:center;font-size:12px;color:#8a7d99}
.ft-status.paused{color:#a98d5f}
.ft-actions{display:flex;gap:10px}
.ft-actions button{flex:1;padding:12px}
.ft-done{text-align:center;padding:14px 0 4px}
.ft-done-icon{display:inline-grid;place-items:center;width:54px;height:54px;border-radius:50%;background:#eaf5ee;color:#4c7f61;margin-bottom:14px}
.ft-done h3{font-size:17px;color:#5f7a68;margin-bottom:10px}
.ft-done p{font-size:13px;color:#8a7d99;line-height:1.9}
.ft-done strong{color:var(--primary-dark)}
@media(max-width:520px){.focus-trigger .focus-label{display:none}.focus-trigger .focus-live-dot{position:absolute;top:-2px;right:-3px}}
</style>
