<template>
  <div class="page">
    <section class="card card-pad reveal in" style="margin-bottom:18px">
      <div class="eyebrow" style="margin-bottom:12px">{{ $t('console.newTask') }}</div>

      <div class="src-block">
        <div class="kicker" style="margin-bottom:6px">{{ $t('console.onlineVideo') }}</div>
        <input class="input" v-model="url" :placeholder="$t('console.urlPh')">
      </div>

      <div class="src-block" style="margin-top:12px">
        <div class="kicker" style="margin-bottom:6px">{{ $t('console.localFile') }}</div>
        <div class="row gap-s" style="align-items:center">
          <label class="btn btn-sm" style="cursor:pointer;position:relative;display:inline-flex;align-items:center;overflow:hidden">
            {{ fileName || $t('console.selectFile') }}
            <input type="file" accept="video/*,audio/*" @change="onFile" style="position:absolute;inset:0;opacity:0;cursor:pointer">
          </label>
          <button v-if="fileName" class="btn btn-ghost btn-sm" @click="clearFile">✕</button>
        </div>
      </div>

      <div class="row gap-s wrap" style="margin-top:14px">
        <span class="kicker">{{ $t('console.asr') }}</span>
        <button v-for="e in asrEngines" :key="e.v" class="chip" :class="{active: form.asr_engine===e.v}" @click="form.asr_engine=e.v">{{ $t(e.l) }}</button>
        <span class="kicker" style="margin-left:12px">{{ $t('console.llm') }}</span>
        <select class="select" style="width:auto" v-model="form.llm_provider"><option v-for="p in llmProviders" :key="p" :value="p">{{ p }}</option></select>
        <span class="kicker" style="margin-left:12px">{{ $t('console.lang') }}</span>
        <button class="chip" :class="{active: form.output_language==='zh'}" @click="form.output_language='zh'">{{ $t('console.zh') }}</button>
        <button class="chip" :class="{active: form.output_language==='en'}" @click="form.output_language='en'">{{ $t('console.en') }}</button>
        <span class="kicker" style="margin-left:12px">{{ $t('console.shot') }}</span>
        <button class="chip" :class="{active: form.extract_images}" @click="form.extract_images=!form.extract_images">{{ form.extract_images ? $t('console.on') : $t('console.off') }}</button>
      </div>

      <div style="margin-top:14px">
        <button class="btn btn-primary" :disabled="loading" @click="start">{{ loading ? $t('console.submitting') : $t('console.start') }} →</button>
      </div>
    </section>

    <div class="row gap-s" style="margin-bottom:18px">
      <div class="card stat"><div class="muted mono-sm">{{ $t('console.sRunning') }}</div><div class="stat-num">{{ stats?.running ?? 0 }}</div></div>
      <div class="card stat"><div class="muted mono-sm">{{ $t('console.sToday') }}</div><div class="stat-num">{{ stats?.today_completed ?? 0 }}</div></div>
      <div class="card stat"><div class="muted mono-sm">{{ $t('console.sTotal') }}</div><div class="stat-num">{{ stats?.total ?? 0 }}</div></div>
      <div class="card stat"><div class="muted mono-sm">{{ $t('console.sCompleted') }}</div><div class="stat-num">{{ stats?.completed ?? 0 }}</div></div>
    </div>

    <div class="section-title"><h2>{{ $t('console.sRunning') }} <span class="muted mono-sm">· {{ tasks.running.length }}</span></h2></div>
    <div v-for="t in tasks.running" :key="t.id" class="card card-pad" style="margin-bottom:12px">
      <div class="spread">
        <div><strong>{{ t.title || t.source_url }}</strong> &nbsp;<span class="badge" :class="t.status"><span class="d"></span>{{ statusText(t.status) }}</span></div>
        <router-link class="btn btn-ghost btn-sm" :to="`/task/${t.id}`">{{ $t('console.viewDetail') }}</router-link>
      </div>
      <div style="margin-top:14px"><PipelineRail :nodes="t.node_statuses || {}" /></div>
    </div>
    <div class="section-title" style="margin-top:24px"><h2>{{ $t('console.recent') }}</h2><router-link class="more" to="/history">{{ $t('console.viewAll') }}</router-link></div>
    <div class="card"><table class="table">
      <thead><tr><th>{{ $t('console.thSource') }}</th><th>{{ $t('console.thStatus') }}</th><th>{{ $t('console.thProduct') }}</th></tr></thead>
      <tbody>
        <tr v-for="t in tasks.completed" :key="t.id">
          <td>{{ t.title || t.source_url }}</td>
          <td><span class="badge completed"><span class="d"></span>{{ statusText('completed') }}</span></td>
          <td class="td-actions"><router-link class="btn btn-sm" :to="`/note/${t.id}`">{{ $t('common.note') }}</router-link> <router-link class="btn btn-sm" :to="`/mindmap/${t.id}`">{{ $t('common.mindmap') }}</router-link> <a class="btn btn-sm" :href="getProductUrl(t.id,'srt')" download>{{ $t('console.srt') }}</a></td>
        </tr>
        <tr v-if="!tasks.completed.length"><td colspan="3" class="muted" style="padding:24px;text-align:center">{{ $t('console.noCompleted') }}</td></tr>
      </tbody>
    </table></div>
  </div>
</template>
<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { taskStats, getProductUrl } from '@/api'
import { ASR_ENGINES } from '@/asr'
import { i18n } from '@/i18n'
import PipelineRail from '@/components/PipelineRail.vue'
const router = useRouter(); const tasks = useTaskStore()
const url = ref(''); const fileName = ref(''); const fileObj = ref(null)
const loading = ref(false); const stats = ref(null)
const llmProviders = ['deepseek','qwen','glm','moonshot','minimax','doubao','baidu','ollama']
const form = reactive({ asr_engine: 'asrtools', llm_provider: 'deepseek', output_language: 'zh', extract_images: false })
const asrEngines = ASR_ENGINES
let timer
const statusText = s => i18n.global.t('status.' + s)
async function refresh() { await Promise.all([tasks.fetchRecent(), taskStats().then(s => stats.value = s).catch(() => {})]) }
// 选文件只暂存,不自动开始(openspec change frontend-console-redesign)
function onFile(e) { const f = e.target.files?.[0]; if (!f) return; fileObj.value = f; fileName.value = f.name }
function clearFile() { fileObj.value = null; fileName.value = ''; document.querySelectorAll('input[type=file]').forEach(i => { i.value = '' }) }
function baseFields(fd) { fd.append('asr_engine', form.asr_engine); fd.append('llm_provider', form.llm_provider); fd.append('output_language', form.output_language); if (form.extract_images) fd.append('extract_images', 'true') }
// 手动「开始」:URL 非空用 URL,否则用已选文件,都空提示
async function start() {
  const u = url.value.trim()
  if (!u && !fileObj.value) { alert(i18n.global.t('console.needSource')); return }
  loading.value = true
  try {
    const fd = new FormData()
    if (u) fd.append('source_url', u)
    else fd.append('file', fileObj.value)
    baseFields(fd)
    const t = await tasks.create(fd)
    url.value = ''; clearFile(); router.push(`/task/${t.id}`)
  } catch (e) { alert(e.message) } finally { loading.value = false }
}
onMounted(() => { refresh(); timer = setInterval(refresh, 2000) })
onUnmounted(() => clearInterval(timer))
</script>
<style scoped>
.src-block { padding: 10px 12px; background: var(--card-2); border-radius: 8px; }
.stat { flex: 1; padding: 14px 16px; }
.stat-num { font-size: 26px; font-weight: 700; margin-top: 4px; color: var(--text); }
</style>
