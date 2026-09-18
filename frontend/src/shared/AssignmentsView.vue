<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Plus, ClipboardList, ArrowRight, CalendarDays, RefreshCw } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, localToday, reviewLabel, type Assignment, type User, type Submission, type ReviewStatus } from './api'
import MathText from './MathText.vue'
import FeedbackView from './FeedbackView.vue'
const props = defineProps<{ user: User; assignments: Assignment[]; createRequested: boolean; openId?: string }>()
const emit = defineEmits<{ saved: []; refresh: []; closeCreate: []; opened: [] }>()
const teacher = computed(() => props.user.role === 'teacher')
const filter = ref('published'), search = ref('')
const visible = computed(() => props.assignments.filter(a => a.status === filter.value && `${a.title} ${a.content}`.includes(search.value)))
const editing = ref(false), editId = ref(''), activeId = ref(''), busy = ref(false), error = ref(''), formError = ref('')
const active = computed(() => props.assignments.find(a => a.id === activeId.value))
const answer = ref(''), extension = ref('')
const form = ref({ title: '', content: '', topic: '函数与极限', due_date: '' })
const confirmation = ref<{ item: Assignment; action: 'archive' | 'delete' } | null>(null)
const reviewing = ref<Submission | null>(null), reviewError = ref('')
const reviewForm = ref<{ comment: string; status: ReviewStatus }>({ comment: '', status: 'needs_improvement' })
function edit(a?: Assignment) { editId.value = a?.id || ''; form.value = a ? { title: a.title, content: a.content, topic: a.topic, due_date: a.due_date } : { title: '', content: '', topic: '函数与极限', due_date: '' }; formError.value = ''; editing.value = true }
watch(() => props.createRequested, value => { if (value) edit() }, { immediate: true })
watch(editing, value => { if (!value) emit('closeCreate') })
watch(() => [props.openId, props.assignments] as const, () => { const item = props.assignments.find(a => a.id === props.openId); if (item) { filter.value = 'draft'; edit(item); emit('opened') } }, { immediate: true })
function open(a: Assignment) { activeId.value = a.id; answer.value = a.answer; extension.value = a.due_date; error.value = '' }
function statusLabel(a: Assignment) { if (a.status === 'draft') return '草稿'; if (a.status === 'archived') return '已归档'; if (!teacher.value && a.submission) return `已提交 · ${reviewLabel(a.submission.review?.status)}`; return a.due_date < localToday() ? '已截止' : '进行中' }
async function save(publish = false) {
  if (busy.value) return; busy.value = true; formError.value = ''
  try {
    const result = await api<Assignment>(editId.value ? `/assignments/${editId.value}` : '/assignments/drafts', { method: editId.value ? 'PATCH' : 'POST', body: JSON.stringify(form.value) }); editId.value = result.id
    if (publish) await api(`/assignments/${result.id}/publish`, { method: 'POST' })
    filter.value = publish ? 'published' : 'draft'; editing.value = false; emit('saved'); ElMessage.success(publish ? '作业已发布至演示班级' : '草稿已保存，仅你可见')
  } catch (e) { formError.value = (e as Error).message; emit('refresh') } finally { busy.value = false }
}
async function action(a: Assignment, kind: 'copy' | 'publish') {
  if (busy.value) return; busy.value = true; error.value = ''
  try { const result = await api<Assignment>(`/assignments/${a.id}/${kind}`, { method: 'POST' }); emit('saved'); if (kind === 'copy') { filter.value = 'draft'; edit(result) } else filter.value = 'published'; ElMessage.success(kind === 'copy' ? '已复制为新草稿' : '作业已发布') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function confirmAction() {
  if (!confirmation.value || busy.value) return; busy.value = true; error.value = ''
  const { item, action } = confirmation.value
  try { await api(`/assignments/${item.id}${action === 'archive' ? '/archive' : ''}`, { method: action === 'archive' ? 'POST' : 'DELETE' }); confirmation.value = null; activeId.value = ''; emit('saved'); ElMessage.success(action === 'archive' ? '已归档，记录完整保留' : '草稿已删除') }
  catch (e) { error.value = (e as Error).message; confirmation.value = null } finally { busy.value = false }
}
async function extend() {
  if (!active.value || busy.value) return; busy.value = true; error.value = ''
  try { await api(`/assignments/${active.value.id}`, { method: 'PATCH', body: JSON.stringify({ due_date: extension.value }) }); emit('saved'); ElMessage.success('截止日期已更新') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function submit() {
  if (!active.value || busy.value) return; busy.value = true; error.value = ''
  try { await api(`/assignments/${active.value.id}/submission`, { method: 'PUT', body: JSON.stringify({ answer: answer.value }) }); emit('saved'); ElMessage.success('作答已保存，等待教师批改') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
function review(s: Submission) { reviewing.value = s; reviewForm.value = { comment: s.review?.comment || '', status: s.review?.status || 'needs_improvement' }; reviewError.value = '' }
async function saveReview() {
  if (!active.value || !reviewing.value || busy.value) return; busy.value = true; reviewError.value = ''
  try { await api(`/assignments/${active.value.id}/submissions/${reviewing.value.student_id}/review`, { method: 'PUT', body: JSON.stringify({ ...reviewForm.value, version: reviewing.value.version }) }); reviewing.value = null; emit('saved'); ElMessage.success('反馈已保存，学生可查看') }
  catch (e) { reviewError.value = (e as Error).message } finally { busy.value = false }
}
function reloadReview() { reviewing.value = null; emit('refresh') }
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">PRACTICE & REFLECTION</div><h1>{{ teacher ? '让课堂的思考继续' : '把理解，写进练习里' }}</h1><p>{{ teacher ? '从草稿到反馈，管理演示班级的每一份作业。' : '留下解题过程，查看老师的建议，再改进一次。' }}</p></div><div class="action-row"><button class="outline-button" :disabled="busy" @click="emit('refresh')"><RefreshCw :size="16"/> 刷新作业</button><button v-if="teacher" class="primary-button" @click="edit()"><Plus :size="17"/> 新建作业</button></div></div>
  <div class="panel work-toolbar"><div class="filter-tabs"><button v-if="teacher" :class="{ active: filter === 'draft' }" @click="filter = 'draft'">草稿</button><button :class="{ active: filter === 'published' }" @click="filter = 'published'">已发布</button><button :class="{ active: filter === 'archived' }" @click="filter = 'archived'">已归档</button></div><input v-model="search" aria-label="搜索作业" placeholder="搜索标题或题干"/></div>
  <p v-if="error && !active" class="form-error" role="alert">{{ error }}</p>
  <div class="assignment-grid"><article v-for="a in visible" :key="a.id" class="panel assignment-card"><div class="section-heading"><span class="stat-icon lilac"><ClipboardList :size="22"/></span><span class="small-pill">{{ statusLabel(a) }}</span></div><span class="section-kicker">{{ a.topic || '章节待填写' }}</span><h3>{{ a.title || '未命名草稿' }}</h3><div class="assignment-preview"><MathText :text="a.content || '题干待填写'"/></div><p v-if="teacher && a.status !== 'draft'" class="muted small">{{ a.submissions?.length || 0 }} 份提交 · {{ a.submissions?.filter(s => !s.review).length || 0 }} 份待批改</p><div class="assignment-footer"><span><CalendarDays :size="14"/> {{ a.due_date || '未设截止日期' }}</span><button class="subtle-link" @click="a.status === 'draft' ? edit(a) : open(a)">{{ a.status === 'draft' ? '继续编辑' : teacher ? '查看 / 批改' : '作答 / 反馈' }} <ArrowRight :size="15"/></button></div><div v-if="teacher" class="action-row card-actions"><button v-if="a.status === 'draft'" class="outline-button" :disabled="busy" @click="action(a, 'publish')">发布</button><button class="subtle-link" :disabled="busy" @click="action(a, 'copy')">复制为草稿</button><button v-if="a.status !== 'archived'" class="subtle-link" :disabled="busy" @click="confirmation = { item: a, action: a.status === 'draft' ? 'delete' : 'archive' }">{{ a.status === 'draft' ? '删除草稿' : '归档' }}</button></div></article></div>
  <div v-if="!visible.length" class="panel empty-state"><ClipboardList :size="38"/><h3>暂无匹配作业</h3><p>{{ teacher ? '新建草稿，或从题库选择题目开始。' : '老师发布后，可在这里查看和提交。' }}</p></div>
  <el-dialog v-model="editing" :title="editId ? '编辑作业草稿' : '新建作业草稿'" width="680px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy"><form class="dialog-form" novalidate @submit.prevent="save(false)"><p class="muted">草稿仅你可见，可稍后补齐；发布后演示班级学生可查看。</p><label>作业标题<input v-model="form.title" maxlength="100" placeholder="例如：导数定义与几何意义"/></label><div class="form-row"><label>所属章节<input v-model="form.topic" maxlength="40"/></label><label>截止日期<input v-model="form.due_date" type="date" :min="localToday()"/></label></div><label>题目与要求<textarea v-model="form.content" rows="7" maxlength="3000" placeholder="支持 $公式$ 与 $$独立公式$$"></textarea></label><details><summary>题干预览</summary><MathText :text="form.content"/></details><p v-if="formError" class="form-error" role="alert">{{ formError }}</p><div class="dialog-actions"><button type="button" class="outline-button" :disabled="busy" @click="editing = false">取消</button><button class="outline-button" :disabled="busy">保存草稿</button><button type="button" class="primary-button" :disabled="busy" @click="save(true)">{{ busy ? '保存中…' : '保存并发布' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!active" :title="active?.title" width="760px" :close-on-click-modal="false" :show-close="!busy" :close-on-press-escape="!busy" @update:model-value="!$event && (activeId = '')"><template v-if="active"><div class="action-row"><span class="small-pill">{{ active.topic }} · {{ statusLabel(active) }}</span><span class="muted">{{ active.due_date }} 截止</span></div><div class="assignment-full"><MathText :text="active.content"/></div><p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <template v-if="teacher"><form v-if="active.status === 'published'" class="dialog-form extension-form" @submit.prevent="extend"><label>延长截止日期<input v-model="extension" type="date" :min="active.due_date" required/></label><button class="outline-button" :disabled="busy">更新日期</button></form><h4>学生作答（{{ active.submissions?.length || 0 }}）</h4><article v-for="s in active.submissions" :key="s.id" class="submission-card"><div class="section-heading"><strong>{{ s.student_name }} · 第 {{ s.version }} 版</strong><small class="muted">{{ new Date(s.created_at).toLocaleString('zh-CN') }}</small></div><MathText :text="s.answer"/><FeedbackView :submission="s"/><button v-if="active.status === 'published'" class="outline-button" :disabled="busy" @click="review(s)">{{ s.review ? '修改当前反馈' : '填写反馈' }}</button></article><p v-if="!active.submissions?.length" class="empty-small">尚未收到作答。可切换学生账号体验。</p></template>
    <template v-else><FeedbackView v-if="active.submission" :submission="active.submission"/><form class="dialog-form" @submit.prevent="submit"><label>我的作答<textarea v-model="answer" rows="7" required maxlength="5000" :readonly="active.status !== 'published' || active.due_date < localToday()"></textarea></label><details><summary>作答预览</summary><MathText :text="answer"/></details><p class="muted small">截止前可修改；每次保存生成新版作答，需教师重新批改。历史反馈保留。</p><div class="dialog-actions"><button class="primary-button" :disabled="busy || active.status !== 'published' || active.due_date < localToday()">{{ active.status === 'archived' ? '已归档 · 只读' : active.due_date < localToday() ? '作业已截止' : busy ? '保存中…' : '提交作答' }}</button></div></form></template>
  </template></el-dialog>
  <el-dialog :model-value="!!reviewing" title="教师人工反馈" width="600px" :close-on-click-modal="false" :show-close="!busy" :close-on-press-escape="!busy" @update:model-value="!$event && (reviewing = null)"><form v-if="reviewing" class="dialog-form" @submit.prevent="saveReview"><p>正在批改 {{ reviewing.student_name }} 的第 {{ reviewing.version }} 版作答。</p><MathText :text="reviewing.answer"/><label>完成状态<select v-model="reviewForm.status"><option value="needs_improvement">待改进</option><option value="completed">已完成</option></select></label><label>教师评语<textarea v-model="reviewForm.comment" required maxlength="3000" rows="5" placeholder="指出值得保留的思路和下一步建议"></textarea></label><p v-if="reviewError" class="form-error" role="alert">{{ reviewError }} <button type="button" class="subtle-link" :disabled="busy" @click="reloadReview">刷新作答后重新批改</button></p><div class="dialog-actions"><button type="button" class="outline-button" :disabled="busy" @click="reviewing = null">取消</button><button class="primary-button" :disabled="busy">保存反馈</button></div></form></el-dialog>
  <el-dialog :model-value="!!confirmation" :title="confirmation?.action === 'delete' ? '删除草稿' : '归档作业'" width="460px" :close-on-click-modal="false" :show-close="!busy" :close-on-press-escape="!busy" @update:model-value="!$event && (confirmation = null)"><p>{{ confirmation?.action === 'delete' ? '此草稿尚未发布，删除后无法恢复。' : '归档后学生可查看已有内容与反馈，但不能再提交；教师不能继续批改。此操作不能撤销。' }}</p><div class="dialog-actions"><button class="outline-button" :disabled="busy" @click="confirmation = null">取消</button><button class="primary-button" :disabled="busy" @click="confirmAction">确认{{ confirmation?.action === 'delete' ? '删除' : '归档' }}</button></div></el-dialog>
</template>
