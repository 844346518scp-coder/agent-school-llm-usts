<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight, ArrowUpRight, BookOpen, GraduationCap, School, Eye, EyeOff, LockKeyhole, UserRound, Sparkles, Check, CircleHelp } from 'lucide-vue-next'
import Brand from './Brand.vue'
import { api, type Role, type User } from './api'
const emit = defineEmits<{ login: [user: User] }>()
const role = ref<Role>('student')
const username = ref('')
const password = ref('')
const visible = ref(false)
const remember = ref(false)
const busy = ref(false)
const error = ref('')
const isTeacher = computed(() => role.value === 'teacher')
function switchRole(value: Role) { role.value = value; username.value = ''; password.value = ''; error.value = ''; remember.value = false }
function fillDemo() { username.value = role.value; password.value = isTeacher.value ? 'Teacher123!' : 'Student123!'; error.value = '' }
async function login() {
  if (busy.value) return
  error.value = ''; busy.value = true
  try { emit('login', await api<User>('/auth/login', { method: 'POST', body: JSON.stringify({ username: username.value, password: password.value, role: role.value, remember: remember.value }) })) }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
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
      <div class="login-top"><span>高等数学 · 学习与教学空间</span><span class="version-chip">MVP 预览版</span></div>
      <div class="login-box">
        <div class="login-heading-icon"><School v-if="isTeacher" :size="27"/><GraduationCap v-else :size="28"/></div>
        <h2>{{ isTeacher ? '欢迎回来，老师' : '开启今天的学习' }}<span class="heading-dot">.</span></h2>
        <p class="muted">{{ isTeacher ? '登录教学空间，陪伴每一次进步。' : '登录你的学习空间，从一个好问题开始。' }}</p>
        <div class="role-tabs" role="tablist" aria-label="登录身份">
          <button role="tab" :aria-selected="!isTeacher" :class="{ active: !isTeacher }" @click="switchRole('student')"><GraduationCap :size="18"/> 学生登录</button>
          <button role="tab" :aria-selected="isTeacher" :class="{ active: isTeacher }" @click="switchRole('teacher')"><School :size="18"/> 教师登录</button>
        </div>
        <form @submit.prevent="login">
          <label class="field-label" for="username">{{ isTeacher ? '教师账号' : '学生账号' }}</label>
          <div class="login-input"><UserRound :size="18"/><input id="username" v-model="username" name="username" autocomplete="username" required maxlength="80" :placeholder="isTeacher ? '请输入教师账号' : '请输入学生账号'" /></div>
          <label class="field-label" for="password">密码</label>
          <div class="login-input"><LockKeyhole :size="17"/><input id="password" v-model="password" name="password" :type="visible ? 'text' : 'password'" autocomplete="current-password" required maxlength="128" placeholder="请输入密码"/><button class="icon-button" type="button" :aria-label="visible ? '隐藏密码' : '显示密码'" @click="visible = !visible"><EyeOff v-if="visible" :size="18"/><Eye v-else :size="18"/></button></div>
          <div class="login-options"><label class="checkbox-label"><input v-model="remember" type="checkbox"/> 记住密码</label><el-tooltip content="演示账号见下方；当前版本暂不提供自助重置密码。"><button type="button" class="subtle-link">登录帮助 <CircleHelp :size="14"/></button></el-tooltip></div>
          <p v-if="remember" class="remember-note">在此设备保留登录 7 天，不保存明文密码。</p>
          <p v-if="error" role="alert" class="form-error">{{ error }}</p>
          <button class="primary-button login-submit" type="submit" :disabled="busy">{{ busy ? '正在验证账号…' : isTeacher ? '进入教学空间' : '进入学习空间' }}<ArrowRight :size="19"/></button>
        </form>
        <div class="demo-account"><div class="demo-account-title"><span class="tiny-dot"/> 先体验，再探索<button @click="fillDemo">填入演示账号 <ArrowUpRight :size="13"/></button></div><div class="demo-credentials"><span>账号 <code>{{ role }}</code></span><span>密码 <code>{{ isTeacher ? 'Teacher123!' : 'Student123!' }}</code></span></div></div>
        <p class="login-footnote"><LockKeyhole :size="13"/> 本地体验环境 · 请使用演示账号</p>
      </div>
      <footer class="login-bottom">数伴 SHUBAN <span>让每一步学习都有回应</span></footer>
    </section>
  </div>
</template>
