<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Users, Plus, RefreshCw, Download, BookOpen, ArrowUpRight, Settings2, ListChecks } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type TeachingClass, type ClassStudent, type Assignment, type User } from '../shared/api'
import { classProgressCsv, downloadCsv, filterClassStudents, memberBatchTargets, runMemberBatch, type MemberFilter } from '../shared/classProgress'
import AssignmentsView from '../shared/AssignmentsView.vue'
const props = defineProps<{ user: User; assignments: Assignment[]; dataLoading: boolean; entry: { classId: string; create: boolean } | null }>()
const emit = defineEmits<{ changed: [] }>()
const view = ref<'list' | 'members' | 'assignments'>('list'), createRequested = ref(false)
function openMembers(id: string) { selectedId.value = id; view.value = 'members' }
function openAssignments(id: string, create = false) { selectedId.value = id; view.value = 'assignments'; createRequested.value = create }
function backToClasses() { view.value = 'list'; selectedId.value = ''; createRequested.value = false }
function refreshWorkspace() { void load(); emit('changed') }
watch(() => props.entry, entry => { if (entry) openAssignments(entry.classId, entry.create); else backToClasses() })
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
const settingsStudent = ref<ClassStudent | null>(null)
const bulkMode = ref(false), selectedStudents = ref<string[]>([])
const bulkAction = ref<{ classId: string; className: string; active: boolean; targets: ClassStudent[] } | null>(null)
const bulkResult = ref('')
const allSelected = computed(() => visibleStudents.value.length > 0 && visibleStudents.value.every(s => selectedStudents.value.includes(s.id)))
const removeTargets = computed(() => memberBatchTargets(visibleStudents.value, selectedStudents.value, false))
const restoreTargets = computed(() => memberBatchTargets(visibleStudents.value, selectedStudents.value, true))
watch([search, memberFilter, selectedId, view], () => { selectedStudents.value = []; settingsStudent.value = null })
watch([selectedId, view], () => { bulkMode.value = false })
function toggleAll() { selectedStudents.value = allSelected.value ? [] : visibleStudents.value.map(s => s.id) }
function openBulk(active: boolean) {
  if (busy.value || rosterLoading.value || !selected.value || selected.value.archived) return
  const targets = memberBatchTargets(visibleStudents.value, selectedStudents.value, active)
  if (!targets.length) return
  bulkResult.value = ''; bulkAction.value = { classId: selected.value.id, className: selected.value.name, active, targets: [...targets] }
}
async function executeBulk() {
  const action = bulkAction.value
  if (!action || busy.value || bulkResult.value) return
  busy.value = true
  try {
    const result = await runMemberBatch(action.targets, s => api('/classes/' + action.classId + '/members/' + s.id, { method: 'PATCH', body: JSON.stringify({ active: action.active }) }))
    bulkResult.value = result.failed
      ? '已确认完成 ' + result.completed.length + ' 人；' + result.failed.name + '（' + result.failed.username + '）请求未确认成功：' + result.error + '。后续 ' + result.unprocessed + ' 人未执行。已尝试刷新名单，请核实状态后再操作，不要直接重复提交。'
      : '已' + (action.active ? '恢复' : '移出') + ' ' + result.completed.length + ' 位成员。历史作答及发布接收名单保持不变。'
    selectedStudents.value = []; await load(); emit('changed')
  } finally { busy.value = false }
}
let rosterRequest = 0
async function loadRoster() {
  const request = ++rosterRequest; selectedStudents.value = []; students.value = []; if (!selectedId.value) { rosterLoading.value = false; return }
  rosterLoading.value = true; error.value = ''
  try { const result = await api<ClassStudent[]>(`/classes/${selectedId.value}/students`); if (request === rosterRequest) students.value = result }
  catch (e) { if (request === rosterRequest) error.value = (e as Error).message }
  finally { if (request === rosterRequest) rosterLoading.value = false }
}
async function load() {
  loading.value = true; error.value = ''
  try { classes.value = await api<TeachingClass[]>('/classes'); if (selectedId.value && !classes.value.some(c => c.id === selectedId.value)) backToClasses(); else if (view.value === 'members') await loadRoster() }
  catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}
watch([selectedId, view], () => { search.value = ''; memberFilter.value = 'active'; if (view.value === 'members') void loadRoster(); else { rosterRequest++; rosterLoading.value = false; students.value = [] } })
function openClass(c?: TeachingClass) { editId.value = c?.id || ''; classForm.value = c ? { name: c.name, course: c.course, term: c.term } : { name: '', course: '高等数学', term: '' }; dialogError.value = ''; classDialog.value = true }
async function saveClass() {
  if (busy.value) return; busy.value = true; dialogError.value = ''
  try { const result = await api<TeachingClass>(`/classes${editId.value ? '/' + editId.value : ''}`, { method: editId.value ? 'PATCH' : 'POST', body: JSON.stringify(classForm.value) }); classDialog.value = false; archived.value = result.archived; await load(); selectedId.value = result.id; if (!editId.value) view.value = 'members'; emit('changed'); ElMessage.success('班级已保存') }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
function openStudent() { studentMode.value = 'create'; studentForm.value = { username: '', name: '', password: '' }; dialogError.value = ''; studentDialog.value = true }
async function saveStudent() {
  if (!selected.value || busy.value) return; busy.value = true; dialogError.value = ''
  try { await api(`/classes/${selected.value.id}/${studentMode.value === 'create' ? 'students' : 'members'}`, { method: 'POST', body: JSON.stringify(studentMode.value === 'create' ? studentForm.value : { username: studentForm.value.username }) }); studentDialog.value = false; studentForm.value.password = ''; await load(); emit('changed'); ElMessage.success('学生已加入班级；已发布作业的接收名单保持不变') }
  catch (e) { dialogError.value = (e as Error).message } finally { busy.value = false }
}
function manageStudent(s: ClassStudent, kind: 'name' | 'password') { settingsStudent.value = null; editStudent.value = s; studentAction.value = kind; studentName.value = s.name; studentPassword.value = ''; dialogError.value = '' }
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
  settingsStudent.value = null
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
onMounted(async () => { await load(); if (props.entry) openAssignments(props.entry.classId, props.entry.create) })
</script>
<template>
  <template v-if="view === 'list'">
    <div class="page-heading"><div><div class="eyebrow">MY CLASSES</div><h1>班级管理</h1><p>从班级出发，安排练习、查看作答与学生进度。</p></div><div class="action-row"><button class="outline-button" :disabled="loading || busy" @click="refreshWorkspace"><RefreshCw :size="16"/> 刷新</button><button class="primary-button" :disabled="busy" @click="openClass()"><Plus :size="17"/> 新建班级</button></div></div>
    <div class="panel work-toolbar"><div class="filter-tabs"><button :class="{ active: !archived }" @click="archived = false">使用中的班级</button><button :class="{ active: archived }" @click="archived = true">已归档</button></div><button class="subtle-link" @click="openAssignments('')">全部作业与草稿 <ArrowUpRight :size="14"/></button></div>
    <p v-if="!loading" class="muted small">{{ visibleClasses.length }} 个班级</p>
    <div v-if="visibleClasses.length" class="class-grid"><article v-for="c in visibleClasses" :key="c.id" class="panel class-card"><div class="section-heading"><span class="stat-icon green"><BookOpen :size="20"/></span><span class="small-pill">{{ c.student_count }} 位有效学生</span></div><h3>{{ c.name }}</h3><p>{{ c.course }} · {{ c.term }}</p><div class="class-card-actions"><button v-if="!c.archived" class="primary-button" @click="openAssignments(c.id, true)"><Plus :size="15"/> 布置作业</button><button class="outline-button" @click="openAssignments(c.id)">查看作业</button><button class="subtle-link" @click="openMembers(c.id)"><Users :size="15"/> 班级成员 <ArrowUpRight :size="14"/></button></div></article></div>
    <div v-if="!loading && !visibleClasses.length && !error" class="panel empty-state"><Users :size="38"/><h3>{{ archived ? '没有归档班级' : '从第一个班级开始' }}</h3><p>{{ archived ? '归档的班级会在这里保留，随时可以恢复。' : '新建班级、添加学生，再布置第一次作业。' }}</p><button v-if="!archived" class="primary-button" @click="openClass()">创建班级</button></div>
  </template>
  <template v-else>
    <button class="subtle-link class-back" :disabled="busy" @click="backToClasses">← 返回班级管理</button>
    <div class="page-heading class-detail-heading"><div><div class="eyebrow">CLASSROOM</div><h1>{{ selected?.name || '全部作业与草稿' }}</h1><p>{{ selected ? selected.course + ' · ' + selected.term : '查看各班作业，也可继续编辑尚未分班的草稿。' }}</p></div><div v-if="selected" class="action-row"><button v-if="!selected.archived" class="subtle-link" :disabled="busy" @click="openClass(selected)">编辑班级</button><button class="subtle-link" :disabled="busy" @click="confirmClass">{{ selected.archived ? '恢复班级' : '归档班级' }}</button></div></div>
    <div v-if="selected" class="filter-tabs class-detail-tabs" aria-label="班级页面"><button :class="{ active: view === 'assignments' }" :aria-current="view === 'assignments' ? 'page' : undefined" @click="openAssignments(selected.id)">班级作业</button><button :class="{ active: view === 'members' }" :aria-current="view === 'members' ? 'page' : undefined" @click="openMembers(selected.id)">班级成员</button></div>
  </template>
  <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="loading" class="muted" role="status">正在读取班级…</p>
  <AssignmentsView v-if="view === 'assignments'" :user="user" :assignments="assignments" :classes="classes" :class-id="selectedId" :create-requested="createRequested" :loading="dataLoading" embedded @close-create="createRequested = false" @filter="openAssignments($event)" @saved="refreshWorkspace" @refresh="refreshWorkspace"/>
  <section v-if="view === 'members' && selected" class="panel roster-panel"><div class="section-heading"><div class="action-row"><button v-if="!selected.archived" class="outline-button" :disabled="busy || rosterLoading" :aria-pressed="bulkMode" @click="bulkMode = !bulkMode; selectedStudents = []"><ListChecks :size="16"/> {{ bulkMode ? '退出批量' : '批量操作' }}</button><h3>班级成员与进度</h3></div><button class="subtle-link" :disabled="rosterLoading || busy" @click="refreshWorkspace"><RefreshCw :size="14"/> 刷新成员</button></div>
    <p v-if="selected.archived" class="info-banner">此班级已归档，成员与作业仅供查阅。恢复班级后可继续管理。</p>
    <div class="work-toolbar roster-toolbar"><input v-model="search" :disabled="busy" aria-label="搜索学生" placeholder="搜索姓名或账号"/><select v-model="memberFilter" :disabled="busy" aria-label="成员状态"><option value="active">在班成员</option><option value="removed">已移出成员</option><option value="all">全部历史成员</option></select><button class="outline-button" :disabled="rosterLoading || !visibleStudents.length" @click="exportCsv"><Download :size="15"/> 导出当前列表</button><button v-if="!selected.archived" class="primary-button" :disabled="busy" @click="openStudent"><Plus :size="16"/> 添加学生</button></div>
    <div v-if="bulkMode && !selected.archived" class="bulk-toolbar"><span role="status">已选 {{ selectedStudents.length }} 人</span><button class="outline-button" :disabled="busy || !removeTargets.length" @click="openBulk(false)">移出班级（{{ removeTargets.length }}）</button><button class="outline-button" :disabled="busy || !restoreTargets.length" @click="openBulk(true)">恢复成员（{{ restoreTargets.length }}）</button><small class="muted">仅选择当前列表；切换筛选会清空勾选。</small></div>
    <p v-if="rosterLoading" role="status" class="muted">正在读取成员与提交进度…</p>
    <div v-else-if="visibleStudents.length" class="roster-scroll"><table class="roster-table"><caption class="sr-only">班级成员与作业提交进度</caption><thead><tr><th v-if="bulkMode && !selected.archived" scope="col" class="roster-select"><input type="checkbox" aria-label="全选当前列表" :disabled="busy" :checked="allSelected" :indeterminate="selectedStudents.length > 0 && !allSelected" @change="toggleAll"/></th><th scope="col">学生</th><th scope="col">状态</th><th scope="col">已交 / 应交</th><th scope="col">未交</th><th scope="col">待批改</th><th scope="col">待改进</th><th scope="col">完成</th><th v-if="!selected.archived" scope="col">管理</th></tr></thead><tbody><tr v-for="s in visibleStudents" :key="s.id"><td v-if="bulkMode && !selected.archived" class="roster-select"><input v-model="selectedStudents" type="checkbox" :value="s.id" :disabled="busy" :aria-label="'选择' + s.name + '（' + s.username + '）'"/></td><td><strong>{{ s.name }}</strong><small>{{ s.username }}</small></td><td><span class="small-pill" :class="{ 'muted-pill': !s.active || !s.member_active }">{{ !s.active ? '账号停用' : !s.member_active ? '已移出' : '在班' }}</span><small v-if="s.must_change_password">待首次改密</small></td><td>{{ s.submitted }} / {{ s.expected }}</td><td>{{ Math.max(0, s.expected - s.submitted) }}</td><td>{{ s.pending }}</td><td>{{ s.needs_improvement }}</td><td>{{ s.completed }}</td><td v-if="!selected.archived"><button class="subtle-link" :disabled="busy" :aria-label="s.name + '的设置'" @click="settingsStudent = s"><Settings2 :size="15"/> 设置</button></td></tr></tbody></table></div>
    <div v-else-if="!error" class="empty-state compact"><Users :size="30"/><h3>{{ search || memberFilter !== 'active' ? '暂无匹配成员' : '这个班级还没有学生' }}</h3><p>{{ search || memberFilter !== 'active' ? '调整搜索或成员状态后再试。' : '添加学生账号后，即可发布本班作业。' }}</p></div>
    <p class="account-note">按本班已发布作业的接收名单统计，不推断学习掌握度。新增学生不会自动收到旧作业，可复制作业后重新发布。导出仅包含当前筛选结果，请妥善保管。</p>
  </section>
  <el-dialog v-model="classDialog" :title="editId ? '编辑班级' : '新建班级'" width="540px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy"><form class="dialog-form" @submit.prevent="saveClass"><label>班级名称<input v-model="classForm.name" required maxlength="80" placeholder="例如：高数 A 班"/></label><label>课程<input v-model="classForm.course" required maxlength="80" placeholder="例如：高等数学"/></label><label>学期<input v-model="classForm.term" required maxlength="80" placeholder="例如：2026 秋季"/></label><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" type="button" :disabled="busy" @click="classDialog = false">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '保存班级' }}</button></div></form></el-dialog>
  <el-dialog v-model="studentDialog" title="添加学生" width="560px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy"><div class="filter-tabs"><button :class="{ active: studentMode === 'create' }" :disabled="busy" @click="studentMode = 'create'; dialogError = ''">创建新学生</button><button :class="{ active: studentMode === 'existing' }" :disabled="busy" @click="studentMode = 'existing'; dialogError = ''">加入已有学生</button></div><form class="dialog-form" @submit.prevent="saveStudent"><label>学生账号<input v-model="studentForm.username" required maxlength="80" autocomplete="off" minlength="3" pattern="[A-Za-z0-9_.\-]{3,80}" placeholder="3–80 位英文、数字、点、下划线或短横线"/></label><template v-if="studentMode === 'create'"><label>学生姓名<input v-model="studentForm.name" required maxlength="80"/></label><label>临时密码<input v-model="studentForm.password" type="password" required minlength="10" maxlength="128" autocomplete="new-password" placeholder="至少 10 位，包含字母与数字"/></label><p class="muted small">学生首次登录须修改密码。请单独告知账号与临时密码，创建后不回显密码。</p></template><p v-else class="muted small">输入你曾创建的学生账号，可将其加入多个自己的班级。其他教师管理的学生不能加入。</p><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" type="button" :disabled="busy" @click="studentDialog = false">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '添加中…' : '添加到班级' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!editStudent" :title="studentAction === 'name' ? '修改学生姓名' : '重置临时密码'" width="500px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @update:model-value="!$event && (editStudent = null)"><form v-if="editStudent" class="dialog-form" @submit.prevent="updateStudent"><p>{{ editStudent.name }} · {{ editStudent.username }}</p><label v-if="studentAction === 'name'">姓名<input v-model="studentName" required maxlength="80"/></label><template v-else><label>新临时密码<input v-model="studentPassword" type="password" required minlength="10" maxlength="128" autocomplete="new-password" placeholder="至少 10 位，包含字母与数字"/></label><p class="muted small">保存后撤销该学生所有登录会话，下次登录必须修改密码。请单独告知本人。</p></template><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button type="button" class="outline-button" :disabled="busy" @click="editStudent = null">取消</button><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '确认保存' }}</button></div></form></el-dialog>
  <el-dialog :model-value="!!confirmation" :title="confirmation?.title" width="500px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @update:model-value="!$event && (confirmation = null)"><p>{{ confirmation?.text }}</p><p v-if="dialogError" class="form-error" role="alert">{{ dialogError }}</p><div class="dialog-actions"><button class="outline-button" :disabled="busy" @click="confirmation = null">取消</button><button class="primary-button" :disabled="busy" @click="confirmAction">{{ busy ? '处理中…' : '确认' }}</button></div></el-dialog>
  <el-dialog :model-value="!!settingsStudent" title="学生设置" width="420px" @update:model-value="!$event && (settingsStudent = null)"><template v-if="settingsStudent"><p>{{ settingsStudent.name }} · {{ settingsStudent.username }}</p><div class="student-settings"><button class="outline-button" :disabled="busy || !settingsStudent.manageable" @click="manageStudent(settingsStudent, 'name')">修改姓名</button><button class="outline-button" :disabled="busy || !settingsStudent.manageable" @click="manageStudent(settingsStudent, 'password')">重置密码</button><button class="outline-button" :disabled="busy" @click="confirmStudent(settingsStudent, 'member')">{{ settingsStudent.member_active ? '移出班级' : '恢复成员' }}</button><button class="outline-button" :disabled="busy || !settingsStudent.manageable" @click="confirmStudent(settingsStudent, 'account')">{{ settingsStudent.active ? '停用账号' : '启用账号' }}</button></div><p v-if="!settingsStudent.manageable" class="account-note">此历史账号不归你管理，仅可维护本班成员身份。</p></template></el-dialog>
  <el-dialog :model-value="!!bulkAction" :title="bulkAction?.active ? '批量恢复成员' : '批量移出班级'" width="540px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @update:model-value="!$event && (bulkAction = null)"><template v-if="bulkAction"><p>{{ bulkAction.className }} · {{ bulkAction.targets.length }} 位成员</p><ul class="bulk-members"><li v-for="s in bulkAction.targets" :key="s.id">{{ s.name }} · {{ s.username }}</li></ul><p v-if="!bulkResult" class="account-note">{{ bulkAction.active ? '恢复本班成员身份，不补发未在接收名单中的旧作业。' : '移出后不能继续提交本班作业，历史作答和反馈保留。' }}不影响其他班级或账号登录；逐人执行，并非一次性事务。</p><p v-if="bulkResult" class="info-banner" role="status">{{ bulkResult }}</p><div class="dialog-actions"><button class="outline-button" :disabled="busy" @click="bulkAction = null">{{ bulkResult ? '关闭' : '取消' }}</button><button v-if="!bulkResult" class="primary-button" :disabled="busy" @click="executeBulk">{{ busy ? '正在处理，请勿关闭…' : '确认' + (bulkAction.active ? '恢复' : '移出') }}</button></div></template></el-dialog>
</template>
