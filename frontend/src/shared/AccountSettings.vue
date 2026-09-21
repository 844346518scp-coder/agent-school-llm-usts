<script setup lang="ts">
import { ref, watch } from 'vue'
import { KeyRound, UserRound, UserPlus } from 'lucide-vue-next'
import ElMessage from 'element-plus/es/components/message/index'
import { api, type User } from './api'
const props = defineProps<{ user: User }>()
const emit = defineEmits<{ updated: [user: User] }>()
const name = ref(props.user.name), current = ref(''), password = ref(''), confirm = ref('')
const busy = ref(''), error = ref(''), teacherOpen = ref(false), teacherError = ref('')
const teacherForm = ref({ username: '', name: '', password: '' })
watch(() => props.user.name, value => name.value = value)
async function profile() {
  if (busy.value) return; busy.value = 'profile'; error.value = ''
  try { emit('updated', await api<User>('/auth/profile', { method: 'PATCH', body: JSON.stringify({ name: name.value }) })); ElMessage.success('姓名已更新') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = '' }
}
async function changePassword() {
  if (busy.value) return; error.value = ''
  if (password.value !== confirm.value) { error.value = '两次输入的新密码不一致。'; return }
  busy.value = 'password'
  try { const result = await api<User>('/auth/password', { method: 'POST', body: JSON.stringify({ current_password: current.value, new_password: password.value }) }); current.value = ''; password.value = ''; confirm.value = ''; emit('updated', result); ElMessage.success('密码已更新，其他设备上的旧登录已失效') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = '' }
}
async function createTeacher() {
  if (busy.value) return; busy.value = 'teacher'; teacherError.value = ''
  try { await api('/auth/teachers', { method: 'POST', body: JSON.stringify(teacherForm.value) }); teacherForm.value = { username: '', name: '', password: '' }; teacherOpen.value = false; ElMessage.success('教师账号已创建，请将账号和临时密码单独告知本人') }
  catch (e) { teacherError.value = (e as Error).message } finally { busy.value = '' }
}
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">YOUR ACCOUNT</div><h1>{{ user.must_change_password ? '先设置属于你的密码' : '账号设置' }}</h1><p>{{ user.must_change_password ? '当前使用临时密码。修改后即可进入你的空间。' : '管理你的姓名与登录密码。' }}</p></div><span class="status-pill">{{ user.username }}</span></div>
  <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  <div class="account-grid">
    <section class="panel"><div class="section-heading"><h3><KeyRound :size="18"/> {{ user.must_change_password ? '首次修改密码' : '修改密码' }}</h3></div><form class="dialog-form" @submit.prevent="changePassword"><label>当前密码<input v-model="current" type="password" autocomplete="current-password" required maxlength="128"/></label><label>新密码<input v-model="password" type="password" autocomplete="new-password" required minlength="10" maxlength="128" placeholder="至少 10 位，包含字母与数字"/></label><label>再次输入新密码<input v-model="confirm" type="password" autocomplete="new-password" required minlength="10" maxlength="128"/></label><p class="muted small">保存后会撤销此账号的其他登录会话，本设备继续保持登录。</p><div class="dialog-actions"><button class="primary-button" :disabled="!!busy">{{ busy === 'password' ? '正在更新…' : '保存新密码' }}</button></div></form></section>
    <div v-if="!user.must_change_password" class="account-side"><section class="panel"><div class="section-heading"><h3><UserRound :size="18"/> 个人资料</h3></div><form class="dialog-form" @submit.prevent="profile"><label>姓名<input v-model="name" required maxlength="80" autocomplete="name"/></label><p class="muted small">身份：{{ user.role === 'teacher' ? '教师' : '学生' }}{{ user.is_demo ? ' · 演示账号' : '' }}</p><div class="dialog-actions"><button class="outline-button" :disabled="!!busy">保存姓名</button></div></form></section><section v-if="user.role === 'teacher'" class="panel"><div class="section-heading"><h3><UserPlus :size="18"/> 添加教师</h3></div><p class="muted small">为其他老师开通独立教学空间。每位教师分别管理自己的班级、学生、题库与作业。</p><button class="outline-button" :disabled="!!busy" @click="teacherError = ''; teacherOpen = true">创建教师账号</button></section></div>
  </div>
  <el-dialog v-model="teacherOpen" title="创建教师账号" width="520px" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy"><form class="dialog-form" @submit.prevent="createTeacher"><label>教师账号<input v-model="teacherForm.username" required minlength="3" pattern="[A-Za-z0-9_.\-]{3,80}" maxlength="80" autocomplete="off"/></label><label>教师姓名<input v-model="teacherForm.name" required maxlength="80"/></label><label>临时密码<input v-model="teacherForm.password" type="password" required minlength="10" maxlength="128" autocomplete="new-password" placeholder="至少 10 位，包含字母与数字"/></label><p class="muted small">新教师首次登录须修改密码。请通过独立渠道告知账号与临时密码，密码不会在创建后显示。</p><p v-if="teacherError" class="form-error" role="alert">{{ teacherError }}</p><div class="dialog-actions"><button type="button" class="outline-button" :disabled="!!busy" @click="teacherOpen = false">取消</button><button class="primary-button" :disabled="!!busy">{{ busy ? '创建中…' : '创建账号' }}</button></div></form></el-dialog>
</template>
