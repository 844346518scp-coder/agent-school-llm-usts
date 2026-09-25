<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowUp, Sparkles, Plus, Bookmark, Check, Lightbulb, Sigma, BookOpen, History, RefreshCw, Camera, ChartSpline, Mic } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type Conversation, type User, formatDate } from './api'
import { decideTopic, topicOptions } from './agentTools'
import MathText from './MathText.vue'
import RecordsView from './RecordsView.vue'
import PhotoSearchDialog from './PhotoSearchDialog.vue'
import HintPanel from './HintPanel.vue'
import PlotAnnotate from './PlotAnnotate.vue'
import VoiceInput from './VoiceInput.vue'
const props = defineProps<{ user: User; records: Conversation[]; initialQuestion: string; selectedId: string }>()
const emit = defineEmits<{ saved: []; select: [id: string] }>()
const question = ref(props.initialQuestion)
const topic = ref(props.user.role === 'teacher' ? '教学设计' : props.initialQuestion.includes('费曼') ? '费曼练习' : props.initialQuestion.includes('导数') ? '导数与微分' : '函数与极限')
/* 主题下拉选项：与后端 suggest_topic 的建议值共用同一份列表，见 agentTools.topicOptions */
const topics = computed(() => topicOptions(props.user.role))
const active = ref<Conversation | null>(props.records.find(r => r.id === props.selectedId) || null)
const busy = ref(false), favoriting = ref(false)
const historyOpen = ref(false), favoritesOnly = ref(false)
const locked = computed(() => busy.value || favoriting.value)
function openHistoryRecord(id: string) { if (locked.value) return; emit('select', id); historyOpen.value = false }
function askFromHistory() { historyOpen.value = false; newQuestion() }
const error = ref('')
const serviceMode = ref<'demo' | 'live' | 'unknown'>('unknown')
async function refreshMode() {
  try { serviceMode.value = (await api<{ mode: 'demo' | 'live' }>('/agent/status')).mode }
  catch { serviceMode.value = 'unknown' }
}
onMounted(refreshMode)
const input = ref<HTMLTextAreaElement>()
watch(() => props.selectedId, id => {
  if (!id) active.value = null
  else if (active.value?.id !== id) active.value = props.records.find(r => r.id === id) || null
})
watch(() => props.initialQuestion, value => { question.value = value; if (value.includes('费曼')) topic.value = '费曼练习' })
const prompts = props.user.role === 'teacher' ? ['帮我设计一节导数概念微课', '如何用例题解释瞬时变化率？', '设计一道课后反思问题'] : ['如何理解 sin(x)/x 在 x→0 时的极限？', '用定义求 x² 的导数', '我想用费曼学习法解释导数']
function setPrompt(text: string) { question.value = text; if (text.includes('费曼')) topic.value = '费曼练习'; nextTick(() => input.value?.focus()) }
async function send() {
  if (!question.value.trim() || locked.value) return
  error.value = ''; busy.value = true
  try { active.value = await api<Conversation>('/conversations', { method: 'POST', body: JSON.stringify({ question: question.value, topic: topic.value }) }); question.value = ''; emit('saved'); emit('select', active.value.id) }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false; void refreshMode() }
}
async function toggleFavorite() {
  if (!active.value || locked.value) return
  favoriting.value = true
  try { active.value = await api<Conversation>(`/conversations/${active.value.id}`, { method: 'PATCH', body: JSON.stringify({ favorite: !active.value.favorite }) }); emit('saved') }
  catch (e) { ElMessage.error((e as Error).message) }
  finally { favoriting.value = false }
}
function newQuestion() { if (locked.value) return; active.value = null; question.value = ''; error.value = ''; emit('select', ''); nextTick(() => input.value?.focus()) }

/* 拍照搜题：识别文本确认后回填提问框，发送仍走原有 /conversations 流程 */
const photoOpen = ref(false)
function applyRecognized(text: string) {
  if (locked.value) return
  const trimmed = text.trim()
  if (!trimmed) return
  const combined = question.value.trim() ? `${question.value.trim()}\n\n${trimmed}` : trimmed
  if (combined.length > 2000) {
    ElMessage.warning('合并后超过2000字，请缩短识别文本或现有问题后重试')
    return
  }
  question.value = combined
  photoOpen.value = false
  /* 拍照组件不带 suggested_topic，这里按关键词兜底；与语音共用 decideTopic，保证行为一致 */
  const decision = decideTopic(props.user.role, null, trimmed, topics.value)
  if (decision.applied) topic.value = decision.topic
  nextTick(() => input.value?.focus())
  ElMessage.success('识别文本已带入提问框，请核对后再发送')
}

/* 工具面板（分层提示 / 图形批注）：默认收起，避免挤占对话空间 */
const toolsOpen = ref(false)
/* 提示与画布的取题对象：优先当前正在编辑的问题，其次正在回看的历史问题 */
const toolQuestion = computed(() => question.value.trim() || active.value?.question.trim() || '')

/* 语音输入：识别草稿确认后回填提问框，与拍照走同一条「不自动发送」的路径 */
const voiceOpen = ref(false)
function applyVoiceText(text: string, suggestedTopic: string | null) {
  if (locked.value) return
  const trimmed = text.trim()
  if (!trimmed) return
  const combined = question.value.trim() ? `${question.value.trim()}\n\n${trimmed}` : trimmed
  if (combined.length > 2000) {
    ElMessage.warning('合并后超过2000字，请缩短识别文本或现有问题后重试')
    return
  }
  question.value = combined
  voiceOpen.value = false
  /* 后端建议的主题若不在下拉里，就保留当前主题并提示，不静默改动 */
  const decision = decideTopic(props.user.role, suggestedTopic, trimmed, topics.value)
  if (decision.applied) topic.value = decision.topic
  else if (decision.suggested) ElMessage.info(`语音建议知识点「${decision.suggested}」不在可选主题内，已保留当前主题`)
  nextTick(() => input.value?.focus())
  ElMessage.success('识别文本已带入提问框，请核对后再发送')
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">THINK TOGETHER</div><h1>{{ user.role === 'teacher' ? '教学灵感，从对话开始' : '把困惑说出来，一起想明白' }}</h1><p>数伴智能体 · 你的高数{{ user.role === 'teacher' ? '教学' : '学习' }}伙伴</p></div><span class="status-pill"><span class="tiny-dot"/> {{ serviceMode === 'live' ? '模型模式' : serviceMode === 'demo' ? '演示模式' : '状态待确认' }}</span></div>
  <div class="agent-layout">
    <section class="chat-panel panel">
      <header class="chat-header"><div class="agent-avatar"><Sparkles :size="20"/></div><div><strong>数伴 AI</strong><small>耐心听你说，陪你一步步探索</small></div><div class="chat-header-actions"><button class="subtle-link" :disabled="locked" @click="photoOpen = true"><Camera :size="15"/> 拍照搜题</button><button class="subtle-link" :disabled="locked" @click="voiceOpen = true"><Mic :size="15"/> 语音提问</button><button class="subtle-link" :class="{ 'is-on': toolsOpen }" :disabled="locked" @click="toolsOpen = !toolsOpen"><ChartSpline :size="15"/> 学习工具</button><button class="subtle-link" :disabled="locked" @click="historyOpen = true"><History :size="15"/> 对话记录</button><button class="subtle-link" :disabled="locked" @click="newQuestion"><Plus :size="15"/> 新问题</button></div></header>
      <div class="chat-body" aria-live="polite">
        <div v-if="!active" class="chat-welcome"><div class="welcome-symbol"><Sparkles :size="32"/></div><h2>你好，{{ user.name }} 👋</h2><p>不用急着得到答案。<br>我们可以先从你最想理解的那一步开始。</p><div class="prompt-list"><button v-for="(prompt, i) in prompts" :key="prompt" @click="setPrompt(prompt)"><component :is="[Sigma, Lightbulb, BookOpen][i]" :size="18"/><span>{{ prompt }}</span><ArrowUp :size="15"/></button></div></div>
        <template v-else><div class="user-message"><span class="message-label">{{ user.name }} · {{ formatDate(active.created_at) }}</span><div>{{ active.question }}</div></div><div class="agent-message"><div class="agent-avatar"><Sparkles :size="18"/></div><div class="answer-content"><div class="message-label">数伴 AI <span class="demo-label">{{ active.mode === 'live' ? '模型生成 · 请核对' : '预设演示回复' }}</span></div><p v-if="active.notice" class="form-error" role="status">{{ active.notice }}</p><MathText :text="active.answer"/><div v-if="active.references?.length" class="answer-references"><strong>检索资料</strong><p v-for="reference in active.references" :key="reference.id">[{{ reference.index }}] {{ reference.title }} · {{ reference.source }}<small>{{ reference.verified ? '已复核' : '待课程资料复核' }}</small></p></div><button class="subtle-link save-answer" :disabled="locked" @click="toggleFavorite"><Check v-if="active.favorite" :size="15"/><Bookmark v-else :size="15"/>{{ active.favorite ? '已收藏到复习本' : '收藏到复习本' }}</button></div></div></template>
        <div v-if="busy" class="thinking">正在准备回复<span>···</span></div>
      </div>
      <form class="chat-compose" @submit.prevent="send"><div class="compose-topic"><span class="tiny-dot"/><label for="topic-select">本次主题</label><select id="topic-select" v-model="topic"><option v-for="item in topics" :key="item" :value="item">{{ item }}</option></select><span class="char-count">{{ question.length }}/2000</span></div><textarea ref="input" v-model="question" maxlength="2000" aria-label="向数伴提问" placeholder="写下你的问题或思考，让我们一起探索…" @keydown.enter.exact.prevent="!$event.isComposing && send()"></textarea><div class="compose-bottom"><span>Enter 发送 · Shift + Enter 换行</span><button class="send-button" type="submit" aria-label="发送问题" :disabled="locked || !question.trim()"><ArrowUp :size="20"/></button></div><p v-if="error" class="form-error" role="alert">{{ error }} 问题已保留。</p></form>
      <div v-if="toolsOpen" class="agent-tools">
        <HintPanel :question="toolQuestion" :topic="topic" :disabled="locked"/>
        <PlotAnnotate :question="toolQuestion" :topic="topic" :disabled="locked"/>
        <p class="agent-tools-note">提示与图形批注都基于上面的问题内容；两者都不会写入学习记录，也不会代替你的作答。</p>
      </div>
      <p class="chat-disclaimer">按每条回复标明模型或演示来源；模型输出和检索资料都需要结合教材核对。</p>
    </section>
    <aside class="agent-aside"><div class="panel side-tip"><div class="section-kicker"><Lightbulb :size="18"/> 好问题的小提示</div><h3>让思考更进一步</h3><p>告诉数伴你正在学什么、尝试过什么，以及具体卡在哪里。</p><div class="quote">“我知道导数的公式，<br>但为什么要用极限定义它？”</div></div><div class="panel"><div class="section-heading"><h3>最近的问题</h3><button class="subtle-link" :disabled="locked" @click="historyOpen = true">全部记录</button></div><button v-for="r in records.slice(0, 5)" :key="r.id" class="recent-question" :disabled="locked" @click="openHistoryRecord(r.id)"><span>{{ r.question }}</span><small>{{ formatDate(r.created_at) }}</small></button><p v-if="!records.length" class="empty-small">还没有提问，从左边开始吧。</p></div><div class="coming-note"><span>接下来，我们还会…</span><p>步骤反馈 · 语音讲解</p><small>拍照搜题、语音提问已可在对话上方使用，识别文本确认后带入提问；「学习工具」里可按层级要提示、画函数图形批注；课程引用已可随问答查看</small></div></aside>
    <PhotoSearchDialog v-model="photoOpen" :user="user" @apply="applyRecognized"/>
    <VoiceInput v-model="voiceOpen" :user="user" @apply="applyVoiceText"/>
  </div>
  <el-dialog v-model="historyOpen" title="对话记录" width="900px" class="agent-history-dialog"><div class="history-controls"><div class="filter-tabs" aria-label="记录范围"><button :class="{ active: !favoritesOnly }" @click="favoritesOnly = false">全部记录</button><button :class="{ active: favoritesOnly }" @click="favoritesOnly = true">已收藏</button></div><button class="subtle-link" @click="emit('saved')"><RefreshCw :size="14"/> 刷新记录</button></div><RecordsView :records="records" :favorites="favoritesOnly" embedded :disabled="locked" @open="openHistoryRecord" @ask="askFromHistory"/><p class="account-note">仅显示当前账号的提问与回复。打开记录用于回看；新的提问仍独立处理，不自动携带历史上下文。</p></el-dialog>
</template>
