<template>
  <div class="page">
    <div class="spread" style="margin-bottom:16px">
      <strong>{{ $t('asr.title') }}</strong>
      <button class="btn btn-primary btn-sm" @click="save">{{ $t('asr.save') }}</button>
    </div>
    <div v-for="e in ASR_ENGINES" :key="e.v" class="card card-pad" style="margin-bottom:12px">
      <div class="spread">
        <div style="min-width:0">
          <div class="row gap-s" style="align-items:center;flex-wrap:wrap">
            <strong>{{ $t(e.l) }}</strong>
            <span v-if="s['asr.engine']===e.v" class="badge completed"><span class="d"></span>{{ $t('asr.current') }}</span>
            <span class="muted mono-sm">{{ e.v }}</span>
          </div>
          <div class="muted" style="margin-top:4px">{{ $t(e.desc) }}</div>
          <div class="muted mono-sm" style="margin-top:4px">
            <span v-if="e.v==='asrtools'">在线免费 · 无需配置</span>
            <span v-else-if="e.v==='whisper_cpp'">model: {{ status?.whisper_cpp?.model_exists ? '✓ ' + status.whisper_cpp.model_path : '✗ not ready' }}</span>
            <span v-else>endpoint: {{ status?.external?.endpoint_configured ? status.external.endpoint : '✗ not configured' }}</span>
          </div>
        </div>
        <div class="row gap-s" style="flex:none">
          <button class="btn btn-sm" :disabled="testing===e.v" @click="test(e.v)">{{ testing===e.v ? $t('asr.testing') : $t('asr.test') }}</button>
          <button class="chip btn-sm" :class="{active: s['asr.engine']===e.v}" @click="s['asr.engine']=e.v">{{ $t('asr.setDefault') }}</button>
        </div>
      </div>
      <div v-if="result[e.v]" :class="['test-result', result[e.v].ok ? 'ok' : 'fail']">
        {{ result[e.v].ok ? '✓ ' : '✗ ' }}{{ result[e.v].message }} <span class="muted mono-sm">· {{ result[e.v].latency_ms }}ms</span>
      </div>
    </div>
    <div class="card card-pad" style="margin-bottom:12px">
      <div class="kicker" style="margin-bottom:10px">{{ $t('asr.strategy') }}</div>
      <div class="row wrap">
        <button v-for="st in ASR_STRATEGIES" :key="st.v" class="chip" :class="{active: s['asr.strategy']===st.v}" @click="s['asr.strategy']=st.v">{{ $t(st.l) }}</button>
      </div>
      <div class="muted mono-sm" style="margin-top:8px">{{ $t('asr.strategyHint') }}</div>
    </div>
    <div class="card card-pad" style="margin-bottom:12px">
      <div class="kicker" style="margin-bottom:10px">Whisper 本地模型路径(选用「Whisper 本地」时需配置)</div>
      <input class="input" v-model="ext.whisper_model_path" placeholder="容器内绝对路径,如 /app/data/models/whisper-tiny">
      <div class="muted mono-sm" style="margin-top:8px">留空用容器内置默认模型(faster-whisper-tiny)。</div>
    </div>
    <div class="card card-pad" style="margin-bottom:12px">
      <div class="kicker" style="margin-bottom:10px">{{ $t('asr.externalTitle') }}</div>
      <div class="row" style="margin-bottom:8px"><input class="input" style="flex:1" v-model="ext.endpoint" :placeholder="$t('asr.endpointPh')"></div>
      <div class="row"><input class="input" style="flex:1" v-model="ext.api_key" :placeholder="$t('asr.apiKeyPh')" type="password"></div>
      <div class="muted mono-sm" style="margin-top:8px">{{ $t('asr.maskedHint') }}</div>
    </div>
  </div>
</template>
<script setup>
import { reactive, ref, onMounted } from 'vue'
import { getSettings, putSettings, asrStatus, asrTest } from '@/api'
import { ASR_ENGINES, ASR_STRATEGIES } from '@/asr'
import { i18n } from '@/i18n'
const s = reactive({ 'asr.engine': 'asrtools', 'asr.strategy': 'online_first' })
const ext = reactive({ endpoint: '', api_key: '', whisper_model_path: '' })
const status = ref(null); const testing = ref(''); const result = reactive({})
async function load() {
  try {
    const r = await getSettings(); const st = r.settings || {}
    s['asr.engine'] = st['asr.engine'] || 'asrtools'; s['asr.strategy'] = st['asr.strategy'] || 'online_first'
    const cfg = st['asr.config']
    if (cfg && cfg !== '***') { try { const o = typeof cfg === 'string' ? JSON.parse(cfg) : cfg; ext.endpoint = o.external_endpoint || ''; ext.api_key = o.external_api_key || ''; ext.whisper_model_path = o.whisper_model_path || '' } catch (e) {} }
  } catch (e) {}
  try { status.value = await asrStatus() } catch (e) {}
}
async function test(engine) { testing.value = engine; result[engine] = null; try { result[engine] = await asrTest(engine) } catch (e) { result[engine] = { ok: false, message: e.message, latency_ms: 0 } } finally { testing.value = '' } }
async function save() {
  const payload = { 'asr.engine': s['asr.engine'], 'asr.strategy': s['asr.strategy'] }
  const cfg = {}
  if (ext.endpoint || ext.api_key) { cfg.external_endpoint = ext.endpoint || ''; cfg.external_api_key = ext.api_key || '' }
  if (ext.whisper_model_path) cfg.whisper_model_path = ext.whisper_model_path
  if (Object.keys(cfg).length) payload['asr.config'] = cfg
  try { await putSettings(payload); alert(i18n.global.t('common.saved')); load() } catch (e) { alert(e.message) }
}
onMounted(load)
</script>
<style scoped>
.test-result { margin-top: 10px; padding: 8px 10px; border-radius: 6px; font-size: 13px; }
.test-result.ok { background: var(--accent-soft); color: var(--success); }
.test-result.fail { background: #fef2f2; color: var(--danger); }
</style>
