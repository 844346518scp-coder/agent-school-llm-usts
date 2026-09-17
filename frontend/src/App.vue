<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import ElMessage from 'element-plus/es/components/message/index'
import { LayoutDashboard, Sparkles, BookOpen, ClipboardList, Bookmark, History, Users, LogOut, ChevronRight, Menu, X, ArrowUpRight, GraduationCap, CircleHelp, RefreshCw } from 'lucide-vue-next'
import Brand from './shared/Brand.vue'
import LoginView from './shared/LoginView.vue'
import StudentHome from './student/StudentHome.vue'
import TeacherHome from './teacher/TeacherHome.vue'
import QuestionBank from './teacher/QuestionBank.vue'
import AgentView from './shared/AgentView.vue'
import AssignmentsView from './shared/AssignmentsView.vue'
import RecordsView from './shared/RecordsView.vue'
import CoursesView from './student/CoursesView.vue'
import { api, ApiError, type User, type Conversation, type Assignment, type TeachingStats, localToday } from './shared/api'
const user = ref<User | null>(null)
const booting = ref(true)
const page = ref('dashboard')
const records = ref<Conversation[]>([])
const assignments = ref<Assignment[]>([])
const teachingStats = ref<TeachingStats>({ published: 0, submitted: 0, pending: 0, needs_improvement: 0, completed: 0 })
const draftToOpen = ref('')
const mobileNav = ref(false)
const initialQuestion = ref('')
const selectedId = ref('')
const createRequested = ref(false)
const loadError = ref('')
const loggingOut = ref(false)
const help = ref(false)
const teacher = computed(() => user.value?.role === 'teacher')
const navigation = computed(() => teacher.value ? [
  { id: 'dashboard', label: '教学概览', icon: LayoutDashboard }, { id: 'agent', label: '教学助手', icon: Sparkles },
  { id: 'questions', label: '我的题库', icon: BookOpen }, { id: 'assignments', label: '作业管理', icon: ClipboardList }, { id: 'students', label: '我的班级', icon: Users }, { id: 'records', label: '对话记录', icon: History },
] : [
  { id: 'dashboard', label: '学习概览', icon: LayoutDashboard }, { id: 'agent', label: '数伴智能体', icon: Sparkles },
  { id: 'courses', label: '课程探索', icon: BookOpen }, { id: 'assignments', label: '我的作业', icon: ClipboardList },
  { id: 'favorites', label: '复习收藏', icon: Bookmark }, { id: 'records', label: '学习记录', icon: History },
])
let generation = 0
async function loadData() {
  const current = ++generation
  try {
    const [r, a, stats] = await Promise.all([api<Conversation[]>('/conversations'), api<Assignment[]>('/assignments'), teacher.value ? api<TeachingStats>('/teaching/stats') : Promise.resolve(null)])
    if (current !== generation || !user.value) return
    records.value = r; assignments.value = a; if (stats) teachingStats.value = stats; loadError.value = ''
  } catch (e) { if (current === generation && user.value) loadError.value = (e as Error).message }
}
function navigate(id: string) { if (id === 'assignments' || id === 'dashboard' || id === 'students') void loadData(); page.value = id; mobileNav.value = false; if (id !== 'agent') { initialQuestion.value = ''; selectedId.value = '' } }
function ask(question: string) { initialQuestion.value = question; selectedId.value = ''; navigate('agent') }
function openRecord(id: string) { initialQuestion.value = ''; selectedId.value = id; navigate('agent') }
async function drafted(id: string) { draftToOpen.value = id; page.value = 'assignments'; await loadData() }
function create() { createRequested.value = true; navigate('assignments') }
function reset() { generation++; draftToOpen.value = ''; teachingStats.value = { published: 0, submitted: 0, pending: 0, needs_improvement: 0, completed: 0 }; user.value = null; records.value = []; assignments.value = []; page.value = 'dashboard'; initialQuestion.value = ''; selectedId.value = ''; mobileNav.value = false; createRequested.value = false; loadError.value = '' }
async function loggedIn(value: User) { reset(); user.value = value; await loadData() }
async function logout() {
  loggingOut.value = true
  try { await api('/auth/logout', { method: 'POST' }); reset() }
  catch (e) { ElMessage.error((e as Error).message) }
  finally { loggingOut.value = false }
}
function expired() { reset(); ElMessage.warning('登录已过期，请重新登录。') }
onMounted(async () => {
  window.addEventListener('session-expired', expired)
  try { user.value = await api<User>('/auth/me'); await loadData() }
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
    <aside class="sidebar" :class="{ 'is-open': mobileNav }"><div class="sidebar-brand"><Brand/><button class="icon-button mobile-only" aria-label="关闭导航" @click="mobileNav = false"><X :size="20"/></button></div><div class="workspace-label"><span class="tiny-dot"/>{{ teacher ? '教师教学空间' : '学生学习空间' }}</div><div class="nav-section-label">{{ teacher ? '教学工作台' : '我的学习空间' }}</div><nav><button v-for="nav in navigation" :key="nav.id" :class="{ active: page === nav.id }" @click="navigate(nav.id)"><component :is="nav.icon" :size="19"/><span>{{ nav.label }}</span><span v-if="nav.id === 'agent'" class="nav-ai">AI</span><span v-if="nav.id === 'assignments' && !teacher && assignments.some(a => a.status === 'published' && !a.submitted && a.due_date >= localToday())" class="nav-dot"></span></button></nav><div class="sidebar-bottom"><div class="sidebar-note"><span>一点好奇，一点进步。</span><p>数伴陪你，把每一步走扎实。</p><Sparkles :size="22"/></div><button class="help-link" @click="help = true"><CircleHelp :size="17"/> 体验说明<ArrowUpRight :size="14"/></button><div class="sidebar-user"><span class="user-avatar">{{ teacher ? '陈' : '林' }}</span><div><strong>{{ user.name }}</strong><small>{{ teacher ? '教师' : '学生' }} · 演示账号</small></div><button class="icon-button" :disabled="loggingOut" aria-label="退出登录" title="退出登录" @click="logout"><LogOut :size="17"/></button></div></div></aside>
    <div class="app-body"><header class="topbar"><button class="icon-button mobile-only" aria-label="打开导航" @click="mobileNav = true"><Menu :size="22"/></button><div class="breadcrumb"><span>工作台</span><ChevronRight :size="13"/><strong>{{ navigation.find(n => n.id === page)?.label }}</strong></div><div class="topbar-right"><span class="local-indicator"><span class="tiny-dot"/> 本地体验版</span><span class="topbar-divider"></span><GraduationCap :size="18"/><span>高等数学</span></div></header><main class="main-content"><div v-if="loadError" class="load-error" role="alert"><span>{{ loadError }}</span><button class="subtle-link" @click="loadData"><RefreshCw :size="14"/> 重新加载</button></div>
      <StudentHome v-if="page === 'dashboard' && !teacher" :user="user" :records="records" :assignments="assignments" @navigate="navigate" @ask="ask"/>
      <TeacherHome v-else-if="page === 'dashboard'" :user="user" :records="records" :assignments="assignments" :stats="teachingStats" @navigate="navigate" @create="create" @refresh="loadData"/>
      <QuestionBank v-else-if="page === 'questions' && teacher" @drafted="drafted"/>
      <AgentView v-else-if="page === 'agent'" :user="user" :records="records" :initial-question="initialQuestion" :selected-id="selectedId" @saved="loadData" @select="selectedId = $event"/>
      <AssignmentsView v-else-if="page === 'assignments'" :user="user" :assignments="assignments" :create-requested="createRequested" :open-id="draftToOpen" @opened="draftToOpen = ''" @refresh="loadData" @saved="loadData" @close-create="createRequested = false"/>
      <CoursesView v-else-if="page === 'courses' && !teacher" @ask="ask"/>
      <RecordsView v-else-if="page === 'favorites' || page === 'records'" :records="records" :favorites="page === 'favorites'" @open="openRecord" @ask="navigate('agent')"/>
      <template v-else-if="page === 'students' && teacher"><div class="page-heading"><div><div class="eyebrow">GROW TOGETHER</div><h1>看见每一位同学</h1><p>高等数学 · 演示班级，当前只有一名预设学生。</p></div><span class="status-pill">1 位学生</span></div><section class="panel"><div class="section-heading"><h3>班级成员</h3><span class="muted small">账号与作业数据</span></div><div class="class-student"><span class="user-avatar">林</span><div><h3>林同学</h3><p class="muted">student · 学生演示账号</p></div><div><strong>{{ assignments.filter(a => a.status === 'published' && a.submissions?.some(s => s.student_id === 'student')).length }} / {{ teachingStats.published }}</strong><p class="muted">已提交作业</p></div><button class="outline-button" @click="navigate('assignments')">查看作业 <ArrowUpRight :size="15"/></button></div><div class="teaching-reminder"><h4>先观察，再判断</h4><p>本版仅记录作业提交，不推断知识点掌握程度。当前可进行教师人工作业反馈；多班级管理、成员邀请、AI 学情诊断与 AI 反馈复核尚未开放。</p></div></section></template>
      <footer class="workspace-footer"><span>数伴 · 让每一步学习都有回应</span><span>MVP 0.2 <span class="tiny-dot"/> 持续生长中</span></footer>
    </main></div>
    <el-dialog v-model="help" title="欢迎体验数伴" width="520px"><div class="help-content"><p>这是一个高数教学与学习的最小可行版本。</p><p><strong>已经可以体验：</strong>学生 / 教师登录、记住登录、课程入口、演示问答与收藏、历史记录、教师题库、草稿与发布、学生提交、教师人工反馈和历史记录、作业归档。</p><p><strong>当前尚未接入：</strong>真实 AI、拍照识题、语音、RAG、自动评分和多班级管理。页面会明确标注演示内容。</p><p>所有预设账号均用于本地体验，不要填入真实师生隐私。账号切换请先退出登录；退出会撤销已记住的会话。</p></div></el-dialog>
  </div>
</template>
