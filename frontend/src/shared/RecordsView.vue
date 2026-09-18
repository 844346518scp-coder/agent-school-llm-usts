<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, MessageSquare, ArrowUpRight, Bookmark, Clock3 } from 'lucide-vue-next'
import type { Conversation } from './api'
import { formatDate } from './api'
const props = defineProps<{ records: Conversation[]; favorites: boolean }>()
const emit = defineEmits<{ open: [id: string]; ask: [] }>()
const query = ref('')
const filtered = computed(() => props.records.filter(r => (!props.favorites || r.favorite) && `${r.question} ${r.topic}`.toLowerCase().includes(query.value.toLowerCase())))
</script>
<template><div class="page-heading"><div><div class="eyebrow">EVERY QUESTION COUNTS</div><h1>{{ favorites ? '值得再想一遍的问题' : '回看每一步探索' }}</h1><p>{{ favorites ? '收藏有启发的讲解，让复习更有方向。收藏不代表系统判定你答错。' : '提问与回复会保存在这里，刷新或重新登录后仍可查看。' }}</p></div><span class="status-pill">{{ filtered.length }} 条记录</span></div><div class="records-toolbar"><Search :size="18"/><input v-model="query" aria-label="搜索学习记录" placeholder="搜索问题、章节关键词…"/></div><div v-if="!filtered.length" class="panel empty-state"><Bookmark v-if="favorites" :size="40"/><MessageSquare v-else :size="40"/><h3>{{ query ? '暂时没有匹配的记录' : favorites ? '复习本，等待你的第一条收藏' : '你的探索，从第一个问题开始' }}</h3><p>{{ query ? '试着换一个关键词。' : '和数伴聊聊，在讲解下方点击收藏，就能留住有用的思路。' }}</p><button class="primary-button" @click="emit('ask')">去问数伴 <ArrowUpRight :size="16"/></button></div><div v-else class="records-list"><button v-for="r in filtered" :key="r.id" class="panel record-card" @click="emit('open', r.id)"><span class="stat-icon lilac"><MessageSquare :size="20"/></span><div><div class="record-top"><span class="small-pill">{{ r.topic }}</span><span v-if="r.favorite" class="saved-badge"><Bookmark :size="12"/> 已收藏</span></div><h3>{{ r.question }}</h3><p><Clock3 :size="13"/> {{ formatDate(r.created_at) }}<span>{{ r.mode === 'live' ? '模型回复' : '演示反馈' }}</span></p></div><ArrowUpRight :size="19"/></button></div></template>
