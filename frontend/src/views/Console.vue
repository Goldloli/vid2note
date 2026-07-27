<template>
  <div class="page console">
    <!-- 新建任务 -->
    <section class="create card">
      <div class="create-head">
        <h2 class="h-section">{{ $t('console.newTask') }}</h2>
        <span class="muted mono-sm">{{ $t('console.onlineVideo') }} / {{ $t('console.localFile') }}</span>
      </div>

      <div class="src-row">
        <div class="src-block">
          <div class="src-label">{{ $t('console.onlineVideo') }}</div>
          <input class="input" v-model="url" :placeholder="$t('console.urlPh')">
        </div>
        <div class="src-block">
          <div class="src-label">{{ $t('console.localFile') }}</div>
          <div class="row gap-s" style="align-items:center">
            <label class="btn btn-sm file-pick">
              <span>{{ fileName || $t('console.selectFile') }}</span>
              <input type="file" accept="video/*,audio/*" @change="onFile">
            </label>
            <button v-if="fileName" class="btn btn-ghost btn-sm" @click="clearFile">✕</button>
          </div>
        </div>
      </div>

      <div class="engine-row">
        <span class="kicker">{{ $t('console.asr') }}</span>
        <button v-for="e in asrEngines" :key="e.v" class="chip" :class="{active: form.asr_engine===e.v}" @click="form.asr_engine=e.v">{{ $t(e.l) }}</button>
        <span class="kicker sep">{{ $t('console.llm') }}</span>
        <select class="select select-sm" v-model="form.llm_provider"><option v-for="p in llmProviders" :key="p" :value="p">{{ p }}</option></select>
        <span class="kicker sep">{{ $t('console.lang') }}</span>
        <button class="chip" :class="{active: form.output_language==='zh'}" @click="form.output_language='zh'">{{ $t('console.zh') }}</button>
        <button class="chip" :class="{active: form.output_language==='en'}" @click="form.output_language='en'">{{ $t('console.en') }}</button>
        <span class="kicker sep">{{ $t('console.shot') }}</span>
        <button class="chip" :class="{active: form.extract_images}" @click="form.extract_images=!form.extract_images">{{ form.extract_images ? $t('console.on') : $t('console.off') }}</button>
        <span class="engine-spacer"></span>
        <button class="btn btn-primary start-btn" :disabled="loading" @click="start">{{ loading ? $t('console.submitting') : $t('console.start') }}</button>
      </div>
    </section>

    <!-- 统计 -->
    <div class="stats">
      <div class="stat-card"><span class="stat-label">{{ $t('console.sRunning') }}</span><span class="stat-value">{{ stats?.running ?? 0 }}</span></div>
      <div class="stat-card"><span class="stat-label">{{ $t('console.sToday') }}</span><span class="stat-value">{{ stats?.today_completed ?? 0 }}</span></div>
      <div class="stat-card"><span class="stat-label">{{ $t('console.sTotal') }}</span><span class="stat-value">{{ stats?.total ?? 0 }}</span></div>
      <div class="stat-card"><span class="stat-label">{{ $t('console.sCompleted') }}</span><span class="stat-value">{{ stats?.completed ?? 0 }}</span></div>
    </div>

    <!-- 进行中 -->
    <div class="section-head">
      <h2 class="h-section">{{ $t('console.sRunning') }} <span class="count">{{ tasks.running.length }}</span></h2>
    </div>
    <div v-for="t in tasks.running" :key="t.id" class="task-card card">
      <div class="spread">
        <div class="task-title"><strong>{{ t.title || t.source_url }}</strong> <span class="badge" :class="t.status"><span class="d"></span>{{ statusText(t.status) }}</span></div>
        <router-link class="btn btn-ghost btn-sm" :to="`/task/${t.id}`">{{ $t('console.viewDetail') }}</router-link>
      </div>
      <div class="rail-wrap"><PipelineRail :nodes="t.node_statuses || {}" /></div>
    </div>
    <div v-if="!tasks.running.length" class="empty muted mono-sm">{{ $t('console.noCompleted') }}</div>

    <!-- 最近完成 -->
    <div class="section-head">
      <h2 class="h-section">{{ $t('console.recent') }}</h2>
      <router-link class="more" to="/history">{{ $t('console.viewAll') }}</router-link>
    </div>
    <div class="card table-wrap"><table class="table">
      <thead><tr><th>{{ $t('console.thSource') }}</th><th>{{ $t('console.thStatus') }}</th><th>{{ $t('console.thProduct') }}</th></tr></thead>
      <tbody>
        <tr v-for="t in tasks.completed" :key="t.id">
          <td>{{ t.title || t.source_url }}</td>
          <td><span class="badge completed"><span class="d"></span>{{ statusText('completed') }}</span></td>
          <td class="td-actions"><router-link class="btn btn-sm" :to="`/note/${t.id}`">{{ $t('common.note') }}</router-link> <router-link class="btn btn-sm" :to="`/mindmap/${t.id}`">{{ $t('common.mindmap') }}</router-link> <a class="btn btn-sm" :href="getProductUrl(t.id,'srt')" download>{{ $t('console.srt') }}</a></td>
        </tr>
        <tr v-if="!tasks.completed.length"><td colspan="3" class="muted empty-cell">{{ $t('console.noCompleted') }}</td></tr>
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
function onFile(e) { const f = e.target.files?.[0]; if (!f) return; fileObj.value = f; fileName.value = f.name }
function clearFile() { fileObj.value = null; fileName.value = ''; document.querySelectorAll('input[type=file]').forEach(i => { i.value = '' }) }
function baseFields(fd) { fd.append('asr_engine', form.asr_engine); fd.append('llm_provider', form.llm_provider); fd.append('output_language', form.output_language); if (form.extract_images) fd.append('extract_images', 'true') }
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
/* 字体层级 + 间距节奏(清晰普通版底线,无渐变/玻璃/inset/hover-scale) */
.console .h-section { font-size: 17px; font-weight: 600; letter-spacing: -0.01em; margin: 0; }
.count { font-size: 13px; color: var(--muted); font-weight: 500; margin-left: 4px; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; margin: 28px 0 14px; }

/* 新建任务区 */
.create { padding: 20px 22px; }
.create-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 16px; }
.src-row { display: grid; grid-template-columns: 1fr; gap: 12px; }
.src-block { padding: 12px 14px; background: var(--card-2); border-radius: 8px; }
.src-label { font-size: 12px; color: var(--text-2); font-weight: 600; margin-bottom: 8px; letter-spacing: 0.02em; }
.file-pick { position: relative; overflow: hidden; cursor: pointer; }
.file-pick input[type=file] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.engine-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.engine-row .kicker { margin: 0; }
.engine-row .sep { margin-left: 8px; }
.engine-row .select-sm { width: auto; height: 30px; }
.engine-spacer { flex: 1; }
.start-btn { padding: 8px 22px; }

/* 统计卡 */
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 20px; }
.stat-card { position: relative; padding: 16px 18px 16px 20px; background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.stat-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--accent); opacity: 0.65; }
.stat-label { display: block; font-size: 11px; color: var(--text-2); text-transform: uppercase; letter-spacing: 0.08em; }
.stat-value { display: block; font-size: 34px; font-weight: 700; margin-top: 6px; font-variant-numeric: tabular-nums; line-height: 1; color: var(--text); }

/* 任务卡 */
.task-card { padding: 16px 18px; margin-bottom: 12px; transition: background .15s; }
.task-card:hover { background: var(--card-2); }
.task-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rail-wrap { margin-top: 14px; }
.empty { padding: 20px; text-align: center; }

/* 表格 */
.table-wrap { padding: 4px; }
.empty-cell { padding: 24px; text-align: center; }

@media (max-width: 760px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
}
</style>
