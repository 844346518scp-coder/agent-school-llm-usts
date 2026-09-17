<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus, RefreshCw, Search, BookOpen } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type Question } from '../shared/api'
import MathText from '../shared/MathText.vue'
const emit = defineEmits<{ drafted: [id: string] }>()
const questions = ref<Question[]>([])
const search = ref(''), topic = ref(''), archived = ref(false), selected = ref<Question[]>([])
const loading = ref(false), busy = ref(false), error = ref(''), dialogError = ref(''), editing = ref(false), editId = ref('')
const form = ref({ title: '', topic: '函数与极限', content: '', reference_answer: '' })
const confirmArchive = ref<Question | null>(null)
let request = 0
async function load() {
  const current = ++request; loading.value = true; error.value = ''
  try { const result = await api<Question[]>(`/questions?${new URLSearchParams({ search: search.value, topic: topic.value, archived: String(archived.value) })}`); if (current === request) questions.value = result }
  catch (e) { if (current === request) error.value = (e as Error).message }
  finally { if (current === request) loading.value = false }
}
function edit(q?: Question) { editId.value = q?.id || ''; form.value = q ? { title: q.title, topic: q.topic, content: q.content, reference_answer: q.reference_answer } : { title: '', topic: '函数与极限', content: '', reference_answer: '' }; dialogError.value = ''; editing.value = true }
function toggle(q: Question) { selected.value = selected.value.some(s => s.id === q.id) ? selected.value.filter(s => s.id !== q.id) : [...selected.value, q] }
async function save() {
  if (busy.value) return; busy.value = true; dialogError.value = ''
  try { await api(`/questions${editId.value ? '/' + editId.value : ''}`, { method: editId.value ? 'PATCH' : 'POST', body: JSON.stringify(form.value) }); editing.value = false; await load(); ElMessage.success('题目已保存') }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
async function archive() {
  if (!confirmArchive.value || busy.value) return; busy.value = true; error.value = ''
  try { await api(`/questions/${confirmArchive.value.id}/archive`, { method: 'POST' }); selected.value = selected.value.filter(q => q.id !== confirmArchive.value!.id); confirmArchive.value = null; await load() }
  catch (e) { error.value = (e as Error).message; confirmArchive.value = null } finally { busy.value = false }
}
async function draft() {
  if (busy.value || !selected.value.length) return; busy.value = true; error.value = ''
  try { const result = await api<{ id: string }>('/assignments/drafts', { method: 'POST', body: JSON.stringify({ title: '题库练习', topic: selected.value[0].topic, question_ids: selected.value.map(q => q.id) }) }); selected.value = []; emit('drafted', result.id); ElMessage.success('题干已复制到草稿，请补充要求和截止日期') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">PREPARE WITH CARE</div><h1>我的题库</h1><p>积累好问题，组合下一次课堂练习。参考答案仅你可见。</p></div><button class="primary-button" @click="edit()"><Plus :size="17"/> 新建题目</button></div>
  <form class="panel work-toolbar" @submit.prevent="load"><label class="search-field"><Search :size="17"/><input v-model="search" aria-label="搜索题目" placeholder="搜索标题或题干"/></label><input v-model="topic" aria-label="按章节筛选" placeholder="章节名称（精确匹配）"/><select v-model="archived" aria-label="题库状态" @change="load"><option :value="false">使用中</option><option :value="true">已归档</option></select><button class="outline-button" :disabled="loading"><RefreshCw :size="15"/> 查询 / 刷新</button></form>
  <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="loading" class="muted" role="status">正在读取题库…</p>
  <section v-if="selected.length" class="panel selection-panel"><strong>已选 {{ selected.length }} 道 · 按选择顺序出题</strong><div class="action-row"><button v-for="(q, i) in selected" :key="q.id" class="small-pill" @click="toggle(q)">{{ i + 1 }}. {{ q.title }} ×</button></div><button class="primary-button" :disabled="busy" @click="draft">生成作业草稿</button></section>
  <div class="question-grid"><article v-for="q in questions" :key="q.id" class="panel question-card"><div class="section-heading"><span class="small-pill">{{ q.topic }}</span><label v-if="!q.archived" class="check-label"><input type="checkbox" :checked="selected.some(s => s.id === q.id)" @change="toggle(q)"/> 选择出题</label><span v-else class="muted">已归档</span></div><h3>{{ q.title }}</h3><MathText :text="q.content"/><details v-if="q.reference_answer"><summary>参考答案 · 仅教师可见</summary><MathText :text="q.reference_answer"/></details><div v-if="!q.archived" class="action-row"><button class="outline-button" @click="edit(q)">编辑题目</button><button class="subtle-link" @click="confirmArchive = q">归档题目</button></div></article></div>
  <div v-if="!loading && !questions.length" class="panel empty-state"><BookOpen :size="34"/><h3>暂无匹配题目</h3><p>新建一道题，或调整搜索条件。</p></div>
  <el-dialog v-model="editing" :title="editId ? '编辑题目' : '新建题目'" width="680px" :close-on-click-modal="false" :show-close="!busy" :close-on-press-escape="!busy"><form class="dialog-form" @submit.prevent="save"><label>标题<input v-model="form.title" required maxlength="100"/></label><label>章节<input v-model="form.topic" required maxlength="40" list="question-topics"/></label><datalist id="question-topics"><option>函数与极限</option><option>导数与微分</option></datalist><label>题干<textarea v-model="form.content" required rows="5" maxlength="3000" placeholder="可使用 $公式$ 或 $$独立公式$$"></textarea></label><label>参考答案（可选，仅教师可见）<textarea v-model="form.reference_answer" rows="3" maxlength="3000"></textarea></label><details><summary>公式预览</summary><MathText :text="form.content"/><MathText :text="form.reference_answer"/></details><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" type="button" :disabled="busy" @click="editing = false">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '保存题目' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!confirmArchive" title="归档题目" width="440px" :show-close="!busy" :close-on-click-modal="false" :close-on-press-escape="!busy" @update:model-value="!$event && (confirmArchive = null)"><p>归档后不能编辑或加入新作业，已有作业保持原样。</p><div class="dialog-actions"><button class="outline-button" :disabled="busy" @click="confirmArchive = null">取消</button><button class="primary-button" :disabled="busy" @click="archive">确认归档</button></div></el-dialog>
</template>
