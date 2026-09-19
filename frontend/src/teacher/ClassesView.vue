<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Users, Plus, RefreshCw, Download, BookOpen, ArrowUpRight } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type TeachingClass, type ClassStudent } from '../shared/api'
import { classProgressCsv, downloadCsv, filterClassStudents, type MemberFilter } from '../shared/classProgress'
const emit = defineEmits<{ changed: []; assignments: [classId: string] }>()
const classes = ref<TeachingClass[]>([]), students = ref<ClassStudent[]>([])
const selectedId = ref(''), archived = ref(false), search = ref(''), memberFilter = ref<MemberFilter>('active')
const loading = ref(true), rosterLoading = ref(false), busy = ref(false), error = ref(''), dialogError = ref('')
const selected = computed(() => classes.value.find(c => c.id === selectedId.value))
const visibleClasses = computed(() => classes.value.filter(c => c.archived === archived.value))
const visibleStudents = computed(() => filterClassStudents(students.value, search.value, memberFilter.value))
const classDialog = ref(false), editId = ref(''), classForm = ref({ name: '', course: '高等数学', term: '' })
const studentDialog = ref(false), studentMode = ref<'create' | 'existing'>('create'), studentForm = ref({ username: '', name: '', password: '' })
const editStudent = ref<ClassStudent | null>(null), studentAction = ref<'name' | 'password'>('name'), studentName = ref(''), studentPassword = ref('')
const confirmation = ref<{ kind: 'class' | 'member' | 'account'; title: string; text: string; path: string; body: object } | null>(null)
let rosterRequest = 0
async function loadRoster() {
  const request = ++rosterRequest; students.value = []; if (!selectedId.value) { rosterLoading.value = false; return }
  rosterLoading.value = true; error.value = ''
  try { const result = await api<ClassStudent[]>(`/classes/${selectedId.value}/students`); if (request === rosterRequest) students.value = result }
  catch (e) { if (request === rosterRequest) error.value = (e as Error).message }
  finally { if (request === rosterRequest) rosterLoading.value = false }
}
async function load() {
  loading.value = true; error.value = ''
  try { classes.value = await api<TeachingClass[]>('/classes'); if (!visibleClasses.value.some(c => c.id === selectedId.value)) selectedId.value = visibleClasses.value[0]?.id || ''; else await loadRoster() }
  catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}
watch(selectedId, () => { search.value = ''; memberFilter.value = 'active'; void loadRoster() })
watch(archived, () => { selectedId.value = visibleClasses.value[0]?.id || '' })
function openClass(c?: TeachingClass) { editId.value = c?.id || ''; classForm.value = c ? { name: c.name, course: c.course, term: c.term } : { name: '', course: '高等数学', term: '' }; dialogError.value = ''; classDialog.value = true }
async function saveClass() {
  if (busy.value) return; busy.value = true; dialogError.value = ''
  try { const result = await api<TeachingClass>(`/classes${editId.value ? '/' + editId.value : ''}`, { method: editId.value ? 'PATCH' : 'POST', body: JSON.stringify(classForm.value) }); classDialog.value = false; archived.value = result.archived; await load(); selectedId.value = result.id; emit('changed'); ElMessage.success('班级已保存') }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
function openStudent() { studentMode.value = 'create'; studentForm.value = { username: '', name: '', password: '' }; dialogError.value = ''; studentDialog.value = true }
async function saveStudent() {
  if (!selected.value || busy.value) return; busy.value = true; dialogError.value = ''
  try { await api(`/classes/${selected.value.id}/${studentMode.value === 'create' ? 'students' : 'members'}`, { method: 'POST', body: JSON.stringify(studentMode.value === 'create' ? studentForm.value : { username: studentForm.value.username }) }); studentDialog.value = false; studentForm.value.password = ''; await load(); emit('changed'); ElMessage.success('学生已加入班级；已发布作业的接收名单保持不变') }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
function manageStudent(s: ClassStudent, kind: 'name' | 'password') { editStudent.value = s; studentAction.value = kind; studentName.value = s.name; studentPassword.value = ''; dialogError.value = '' }
async function updateStudent() {
  if (!editStudent.value || busy.value) return; busy.value = true; dialogError.value = ''
  try { await api(`/students/${editStudent.value.id}${studentAction.value === 'password' ? '/password' : ''}`, { method: studentAction.value === 'password' ? 'POST' : 'PATCH', body: JSON.stringify(studentAction.value === 'password' ? { password: studentPassword.value } : { name: studentName.value }) }); editStudent.value = null; studentPassword.value = ''; await load(); emit('changed'); ElMessage.success(studentAction.value === 'password' ? '临时密码已重置，学生下次登录须改密' : '学生姓名已更新') }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
function confirmClass() {
  const c = selected.value; if (!c) return
  confirmation.value = { kind: 'class', title: c.archived ? '恢复班级' : '归档班级', text: c.archived ? `恢复“${c.name}”后，可以继续管理成员、发布作业和批改。已单独归档的作业保持归档。` : `归档“${c.name}”后，本班作业只读，学生不能提交、教师不能批改。所有数据保留，可随时恢复班级。`, path: `/classes/${c.id}`, body: { archived: !c.archived } }; dialogError.value = ''
}
function confirmStudent(s: ClassStudent, kind: 'member' | 'account') {
  if (!selected.value) return
  const active = kind === 'member' ? s.member_active : s.active
  confirmation.value = { kind, title: kind === 'member' ? active ? '移出班级' : '恢复班级成员' : active ? '停用学生账号' : '启用学生账号', text: kind === 'member' ? active ? `将 ${s.name} 移出本班，保留作答与反馈历史；该学生不能继续提交本班作业。不会影响其他班级成员身份。` : `恢复 ${s.name} 的本班成员身份。后加入成员不会自动获得未在接收名单中的旧作业。` : active ? `停用 ${s.name} 后会立即撤销其登录，在所有班级均无法登录或提交，历史记录保留。` : `启用 ${s.name} 后可重新登录，班级成员状态和作业接收名单保持不变。`, path: kind === 'member' ? `/classes/${selected.value.id}/members/${s.id}` : `/students/${s.id}`, body: { active: !active } }; dialogError.value = ''
}
async function confirmAction() {
  if (!confirmation.value || busy.value) return; busy.value = true; dialogError.value = ''
  try { const action = confirmation.value; await api(action.path, { method: 'PATCH', body: JSON.stringify(action.body) }); confirmation.value = null; await load(); emit('changed'); ElMessage.success(`${action.title}已完成`) }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
function exportCsv() {
  if (!selected.value || rosterLoading.value || !visibleStudents.value.length) return
  try { downloadCsv(classProgressCsv(selected.value.name, visibleStudents.value), '班级作业进度.csv') }
  catch { ElMessage.error('未能启动下载，请稍后重试。') }
}
onMounted(load)
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">GROW TOGETHER</div><h1>看见每一位同学</h1><p>维护班级与学生账号，按实际作答安排下一次反馈。</p></div><div class="action-row"><button class="outline-button" :disabled="loading || busy" @click="load"><RefreshCw :size="16"/> 刷新</button><button class="primary-button" :disabled="busy" @click="openClass()"><Plus :size="17"/> 新建班级</button></div></div>
  <div class="panel work-toolbar"><div class="filter-tabs"><button :class="{ active: !archived }" @click="archived = false">使用中的班级</button><button :class="{ active: archived }" @click="archived = true">已归档</button></div><span class="muted small">{{ visibleClasses.length }} 个班级 · 仅显示你管理的班级</span></div>
  <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="loading" class="muted" role="status">正在读取班级…</p>
  <div v-if="visibleClasses.length" class="class-grid"><button v-for="c in visibleClasses" :key="c.id" class="panel class-card" :class="{ selected: selectedId === c.id }" :aria-pressed="selectedId === c.id" @click="selectedId = c.id"><div class="section-heading"><span class="stat-icon green"><BookOpen :size="20"/></span><span class="small-pill">{{ c.student_count }} 位有效学生</span></div><h3>{{ c.name }}</h3><p>{{ c.course }}{{ c.term ? ' · ' + c.term : '' }}</p><span class="subtle-link">{{ selectedId === c.id ? '正在查看成员' : '查看班级成员' }} <ArrowUpRight :size="14"/></span></button></div>
  <div v-if="!loading && !visibleClasses.length && !error" class="panel empty-state"><Users :size="38"/><h3>{{ archived ? '没有归档班级' : '从第一个班级开始' }}</h3><p>{{ archived ? '归档的班级会在这里保留，随时可以恢复。' : '新建班级、添加学生，再把作业发布给他们。' }}</p><button v-if="!archived" class="primary-button" @click="openClass()">创建班级</button></div>
  <section v-if="selected" class="panel roster-panel"><div class="section-heading"><div><h3>{{ selected.name }} · 班级成员</h3><p class="muted small">{{ selected.course }} · {{ selected.term || '未设学期' }}</p></div><div class="action-row"><button class="subtle-link" @click="emit('assignments', selected.id)">查看本班作业</button><button v-if="!selected.archived" class="subtle-link" :disabled="busy" @click="openClass(selected)">编辑班级</button><button class="subtle-link" :disabled="busy" @click="confirmClass">{{ selected.archived ? '恢复班级' : '归档班级' }}</button></div></div>
    <p v-if="selected.archived" class="info-banner">此班级已归档，成员与作业仅供查阅。恢复班级后可继续管理。</p>
    <div class="work-toolbar roster-toolbar"><input v-model="search" aria-label="搜索学生" placeholder="搜索姓名或账号"/><select v-model="memberFilter" aria-label="成员状态"><option value="active">在班成员</option><option value="removed">已移出成员</option><option value="all">全部历史成员</option></select><button class="outline-button" :disabled="rosterLoading || !visibleStudents.length" @click="exportCsv"><Download :size="15"/> 导出当前列表</button><button v-if="!selected.archived" class="primary-button" :disabled="busy" @click="openStudent"><Plus :size="16"/> 添加学生</button></div>
    <p v-if="rosterLoading" role="status" class="muted">正在读取成员与提交进度…</p>
    <div v-else-if="visibleStudents.length" class="roster-scroll"><table class="roster-table"><caption class="sr-only">班级成员与作业提交进度</caption><thead><tr><th scope="col">学生</th><th scope="col">状态</th><th scope="col">已交 / 应交</th><th scope="col">未交</th><th scope="col">待批改</th><th scope="col">待改进</th><th scope="col">完成</th><th v-if="!selected.archived" scope="col">管理</th></tr></thead><tbody><tr v-for="s in visibleStudents" :key="s.id"><td><strong>{{ s.name }}</strong><small>{{ s.username }}</small></td><td><span class="small-pill" :class="{ 'muted-pill': !s.active || !s.member_active }">{{ !s.active ? '账号停用' : !s.member_active ? '已移出' : '在班' }}</span><small v-if="s.must_change_password">待首次改密</small></td><td>{{ s.submitted }} / {{ s.expected }}</td><td>{{ Math.max(0, s.expected - s.submitted) }}</td><td>{{ s.pending }}</td><td>{{ s.needs_improvement }}</td><td>{{ s.completed }}</td><td v-if="!selected.archived"><div class="roster-actions"><button class="subtle-link" :disabled="busy || !s.manageable" :title="s.manageable ? '' : '该历史账号不归你管理'" @click="manageStudent(s, 'name')">改姓名</button><button class="subtle-link" :disabled="busy || !s.manageable" :title="s.manageable ? '' : '该历史账号不归你管理'" @click="manageStudent(s, 'password')">重置密码</button><button class="subtle-link" :disabled="busy" @click="confirmStudent(s, 'member')">{{ s.member_active ? '移出' : '恢复成员' }}</button><button class="subtle-link" :disabled="busy || !s.manageable" :title="s.manageable ? '' : '该历史账号不归你管理'" @click="confirmStudent(s, 'account')">{{ s.active ? '停用账号' : '启用账号' }}</button></div></td></tr></tbody></table></div>
    <div v-else-if="!error" class="empty-state compact"><Users :size="30"/><h3>{{ search || memberFilter !== 'active' ? '暂无匹配成员' : '这个班级还没有学生' }}</h3><p>{{ search || memberFilter !== 'active' ? '调整搜索或成员状态后再试。' : '添加学生账号后，即可发布本班作业。' }}</p></div>
    <p class="account-note">按本班已发布作业的接收名单统计，不推断学习掌握度。新增学生不会自动收到旧作业，可复制作业后重新发布。导出仅包含当前筛选结果，请妥善保管。</p>
  </section>
  <el-dialog v-model="classDialog" :title="editId ? '编辑班级' : '新建班级'" width="540px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy"><form class="dialog-form" @submit.prevent="saveClass"><label>班级名称<input v-model="classForm.name" required maxlength="80" placeholder="例如：高数 A 班"/></label><label>课程<input v-model="classForm.course" required maxlength="80" placeholder="例如：高等数学"/></label><label>学期<input v-model="classForm.term" required maxlength="80" placeholder="例如：2026 秋季"/></label><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" type="button" :disabled="busy" @click="classDialog = false">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '保存班级' }}</button></div></form></el-dialog>
  <el-dialog v-model="studentDialog" title="添加学生" width="560px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy"><div class="filter-tabs"><button :class="{ active: studentMode === 'create' }" :disabled="busy" @click="studentMode = 'create'; dialogError = ''">创建新学生</button><button :class="{ active: studentMode === 'existing' }" :disabled="busy" @click="studentMode = 'existing'; dialogError = ''">加入已有学生</button></div><form class="dialog-form" @submit.prevent="saveStudent"><label>学生账号<input v-model="studentForm.username" required maxlength="80" autocomplete="off" minlength="3" pattern="[A-Za-z0-9_.\-]{3,80}" placeholder="3–80 位英文、数字、点、下划线或短横线"/></label><template v-if="studentMode === 'create'"><label>学生姓名<input v-model="studentForm.name" required maxlength="80"/></label><label>临时密码<input v-model="studentForm.password" type="password" required minlength="10" maxlength="128" autocomplete="new-password" placeholder="至少 10 位，包含字母与数字"/></label><p class="muted small">学生首次登录须修改密码。请单独告知账号与临时密码，创建后不回显密码。</p></template><p v-else class="muted small">输入你曾创建的学生账号，可将其加入多个自己的班级。其他教师管理的学生不能加入。</p><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" type="button" :disabled="busy" @click="studentDialog = false">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '添加中…' : '添加到班级' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!editStudent" :title="studentAction === 'name' ? '修改学生姓名' : '重置临时密码'" width="500px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @update:model-value="!$event && (editStudent = null)"><form v-if="editStudent" class="dialog-form" @submit.prevent="updateStudent"><p>{{ editStudent.name }} · {{ editStudent.username }}</p><label v-if="studentAction === 'name'">姓名<input v-model="studentName" required maxlength="80"/></label><template v-else><label>新临时密码<input v-model="studentPassword" type="password" required minlength="10" maxlength="128" autocomplete="new-password" placeholder="至少 10 位，包含字母与数字"/></label><p class="muted small">保存后撤销该学生所有登录会话，下次登录必须修改密码。请单独告知本人。</p></template><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button type="button" class="outline-button" :disabled="busy" @click="editStudent = null">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '确认保存' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!confirmation" :title="confirmation?.title" width="500px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @update:model-value="!$event && (confirmation = null)"><p>{{ confirmation?.text }}</p><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" :disabled="busy" @click="confirmation = null">取消</button><button class="primary-button" :disabled="busy" @click="confirmAction">{{ busy ? '处理中…' : '确认' }}</button></div></el-dialog>
</template>
