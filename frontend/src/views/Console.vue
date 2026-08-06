<template>
  <div class="page page-wide console">
    <PageHeader :title="$t('console.title')" :subtitle="$t('console.subtitle')" icon="console">
      <template #meta>
        <div class="page-meta-row">
          <span class="meta-item"><span class="dot-live"></span>{{ $t('nav.local') }}</span>
          <span class="meta-item">{{ $t('console.asr') }}: {{ $t(`engine.short.${form.asr_engine}`) }}</span>
          <span class="meta-item">{{ $t('console.llm') }}: {{ form.llm_provider || $t('console.noLlm') }}</span>
        </div>
      </template>
    </PageHeader>

    <section id="task-composer" class="task-composer surface">
      <SectionHeader :title="$t('console.newTask')" :description="$t('console.composerHint')" />

      <div class="source-grid">
        <div class="source-option" :class="{ active: tab === 'url' }" @click="tab = 'url'">
          <div class="source-option-head">
            <div class="source-icon"><AppIcon name="link" :size="20" weight="duotone" /></div>
            <div>
              <strong>{{ $t('console.onlineVideo') }}</strong>
              <small>{{ $t('console.networkHint') }}</small>
            </div>
          </div>
          <label class="field-label" for="source-url">{{ $t('console.urlLabel') }}</label>
          <input
            id="source-url"
            v-model="url"
            class="input"
            :placeholder="$t('console.urlPh')"
            @focus="tab = 'url'"
            @keyup.enter="start"
          >
        </div>

        <div class="source-option" :class="{ active: tab === 'file' }" @click="tab = 'file'">
          <div class="source-option-head">
            <div class="source-icon"><AppIcon name="upload" :size="20" weight="duotone" /></div>
            <div>
              <strong>{{ $t('console.localFile') }}</strong>
              <small>{{ $t('console.localHint') }}</small>
            </div>
          </div>
          <span class="field-label">{{ $t('console.fileLabel') }}</span>
          <div class="file-control">
            <label class="btn file-pick">
              <AppIcon name="folder" :size="17" />
              <span>{{ fileNames.length ? fileNames.join(', ').slice(0, 58) : $t('console.selectFile') }}</span>
              <input type="file" accept="video/*,audio/*" multiple @change="onFile">
            </label>
            <button v-if="fileNames.length" class="icon-btn" type="button" :aria-label="$t('console.clearFile')" @click.stop="clearFile">
              <AppIcon name="close" :size="17" />
            </button>
          </div>
        </div>
      </div>

      <div class="quick-settings">
        <div class="option-group option-group-wide">
          <span class="field-label">{{ $t('console.asr') }}</span>
          <div class="row wrap">
            <button
              v-for="engine in asrEngines"
              :key="engine.v"
              class="chip"
              :class="{ active: form.asr_engine === engine.v }"
              :aria-pressed="form.asr_engine === engine.v"
              data-testid="task-asr-engine"
              :data-engine="engine.v"
              type="button"
              @click="form.asr_engine = engine.v"
            >
              {{ $t(engine.l) }}
            </button>
          </div>
        </div>
        <div class="option-group">
          <label class="field-label" for="task-llm-provider">{{ $t('console.llm') }}</label>
          <select id="task-llm-provider" v-model="form.llm_provider" class="select" data-testid="task-llm-provider" :disabled="!llmProviders.length">
            <option v-for="provider in llmProviders" :key="provider.id" :value="provider.id">{{ provider.name }}</option>
            <option v-if="!llmProviders.length" value="" disabled>{{ $t('console.noLlm') }}</option>
          </select>
          <router-link v-if="!llmProviders.length" class="llm-config-hint" to="/settings">{{ $t('console.configureLlm') }}</router-link>
        </div>
        <div class="option-group">
          <span class="field-label">{{ $t('console.lang') }}</span>
          <div class="segmented">
            <button type="button" data-testid="task-output-language" data-language="zh" :class="{ active: form.output_language === 'zh' }" @click="form.output_language = 'zh'">{{ $t('console.zh') }}</button>
            <button type="button" data-testid="task-output-language" data-language="en" :class="{ active: form.output_language === 'en' }" @click="form.output_language = 'en'">{{ $t('console.en') }}</button>
          </div>
        </div>
      </div>

      <button class="advanced-toggle" type="button" :aria-expanded="advancedOpen" @click="advancedOpen = !advancedOpen">
        <span><AppIcon name="sliders" :size="17" />{{ $t('console.advanced') }}</span>
        <AppIcon :name="advancedOpen ? 'caret-down' : 'caret-right'" :size="16" />
      </button>

      <div v-if="advancedOpen" class="advanced-panel">
        <label class="option-group">
          <span class="field-label">{{ $t('console.detail') }}</span>
          <select v-model="form.note_detail_level" class="select" data-testid="task-detail-level">
            <option value="concise">{{ $t('settings.detail.concise') }}</option>
            <option value="balanced">{{ $t('settings.detail.balanced') }}</option>
            <option value="detailed">{{ $t('settings.detail.detailed') }}</option>
            <option value="exhaustive">{{ $t('settings.detail.exhaustive') }}</option>
          </select>
        </label>
        <div class="option-group">
          <span class="field-label">{{ $t('console.shot') }}</span>
          <button
            class="choice-card"
            :class="{ active: form.extract_images }"
            type="button"
            :aria-pressed="form.extract_images"
            data-testid="task-extract-images"
            @click="form.extract_images = !form.extract_images"
          >
            <AppIcon :name="form.extract_images ? 'check-circle' : 'file-video'" :size="19" />
            <span>{{ form.extract_images ? $t('console.on') : $t('console.off') }}</span>
          </button>
        </div>
        <div class="option-group option-group-wide">
          <span class="field-label">{{ $t('console.pdfLecture') }}</span>
          <div class="file-control">
            <label class="btn file-pick">
              <AppIcon name="file-pdf" :size="17" />
              <span>{{ pdfName || $t('console.pdfSelect') }}</span>
              <input type="file" accept="application/pdf" @change="onPdf">
            </label>
            <button v-if="pdfName" class="icon-btn" type="button" :aria-label="$t('console.clearPdf')" @click="clearPdf">
              <AppIcon name="close" :size="17" />
            </button>
          </div>
        </div>
      </div>

      <div class="composer-footer">
        <p>{{ $t('console.startHint') }}</p>
        <button class="btn btn-primary start-btn" type="button" :disabled="loading || !llmProviders.length" @click="start">
          <AppIcon name="upload" :size="17" weight="bold" />
          {{ loading ? $t('console.submitting') : $t('console.start') }}
        </button>
      </div>
    </section>

    <div class="stats" aria-label="任务统计">
      <div class="stat-card stat-card-primary">
        <span class="stat-label">{{ $t('console.sRunning') }}</span>
        <span class="stat-value">{{ stats?.running ?? 0 }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">{{ $t('console.sToday') }}</span>
        <span class="stat-value">{{ stats?.today_completed ?? 0 }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">{{ $t('console.sTotal') }}</span>
        <span class="stat-value">{{ stats?.total ?? 0 }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">{{ $t('console.sCompleted') }}</span>
        <span class="stat-value">{{ stats?.completed ?? 0 }}</span>
      </div>
    </div>

    <SectionHeader
      :title="$t('console.sRunning')"
      :description="$t('console.runningHint')"
      :count="tasks.running.length"
    />
    <div v-if="tasks.running.length" class="running-list">
      <article v-for="task in tasks.running" :key="task.id" class="task-card surface">
        <div class="task-card-head">
          <div class="task-title">
            <strong>{{ task.title || task.source_url }}</strong>
            <span class="badge" :class="task.status"><span class="d"></span>{{ statusText(task.status) }}</span>
          </div>
          <router-link class="btn btn-ghost btn-sm" :to="`/task/${task.id}`">{{ $t('console.viewDetail') }}<AppIcon name="arrow-right" :size="14" /></router-link>
        </div>
        <div class="rail-wrap"><PipelineRail :nodes="task.node_statuses || {}" /></div>
      </article>
    </div>
    <EmptyState
      v-else
      class="surface"
      :title="$t('console.noRunningTitle')"
      :description="$t('console.noRunningHint')"
      icon="check-circle"
    >
      <template #actions>
        <a class="btn btn-primary" href="#task-composer">{{ $t('console.createNow') }}</a>
      </template>
    </EmptyState>

    <SectionHeader :title="$t('console.recent')" :description="$t('console.recentHint')">
      <template #actions>
        <router-link class="btn btn-ghost btn-sm" to="/history">{{ $t('console.viewAll') }}<AppIcon name="arrow-right" :size="14" /></router-link>
      </template>
    </SectionHeader>
    <div class="surface table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ $t('console.thSource') }}</th>
            <th>{{ $t('console.thStatus') }}</th>
            <th>{{ $t('console.thProduct') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks.completed" :key="task.id">
            <td class="recent-title">{{ task.title || task.source_url }}</td>
            <td><span class="badge completed"><span class="d"></span>{{ statusText('completed') }}</span></td>
            <td>
              <div class="td-actions">
                <router-link class="btn btn-sm" :to="`/note/${task.id}`">{{ $t('common.note') }}</router-link>
                <router-link class="btn btn-sm" :to="`/mindmap/${task.id}`">{{ $t('common.mindmap') }}</router-link>
                <a class="btn btn-sm" :href="getProductUrl(task.id, 'srt')" download>{{ $t('console.srt') }}</a>
              </div>
            </td>
          </tr>
          <tr v-if="!tasks.completed.length">
            <td colspan="3" class="empty-cell">{{ $t('console.noCompleted') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import PipelineRail from '@/components/PipelineRail.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { getProductUrl, taskStats } from '@/api'
import { ASR_ENGINES } from '@/asr'
import { i18n } from '@/i18n'
import { configuredLlmProviders, resolveConfiguredLlmProvider } from '@/llm'
import { useConfigStore } from '@/stores/config'
import { useTaskStore } from '@/stores/task'

const tasks = useTaskStore()
const config = useConfigStore()
const url = ref('')
const fileNames = ref([])
const files = ref([])
const pdfFile = ref(null)
const pdfName = ref('')
const tab = ref('url')
const advancedOpen = ref(false)
const loading = ref(false)
const stats = ref(null)
const llmProviders = computed(() => configuredLlmProviders(config.settings))
const form = reactive({ asr_engine: 'bcut', llm_provider: '', output_language: 'zh', note_detail_level: 'balanced', extract_images: false })
const asrEngines = ASR_ENGINES
let defaultsApplied = false
let timer

const statusText = status => i18n.global.t(`status.${status}`)
async function refresh() {
  await Promise.all([
    tasks.fetchRecent(),
    taskStats().then(response => { stats.value = response }).catch(() => {}),
  ])
}
function onFile(event) {
  const list = Array.from(event.target.files || [])
  if (!list.length) return
  files.value = list
  fileNames.value = list.map(file => file.name)
  tab.value = 'file'
}
function clearFile() {
  files.value = []
  fileNames.value = []
  document.querySelectorAll('input[type=file][accept="video/*,audio/*"]').forEach(input => { input.value = '' })
}
function onPdf(event) {
  const file = event.target.files?.[0]
  if (!file) return
  pdfFile.value = file
  pdfName.value = file.name
}
function clearPdf() {
  pdfFile.value = null
  pdfName.value = ''
  document.querySelectorAll('input[type=file][accept="application/pdf"]').forEach(input => { input.value = '' })
}
function baseFields(formData) {
  formData.append('asr_engine', form.asr_engine)
  formData.append('llm_provider', form.llm_provider)
  formData.append('output_language', form.output_language)
  formData.append('note_detail_level', form.note_detail_level)
  formData.append('extract_images', form.extract_images ? 'true' : 'false')
}
async function start() {
  if (!llmProviders.value.some(provider => provider.id === form.llm_provider)) {
    alert(i18n.global.t('console.noLlm'))
    return
  }
  loading.value = true
  try {
    const makeFormData = () => {
      const formData = new FormData()
      baseFields(formData)
      if (pdfFile.value) formData.append('pdf', pdfFile.value)
      return formData
    }
    if (tab.value === 'url') {
      const sourceUrl = url.value.trim()
      if (!sourceUrl) {
        alert(i18n.global.t('console.needSource'))
        return
      }
      const formData = makeFormData()
      formData.append('source_url', sourceUrl)
      await tasks.create(formData)
    } else {
      if (!files.value.length) {
        alert(i18n.global.t('console.needSource'))
        return
      }
      for (const file of files.value) {
        const formData = makeFormData()
        formData.append('file', file)
        await tasks.create(formData)
      }
    }
    url.value = ''
    clearFile()
    clearPdf()
    await refresh()
  } catch (error) {
    alert(error.message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 2000)
})
onUnmounted(() => clearInterval(timer))
watch(() => config.settings, response => {
  const settings = response?.settings
  if (!settings) return
  const preferredProvider = defaultsApplied ? form.llm_provider : settings['llm.provider']
  form.llm_provider = resolveConfiguredLlmProvider(llmProviders.value, preferredProvider)
  if (!defaultsApplied) {
    form.asr_engine = settings['asr.engine'] || form.asr_engine
    form.output_language = settings['note.output_language'] || form.output_language
    form.note_detail_level = settings['note.detail_level'] || form.note_detail_level
    form.extract_images = String(settings['note.extract_images']).toLowerCase() === 'true'
    defaultsApplied = true
  }
}, { immediate: true })
</script>

<style scoped>
.page-meta-row{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:9px}
.meta-item{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border:1px solid var(--border);border-radius:999px;background:var(--card);color:var(--muted);font-size:10.5px}
.meta-item .dot-live{width:5px;height:5px}
.task-composer{padding:20px 22px 0}
.task-composer :deep(.section-header){margin:0 0 15px}
.source-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:12px}
.source-option{min-width:0;padding:15px;border:1px solid var(--border);border-radius:var(--r);background:var(--card);transition:border-color var(--ease),background var(--ease),box-shadow var(--ease)}
.source-option:hover{border-color:var(--border-2)}
.source-option.active{border-color:var(--accent);background:var(--accent-soft);box-shadow:0 0 0 1px rgba(40,100,220,.06)}
.source-option-head{display:flex;align-items:flex-start;gap:10px;margin-bottom:13px}
.source-icon{display:grid;place-items:center;width:35px;height:35px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--accent)}
.source-option-head strong{display:block;font-size:13.5px}
.source-option-head small{display:block;margin-top:2px;color:var(--muted);font-size:11px}
.field-label{display:block;margin-bottom:6px;color:var(--text-2);font-size:11.5px;font-weight:600}
.file-control{display:flex;align-items:center;gap:7px;min-width:0}
.file-pick{position:relative;min-width:0;max-width:100%;overflow:hidden;cursor:pointer}
.file-pick span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-pick input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer}
.quick-settings{display:grid;grid-template-columns:minmax(300px,1.5fr) minmax(160px,.7fr) minmax(130px,.5fr);gap:12px;padding:17px 0}
.option-group{display:block;min-width:0}
.llm-config-hint{display:inline-flex;margin-top:6px;color:var(--accent);font-size:10.5px;font-weight:600}
.segmented{display:inline-flex;height:38px;padding:3px;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--card-2)}
.segmented button{min-width:46px;padding:0 12px;border-radius:5px;color:var(--muted);font-size:12px}
.segmented button.active{background:var(--card);color:var(--accent);box-shadow:var(--shadow-sm);font-weight:600}
.advanced-toggle{display:flex;align-items:center;justify-content:space-between;width:100%;padding:11px 0;border-top:1px solid var(--border);color:var(--text-2);font-size:12px;font-weight:600}
.advanced-toggle>span{display:flex;align-items:center;gap:7px}
.advanced-panel{display:grid;grid-template-columns:minmax(180px,.65fr) minmax(140px,.5fr) minmax(220px,1fr);gap:12px;padding:13px;border:1px solid var(--border);border-radius:var(--r);background:var(--card-2)}
.choice-card{display:flex;align-items:center;gap:8px;width:100%;height:38px;padding:0 11px;border:1px solid var(--border-2);border-radius:var(--r-sm);background:var(--card);color:var(--text-2);font-size:12px}
.choice-card.active{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.composer-footer{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:18px -22px 0;padding:15px 22px;border-top:1px solid var(--border);background:var(--card-2);border-radius:0 0 var(--r-lg) var(--r-lg)}
.composer-footer p{color:var(--muted);font-size:11.5px}
.start-btn{height:38px;padding:0 20px}
.stats{display:grid;grid-template-columns:1.15fr repeat(3,1fr);gap:10px;margin-top:16px}
.stat-card{display:flex;align-items:center;justify-content:space-between;min-height:74px;padding:14px 16px;border:1px solid var(--border);border-radius:var(--r);background:var(--card);box-shadow:var(--shadow-sm)}
.stat-card-primary{border-color:rgba(40,100,220,.2);background:var(--accent-soft)}
.stat-label{color:var(--muted);font-size:11.5px}
.stat-value{font-family:var(--mono);font-size:27px;font-weight:650;line-height:1;color:var(--text)}
.running-list{display:grid;gap:10px}
.task-card{padding:16px 18px}
.task-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.task-title{display:flex;align-items:center;gap:9px;min-width:0;flex-wrap:wrap}
.task-title strong{max-width:68ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rail-wrap{margin-top:16px;overflow-x:auto;padding-bottom:3px}
.table-wrap{overflow:hidden}
.table-wrap .table th:first-child,.table-wrap .table td:first-child{padding-left:18px}
.table-wrap .table th:last-child,.table-wrap .table td:last-child{padding-right:18px}
.recent-title{max-width:520px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.empty-cell{padding:32px!important;text-align:center;color:var(--muted)}

@media (max-width:1050px){
  .source-grid{grid-template-columns:1fr 1fr}
  .quick-settings{grid-template-columns:1fr 180px}
  .quick-settings .option-group:last-child{grid-column:1 / -1}
  .advanced-panel{grid-template-columns:1fr 1fr}
  .advanced-panel .option-group-wide{grid-column:1 / -1}
}
@media (max-width:899px){
  .source-grid{grid-template-columns:1fr}
  .quick-settings{grid-template-columns:1fr 1fr}
  .quick-settings .option-group-wide{grid-column:1 / -1}
  .stats{grid-template-columns:1fr 1fr}
}
@media (max-width:767px){
  .task-composer{padding:16px 16px 0}
  .quick-settings,.advanced-panel{grid-template-columns:1fr}
  .quick-settings .option-group-wide,.quick-settings .option-group:last-child,.advanced-panel .option-group-wide{grid-column:auto}
  .composer-footer{align-items:stretch;flex-direction:column;margin:16px -16px 0;padding:14px 16px}
  .start-btn{width:100%}
  .stats{grid-template-columns:1fr 1fr}
  .stat-card{min-height:68px}
  .table-wrap{overflow-x:auto}
  .task-card-head{align-items:stretch;flex-direction:column}
}
</style>
