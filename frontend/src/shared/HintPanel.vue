<script setup lang="ts">
/**
 * 分层提示（A 端接入 B 模块 POST /api/agent/hint，9/25–27 第三阶段）。
 *
 * 契约与诚实性约束（docs/contracts/README.md「智能体接口 v0.4」）：
 * - 三级提示一律由后端返回，前端**不自己拼接**、不猜测层级；「再具体一点」只在后端给出
 *   next_level 时可用，为 null 就禁用。
 * - 任何级别的响应固定带 answer_leaked=false 与 guard，界面把 guard 原文展示出来，
 *   明确告诉学生「这里没有最终答案」。
 * - mode=demo 表示内容来自本地知识点规则而非模型，必须标注，不得显示成「AI 生成」。
 * - point.verified / references[].verified 为 false 时标注「待课程资料复核」。
 */
import { ref, watch } from 'vue'
import { ChevronRight, Lightbulb, LoaderCircle, OctagonX, RotateCcw } from 'lucide-vue-next'
import { api, type Reference } from './api'
import { HINT_QUESTION_MAX, clampForHint, nextHintLevel } from './agentTools'
import MathText from './MathText.vue'

interface HintPoint { id: string; title: string; topic: string; source: string; verified: boolean }
interface HintResponse {
  mode?: 'demo' | 'live'
  notice?: string | null
  level?: number
  level_title?: string
  levels_total?: number
  hint?: string
  self_check?: string
  next_level?: number | null
  next_level_action?: string
  answer_leaked?: boolean
  guard?: string
  point?: HintPoint | null
  references?: Reference[]
  method?: string
}

const props = defineProps<{ question: string; topic: string; disabled?: boolean }>()

const cards = ref<Array<{ level: number; data: HintResponse }>>([])
const busy = ref(false)
const error = ref('')
const truncated = ref(false)
/* 提示是针对具体题目生成的：记下第一次请求时的题目，界面据此说明；
   题目被清空时重置，避免留着与空输入不符的提示。 */
const sourceQuestion = ref('')
watch(() => props.question, value => {
  if (!value.trim()) { cards.value = []; error.value = ''; truncated.value = false; sourceQuestion.value = '' }
})

function reset() {
  if (busy.value) return
  cards.value = []
  error.value = ''
  truncated.value = false
  sourceQuestion.value = ''
}

async function request(level: number) {
  if (busy.value || props.disabled) return
  const text = props.question.trim()
  if (!text) { error.value = '先写下你的问题，再来要提示。'; return }
  const clamped = clampForHint(text, HINT_QUESTION_MAX)
  truncated.value = clamped.truncated
  busy.value = true
  error.value = ''
  if (!cards.value.length) sourceQuestion.value = text
  try {
    const data = await api<HintResponse>('/agent/hint', {
      method: 'POST',
      body: JSON.stringify({ question: clamped.text, level, topic: props.topic || null }),
    })
    const shown = typeof data.level === 'number' ? data.level : level
    cards.value = [...cards.value.filter(card => card.level !== shown), { level: shown, data }]
    cards.value.sort((a, b) => a.level - b.level)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}

function askNext() {
  const last = cards.value[cards.value.length - 1]
  const level = last ? nextHintLevel(last.level, last.data.next_level) : 1
  if (level === null) return
  void request(level)
}

function nextLevel(): number | null {
  const last = cards.value[cards.value.length - 1]
  return last ? nextHintLevel(last.level, last.data.next_level) : 1
}
</script>

<template>
  <div class="hint-panel">
    <div class="hint-head">
      <span class="hint-kicker"><Lightbulb :size="15"/> 分层提示</span>
      <p>概念 → 方法 → 关键步骤，按你需要的程度一级级要；<strong>任何一级都不给最终答案</strong>。</p>
    </div>

    <div v-if="!cards.length" class="hint-empty">
      <p v-if="!question.trim()">先在下面写下你卡住的那道题，就能来要提示。</p>
      <p v-else>卡住了？先要一级「概念提示」，通常只需要一点点方向。</p>
    </div>
    <p v-else-if="sourceQuestion" class="hint-source">
      以下提示针对：<span>{{ sourceQuestion }}</span>
    </p>

    <div v-for="card in cards" :key="card.level" class="hint-card">
      <div class="hint-card-top">
        <strong>第 {{ card.level }} 级 · {{ card.data.level_title || '提示' }}</strong>
        <span class="small-pill" :class="card.data.mode === 'live' ? 'success' : ''">
          {{ card.data.mode === 'live' ? '模型生成 · 请核对' : '本地知识点规则 · 演示内容' }}
        </span>
      </div>
      <p v-if="card.data.notice" class="form-error" role="status">{{ card.data.notice }}</p>
      <MathText v-if="card.data.hint" class="hint-body" :text="card.data.hint"/>
      <div v-if="card.data.self_check" class="hint-check">
        <span>自检一下</span>
        <MathText :text="card.data.self_check"/>
      </div>
      <div v-if="card.data.point" class="hint-point">
        关联知识点：{{ card.data.point.title }}（{{ card.data.point.topic }}）
        <small>{{ card.data.point.verified ? '已复核' : '待课程资料复核' }} · 出处 {{ card.data.point.source }}</small>
      </div>
      <details v-if="card.data.references?.length" class="hint-refs">
        <summary>本次检索到的资料 {{ card.data.references.length }} 条</summary>
        <p v-for="reference in card.data.references" :key="reference.id">
          [{{ reference.index }}] {{ reference.title }} · {{ reference.source }}
          <small>{{ reference.verified ? '已复核' : '待课程资料复核' }}</small>
        </p>
      </details>
      <p v-if="card.data.guard" class="hint-guard">{{ card.data.guard }}</p>
    </div>

    <div class="hint-actions">
      <button type="button" class="outline-button" :disabled="busy || disabled || nextLevel() === null" @click="askNext">
        <LoaderCircle v-if="busy" :size="15" class="spin"/>
        <ChevronRight v-else :size="15"/>
        {{ busy ? '正在准备提示…' : cards.length ? '再具体一点' : '要一点提示' }}
      </button>
      <button v-if="cards.length" type="button" class="subtle-link" :disabled="busy || disabled" @click="reset">
        <RotateCcw :size="14"/> 重新开始
      </button>
      <span v-if="nextLevel() === null && cards.length" class="hint-limit">
        <OctagonX :size="14"/> 已到最具体一级；接下来请把你写出的这一步提交「步骤反馈」核对。
      </span>
    </div>

    <p v-if="truncated" class="hint-note">
      你的问题超过 {{ HINT_QUESTION_MAX }} 字，本次只把前面 {{ HINT_QUESTION_MAX }} 字送去生成提示。
    </p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.hint-panel{display:flex;flex-direction:column;gap:12px;margin-top:18px;padding:16px 17px;border:1px solid var(--line);border-radius:11px;background:#fdfbff}
.hint-head{display:flex;flex-direction:column;gap:6px}
.hint-kicker{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--primary)}
.hint-head p{font-size:12px;line-height:1.8;color:var(--muted)}
.hint-empty p{font-size:12px;line-height:1.8;color:var(--muted)}
.hint-source{font-size:11.5px;line-height:1.7;color:var(--muted)}
.hint-source>span{display:block;color:#7d6b8c;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hint-card{border:1px solid var(--line);border-radius:10px;padding:13px 14px;background:#fff;display:flex;flex-direction:column;gap:9px}
.hint-card-top{display:flex;flex-wrap:wrap;align-items:center;gap:9px}
.hint-card-top strong{font-size:13px;color:#64576f}
.hint-body{font-size:13px}
.hint-check{background:var(--soft);border-radius:8px;padding:10px 12px}
.hint-check>span{display:block;font-size:11px;color:var(--primary);margin-bottom:5px}
.hint-check :deep(.math-text){font-size:12px;line-height:1.85}
.hint-point{font-size:12px;color:#7d6b8c}
.hint-point small{display:block;font-size:11px;color:var(--muted);margin-top:4px}
.hint-refs{font-size:12px}
.hint-refs summary{cursor:pointer;color:var(--primary);font-size:12px}
.hint-refs p{margin:7px 0 0;font-size:12px;line-height:1.75;color:#7d6b8c;overflow-wrap:anywhere}
.hint-refs small{display:block;font-size:11px;color:var(--muted)}
.hint-guard{font-size:11.5px;line-height:1.8;color:var(--muted);border-left:2px solid var(--line);padding-left:10px}
.hint-actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px}
.hint-actions .outline-button{padding:10px 15px;font-size:12px}
.hint-limit{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--muted);line-height:1.7}
.hint-note{font-size:11.5px;line-height:1.75;color:#8a5300;background:#fff6e6;border-radius:8px;padding:9px 11px}
.spin{animation:hint-spin 1s linear infinite}
@keyframes hint-spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
