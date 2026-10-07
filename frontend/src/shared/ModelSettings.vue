<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from './api'
const props = defineProps<{ demo: boolean }>()
const form = ref({ base_url: 'https://api.deepseek.com', model: 'deepseek-flash', vision_model: 'deepseek-flash', api_key: '' })
const hasKey = ref(false), ready = ref(false), busy = ref(''), message = ref(''), error = ref('')
async function load() {
  busy.value = 'load'; error.value = ''
  try {
    const saved = await api<typeof form.value & { has_key: boolean }>('/model-settings')
    form.value = { base_url: saved.base_url, model: saved.model, vision_model: saved.vision_model, api_key: '' }
    hasKey.value = saved.has_key; ready.value = true
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = '' }
}
async function act(action: 'save' | 'test' | 'clear') {
  if (busy.value) return
  busy.value = action; error.value = ''; message.value = ''
  try {
    if (action === 'clear') {
      await api('/model-settings', { method: 'DELETE' }); await load()
      message.value = '个人配置已清除，后续提问使用服务默认配置。'
    } else {
      const result = await api<{ message?: string }>('/model-settings' + (action === 'test' ? '/test' : ''), { method: action === 'test' ? 'POST' : 'PUT', body: JSON.stringify(form.value) })
      if (action === 'save') { hasKey.value = true; form.value.api_key = ''; message.value = '已加密保存，下一次提问立即生效。' }
      else message.value = result.message || '连接成功'
    }
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = '' }
}
onMounted(load)
</script>
<template>
  <section class="panel model-settings">
    <div class="section-heading"><h3>AI / API 配置</h3><span class="status-pill">{{ hasKey ? '已保存密钥' : '未配置个人 API' }}</span></div>
    <p class="muted small">支持 OpenAI 兼容的 Chat Completions 接口。配置仅用于当前账号，保存后无需重启。测试会向所填服务发送一条简短请求，可能产生少量费用。</p>
    <p v-if="props.demo" class="account-note">你正在使用共享演示账号，同一演示账号的使用者会共用此配置。个人密钥建议在正式账号中保存。</p>
    <form class="dialog-form" @submit.prevent="act('save')">
      <fieldset :disabled="!!busy || !ready">
        <label>API 地址<input v-model="form.base_url" required maxlength="500" placeholder="https://api.deepseek.com"/></label>
        <label>文字模型<input v-model="form.model" required maxlength="120" placeholder="deepseek-flash"/></label>
        <label>图片识别模型（可选）<input v-model="form.vision_model" maxlength="120" placeholder="留空使用文字模型；需服务支持图片"/></label>
        <label>API Key<input v-model="form.api_key" type="password" maxlength="1024" autocomplete="off" :placeholder="hasKey ? '已保存，留空保留原密钥；修改地址时须重新填写' : '填写服务商提供的 API Key'"/></label>
      </fieldset>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
      <div class="dialog-actions">
        <button v-if="!ready" type="button" class="outline-button" :disabled="!!busy" @click="load">重新加载</button>
        <button type="button" class="outline-button" :disabled="!!busy || !ready" @click="act('test')">{{ busy === 'test' ? '测试中…' : '测试连接' }}</button>
        <button type="submit" class="primary-button" :disabled="!!busy || !ready">{{ busy === 'save' ? '保存中…' : '保存配置' }}</button>
        <button type="button" class="outline-button" :disabled="!!busy || !hasKey" @click="act('clear')">清除配置</button>
      </div>
      <p class="muted small">密钥以 Windows 本机用户加密保护，不会回显或保存在浏览器中。清除个人配置不会删除服务端原有环境配置。</p>
    </form>
  </section>
</template>
<style scoped>
.model-settings { margin-top: 24px; }
fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 16px; }
.dialog-actions { flex-wrap: wrap; }
</style>
