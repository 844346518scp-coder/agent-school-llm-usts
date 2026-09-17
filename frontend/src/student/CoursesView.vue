<script setup lang="ts">
import { ArrowUpRight, BookOpen, Lightbulb, Sigma } from 'lucide-vue-next'
import { ref, computed } from 'vue'
const emit = defineEmits<{ ask: [question: string] }>()
const selected = ref('全部章节')
const lessons = [
  { chapter: '函数与极限', number: '01', title: '无限接近，意味着什么？', text: '从直觉出发，建立函数极限的初步认识。', formula: 'lim f(x)', prompt: '如何理解函数极限？', label: '概念探索' },
  { chapter: '函数与极限', number: '02', title: '一个重要的极限', text: '从 sin(x)/x 入手，学习夹逼思想。', formula: 'sin x / x', prompt: '如何理解 sin(x)/x 在 x→0 时的极限？', label: '预设例题' },
  { chapter: '导数与微分', number: '03', title: '让变化，有一个刻度', text: '从割线到切线，用定义理解导数。', formula: 'f′(x)', prompt: '用定义求 x² 的导数', label: '预设例题' },
  { chapter: '导数与微分', number: '04', title: '讲给另一个人听', text: '尝试解释导数，用讲解梳理你的理解。', formula: 'Δy / Δx', prompt: '我想用费曼学习法解释导数', label: '费曼练习' },
]
const filtered = computed(() => lessons.filter(l => selected.value === '全部章节' || l.chapter === selected.value))
</script>
<template><div class="page-heading"><div><div class="eyebrow">LEARN AT YOUR OWN PACE</div><h1>循着好奇，走进高数</h1><p>当前提供概念入口与预设例题，完整课程知识库将在后续接入。</p></div><BookOpen :size="30" class="heading-illustration"/></div><div class="filter-tabs"><button v-for="tab in ['全部章节', '函数与极限', '导数与微分']" :key="tab" :class="{ active: selected === tab }" @click="selected = tab">{{ tab }}</button></div><div class="lesson-grid"><article v-for="lesson in filtered" :key="lesson.number" class="panel lesson-card"><div class="lesson-art"><span>{{ lesson.formula }}</span><small>{{ lesson.number }}</small></div><div class="lesson-copy"><div class="section-kicker">{{ lesson.chapter }} <span>· {{ lesson.label }}</span></div><h3>{{ lesson.title }}</h3><p>{{ lesson.text }}</p><button class="subtle-link" @click="emit('ask', lesson.prompt)">带着问题去探索 <ArrowUpRight :size="16"/></button></div></article></div><div class="course-note"><Lightbulb :size="21"/><p>先理解概念，再练习迁移。数伴不会仅凭一次对话就认定你已经掌握。</p><Sigma :size="25"/></div></template>
