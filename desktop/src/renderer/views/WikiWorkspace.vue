<template>
  <section class="focus-workspace wiki-workspace">
    <header class="focus-header"><div><small>{{ page?.path ?? 'Vault' }}</small><h1>{{ title }}</h1></div><button v-if="page" type="button" @click="editing = !editing">{{ editing ? '阅读' : '编辑' }}</button></header>
    <p v-if="vault.loading">正在读取页面…</p><p v-else-if="vault.error" role="alert">页面读取失败，请重试。</p>
    <div v-else-if="editing && page">
      <MarkdownEditor :content="page.content" :error-message="saveError" @cancel="editing = false" @save="save" />
      <section v-if="conflict" class="conflict-review" role="alertdialog" aria-label="页面保存冲突">
        <h2>页面已在外部修改</h2><p>草稿未被覆盖。比较三个版本后，选择继续编辑或明确载入最新版本。</p>
        <div class="conflict-columns"><article><h3>编辑前</h3><pre>{{ conflict.before }}</pre></article><article><h3>磁盘最新</h3><pre>{{ conflict.current }}</pre></article><article><h3>你的草稿</h3><pre>{{ conflict.draft }}</pre></article></div>
        <button type="button" @click="conflict = null">继续编辑草稿</button><button type="button" @click="reloadConflict">载入磁盘最新版本</button>
      </section>
    </div>
    <div v-else-if="page" class="wiki-reader-grid">
      <MarkdownReader :content="body" @navigate="open" @evidence="evidence" />
      <aside class="page-aside"><PageOutline :headings="outline" /><BacklinksPanel :links="vault.backlinks" @open="open" /></aside>
    </div>
    <div v-else class="empty-state"><h1>个人知识库</h1><p>从左侧选择页面，或导入一个来源开始。</p><RouterLink to="/workspace/import">导入来源</RouterLink></div>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MarkdownEditor from '../components/wiki/MarkdownEditor.vue'
import MarkdownReader from '../components/wiki/MarkdownReader.vue'
import BacklinksPanel from '../components/wiki/BacklinksPanel.vue'
import PageOutline from '../components/wiki/PageOutline.vue'
import { extractOutline } from '../components/wiki/renderMarkdown'
import { readVaultPage } from '../api/vault'
import { useVaultStore } from '../stores/vault'
const vault = useVaultStore(); const route = useRoute(); const router = useRouter(); const editing = ref(false); const saveError = ref(''); const conflict = ref<{ before: string; current: string; draft: string } | null>(null)
const page = computed(() => vault.currentPage)
const body = computed(() => page.value?.content.replace(/^---\n[\s\S]*?\n---\n/, '') ?? '')
const title = computed(() => String(page.value?.frontmatter?.title ?? page.value?.path.split('/').pop() ?? '知识库'))
const outline = computed(() => extractOutline(body.value))
async function load(): Promise<void> { await vault.open(String(route.query.path || 'index.md')) }
function open(path: string): void { void router.push({ path: '/workspace/wiki', query: { path } }) }
function evidence(reference: { sourceId: string; startMs: number; endMs: number }): void { void router.push({ path: `/workspace/sources/${reference.sourceId}`, query: { start: reference.startMs, end: reference.endMs } }) }
async function save(content: string): Promise<void> { saveError.value = ''; conflict.value = null; try { await vault.save(content); editing.value = false } catch (cause) { const code = typeof cause === 'object' && cause && 'code' in cause ? String(cause.code) : ''; if (code === 'VAULT_CONFLICT' && page.value) { const latest = await readVaultPage(page.value.path); conflict.value = { before: page.value.content, current: latest.content, draft: content }; saveError.value = '保存冲突：草稿已保留，请比较三个版本。' } else saveError.value = '保存失败，当前草稿已保留，请重试。' } }
async function reloadConflict(): Promise<void> { if (!page.value) return; await vault.open(page.value.path); conflict.value = null; saveError.value = '' }
watch(() => route.query.path, load); onMounted(load)
</script>
