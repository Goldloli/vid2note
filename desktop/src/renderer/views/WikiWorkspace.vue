<template>
  <section class="focus-workspace wiki-workspace">
    <header class="focus-header"><div><small>{{ page?.path ?? 'Vault' }}</small><h1>{{ title }}</h1></div><button v-if="page" type="button" @click="editing = !editing">{{ editing ? '阅读' : '编辑' }}</button></header>
    <p v-if="vault.loading">正在读取页面…</p><p v-else-if="vault.error" role="alert">页面读取失败，请重试。</p>
    <MarkdownEditor v-else-if="editing && page" :content="page.content" :error-message="saveError" @cancel="editing = false" @save="save" />
    <div v-else-if="page" class="wiki-reader-grid">
      <MarkdownReader :content="body" @navigate="open" @evidence="evidence" />
      <aside class="page-aside"><h2>本页目录</h2><a v-for="heading in outline" :key="heading" href="#">{{ heading }}</a><h2>反向链接</h2><button v-for="link in vault.backlinks" :key="link.path" type="button" @click="open(link.path)">{{ link.title }}</button><p v-if="!vault.backlinks.length">暂无反向链接</p></aside>
    </div>
    <div v-else class="empty-state"><h1>个人知识库</h1><p>从左侧选择页面，或导入一个来源开始。</p><RouterLink to="/workspace/import">导入来源</RouterLink></div>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MarkdownEditor from '../components/wiki/MarkdownEditor.vue'
import MarkdownReader from '../components/wiki/MarkdownReader.vue'
import { useVaultStore } from '../stores/vault'
const vault = useVaultStore(); const route = useRoute(); const router = useRouter(); const editing = ref(false); const saveError = ref('')
const page = computed(() => vault.currentPage)
const body = computed(() => page.value?.content.replace(/^---\n[\s\S]*?\n---\n/, '') ?? '')
const title = computed(() => String(page.value?.frontmatter?.title ?? page.value?.path.split('/').pop() ?? '知识库'))
const outline = computed(() => [...body.value.matchAll(/^#{1,3}\s+(.+)$/gm)].map((match) => match[1]!))
async function load(): Promise<void> { await vault.open(String(route.query.path || 'index.md')) }
function open(path: string): void { void router.push({ path: '/workspace/wiki', query: { path } }) }
function evidence(reference: { sourceId: string; startMs: number; endMs: number }): void { void router.push({ path: `/workspace/sources/${reference.sourceId}`, query: { start: reference.startMs, end: reference.endMs } }) }
async function save(content: string): Promise<void> { saveError.value = ''; try { await vault.save(content); editing.value = false } catch (cause) { const code = typeof cause === 'object' && cause && 'code' in cause ? String(cause.code) : ''; saveError.value = code === 'VAULT_CONFLICT' ? '保存冲突：页面已在别处修改。当前草稿已保留，请重新载入后手动合并。' : '保存失败，当前草稿已保留，请重试。' } }
watch(() => route.query.path, load); onMounted(load)
</script>
