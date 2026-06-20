<template>
  <section aria-label="反向链接" class="backlinks-panel">
    <h2>反向链接</h2>
    <button v-for="link in links" :key="link.path" type="button" @click="$emit('open', link.path)">{{ link.title }}</button>
    <p v-if="!links.length">暂无反向链接</p>
  </section>
</template>
<script setup lang="ts">
import type { VaultBacklink } from '../../api/vault'
defineProps<{ links: VaultBacklink[] }>()
defineEmits<{ open: [path: string] }>()
</script>
