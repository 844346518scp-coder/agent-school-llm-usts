<script setup lang="ts">
import { ref, watch } from 'vue'
import { Plus, ClipboardList, ArrowRight, Check, CalendarDays, Send } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type Assignment, type User } from './api'
const props = defineProps<{ user: User; assignments: Assignment[]; createRequested: boolean }>()
const emit = defineEmits<{ saved: []; closeCreate: [] }>()
const creating = ref(props.createRequested)
const active = ref<Assignment | null>(null)
const answer = ref('')
const busy = ref(false)
const error = ref('')
const form = ref({ title: '', content: '', topic: '函数与极限', due_date: '' })
watch(() => props.createRequested, value => { if (value) creating.value = true })
watch(creating, value => { error.value = ''; if (!value) emit('closeCreate') })
function open(a: Assignment) { active.value = a; answer.value = a.answer; error.value = '' }
async function create() {
  if (busy.value) return
  error.value = ''; busy.value = true
  try { await api('/assignments', { method: 'POST', body: JSON.stringify(form.value) }); creating.value = false; form.value = { title: '', content: '', topic: '函数与极限', due_date: '' }; emit('saved'); ElMessage.success('作业已发布，学生端现在可以查看。') }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
async function submit() {
  if (!active.value || busy.value) return
  error.value = ''; busy.value = true
  try { await api(`/assignments/${active.value.id}/submission`, { method: 'PUT', body: JSON.stringify({ answer: answer.value }) }); active.value = null; emit('saved'); ElMessage.success('作答已保存，老师可以查看你的思考。') }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">PRACTICE & REFLECTION</div><h1>{{ user.role === 'teacher' ? '让课堂的思考继续' : '把理解，写进练习里' }}</h1><p>{{ user.role === 'teacher' ? '发布给演示班级的作业，并查看学生的实际提交。' : '完成老师的课堂任务，留下你的解题过程。' }}</p></div><button v-if="user.role === 'teacher'" class="primary-button" @click="creating = true"><Plus :size="17"/> 发布新作业</button></div>
  <div class="assignment-grid"><article v-for="a in assignments" :key="a.id" class="panel assignment-card"><div class="section-heading"><span class="stat-icon" :class="a.submitted ? 'green' : 'lilac'"><Check v-if="a.submitted" :size="22"/><ClipboardList v-else :size="22"/></span><span class="small-pill" :class="{ success: a.submitted }">{{ user.role === 'teacher' ? `${a.submissions?.length || 0} 份提交` : a.submitted ? '已提交' : a.due_date < today() ? '已截止' : '待完成' }}</span></div><span class="section-kicker">{{ a.topic }}</span><h3>{{ a.title }}</h3><p class="assignment-preview">{{ a.content }}</p><div class="assignment-footer"><span><CalendarDays :size="14"/> {{ a.due_date }}</span><button class="subtle-link" @click="open(a)">{{ user.role === 'teacher' ? '查看作答' : a.submitted ? '查看 / 修改' : '开始作答' }} <ArrowRight :size="15"/></button></div></article></div><div v-if="!assignments.length" class="panel empty-state"><ClipboardList :size="38"/><h3>还没有作业</h3><p>{{ user.role === 'teacher' ? '发布第一份练习，开启教学闭环。' : '老师发布后，作业会出现在这里。' }}</p></div>
  <el-dialog v-model="creating" title="发布新作业" width="560px" :close-on-click-modal="false"><form class="dialog-form" @submit.prevent="create"><p class="muted">发布至「高等数学 · 演示班级」，预设学生可立即查看。</p><label>作业标题<input v-model="form.title" required maxlength="100" placeholder="例如：导数定义与几何意义"/></label><div class="form-row"><label>所属章节<select v-model="form.topic"><option>函数与极限</option><option>导数与微分</option></select></label><label>截止日期<input v-model="form.due_date" type="date" required :min="today()"/></label></div><label>题目与要求<textarea v-model="form.content" rows="5" maxlength="3000" required placeholder="写下题目，鼓励学生展示思考过程。"></textarea></label><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="dialog-actions"><button type="button" class="outline-button" @click="creating = false">取消</button><button class="primary-button" type="submit" :disabled="busy"><Send :size="16"/>{{ busy ? '正在发布…' : '确认发布' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!active" :title="active?.title" width="660px" :close-on-click-modal="false" @update:model-value="!$event && (active = null)"><template v-if="active"><span class="small-pill">{{ active.topic }} · {{ active.due_date }} 截止</span><div class="assignment-full">{{ active.content }}</div><form v-if="user.role === 'student'" class="dialog-form" @submit.prevent="submit"><label>我的作答<textarea v-model="answer" rows="7" required maxlength="5000" placeholder="写出你的答案与推理步骤…"></textarea></label><p class="muted small">提交后仍可在截止前修改；本版本不自动评分。</p><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="dialog-actions"><button class="primary-button" type="submit" :disabled="busy || active.due_date < today()">{{ busy ? '正在保存…' : active.due_date < today() ? '作业已截止' : '提交作答' }}</button></div></form><div v-else><h4>学生作答（{{ active.submissions?.length || 0 }}）</h4><div v-for="s in active.submissions" :key="s.student_name" class="submission-card"><strong>{{ s.student_name }}</strong><p>{{ s.answer }}</p><small class="muted">{{ new Date(s.created_at).toLocaleString('zh-CN') }}</small></div><p v-if="!active.submissions?.length" class="empty-small">暂未收到提交。可退出后使用学生账号体验作答流程。</p></div></template></el-dialog>
</template>
