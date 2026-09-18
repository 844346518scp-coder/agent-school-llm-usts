<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Search, MessageSquare, ArrowUpRight, Bookmark, Clock3, Repeat, Tags } from 'lucide-vue-next'
import type { Conversation } from './api'
import { formatDate } from './api'
const props = defineProps<{ records: Conversation[]; favorites: boolean }>()
const emit = defineEmits<{ open: [id: string]; ask: []; practice: [topic: string] }>()
const query = ref('')
const activeTag = ref('全部')
watch(() => props.favorites, () => { activeTag.value = '全部' })
const favoriteList = computed(() => props.records.filter(r => !props.favorites || r.favorite))
const tagCounts = computed(() => {
  const map = new Map<string, number>()
  for (const r of favoriteList.value) map.set(r.topic, (map.get(r.topic) ?? 0) + 1)
  return Array.from(map, ([tag, count]) => ({ tag, count }))
})
const filtered = computed(() => favoriteList.value.filter(r =>
  (!props.favorites || activeTag.value === '全部' || r.topic === activeTag.value) &&
  `${r.question} ${r.topic}`.toLowerCase().includes(query.value.toLowerCase())))
function practiceActiveTag() { if (activeTag.value !== '全部') emit('practice', activeTag.value) }
function onCardKey(event: KeyboardEvent, id: string) {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); emit('open', id) }
}
function onPracticeKey(event: KeyboardEvent, topic: string) {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); emit('practice', topic) }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">EVERY QUESTION COUNTS</div>
      <h1>{{ favorites ? '值得再想一遍的问题' : '回看每一步探索' }}</h1>
      <p>{{ favorites ? '收藏有启发的讲解，让复习更有方向。收藏不代表系统判定你答错。' : '提问与回复会保存在这里，刷新或重新登录后仍可查看。' }}</p>
    </div>
    <span class="status-pill">{{ filtered.length }} 条记录</span>
  </div>
  <div class="records-toolbar"><Search :size="18"/><input v-model="query" aria-label="搜索学习记录" placeholder="搜索问题、章节关键词…"/></div>
  <div v-if="favorites && tagCounts.length" class="fav-tags" aria-label="按标签筛选收藏">
    <span class="fav-tags-label"><Tags :size="13"/> 标签</span>
    <button type="button" :class="{ active: activeTag === '全部' }" @click="activeTag = '全部'">全部<i>{{ favoriteList.length }}</i></button>
    <button v-for="t in tagCounts" :key="t.tag" type="button" :class="{ active: activeTag === t.tag }" @click="activeTag = t.tag">{{ t.tag }}<i>{{ t.count }}</i></button>
    <button v-if="activeTag !== '全部'" type="button" class="fav-practice" @click="practiceActiveTag"><Repeat :size="13"/> 重练「{{ activeTag }}」</button>
  </div>
  <div v-if="!filtered.length" class="panel empty-state">
    <Bookmark v-if="favorites" :size="40"/><MessageSquare v-else :size="40"/>
    <h3>{{ query || (favorites && activeTag !== '全部') ? '暂时没有匹配的记录' : favorites ? '复习本，等待你的第一条收藏' : '你的探索，从第一个问题开始' }}</h3>
    <p>{{ query || (favorites && activeTag !== '全部') ? '试着换一个关键词或标签。' : '和数伴聊聊，在讲解下方点击收藏，就能留住有用的思路。' }}</p>
    <button class="primary-button" @click="emit('ask')">去问数伴 <ArrowUpRight :size="16"/></button>
  </div>
  <div v-else class="records-list">
    <div v-for="r in filtered" :key="r.id" class="panel record-card" role="button" tabindex="0" @click="emit('open', r.id)" @keydown="onCardKey($event, r.id)">
      <span class="stat-icon lilac"><MessageSquare :size="20"/></span>
      <div>
        <div class="record-top"><span class="small-pill">{{ r.topic }}</span><span v-if="r.favorite" class="saved-badge"><Bookmark :size="12"/> 已收藏</span></div>
        <h3>{{ r.question }}</h3>
        <p><Clock3 :size="13"/> {{ formatDate(r.created_at) }}<span>{{ r.mode === 'live' ? '模型回复' : '演示反馈' }}</span></p>
      </div>
      <span v-if="favorites" class="card-practice" role="button" tabindex="0" title="按这个知识点标签再练一道新题" @click.stop="emit('practice', r.topic)" @keydown="onPracticeKey($event, r.topic)"><Repeat :size="13"/>同标签重练</span>
      <ArrowUpRight :size="19"/>
    </div>
  </div>
</template>

<style scoped>
.fav-tags{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:-4px 0 20px}
.fav-tags-label{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);margin-right:2px}
.fav-tags>button{font-size:12px;background:#fff;border:1px solid var(--line);color:#a994ba;border-radius:7px;padding:7px 12px;display:inline-flex;align-items:center;gap:6px}
.fav-tags>button i{font-style:normal;font-size:10px;color:var(--muted);background:var(--soft);border-radius:5px;padding:1px 6px}
.fav-tags>button.active{background:var(--soft);color:var(--primary);border-color:#e4d9f1;font-weight:600}
.fav-tags>button.active i{color:var(--primary)}
.fav-tags .fav-practice{margin-left:auto;background:var(--primary);color:#fff;border-color:var(--primary);font-weight:500}
.fav-tags .fav-practice i{display:none}
.record-card{cursor:pointer}
.card-practice{display:inline-flex;align-items:center;gap:5px;color:var(--primary);font-size:11px;white-space:nowrap;align-self:center;padding:7px 9px;border-radius:7px;flex-shrink:0}
.card-practice:hover{background:var(--soft)}
.card-practice:focus-visible{outline:3px solid #bcb0e1;outline-offset:1px}
@media(max-width:760px){.fav-tags .fav-practice{margin-left:0;width:100%;justify-content:center}}
</style>
