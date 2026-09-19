<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import ElMessage from 'element-plus/es/components/message/index'
import { LayoutDashboard, Sparkles, BookOpen, ClipboardList, Bookmark, History, Users, LogOut, ChevronRight, Menu, X, ArrowUpRight, GraduationCap, CircleHelp, RefreshCw, Settings } from 'lucide-vue-next'
import Brand from './shared/Brand.vue'
import LoginView from './shared/LoginView.vue'
import StudentHome from './student/StudentHome.vue'
import TeacherHome from './teacher/TeacherHome.vue'
import QuestionBank from './teacher/QuestionBank.vue'
import ClassesView from './teacher/ClassesView.vue'
import AccountSettings from './shared/AccountSettings.vue'
import AgentView from './shared/AgentView.vue'
import AssignmentsView from './shared/AssignmentsView.vue'
import RecordsView from './shared/RecordsView.vue'
import CoursesView from './student/CoursesView.vue'
import { api, ApiError, type User, type Conversation, type Assignment, type TeachingStats, type TeachingClass, localToday } from './shared/api'
const user = ref<User | null>(null)
const booting = ref(true)
const page = ref('dashboard')
const records = ref<Conversation[]>([])
const assignments = ref<Assignment[]>([])
const emptyStats = (): TeachingStats => ({ published: 0, submitted: 0, pending: 0, needs_improvement: 0, completed: 0, classes: 0, students: 0, expected: 0, unsubmitted: 0 })
const teachingStats = ref<TeachingStats>(emptyStats())
const classes = ref<TeachingClass[]>([]), classFilter = ref(''), dataLoading = ref(false)
const draftToOpen = ref('')
const mobileNav = ref(false)
const initialQuestion = ref('')
const selectedId = ref('')
const createRequested = ref(false)
const loadError = ref('')
const loggingOut = ref(false)
const help = ref(false)
const teacher = computed(() => user.value?.role === 'teacher')
const navigation = computed(() => user.value?.must_change_password ? [{ id: 'account', label: '设置密码', icon: Settings }] : [...(teacher.value ? [
  { id: 'dashboard', label: '教学概览', icon: LayoutDashboard }, { id: 'agent', label: '教学助手', icon: Sparkles },
  { id: 'questions', label: '我的题库', icon: BookOpen }, { id: 'assignments', label: '作业管理', icon: ClipboardList }, { id: 'students', label: '我的班级', icon: Users }, { id: 'records', label: '对话记录', icon: History },
] : [
  { id: 'dashboard', label: '学习概览', icon: LayoutDashboard }, { id: 'agent', label: '数伴智能体', icon: Sparkles },
  { id: 'courses', label: '课程探索', icon: BookOpen }, { id: 'assignments', label: '我的作业', icon: ClipboardList },
  { id: 'favorites', label: '复习收藏', icon: Bookmark }, { id: 'records', label: '学习记录', icon: History },
]), { id: 'account', label: '账号设置', icon: Settings }])
let generation = 0
async function loadData() {
  if (!user.value || user.value.must_change_password) return
  const current = ++generation
  dataLoading.value = true
  const query = teacher.value && classFilter.value ? `?class_id=${encodeURIComponent(classFilter.value)}` : ''
  try {
    const [r, a, stats, c] = await Promise.all([api<Conversation[]>('/conversations'), api<Assignment[]>('/assignments' + query), teacher.value ? api<TeachingStats>('/teaching/stats' + query) : Promise.resolve(null), teacher.value ? api<TeachingClass[]>('/classes') : Promise.resolve([])])
    if (current !== generation || !user.value) return
    records.value = r; assignments.value = a; classes.value = c; if (stats) teachingStats.value = stats; loadError.value = ''
  } catch (e) { if (current === generation && user.value) loadError.value = (e as Error).message }
  finally { if (current === generation) dataLoading.value = false }
}
function navigate(id: string) { if (user.value?.must_change_password) id = 'account'; if (id === 'dashboard' && classes.value.find(c => c.id === classFilter.value)?.archived) classFilter.value = ''; if (id === 'assignments' || id === 'dashboard' || id === 'students') void loadData(); page.value = id; mobileNav.value = false; if (id !== 'agent') { initialQuestion.value = ''; selectedId.value = '' } }
function filterClass(value: string) { classFilter.value = value; void loadData() }
function classAssignments(value: string) { classFilter.value = value; navigate('assignments') }
async function updatedUser(value: User) { const wasRequired = user.value?.must_change_password; user.value = value; if (wasRequired && !value.must_change_password) { page.value = 'dashboard'; await loadData() } }
function ask(question: string) { initialQuestion.value = question; selectedId.value = ''; navigate('agent') }
function openRecord(id: string) { initialQuestion.value = ''; selectedId.value = id; navigate('agent') }
async function drafted(id: string) { classFilter.value = ''; draftToOpen.value = id; page.value = 'assignments'; await loadData() }
function create() { createRequested.value = true; navigate('assignments') }
function reset() { generation++; draftToOpen.value = ''; teachingStats.value = emptyStats(); classes.value = []; classFilter.value = ''; dataLoading.value = false; user.value = null; records.value = []; assignments.value = []; page.value = 'dashboard'; initialQuestion.value = ''; selectedId.value = ''; mobileNav.value = false; createRequested.value = false; loadError.value = '' }
async function loggedIn(value: User) { reset(); user.value = value; if (value.must_change_password) page.value = 'account'; await loadData() }
async function logout() {
  loggingOut.value = true
  try { await api('/auth/logout', { method: 'POST' }); reset() }
  catch (e) { ElMessage.error((e as Error).message) }
  finally { loggingOut.value = false }
}
function expired() { reset(); ElMessage.warning('登录已过期，请重新登录。') }
onMounted(async () => {
  window.addEventListener('session-expired', expired)
  try { user.value = await api<User>('/auth/me'); if (user.value.must_change_password) page.value = 'account'; await loadData() }
  catch (e) { if (!(e instanceof ApiError && e.status === 401)) ElMessage.warning((e as Error).message) }
  finally { booting.value = false }
})
onBeforeUnmount(() => window.removeEventListener('session-expired', expired))
</script>
<template>
  <div v-if="booting" class="boot-screen"><Brand/><span>正在打开你的空间…</span></div>
  <LoginView v-else-if="!user" @login="loggedIn"/>
  <div v-else class="app-shell" :class="{ 'teacher-theme': teacher }">
    <div v-if="mobileNav" class="nav-backdrop" @click="mobileNav = false"></div>
    <aside class="sidebar" :class="{ 'is-open': mobileNav }"><div class="sidebar-brand"><Brand/><button class="icon-button mobile-only" aria-label="关闭导航" @click="mobileNav = false"><X :size="20"/></button></div><div class="workspace-label"><span class="tiny-dot"/>{{ teacher ? '教师教学空间' : '学生学习空间' }}</div><div class="nav-section-label">{{ teacher ? '教学工作台' : '我的学习空间' }}</div><nav><button v-for="nav in navigation" :key="nav.id" :class="{ active: page === nav.id }" @click="navigate(nav.id)"><component :is="nav.icon" :size="19"/><span>{{ nav.label }}</span><span v-if="nav.id === 'agent'" class="nav-ai">AI</span><span v-if="nav.id === 'assignments' && !teacher && assignments.some(a => a.status === 'published' && a.can_submit !== false && !a.class_archived && !a.submitted && a.due_date >= localToday())" class="nav-dot"></span></button></nav><div class="sidebar-bottom"><div class="sidebar-note"><span>一点好奇，一点进步。</span><p>数伴陪你，把每一步走扎实。</p><Sparkles :size="22"/></div><button class="help-link" @click="help = true"><CircleHelp :size="17"/> 使用说明<ArrowUpRight :size="14"/></button><div class="sidebar-user"><span class="user-avatar">{{ user.name.slice(0, 1) }}</span><div><strong>{{ user.name }}</strong><small>{{ teacher ? '教师' : '学生' }}{{ user.is_demo ? ' · 演示账号' : '' }}</small></div><button class="icon-button" :disabled="loggingOut" aria-label="退出登录" title="退出登录" @click="logout"><LogOut :size="17"/></button></div></div></aside>
    <div class="app-body"><header class="topbar"><button class="icon-button mobile-only" aria-label="打开导航" @click="mobileNav = true"><Menu :size="22"/></button><div class="breadcrumb"><span>工作台</span><ChevronRight :size="13"/><strong>{{ navigation.find(n => n.id === page)?.label }}</strong></div><div class="topbar-right"><span class="local-indicator"><span class="tiny-dot"/> 本地教学空间</span><span class="topbar-divider"></span><GraduationCap :size="18"/><span>高等数学</span></div></header><main class="main-content"><div v-if="loadError" class="load-error" role="alert"><span>{{ loadError }}</span><button class="subtle-link" @click="loadData"><RefreshCw :size="14"/> 重新加载</button></div>
      <AccountSettings v-if="user.must_change_password || page === 'account'" :user="user" @updated="updatedUser"/>
      <StudentHome v-else-if="page === 'dashboard' && !teacher" :user="user" :records="records" :assignments="assignments" @navigate="navigate" @ask="ask"/>
      <TeacherHome v-else-if="page === 'dashboard'" :user="user" :records="records" :assignments="assignments" :stats="teachingStats" :classes="classes" :class-id="classFilter" :loading="dataLoading" @filter="filterClass" @navigate="navigate" @create="create" @refresh="loadData"/>
      <QuestionBank v-else-if="page === 'questions' && teacher" @drafted="drafted"/>
      <AgentView v-else-if="page === 'agent'" :user="user" :records="records" :initial-question="initialQuestion" :selected-id="selectedId" @saved="loadData" @select="selectedId = $event"/>
      <AssignmentsView v-else-if="page === 'assignments'" :user="user" :assignments="assignments" :create-requested="createRequested" :open-id="draftToOpen" :classes="classes" :class-id="classFilter" :loading="dataLoading" @filter="filterClass" @opened="draftToOpen = ''" @refresh="loadData" @saved="loadData" @close-create="createRequested = false"/>
      <CoursesView v-else-if="page === 'courses' && !teacher" @ask="ask"/>
      <RecordsView v-else-if="page === 'favorites' || page === 'records'" :records="records" :favorites="page === 'favorites'" @open="openRecord" @ask="navigate('agent')"/>
      <ClassesView v-else-if="page === 'students' && teacher" @changed="loadData" @assignments="classAssignments"/>
      <footer class="workspace-footer"><span>数伴 · 让每一步学习都有回应</span><span>数伴 0.3 <span class="tiny-dot"/> 持续生长中</span></footer>
    </main></div>
    <el-dialog v-model="help" title="数伴使用说明" width="520px"><div class="help-content"><p>这是你的高数教学与学习工作空间。</p><p><strong>已经可以体验：</strong>教师初始化、学生账号与班级管理、按班级发布作业、版本化提交与人工反馈、题库、真实提交统计和成员进度导出，以及模型 / 演示问答、引用与历史。</p><p><strong>能力边界：</strong>已接入模型兼容接口与本地课程检索；未配置模型时仍为演示。拍照识题、步骤反馈和诊断已有后端接口，页面入口待接入；语音、自动评分、AI反馈复核和向量检索尚未实现。</p><p>新学生使用老师提供的临时密码登录后须改密。班级和作业按账号隔离；发布时固定接收名单，后加入的学生需教师另行发布作业。数据保存在当前服务，请妥善备份。</p></div></el-dialog>
  </div>
</template>
