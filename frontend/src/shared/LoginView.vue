<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, ArrowUpRight, BookOpen, GraduationCap, School, Eye, EyeOff, LockKeyhole, UserRound, Sparkles, Check, CircleHelp } from 'lucide-vue-next'
import Brand from './Brand.vue'
import ThemeToggle from './ThemeToggle.vue'
import { api, demoWindow, type Role, type User } from './api'
const emit = defineEmits<{ login: [user: User] }>()
const role = ref<Role>(demoWindow === 'teacher' ? 'teacher' : 'student')
const demoStudent = ref(Number(demoWindow.split('-')[1]) || 1)
const splitNotice = ref('')
const username = ref('')
const password = ref('')
const visible = ref(false)
const remember = ref(false)
const busy = ref(false)
const error = ref('')
const setupRequired = ref(false), checking = ref(true), checkFailed = ref(false), name = ref('')
const registering = ref(false), classCode = ref(''), confirmPassword = ref('')
const creatingAccount = computed(() => creatingTeacher.value || registering.value)
const demoEnabled = ref(false)
const isTeacher = computed(() => role.value === 'teacher')
const creatingTeacher = computed(() => setupRequired.value && isTeacher.value)
function switchRole(value: Role) { registering.value = false; name.value = ''; classCode.value = ''; confirmPassword.value = ''; role.value = value; username.value = ''; password.value = ''; error.value = ''; remember.value = false }
async function checkSetup() {
  checking.value = true; checkFailed.value = false; error.value = ''
  try {
    const [setup, demo] = await Promise.all([api<{ required: boolean }>('/auth/setup'), api<{ enabled: boolean }>('/auth/demo')])
    setupRequired.value = setup.required; demoEnabled.value = demo.enabled
  }
  catch (e) { error.value = (e as Error).message; checkFailed.value = true }
  finally { checking.value = false }
}
async function login() {
  if (busy.value || checking.value || checkFailed.value) return
  if (registering.value && password.value !== confirmPassword.value) { error.value = '两次输入的密码不一致。'; return }
  error.value = ''; busy.value = true
  try { emit('login', await api<User>(registering.value ? '/auth/register/student' : creatingTeacher.value ? '/auth/setup' : '/auth/login', { method: 'POST', body: JSON.stringify(registering.value ? { username: username.value, name: name.value, password: password.value, class_code: classCode.value } : creatingTeacher.value ? { username: username.value, name: name.value, password: password.value } : { username: username.value, password: password.value, role: role.value, remember: remember.value }) })) }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
async function demoLogin() {
  if (busy.value || checking.value || checkFailed.value) return
  error.value = ''; busy.value = true
  try { emit('login', await api<User>('/auth/demo', { method: 'POST', body: JSON.stringify({ role: role.value, student: demoStudent.value }) })) }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
function splitDemo() {
  const target = isTeacher.value ? `student-${demoStudent.value}` : 'teacher'
  const url = new URL(window.location.href)
  url.search = ''; url.hash = ''; url.searchParams.set('demo_window', target)
  const child = window.open(url.toString(), `shuban-demo-${target}`, 'popup,width=1180,height=820,resizable=yes,scrollbars=yes')
  splitNotice.value = child ? '另一个演示窗口已打开，两边可分别登录。完成操作后点击刷新查看对方更新。' : '新窗口被拦截，请允许当前应用打开弹出窗口后重试。'
  child?.focus()
}
onMounted(checkSetup)
</script>

<template>
  <div class="login-page" :class="{ 'teacher-theme': isTeacher }">
    <section class="login-story">
      <Brand />
      <div class="story-content">
        <div class="eyebrow"><span class="tiny-dot"/> {{ isTeacher ? '为每一次有效教学' : '你的高等数学学习伙伴' }}</div>
        <h1 v-if="!isTeacher">每一步思考，<br>都有<span>回应。</span></h1>
        <h1 v-else>看见每一步成长，<br>让教学<span>有据可依。</span></h1>
        <p class="story-description">{{ isTeacher ? '从课堂任务到学习反馈，连接教师的洞察与学生的进步。' : '把抽象变具体，把困惑变进步。和数伴一起，找到属于你的学习节奏。' }}</p>
        <div class="math-scene" aria-hidden="true">
          <div class="scene-orbit orbit-one"></div><div class="scene-orbit orbit-two"></div>
          <div class="graph-card">
            <div class="graph-heading"><span><span class="tiny-dot"/> 思考，正在发生</span><span>f(x)</span></div>
            <svg class="math-graph" viewBox="0 0 420 230">
              <defs><pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M 28 0 L 0 0 0 28" fill="none" stroke="#e5dfef" stroke-width=".7"/></pattern><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#a794df" stop-opacity=".3"/><stop offset="100%" stop-color="#a794df" stop-opacity="0"/></linearGradient></defs>
              <rect x="20" y="10" width="380" height="200" fill="url(#grid)"/><path d="M30 180H400M105 215V15" stroke="#b4abc9" stroke-width="1"/><path d="M30 175C96 175 111 153 144 128S192 117 219 136S280 163 310 118S341 52 392 31V180H30Z" fill="url(#area)"/><path d="M30 175C96 175 111 153 144 128S192 117 219 136S280 163 310 118S341 52 392 31" fill="none" stroke="#8c73ce" stroke-width="3"/><path d="M229 212L361 41" stroke="#d3a66e" stroke-width="1.6" stroke-dasharray="5 5"/><circle cx="310" cy="118" r="7" fill="#fff" stroke="#8c73ce" stroke-width="3"/><text x="393" y="196" fill="#978bab" font-size="12">x</text><text x="87" y="20" fill="#978bab" font-size="12">y</text>
            </svg>
            <div class="graph-caption">从一条曲线，理解变化的意义 <ArrowUpRight :size="14"/></div>
          </div>
          <div class="floating-formula formula-a">lim<span>x → 0</span> <i>sin x</i><b> / x = 1</b></div>
          <div class="floating-note"><span class="check-icon"><Check :size="16"/></span><div>不止于答案<small>理解，才是下一步</small></div></div>
          <span class="scene-spark spark-a">✧</span><span class="scene-spark spark-b">✦</span>
        </div>
        <div class="story-features"><span><BookOpen :size="16"/> 循序理解</span><span><Sparkles :size="16"/> 伴随学习</span><span><GraduationCap :size="17"/> 教学相长</span></div>
      </div>
      <div class="story-footer">让学习被理解，让成长被看见。<span>01 — 开始探索</span></div>
    </section>

    <section class="login-panel">
      <div class="login-top"><span>高等数学 · 学习与教学空间</span><span class="version-chip">数伴 0.3</span><ThemeToggle compact/></div>
      <div class="login-box">
        <div class="login-heading-icon"><School v-if="isTeacher" :size="27"/><GraduationCap v-else :size="28"/></div>
        <h2>{{ registering ? '注册学生账号' : creatingTeacher ? '建立你的教学空间' : isTeacher ? '欢迎回来，老师' : '开启今天的学习' }}<span class="heading-dot">.</span></h2>
        <p class="muted">{{ creatingTeacher ? '首次使用，请创建第一位教师账号。之后可创建班级、学生与其他教师账号。' : isTeacher ? '登录教学空间，陪伴每一次进步。' : '登录已有账号，或注册学生账号后通过班级码加入。' }}</p>
        <p v-if="checking" role="status" class="muted small">正在检查教学空间…</p>
        <div class="role-tabs" role="tablist" aria-label="登录身份">
          <button :disabled="busy || checking" role="tab" :aria-selected="!isTeacher" :class="{ active: !isTeacher }" @click="switchRole('student')"><GraduationCap :size="18"/> 学生登录</button>
          <button :disabled="busy || checking" role="tab" :aria-selected="isTeacher" :class="{ active: isTeacher }" @click="switchRole('teacher')"><School :size="18"/> 教师登录</button>
        </div>
        <div v-if="demoEnabled" class="demo-entry">
          <label v-if="!isTeacher" class="field-label" for="demo-student">选择演示学生</label>
          <select v-if="!isTeacher" id="demo-student" v-model="demoStudent" class="demo-select" :disabled="busy"><option :value="1">演示同学 1（原账号）</option><option :value="2">演示同学 2</option><option :value="3">演示同学 3</option></select>
          <button type="button" class="outline-button demo-login" :disabled="busy || checking || checkFailed" @click="demoLogin"><Sparkles :size="18"/> {{ busy ? '正在进入…' : isTeacher ? '一键登录教师演示账号' : '一键登录学生演示账号' }}</button>
          <button type="button" class="outline-button demo-login split-demo" :disabled="busy || checking || checkFailed" @click="splitDemo">分开演示 · 打开{{isTeacher ? '学生' : '教师'}}窗口</button>
          <p v-if="splitNotice" role="status" class="muted small">{{splitNotice}}</p>
          <p class="muted small">免填账号密码 · 演示班支持布置与提交作业，请勿填写真实隐私信息。</p>
        </div>
        <div v-if="!isTeacher" class="filter-tabs" aria-label="学生账号操作"><button type="button" :disabled="busy" :class="{active:!registering}" @click="registering=false; error=''">账号登录</button><button type="button" :disabled="busy" :class="{active:registering}" @click="registering=true; error=''">注册学生账号</button></div>
        <form @submit.prevent="login">
          <label class="field-label" for="username">{{ isTeacher ? '教师账号' : '学生账号' }}</label>
          <div class="login-input"><UserRound :size="18"/><input id="username" v-model="username" name="username" autocomplete="username" required :minlength="creatingAccount ? 3 : undefined" :pattern="creatingAccount ? '[A-Za-z0-9_.\\-]{3,80}' : undefined" maxlength="80" :placeholder="isTeacher ? '请输入教师账号' : '请输入学生账号'" /></div>
          <template v-if="creatingAccount"><label class="field-label" for="setup-name">{{isTeacher ? '教师姓名' : '学生姓名'}}</label><div class="login-input"><UserRound :size="18"/><input id="setup-name" v-model="name" autocomplete="name" required maxlength="80" placeholder="请输入你的姓名"/></div></template>
          <label class="field-label" for="password">密码</label>
          <div class="login-input"><LockKeyhole :size="17"/><input id="password" v-model="password" name="password" :type="visible ? 'text' : 'password'" :autocomplete="creatingAccount ? 'new-password' : 'current-password'" required :minlength="creatingAccount ? 10 : undefined" maxlength="128" :placeholder="creatingAccount ? '至少 10 位，包含字母与数字' : '请输入密码'"/><button class="icon-button" type="button" :aria-label="visible ? '隐藏密码' : '显示密码'" @click="visible = !visible"><EyeOff v-if="visible" :size="18"/><Eye v-else :size="18"/></button></div>
          <template v-if="registering"><label class="field-label" for="confirm-password">确认密码</label><div class="login-input"><input id="confirm-password" v-model="confirmPassword" type="password" required minlength="10" maxlength="128" autocomplete="new-password"/></div><label class="field-label" for="class-code">班级码（可稍后填写）</label><div class="login-input"><input id="class-code" v-model="classCode" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="填写老师提供的班级码"/></div></template>
          <div v-if="!creatingAccount" class="login-options"><label class="checkbox-label"><input v-model="remember" type="checkbox"/> 保持登录</label><el-tooltip content="教师创建的学生账号忘记密码请联系原创建老师；自行注册账号请妥善保管密码。教师账号由首次初始化或已有教师创建。"><button type="button" class="subtle-link">登录帮助 <CircleHelp :size="14"/></button></el-tooltip></div>
          <p v-else class="account-note">请妥善保管账号与密码。密码至少 10 个字符，同时包含字母和数字。</p>
          <p v-if="remember" class="remember-note">在此设备保留登录 7 天，不保存明文密码。</p>

          <button v-if="checkFailed" class="outline-button" type="button" @click="checkSetup">重新连接</button>
          <button class="primary-button login-submit" type="submit" :disabled="busy || checking || checkFailed">{{ busy ? '正在处理…' : registering ? '注册并进入学习空间' : creatingTeacher ? '创建账号并开始' : isTeacher ? '进入教学空间' : '进入学习空间' }}<ArrowRight :size="19"/></button>
        </form>
        <p v-if="error" role="alert" class="form-error">{{ error }}</p>
        <button v-if="checkFailed && setupRequired && !isTeacher" class="outline-button" @click="checkSetup">重新连接</button>
        <p class="login-footnote"><LockKeyhole :size="13"/> 账号独立 · 数据保存在当前服务</p>
      </div>
      <footer class="login-bottom">数伴 SHUBAN <span>让每一步学习都有回应</span></footer>
    </section>
  </div>
</template>

<style scoped>
.demo-select { width:100%; padding:10px; margin-bottom:10px; border:1px solid var(--el-border-color); border-radius:8px; color:inherit; background:var(--el-bg-color); }
.split-demo { margin-top:10px; }
.demo-entry { margin: 20px 0; }
.demo-login { width: 100%; justify-content: center; min-height: 46px; }
.demo-entry p { margin: 10px 0 0; line-height: 1.6; }
</style>
