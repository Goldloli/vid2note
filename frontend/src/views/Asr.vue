<template>
  <div class="page settings-page">
    <PageHeader :title="$t('asr.title')" :subtitle="$t('asr.subtitle')" icon="asr">
      <template #meta>
        <StatusBadge v-if="dirty" tone="warning">{{ $t('settings.unsaved') }}</StatusBadge>
      </template>
      <template #actions>
        <button class="btn btn-primary" type="button" :disabled="saving || loading" @click="save">
          <AppIcon name="check-circle" :size="16" />
          {{ saving ? $t('settings.saving') : $t('asr.save') }}
        </button>
      </template>
    </PageHeader>

    <SettingsTabs
      v-model="activeTab"
      :tabs="tabs"
      :aria-label="$t('asr.tabsLabel')"
      id-prefix="asr"
    />

    <div v-if="loading" class="settings-section" aria-busy="true">
      <div class="settings-section-body"><div class="skeleton-line short"></div><div class="skeleton-line"></div></div>
    </div>

    <template v-else>
      <section v-show="activeTab === 'engines'" id="asr-panel-engines" class="settings-panel" role="tabpanel" aria-labelledby="asr-tab-engines">
        <div class="settings-section">
          <div class="settings-section-head">
            <h2>{{ $t('asr.engineTitle') }}</h2>
            <p>{{ $t('asr.engineHint') }}</p>
          </div>
          <div class="settings-section-body">
            <div class="engine-grid">
              <article v-for="engine in engines" :key="engine.value" class="engine-option" :class="{ active: s['asr.engine'] === engine.value }">
                <h3>{{ $t(engine.label) }}</h3>
                <p>{{ $t(engine.hint) }}</p>
                <StatusBadge v-if="engine.value !== 'bcut'" :tone="engineTone(engine.value)">{{ engineState(engine.value) }}</StatusBadge>
                <div class="engine-option-actions">
                  <button class="btn btn-sm" type="button" :disabled="testing === engine.value" @click="test(engine.value)">{{ testing === engine.value ? $t('asr.testing') : $t('asr.test') }}</button>
                  <button class="btn btn-sm" :class="{ 'btn-primary': s['asr.engine'] === engine.value }" type="button" @click="setEngine(engine.value)">{{ s['asr.engine'] === engine.value ? $t('asr.current') : $t('asr.setDefault') }}</button>
                </div>
                <div v-if="results[engine.value]" class="connection-result" :class="results[engine.value].ok ? 'success' : 'danger'">{{ results[engine.value].message }}</div>
              </article>
            </div>
          </div>
        </div>
        <div class="settings-section">
          <div class="settings-section-head"><h2>{{ $t('asr.diagnostics') }}</h2><p>{{ $t('asr.diagnosticsHint') }}</p></div>
          <div class="settings-section-body">
            <div class="diagnostic-list">
              <div class="diagnostic-item"><small>{{ $t('asr.currentEngine') }}</small><strong>{{ s['asr.engine'] }}</strong></div>
              <div class="diagnostic-item"><small>{{ $t('asr.currentStrategy') }}</small><strong>{{ s['asr.strategy'] }}</strong></div>
              <div class="diagnostic-item"><small>{{ $t('asr.whisperModel') }}</small><strong>{{ status?.whisper_cpp?.model_path || $t('asr.notConfigured') }}</strong></div>
              <div class="diagnostic-item"><small>{{ $t('asr.externalHost') }}</small><strong>{{ status?.external?.endpoint_host || $t('asr.notConfigured') }}</strong></div>
            </div>
          </div>
        </div>
      </section>

      <section v-show="activeTab === 'whisper'" id="asr-panel-whisper" class="settings-panel" role="tabpanel" aria-labelledby="asr-tab-whisper">
        <div class="settings-section">
          <div class="settings-section-head"><h2>{{ $t('asr.whisperTitle') }}</h2><p>{{ $t('asr.whisperHint') }}</p></div>
          <div class="settings-section-body">
            <SettingField :label="$t('asr.modelPath')" :hint="$t('asr.modelPathHint')"><input v-model.trim="cfg.whisper_model_path" class="input" placeholder="/app/data/models/ggml-small.bin" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.binaryPath')" :hint="$t('asr.binaryPathHint')"><input v-model.trim="cfg.whisper_binary" class="input" placeholder="/usr/local/bin/whisper-cli" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.language')" :hint="$t('asr.languageHint')"><input v-model.trim="cfg.whisper_language" class="input" maxlength="12" placeholder="zh" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.runtimeMode')" :hint="$t('asr.runtimeModeHint')"><span class="code-value">CPU · int8</span></SettingField>
          </div>
        </div>
        <div class="settings-section">
          <div class="settings-section-head"><h2>{{ $t('asr.whisperStatus') }}</h2></div>
          <div class="settings-section-body">
            <div class="diagnostic-list">
              <div class="diagnostic-item"><small>{{ $t('asr.modelPath') }}</small><strong>{{ status?.whisper_cpp?.model_exists ? $t('asr.ready') : $t('asr.missing') }}</strong></div>
              <div class="diagnostic-item"><small>{{ $t('asr.binaryPath') }}</small><strong>{{ status?.whisper_cpp?.binary_exists ? $t('asr.ready') : $t('asr.missing') }}</strong></div>
            </div>
          </div>
        </div>
      </section>

      <section v-show="activeTab === 'external'" id="asr-panel-external" class="settings-panel" role="tabpanel" aria-labelledby="asr-tab-external">
        <div class="settings-section">
          <div class="settings-section-head"><h2>{{ $t('asr.externalTitle') }}</h2><p>{{ $t('asr.externalHint') }}</p></div>
          <div class="settings-section-body">
            <SettingField :label="$t('asr.endpoint')" :hint="$t('asr.endpointHint')"><input v-model.trim="cfg.external_endpoint" class="input" type="url" placeholder="https://asr.example.com/v1/transcribe" @input="markDirty"></SettingField>
            <SettingField label="API Key" :hint="$t('asr.apiKeyHint')">
              <PasswordField
                v-model="apiKeyDraft"
                :configured="externalCredential.configured"
                :masked="externalCredential.masked"
                :revealed="Boolean(revealedKey)"
                :revealed-value="revealedKey"
                :loading="revealing"
                label="External ASR API Key"
                :placeholder="$t('asr.apiKeyPh')"
                :reveal-label="$t('settings.reveal')"
                :hide-label="$t('settings.hide')"
                :replace-label="$t('settings.replace')"
                :clear-label="$t('settings.clear')"
                :confirm-clear-label="$t('settings.confirmClear')"
                :cancel-label="$t('common.cancel')"
                @update:model-value="markDirty"
                @reveal="revealKey"
                @hide="hideKey"
                @clear="clearKey"
              />
            </SettingField>
            <SettingField :label="$t('asr.timeout')" :hint="$t('asr.timeoutHint')"><input v-model.number="cfg.external_timeout" class="input" type="number" min="1" max="600" @input="markDirty"></SettingField>
          </div>
          <div class="inline-notice">{{ $t('asr.externalSecurity') }}</div>
        </div>
      </section>

      <section v-show="activeTab === 'strategy'" id="asr-panel-strategy" class="settings-panel" role="tabpanel" aria-labelledby="asr-tab-strategy">
        <div class="settings-section">
          <div class="settings-section-head"><h2>{{ $t('asr.strategy') }}</h2><p>{{ $t('asr.strategyHint') }}</p></div>
          <div class="settings-section-body">
            <SettingField :label="$t('asr.strategyMode')" :hint="$t('asr.strategyModeHint')">
              <div class="row wrap">
                <button v-for="strategy in strategies" :key="strategy.value" class="chip" :class="{ active: s['asr.strategy'] === strategy.value }" type="button" @click="setStrategy(strategy.value)">{{ $t(strategy.label) }}</button>
              </div>
            </SettingField>
            <SettingField :label="$t('asr.bcutTimeout')" :hint="$t('asr.bcutTimeoutHint')"><input v-model.number="cfg.bcut_timeout" class="input" type="number" min="1" max="600" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.vadThreshold')" :hint="$t('asr.vadThresholdHint')"><input v-model.number="cfg.vad_threshold_seconds" class="input" type="number" min="30" max="7200" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.onlineSegmentLength')" :hint="$t('asr.onlineSegmentLengthHint')"><input v-model.number="cfg.online_target_segment_seconds" class="input" type="number" min="10" max="295" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.onlineConcurrency')" :hint="$t('asr.onlineConcurrencyHint')"><input v-model.number="cfg.online_concurrency" class="input" type="number" min="1" max="3" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.onlineFormat')" :hint="$t('asr.onlineFormatHint')">
              <select v-model="cfg.online_audio_format" class="input" @change="markDirty"><option value="mp3">MP3</option><option value="wav">WAV</option></select>
            </SettingField>
            <SettingField :label="$t('asr.onlineBitrate')" :hint="$t('asr.onlineBitrateHint')"><input v-model.number="cfg.online_audio_bitrate_kbps" class="input" type="number" min="32" max="128" step="16" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.localSegmentLength')" :hint="$t('asr.localSegmentLengthHint')"><input v-model.number="cfg.local_target_segment_seconds" class="input" type="number" min="10" max="1800" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.localConcurrency')" :hint="$t('asr.localConcurrencyHint')"><input v-model.number="cfg.local_concurrency" class="input" type="number" min="1" max="3" @input="markDirty"></SettingField>
            <SettingField :label="$t('asr.cacheEnabled')" :hint="$t('asr.cacheEnabledHint')"><input v-model="cfg.cache_enabled" type="checkbox" @change="markDirty"></SettingField>
            <SettingField :label="$t('asr.requestTimeout')" :hint="$t('asr.requestTimeoutHint')"><input v-model.number="cfg.request_timeout" class="input" type="number" min="1" max="3600" @input="markDirty"></SettingField>
          </div>
        </div>
      </section>
    </template>

    <ToastStack :items="toasts" :dismiss-label="$t('settings.dismiss')" @dismiss="dismissToast" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  asrStatus,
  asrTest,
  clearCredential,
  getSettings,
  putSettings,
  revealCredential,
  saveCredential,
} from '@/api'
import { i18n } from '@/i18n'
import { useConfigStore } from '@/stores/config'
import AppIcon from '@/components/AppIcon.vue'
import PageHeader from '@/components/PageHeader.vue'
import PasswordField from '@/components/settings/PasswordField.vue'
import SettingField from '@/components/settings/SettingField.vue'
import SettingsTabs from '@/components/settings/SettingsTabs.vue'
import StatusBadge from '@/components/settings/StatusBadge.vue'
import ToastStack from '@/components/settings/ToastStack.vue'

const config = useConfigStore()
const activeTab = ref('engines')
const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const testing = ref('')
const revealing = ref(false)
const revealedKey = ref('')
const apiKeyDraft = ref('')
const status = ref(null)
const externalCredential = reactive({ configured: false, masked: '', source: 'none' })
const results = reactive({})
const toasts = ref([])
const s = reactive({ 'asr.engine': 'bcut', 'asr.strategy': 'online_first' })
const asrConfigDefaults = {
  bcut_timeout: 120,
  whisper_model_path: '',
  whisper_binary: '',
  whisper_device: 'cpu',
  whisper_compute_type: 'int8',
  whisper_language: 'zh',
  external_endpoint: '',
  external_timeout: 120,
  vad_threshold_seconds: 300,
  online_target_segment_seconds: 280,
  local_target_segment_seconds: 120,
  online_concurrency: 3,
  local_concurrency: 1,
  online_audio_format: 'mp3',
  online_audio_bitrate_kbps: 64,
  cache_enabled: true,
  request_timeout: 120,
}
const asrConfigKeys = Object.keys(asrConfigDefaults)
const cfg = reactive({ ...asrConfigDefaults })
let revealTimer

const engines = [
  { value: 'bcut', label: 'engine.bcut.l', hint: 'engine.bcut.desc' },
  { value: 'whisper_cpp', label: 'engine.whisper_cpp.l', hint: 'engine.whisper_cpp.desc' },
  { value: 'external', label: 'engine.external.l', hint: 'engine.external.desc' },
]
const strategies = [
  { value: 'online_first', label: 'engine.online_first.l' },
  { value: 'single', label: 'engine.single.l' },
]
const tabs = computed(() => [
  { id: 'engines', label: i18n.global.t('asr.tab.engines') },
  { id: 'whisper', label: i18n.global.t('asr.tab.whisper') },
  { id: 'external', label: i18n.global.t('asr.tab.external') },
  { id: 'strategy', label: i18n.global.t('asr.tab.strategy') },
])
function notify(message, tone = 'success') {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, message, tone })
  setTimeout(() => dismissToast(id), 4500)
}
function dismissToast(id) {
  toasts.value = toasts.value.filter(item => item.id !== id)
}
function markDirty() {
  dirty.value = true
}
function setEngine(value) {
  s['asr.engine'] = value
  markDirty()
}
function setStrategy(value) {
  s['asr.strategy'] = value
  markDirty()
}
function engineTone(engine) {
  if (engine === 'whisper_cpp') return status.value?.whisper_cpp?.available ? 'success' : 'warning'
  return status.value?.external?.available ? 'success' : 'warning'
}
function engineState(engine) {
  if (engine === 'whisper_cpp') return status.value?.whisper_cpp?.available ? i18n.global.t('asr.ready') : i18n.global.t('asr.modelNotReady')
  return status.value?.external?.available ? i18n.global.t('asr.endpointReady') : i18n.global.t('asr.endpointMissing')
}
async function load() {
  loading.value = true
  try {
    const [settingsResponse, statusResponse] = await Promise.all([getSettings(), asrStatus()])
    config.adoptSettings(settingsResponse)
    const settings = settingsResponse.settings || {}
    s['asr.engine'] = settings['asr.engine'] || 'bcut'
    s['asr.strategy'] = settings['asr.strategy'] || 'online_first'
    const incomingConfig = { ...(settings['asr.config'] || {}) }
    if (!incomingConfig.whisper_model_path && incomingConfig.model_path) {
      incomingConfig.whisper_model_path = incomingConfig.model_path
    }
    if (incomingConfig.online_concurrency === undefined && incomingConfig.concurrency !== undefined) {
      incomingConfig.online_concurrency = incomingConfig.concurrency
    }
    if (incomingConfig.vad_target_segment_seconds !== undefined) {
      if (incomingConfig.online_target_segment_seconds === undefined) incomingConfig.online_target_segment_seconds = incomingConfig.vad_target_segment_seconds
      if (incomingConfig.local_target_segment_seconds === undefined) incomingConfig.local_target_segment_seconds = incomingConfig.vad_target_segment_seconds
    }
    Object.assign(
      cfg,
      asrConfigDefaults,
      Object.fromEntries(
        asrConfigKeys
          .filter(key => incomingConfig[key] !== undefined)
          .map(key => [key, incomingConfig[key]])
      ),
    )
    Object.assign(externalCredential, settingsResponse.sensitive?.external_asr?.api_key || {})
    status.value = statusResponse
    dirty.value = false
  } catch (error) {
    notify(error.message || i18n.global.t('common.loadFail'), 'danger')
  } finally {
    loading.value = false
  }
}
async function save() {
  saving.value = true
  try {
    const response = await putSettings({
      'asr.engine': s['asr.engine'],
      'asr.strategy': s['asr.strategy'],
      'asr.config': Object.fromEntries(asrConfigKeys.map(key => [key, cfg[key]])),
    })
    config.adoptSettings(response)
    if (apiKeyDraft.value.trim()) {
      await saveCredential('external_asr', 'api_key', apiKeyDraft.value.trim())
      apiKeyDraft.value = ''
    }
    await load()
    notify(i18n.global.t('common.saved'))
  } catch (error) {
    notify(error.message, 'danger')
  } finally {
    saving.value = false
  }
}
async function test(engine) {
  testing.value = engine
  try {
    if (dirty.value) await save()
    results[engine] = await asrTest(engine)
  } catch (error) {
    results[engine] = { ok: false, message: error.message, latency_ms: 0 }
  } finally {
    testing.value = ''
  }
}
async function revealKey() {
  hideKey()
  revealing.value = true
  try {
    const response = await revealCredential('external_asr', 'api_key')
    revealedKey.value = response.value
    revealTimer = setTimeout(hideKey, 60000)
  } catch (error) {
    notify(error.message, 'danger')
  } finally {
    revealing.value = false
  }
}
function hideKey() {
  clearTimeout(revealTimer)
  revealedKey.value = ''
}
async function clearKey() {
  try {
    await clearCredential('external_asr', 'api_key')
    apiKeyDraft.value = ''
    hideKey()
    await load()
    notify(i18n.global.t('settings.cleared'))
  } catch (error) {
    notify(error.message, 'danger')
  }
}

watch(activeTab, hideKey)
onMounted(load)
onBeforeUnmount(hideKey)
</script>
