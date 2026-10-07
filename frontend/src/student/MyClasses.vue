<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../shared/api'
const emit = defineEmits<{ changed: [] }>()
type Class = { id: string; name: string; course: string; term: string; teacher_name: string; active: boolean; archived: boolean }
const classes = ref<Class[]>([]), code = ref(''), busy = ref(false), error = ref(''), notice = ref('')
async function load() { try { classes.value = await api<Class[]>('/student/classes') } catch(e) { error.value=(e as Error).message } }
async function join() {
 if (busy.value) return
 busy.value=true; error.value=''; notice.value=''
 try { const c=await api<Class>('/student/classes/join',{method:'POST',body:JSON.stringify({code:code.value})}); code.value=''; notice.value='已加入 '+c.name+'。后续新发布的作业会出现在“我的作业”。'; await load(); emit('changed') }
 catch(e) {error.value=(e as Error).message} finally {busy.value=false}
}
onMounted(load)
</script>
<template>
 <div class="page-heading"><div><div class="eyebrow">MY CLASSES</div><h1>我的班级</h1><p>输入老师提供的班级码，加入教学班。</p></div><button class="outline-button" @click="load">刷新班级</button></div>
 <section class="panel"><form class="dialog-form" @submit.prevent="join"><label>班级码<input v-model="code" required inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="6位数字班级码"/></label><div class="dialog-actions"><button class="primary-button" :disabled="busy">{{busy?'正在加入…':'加入班级'}}</button></div></form><p v-if="error" class="form-error" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p></section>
 <div class="class-grid"><article v-for="c in classes" :key="c.id" class="panel"><h3>{{c.name}}</h3><p>{{c.course}} · {{c.term}}</p><p>教师：{{c.teacher_name}}</p><span class="status-pill">{{!c.active?'已移出':c.archived?'已归档':'在班'}}</span></article></div>
 <p v-if="!classes.length" class="muted">还未加入班级。加入后即可与老师通信并接收新作业。</p>
</template>
