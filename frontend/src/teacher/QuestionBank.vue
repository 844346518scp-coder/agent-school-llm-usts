<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Plus, RefreshCw, Search, BookOpen } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type Question } from '../shared/api'
import MathText from '../shared/MathText.vue'
import { courseChapters, chapterTitle, groupQuestions } from '../shared/courseChapters'
const emit = defineEmits<{ selected: [questions: Question[]]; cancel: [] }>()
const questions = ref<Question[]>([])
const search = ref(''), archived = ref(false), selected = ref<Question[]>([])
const loading = ref(false), busy = ref(false), error = ref(''), dialogError = ref(''), editing = ref(false), editId = ref('')
const form = ref({ title: '', topic: '函数与极限', content: '', reference_answer: '' })
const confirmArchive = ref<Question | null>(null)
const customChapter = ref(false)
const groups = computed(() => groupQuestions(questions.value, search.value))
let request = 0
async function load() {
  const current = ++request; loading.value = true; error.value = ''
  try { const result = await api<Question[]>(`/questions?${new URLSearchParams({ archived: String(archived.value) })}`); if (current === request) questions.value = result }
  catch (e) { if (current === request) error.value = (e as Error).message }
  finally { if (current === request) loading.value = false }
}
function edit(q?: Question) { editId.value = q?.id || ''; form.value = q ? { title: q.title, topic: q.topic, content: q.content, reference_answer: q.reference_answer } : { title: '', topic: '函数与极限', content: '', reference_answer: '' }; form.value.topic = chapterTitle(form.value.topic); customChapter.value = !courseChapters.some(c => c.title === form.value.topic); dialogError.value = ''; editing.value = true }
function toggle(q: Question) { if (selected.value.some(s => s.id === q.id)) selected.value = selected.value.filter(s => s.id !== q.id); else if (selected.value.length < 30) selected.value = [...selected.value, q]; else ElMessage.warning('每次最多选择 30 道题目') }
function move(index: number, delta: number) { const copy = [...selected.value]; [copy[index], copy[index + delta]] = [copy[index + delta], copy[index]]; selected.value = copy }
async function save() {
  if (busy.value) return; busy.value = true; dialogError.value = ''
  try { const result = await api<Question>(`/questions${editId.value ? '/' + editId.value : ''}`, { method: editId.value ? 'PATCH' : 'POST', body: JSON.stringify(form.value) }); editing.value = false; selected.value = selected.value.map(q => q.id === result.id ? result : q); await load(); ElMessage.success('题目已保存') }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
async function archive() {
  if (!confirmArchive.value || busy.value) return; busy.value = true; error.value = ''
  try { await api(`/questions/${confirmArchive.value.id}/archive`, { method: 'POST' }); selected.value = selected.value.filter(q => q.id !== confirmArchive.value!.id); confirmArchive.value = null; await load() }
  catch (e) { error.value = (e as Error).message; confirmArchive.value = null } finally { busy.value = false }
}
async function choose() {
  if (busy.value || !selected.value.length) return; busy.value = true; error.value = ''
  try {
    const current = await api<Question[]>('/questions')
    const fresh = selected.value.map(q => current.find(item => item.id === q.id))
    if (fresh.some(q => !q)) { selected.value = fresh.filter((q): q is Question => !!q); error.value = '部分题目已归档或不可用，已移除，请确认后重新加入。'; return }
    emit('selected', fresh as Question[])
  } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <section class="question-picker">
    <div class="section-heading"><div><h3>从题库选题</h3><p class="muted small">题目按章节顺序排列，直接勾选，可跨章组合。</p></div><div class="action-row"><button type="button" class="outline-button" :disabled="busy" @click="edit()"><Plus :size="15"/> 新建题目</button></div></div>
    <p class="account-note">章节分类参考同济《高等数学》第八版 · 题目由教师维护</p>
    <form class="work-toolbar picker-toolbar" @submit.prevent="load"><label class="search-field"><Search :size="17"/><input v-model="search" aria-label="搜索题目" placeholder="搜索标题或题干"/></label><select v-model="archived" aria-label="题库状态" @change="load"><option :value="false">使用中</option><option :value="true">已归档</option></select><button class="outline-button" :disabled="loading || busy"><RefreshCw :size="15"/> 刷新</button></form>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="loading" class="muted" role="status">正在读取题库…</p>
    <div class="picker-chapters"><section v-for="group in groups" :key="group.title" class="picker-chapter"><h4 class="chapter-heading">{{ group.label }} <small>{{ group.volume }} · {{ group.questions.length }} 题</small></h4><div class="chapter-questions"><article v-for="q in group.questions" :key="q.id" class="panel question-card"><div class="section-heading"><span class="small-pill">{{ chapterTitle(q.topic) }}</span><label v-if="!q.archived" class="check-label"><input type="checkbox" :disabled="busy" :checked="selected.some(s => s.id === q.id)" @change="toggle(q)"/> 选择出题</label><span v-else class="muted">已归档</span></div><h3>{{ q.title }}</h3><MathText :text="q.content"/><details v-if="q.reference_answer"><summary>参考答案 · 仅教师可见</summary><MathText :text="q.reference_answer"/></details><div v-if="!q.archived" class="action-row"><button type="button" class="subtle-link" :disabled="busy" @click="edit(q)">编辑题目</button><button type="button" class="subtle-link" :disabled="busy" @click="confirmArchive = q">归档题目</button></div></article></div></section></div>
    <div v-if="!loading && !groups.length" class="empty-state compact"><BookOpen :size="30"/><h3>暂无匹配题目</h3><p>新建题目并填写章节后会自动归类，或调整搜索条件。</p><button type="button" class="outline-button" :disabled="busy" @click="edit()">新建题目</button></div>
    <section class="picker-selection"><strong>已选 {{ selected.length }} 道 · 按下列顺序加入</strong><ol v-if="selected.length" class="selected-questions"><li v-for="(q, i) in selected" :key="q.id"><span>{{ q.title }}</span><button type="button" class="subtle-link" :disabled="busy || i === 0" :aria-label="'上移' + q.title" @click="move(i, -1)">上移</button><button type="button" class="subtle-link" :disabled="busy || i === selected.length - 1" :aria-label="'下移' + q.title" @click="move(i, 1)">下移</button><button type="button" class="subtle-link" :disabled="busy" :aria-label="'移除' + q.title" @click="toggle(q)">移除</button></li></ol><div class="dialog-actions"><button type="button" class="outline-button" :disabled="busy" @click="emit('cancel')">取消选题</button><button type="button" class="primary-button" :disabled="busy || !selected.length" @click="choose">{{ busy ? '正在核对题目…' : '加入作业（' + selected.length + '）' }}</button></div></section>
  </section>
  <el-dialog v-model="editing" append-to-body :title="editId ? '编辑题目' : '新建题目'" width="680px" :close-on-click-modal="false" :show-close="!busy" :close-on-press-escape="!busy"><form class="dialog-form" @submit.prevent="save"><label>标题<input v-model="form.title" required maxlength="100"/></label><label>章节<select :value="customChapter ? '__custom__' : form.topic" @change="customChapter = ($event.target as HTMLSelectElement).value === '__custom__'; form.topic = customChapter ? '' : ($event.target as HTMLSelectElement).value"><optgroup v-for="volume in ['上册', '下册']" :key="volume" :label="volume"><option v-for="chapter in courseChapters.filter(c => c.volume === volume)" :key="chapter.number" :value="chapter.title">第 {{ chapter.number }} 章 {{ chapter.title }}</option></optgroup><option value="__custom__">自定义章节</option></select></label><label v-if="customChapter">自定义章节名称<input v-model="form.topic" required maxlength="40"/></label><label>题干<textarea v-model="form.content" required rows="5" maxlength="3000" placeholder="可使用 $公式$ 或 $$独立公式$$"></textarea></label><label>参考答案（可选，仅教师可见）<textarea v-model="form.reference_answer" rows="3" maxlength="3000"></textarea></label><details><summary>公式预览</summary><MathText :text="form.content"/><MathText :text="form.reference_answer"/></details><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" type="button" :disabled="busy" @click="editing = false">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '保存题目' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!confirmArchive" append-to-body title="归档题目" width="440px" :show-close="!busy" :close-on-click-modal="false" :close-on-press-escape="!busy" @update:model-value="!$event && (confirmArchive = null)"><p>归档后不能编辑或加入新作业，已有作业保持原样。</p><div class="dialog-actions"><button class="outline-button" :disabled="busy" @click="confirmArchive = null">取消</button><button class="primary-button" :disabled="busy" @click="archive">确认归档</button></div></el-dialog>
</template>
