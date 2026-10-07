<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { api, formatDate } from './api'
type Contact = {id:string;name:string;role:string;can_send:boolean;unread:number}
type Message = {id:number;sender_id:string;recipient_id:string;content:string;created_at:string;mine:boolean;read:boolean}
const contacts=ref<Contact[]>([]), selected=ref(''), messages=ref<Message[]>([]), draft=ref(''), error=ref(''), busy=ref(false), loading=ref(false), older=ref(false)
const peer=computed(()=>contacts.value.find(c=>c.id===selected.value))
let generation=0, clientId=crypto.randomUUID(), timer:ReturnType<typeof setInterval>|undefined
watch(draft, () => { if (!busy.value) clientId = crypto.randomUUID() })
async function loadContacts(){try {contacts.value=await api<Contact[]>('/mail/contacts')}catch(e){error.value=(e as Error).message}}
async function open(id:string, previous=false){
 const request=++generation
 if(id!==selected.value){draft.value=''; clientId=crypto.randomUUID();messages.value=[]}
 selected.value=id; loading.value=true; error.value=''
 try {
  const rows=await api<Message[]>('/mail/messages/'+id+(previous&&messages.value.length?'?before='+messages.value[0].id:''))
  if(request!==generation)return
  messages.value=previous?[...rows,...messages.value]:rows; older.value=rows.length===100
  if(rows.length)await api('/mail/messages/'+id+'/read',{method:'POST',body:JSON.stringify({through_id:rows[rows.length-1].id})})
  await loadContacts()
 }catch(e){if(request===generation)error.value=(e as Error).message}finally{if(request===generation)loading.value=false}
}
async function send(){
 if(busy.value||!draft.value.trim()||!peer.value?.can_send)return
 busy.value=true;error.value=''
 try{await api('/mail/messages',{method:'POST',body:JSON.stringify({recipient_id:selected.value,content:draft.value,client_id:clientId})});draft.value='';clientId=crypto.randomUUID();await open(selected.value)}
 catch(e){error.value=(e as Error).message}finally{busy.value=false}
}
onMounted(()=>{void loadContacts();timer=setInterval(()=>{void loadContacts()},15000)})
onBeforeUnmount(()=>{generation++;clearInterval(timer)})
</script>
<template>
 <div class="page-heading"><div><div class="eyebrow">MESSAGES</div><h1>师生信箱</h1><p>与当前班级的老师或学生沟通。退出班级后保留历史，停止发送。</p></div><button class="outline-button" :disabled="loading||busy" @click="selected?open(selected):loadContacts()">刷新信箱</button></div>
 <p v-if="error" class="form-error" role="alert">{{error}}</p>
 <div class="mail-layout"><section class="panel mail-contacts"><h3>联系人</h3><p v-if="!contacts.length" class="muted">暂无联系人，请先加入班级或添加学生。</p><button v-for="c in contacts" :key="c.id" class="outline-button" :class="{chosen:selected===c.id}" :disabled="busy||loading" @click="open(c.id)">{{c.name}} · {{c.role==='teacher'?'老师':'学生'}} <span v-if="c.unread" class="status-pill">{{c.unread}} 未读</span></button></section>
 <section class="panel mail-thread"><h3>{{peer?'与 '+peer.name+' 的通信':'请选择联系人'}}</h3><button v-if="older" class="subtle-link" :disabled="loading" @click="open(selected,true)">加载更早信件</button><p v-if="loading" role="status">正在读取信件…</p><div class="mail-history"><article v-for="m in messages" :key="m.id" :class="{mine:m.mine}"><small>{{m.mine?'我':peer?.name}} · {{formatDate(m.created_at)}} <span v-if="m.mine">· {{m.read?'已读':'未读'}}</span></small><p>{{m.content}}</p></article><p v-if="selected&&!messages.length&&!loading" class="muted">还没有信件，写下第一条消息吧。</p></div>
 <form v-if="peer" class="dialog-form" @submit.prevent="send"><label>信件内容<textarea v-model="draft" :disabled="busy||!peer.can_send" required maxlength="3000" rows="4" placeholder="输入想与老师或学生沟通的内容"/></label><div class="dialog-actions"><span class="muted small">{{draft.length}} / 3000</span><button class="primary-button" :disabled="busy||loading||!peer.can_send||!draft.trim()">{{busy?'发送中…':'发送信件'}}</button></div><p v-if="!peer.can_send" class="muted">当前班级关系已结束或对方已停用，历史信件只读。</p></form></section></div>
</template>
<style scoped>
.mail-layout{display:grid;grid-template-columns:260px minmax(0,1fr);gap:20px}.mail-contacts{display:flex;flex-direction:column;gap:12px;align-self:start}.chosen{border-color:var(--primary,#8c73ce)}.mail-history{max-height:420px;overflow:auto;margin:20px 0}.mail-history article{padding:14px;border:1px solid var(--el-border-color,#ddd);border-radius:12px;margin:12px 0}.mail-history .mine{margin-left:30px;background:var(--el-fill-color-light,#f7f5fb)}.mail-history p{white-space:pre-wrap;overflow-wrap:anywhere}.mail-history small{color:var(--el-text-color-secondary,#888)}@media(max-width:760px){.mail-layout{grid-template-columns:1fr}}
</style>
