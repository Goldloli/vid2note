<template>
  <nav aria-label="本页目录" class="page-outline">
    <h2>本页目录</h2>
    <a v-for="heading in headings" :key="heading.id" :href="`#${heading.id}`" :style="{ paddingInlineStart: `${(heading.level - 1) * 12}px` }">{{ heading.label }}</a>
    <p v-if="!headings.length">暂无目录</p>
  </nav>
</template>
<script setup lang="ts">
import type { OutlineHeading } from './renderMarkdown'
defineProps<{ headings: OutlineHeading[] }>()
</script>
