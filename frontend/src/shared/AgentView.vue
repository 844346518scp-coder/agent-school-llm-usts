<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowUp, Sparkles, Plus, Bookmark, Check, Lightbulb, Sigma, BookOpen, History, RefreshCw } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type Conversation, type User, formatDate } from './api'
import MathText from './MathText.vue'
import RecordsView from './RecordsView.vue'
const props = defineProps<{ user: User; records: Conversation[]; initialQuestion: string; selectedId: string }>()
const emit = defineEmits<{ saved: []; select: [id: string] }>()
const question = ref(props.initialQuestion)
const topic = ref(props.user.role === 'teacher' ? '教学设计' : props.initialQuestion.includes('费曼') ? '费曼练习' : props.initialQuestion.includes('导数') ? '导数与微分' : '函数与极限')
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
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">THINK TOGETHER</div><h1>{{ user.role === 'teacher' ? '教学灵感，从对话开始' : '把困惑说出来，一起想明白' }}</h1><p>数伴智能体 · 你的高数{{ user.role === 'teacher' ? '教学' : '学习' }}伙伴</p></div><span class="status-pill"><span class="tiny-dot"/> {{ serviceMode === 'live' ? '模型模式' : serviceMode === 'demo' ? '演示模式' : '状态待确认' }}</span></div>
  <div class="agent-layout">
    <section class="chat-panel panel">
      <header class="chat-header"><div class="agent-avatar"><Sparkles :size="20"/></div><div><strong>数伴 AI</strong><small>耐心听你说，陪你一步步探索</small></div><div class="chat-header-actions"><button class="subtle-link" :disabled="locked" @click="historyOpen = true"><History :size="15"/> 对话记录</button><button class="subtle-link" :disabled="locked" @click="newQuestion"><Plus :size="15"/> 新问题</button></div></header>
      <div class="chat-body" aria-live="polite">
        <div v-if="!active" class="chat-welcome"><div class="welcome-symbol"><Sparkles :size="32"/></div><h2>你好，{{ user.name }} 👋</h2><p>不用急着得到答案。<br>我们可以先从你最想理解的那一步开始。</p><div class="prompt-list"><button v-for="(prompt, i) in prompts" :key="prompt" @click="setPrompt(prompt)"><component :is="[Sigma, Lightbulb, BookOpen][i]" :size="18"/><span>{{ prompt }}</span><ArrowUp :size="15"/></button></div></div>
        <template v-else><div class="user-message"><span class="message-label">{{ user.name }} · {{ formatDate(active.created_at) }}</span><div>{{ active.question }}</div></div><div class="agent-message"><div class="agent-avatar"><Sparkles :size="18"/></div><div class="answer-content"><div class="message-label">数伴 AI <span class="demo-label">{{ active.mode === 'live' ? '模型生成 · 请核对' : '预设演示回复' }}</span></div><p v-if="active.notice" class="form-error" role="status">{{ active.notice }}</p><MathText :text="active.answer"/><div v-if="active.references?.length" class="answer-references"><strong>检索资料</strong><p v-for="reference in active.references" :key="reference.id">[{{ reference.index }}] {{ reference.title }} · {{ reference.source }}<small>{{ reference.verified ? '已复核' : '待课程资料复核' }}</small></p></div><button class="subtle-link save-answer" :disabled="locked" @click="toggleFavorite"><Check v-if="active.favorite" :size="15"/><Bookmark v-else :size="15"/>{{ active.favorite ? '已收藏到复习本' : '收藏到复习本' }}</button></div></div></template>
        <div v-if="busy" class="thinking">正在准备回复<span>···</span></div>
      </div>
      <form class="chat-compose" @submit.prevent="send"><div class="compose-topic"><span class="tiny-dot"/><label for="topic-select">本次主题</label><select id="topic-select" v-model="topic"><option>函数与极限</option><option>导数与微分</option><option>费曼练习</option><option v-if="user.role === 'teacher'">教学设计</option></select><span class="char-count">{{ question.length }}/2000</span></div><textarea ref="input" v-model="question" maxlength="2000" aria-label="向数伴提问" placeholder="写下你的问题或思考，让我们一起探索…" @keydown.enter.exact.prevent="!$event.isComposing && send()"></textarea><div class="compose-bottom"><span>Enter 发送 · Shift + Enter 换行</span><button class="send-button" type="submit" aria-label="发送问题" :disabled="locked || !question.trim()"><ArrowUp :size="20"/></button></div><p v-if="error" class="form-error" role="alert">{{ error }} 问题已保留。</p></form>
      <p class="chat-disclaimer">按每条回复标明模型或演示来源；模型输出和检索资料都需要结合教材核对。</p>
    </section>
    <aside class="agent-aside"><div class="panel side-tip"><div class="section-kicker"><Lightbulb :size="18"/> 好问题的小提示</div><h3>让思考更进一步</h3><p>告诉数伴你正在学什么、尝试过什么，以及具体卡在哪里。</p><div class="quote">“我知道导数的公式，<br>但为什么要用极限定义它？”</div></div><div class="panel"><div class="section-heading"><h3>最近的问题</h3><button class="subtle-link" :disabled="locked" @click="historyOpen = true">全部记录</button></div><button v-for="r in records.slice(0, 5)" :key="r.id" class="recent-question" :disabled="locked" @click="openHistoryRecord(r.id)"><span>{{ r.question }}</span><small>{{ formatDate(r.created_at) }}</small></button><p v-if="!records.length" class="empty-small">还没有提问，从左边开始吧。</p></div><div class="coming-note"><span>接下来，我们还会…</span><p>拍照识题 · 步骤反馈</p><small>已有后端接口，页面入口后续接入；课程引用已可随问答查看</small></div></aside>
  </div>
  <el-dialog v-model="historyOpen" title="对话记录" width="900px" class="agent-history-dialog"><div class="history-controls"><div class="filter-tabs" aria-label="记录范围"><button :class="{ active: !favoritesOnly }" @click="favoritesOnly = false">全部记录</button><button :class="{ active: favoritesOnly }" @click="favoritesOnly = true">已收藏</button></div><button class="subtle-link" @click="emit('saved')"><RefreshCw :size="14"/> 刷新记录</button></div><RecordsView :records="records" :favorites="favoritesOnly" embedded :disabled="locked" @open="openHistoryRecord" @ask="askFromHistory"/><p class="account-note">仅显示当前账号的提问与回复。打开记录用于回看；新的提问仍独立处理，不自动携带历史上下文。</p></el-dialog>
</template>
