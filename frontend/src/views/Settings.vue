<template>
  <div class="page settings-page">
    <PageHeader :title="$t('settings.title')" :subtitle="$t('settings.subtitle')" icon="settings">
      <template #meta>
        <StatusBadge v-if="dirty" tone="warning">{{ $t('settings.unsaved') }}</StatusBadge>
      </template>
      <template #actions>
        <button class="btn btn-primary" type="button" :disabled="saving || loading" @click="saveAll">
          <AppIcon name="check-circle" :size="16" />
          {{ saving ? $t('settings.saving') : $t('settings.save') }}
        </button>
      </template>
    </PageHeader>

    <SettingsTabs
      v-model="activeTab"
      :tabs="tabs"
      :aria-label="$t('settings.tabsLabel')"
      id-prefix="settings"
    />

    <div v-if="loading" class="settings-section" aria-busy="true">
      <div class="settings-section-body">
        <div class="skeleton-line short"></div>
        <div class="skeleton-line"></div>
        <div class="skeleton-line"></div>
      </div>
    </div>

    <template v-else>
      <section
        v-show="activeTab === 'general'"
        id="settings-panel-general"
        class="settings-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-general"
      >
        <div class="settings-section">
          <div class="settings-section-head">
            <h2>{{ $t('settings.appearanceTitle') }}</h2>
            <p>{{ $t('settings.appearanceHint') }}</p>
          </div>
          <div class="settings-section-body">
            <SettingField :label="$t('settings.uiLang')" :hint="$t('settings.uiLangHint')">
              <div class="row wrap">
                <button class="chip" :class="{ active: config.locale === 'zh' }" type="button" @click="setLocale('zh')">{{ $t('settings.zh') }}</button>
                <button class="chip" :class="{ active: config.locale === 'en' }" type="button" @click="setLocale('en')">{{ $t('settings.en') }}</button>
              </div>
            </SettingField>
            <SettingField :label="$t('settings.theme')" :hint="$t('settings.themeHint')">
              <select v-model="s['ui.theme']" class="select" @change="applyTheme">
                <option value="system">{{ $t('settings.themeSystem') }}</option>
                <option value="light">{{ $t('settings.themeLight') }}</option>
                <option value="dark">{{ $t('settings.themeDark') }}</option>
              </select>
            </SettingField>
            <SettingField :label="$t('settings.bg')" :hint="$t('settings.bgHint')">
              <div class="row wrap">
                <button v-for="item in backgrounds" :key="item.value" class="chip" :class="{ active: s['ui.background'] === item.value }" type="button" @click="setBackground(item.value)">{{ $t(item.label) }}</button>
              </div>
            </SettingField>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-head">
            <h2>{{ $t('settings.asrSummaryTitle') }}</h2>
            <p>{{ $t('settings.asrSummaryHint') }}</p>
          </div>
          <div class="settings-section-body">
            <SettingField :label="$t('settings.asrEngine')" :hint="$t('settings.strategy')">
              <div class="spread">
                <div>
                  <strong>{{ $t(`engine.${s['asr.engine'] || 'bcut'}.l`) }}</strong>
                  <div class="muted mono-sm">{{ s['asr.strategy'] || 'online_first' }}</div>
                </div>
                <router-link class="btn" to="/asr">{{ $t('settings.asrPageLink') }}</router-link>
              </div>
            </SettingField>
          </div>
        </div>
      </section>

      <section
        v-show="activeTab === 'llm'"
        id="settings-panel-llm"
        class="settings-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-llm"
      >
        <div class="inline-notice">{{ $t('settings.llmCostNotice') }}</div>
        <div class="provider-layout">
          <nav class="provider-list" :aria-label="$t('settings.providerList')">
            <button
              v-for="provider in providers"
              :key="provider.id"
              class="provider-item"
              :class="{ active: activeProvider === provider.id }"
              type="button"
              @click="activeProvider = provider.id"
            >
              <strong>{{ provider.name }}</strong>
              <small>{{ profiles[provider.id]?.model || $t('settings.notConfigured') }}</small>
              <StatusBadge :tone="providerTone(provider.id)">{{ providerStateLabel(provider.id) }}</StatusBadge>
            </button>
          </nav>

          <div v-if="currentProvider && currentProfile" class="provider-editor">
            <div class="settings-section">
              <div class="settings-section-head provider-heading">
                <div class="provider-heading-copy">
                  <h2>{{ currentProvider.name }}</h2>
                  <p>{{ currentProvider.description }}</p>
                </div>
                <div class="provider-heading-actions">
                  <StatusBadge v-if="s['llm.provider'] === activeProvider" tone="accent">{{ $t('settings.currentDefault') }}</StatusBadge>
                  <button v-else class="btn btn-sm" type="button" @click="setDefaultProvider">{{ $t('settings.setDefault') }}</button>
                  <button class="btn btn-sm" type="button" :disabled="testingProvider === activeProvider" @click="testProvider">
                    {{ testingProvider === activeProvider ? $t('settings.testing') : $t('settings.testConnection') }}
                  </button>
                </div>
              </div>
              <div class="settings-section-body">
                <SettingField v-if="activeProvider === 'custom'" :label="$t('settings.displayName')" :hint="$t('settings.displayNameHint')">
                  <input v-model.trim="currentProfile.display_name" class="input" maxlength="50" @input="markDirty">
                </SettingField>
                <SettingField :label="$t('settings.modelId')" :hint="$t('settings.modelHint')">
                  <input v-model.trim="currentProfile.model" class="input" maxlength="200" :placeholder="currentProvider.default_model" @input="markDirty">
                </SettingField>
                <SettingField :label="$t('settings.baseUrl')" :hint="$t('settings.baseUrlHint')">
                  <input v-model.trim="currentProfile.base_url" class="input" type="url" :placeholder="currentProvider.default_base_url" @input="markDirty">
                </SettingField>
                <SettingField :label="$t('settings.timeout')" :hint="$t('settings.timeoutHint')">
                  <input v-model.number="currentProfile.timeout" class="input" type="number" min="1" max="600" @input="markDirty">
                </SettingField>
                <SettingField
                  v-if="hasApiKeyField"
                  label="API Key"
                  :hint="$t('settings.apiKeyHint')"
                >
                  <PasswordField
                    :key="activeProvider"
                    v-model="keyDrafts[activeProvider]"
                    :configured="credentialState(activeProvider).configured"
                    :masked="credentialState(activeProvider).masked"
                    :revealed="Boolean(revealedKeys[activeProvider])"
                    :revealed-value="revealedKeys[activeProvider] || ''"
                    :loading="revealingProvider === activeProvider"
                    label="API Key"
                    :placeholder="$t('settings.apiKeyPlaceholder')"
                    :reveal-label="$t('settings.reveal')"
                    :hide-label="$t('settings.hide')"
                    :replace-label="$t('settings.replace')"
                    :clear-label="$t('settings.clear')"
                    :confirm-clear-label="$t('settings.confirmClear')"
                    :cancel-label="$t('common.cancel')"
                    @update:model-value="markDirty"
                    @reveal="revealKey(activeProvider)"
                    @hide="hideSecrets"
                    @clear="clearKey(activeProvider)"
                  />
                </SettingField>
              </div>
              <div v-if="connectionResults[activeProvider]" class="connection-result" :class="connectionResults[activeProvider].ok ? 'success' : 'danger'">
                {{ connectionResults[activeProvider].message }}
                <span v-if="connectionResults[activeProvider].latency_ms" class="mono-sm"> · {{ connectionResults[activeProvider].latency_ms }} ms</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        v-show="activeTab === 'note'"
        id="settings-panel-note"
        class="settings-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-note"
      >
        <div class="settings-section">
          <div class="settings-section-head">
            <h2>{{ $t('settings.detailTitle') }}</h2>
            <p>{{ $t('settings.detailHint') }}</p>
          </div>
          <div class="settings-section-body">
            <div class="detail-grid" role="radiogroup" :aria-label="$t('settings.detailTitle')">
              <button
                v-for="level in detailLevels"
                :key="level.value"
                class="detail-option"
                :class="{ active: s['note.detail_level'] === level.value }"
                type="button"
                role="radio"
                :aria-checked="s['note.detail_level'] === level.value"
                @click="setSetting('note.detail_level', level.value)"
              >
                <strong>{{ $t(level.label) }}</strong>
                <small>{{ $t(level.hint) }}</small>
              </button>
            </div>
            <SettingField :label="$t('settings.lang')" :hint="$t('settings.outputLanguageHint')">
              <div class="row wrap">
                <button v-for="language in ['zh', 'en']" :key="language" class="chip" :class="{ active: s['note.output_language'] === language }" type="button" @click="setSetting('note.output_language', language)">{{ language === 'zh' ? $t('settings.zh') : $t('settings.en') }}</button>
              </div>
            </SettingField>
            <SettingField :label="$t('settings.extractImages')" :hint="$t('settings.extractImagesHint')">
              <SettingSwitch v-model="extractImages" :label="$t('settings.extractImages')" @update:model-value="markDirty" />
            </SettingField>
            <SettingField :label="$t('settings.imageQuality')" :hint="$t('settings.imageQualityHint')">
              <select v-model="s['note.image_quality']" class="select" @change="markDirty">
                <option value="low">{{ $t('settings.qualityLow') }}</option>
                <option value="medium">{{ $t('settings.qualityMedium') }}</option>
                <option value="high">{{ $t('settings.qualityHigh') }}</option>
              </select>
            </SettingField>
            <SettingField :label="$t('settings.pdfMode')" :hint="$t('settings.pdfModeHint')">
              <select v-model="s['pdf.mode']" class="select" @change="markDirty">
                <option value="pypdf">pypdf</option>
              </select>
            </SettingField>
          </div>
        </div>
      </section>

      <section
        v-show="activeTab === 'storage'"
        id="settings-panel-storage"
        class="settings-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-storage"
      >
        <div class="settings-section">
          <div class="settings-section-head">
            <h2>{{ $t('settings.storageTitle') }}</h2>
            <p>{{ $t('settings.storageHint') }}</p>
          </div>
          <div class="settings-section-body">
            <div class="storage-metrics">
              <div class="storage-metric">
                <small>{{ $t('settings.totalUsage') }}</small>
                <strong>{{ formatBytes(storage?.total_bytes || 0) }}</strong>
              </div>
              <div v-for="kind in retentionKinds" :key="kind" class="storage-metric">
                <small>{{ $t(`settings.kind.${kind}`) }}</small>
                <strong>{{ formatBytes(storageBytes(kind)) }}</strong>
              </div>
            </div>
            <SettingField v-for="kind in retentionKinds" :key="kind" :label="$t(`settings.kind.${kind}`)" :hint="$t('settings.retentionHint')">
              <div class="row wrap">
                <button v-for="policy in retentionPolicies" :key="policy" class="chip" :class="{ active: s[`retention.${kind}`] === policy }" type="button" @click="setSetting(`retention.${kind}`, policy)">{{ $t(`settings.policy.${policy}`) }}</button>
              </div>
            </SettingField>
          </div>
        </div>
      </section>

      <section
        v-show="activeTab === 'advanced'"
        id="settings-panel-advanced"
        class="settings-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-advanced"
      >
        <div class="inline-notice">{{ $t('settings.advancedNotice') }}</div>
        <div class="settings-section">
          <div class="settings-section-head">
            <h2>{{ $t('settings.advancedTitle') }}</h2>
            <p>{{ $t('settings.advancedHint') }}</p>
          </div>
          <div class="settings-section-body">
            <SettingField :label="$t('settings.concurrency')" :hint="$t('settings.concurrencyHint')"><input v-model.number="s['concurrency.max']" class="input" type="number" min="1" max="3" @input="markDirty"></SettingField>
            <SettingField :label="$t('settings.chunkSize')" :hint="$t('settings.chunkSizeHint')"><input v-model.number="s['advanced.chunk_size']" class="input" type="number" min="1" max="1000000" @input="markDirty"></SettingField>
            <SettingField :label="$t('settings.temperature')" :hint="$t('settings.temperatureHint')"><input v-model.number="s['advanced.temperature']" class="input" type="number" min="0" max="2" step="0.1" @input="markDirty"></SettingField>
            <SettingField :label="$t('settings.maxRetries')" :hint="$t('settings.maxRetriesHint')"><input v-model.number="s['advanced.max_retries']" class="input" type="number" min="0" max="20" @input="markDirty"></SettingField>
          </div>
        </div>
      </section>

      <section
        v-show="activeTab === 'about'"
        id="settings-panel-about"
        class="settings-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-about"
      >
        <div class="settings-section">
          <div class="settings-section-head">
            <h2>vid2note</h2>
            <p>{{ $t('settings.aboutIntro') }}</p>
          </div>
          <div class="settings-section-body">
            <SettingField :label="$t('settings.version')" :hint="$t('settings.localMode')"><span class="code-value">v1.2 · Docker · localhost</span></SettingField>
            <SettingField :label="$t('settings.settingsPath')" :hint="$t('settings.settingsPathHint')"><span class="code-value" :title="storageInfo.settings_path">{{ storageInfo.settings_path }}</span></SettingField>
            <SettingField :label="$t('settings.credentialsPath')" :hint="$t('settings.credentialsPathHint')"><span class="code-value" :title="storageInfo.credentials_path">{{ storageInfo.credentials_path }}</span></SettingField>
            <SettingField :label="$t('settings.masterKey')" :hint="$t('settings.masterKeyHint')"><StatusBadge :tone="storageInfo.master_key_source === 'environment' || storageInfo.master_key_source === 'file' ? 'success' : 'warning'">{{ masterKeyLabel }}</StatusBadge></SettingField>
          </div>
          <div class="inline-notice">{{ $t('settings.securityNotice') }}</div>
        </div>
      </section>
    </template>

    <ToastStack :items="toasts" :dismiss-label="$t('settings.dismiss')" @dismiss="dismissToast" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  clearCredential,
  getSettings,
  putSettings,
  revealCredential,
  saveCredential,
  storageStats,
  testLlm,
} from '@/api'
import { i18n } from '@/i18n'
import { useConfigStore } from '@/stores/config'
import AppIcon from '@/components/AppIcon.vue'
import PageHeader from '@/components/PageHeader.vue'
import PasswordField from '@/components/settings/PasswordField.vue'
import SettingField from '@/components/settings/SettingField.vue'
import SettingsTabs from '@/components/settings/SettingsTabs.vue'
import SettingSwitch from '@/components/settings/SettingSwitch.vue'
import StatusBadge from '@/components/settings/StatusBadge.vue'
import ToastStack from '@/components/settings/ToastStack.vue'

const config = useConfigStore()
const activeTab = ref('general')
const activeProvider = ref('deepseek')
const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const testingProvider = ref('')
const revealingProvider = ref('')
const providers = ref([])
const storage = ref(null)
const s = reactive({})
const profiles = reactive({})
const credentials = reactive({})
const storageInfo = reactive({ settings_path: '', credentials_path: '', master_key_source: '' })
const keyDrafts = reactive({})
const revealedKeys = reactive({})
const connectionResults = reactive({})
const toasts = ref([])
const revealTimers = new Map()

const defaults = {
  'asr.engine': 'bcut',
  'asr.strategy': 'online_first',
  'llm.provider': 'deepseek',
  'llm.model': 'deepseek-v4-flash',
  'concurrency.max': 1,
  'pdf.mode': 'pypdf',
  'note.output_language': 'zh',
  'note.detail_level': 'balanced',
  'note.extract_images': 'false',
  'note.image_quality': 'medium',
  'ui.language': 'zh',
  'ui.theme': 'system',
  'ui.background': 'plain',
  'retention.video': '7d',
  'retention.audio': '7d',
  'retention.srt': '30d',
  'retention.note': 'permanent',
  'retention.screenshot': '30d',
  'advanced.chunk_size': 4000,
  'advanced.temperature': 0.3,
  'advanced.max_retries': 3,
}
const backgrounds = [
  { value: 'mesh', label: 'settings.bgMesh' },
  { value: 'static', label: 'settings.bgStatic' },
  { value: 'plain', label: 'settings.bgPlain' },
]
const detailLevels = [
  { value: 'concise', label: 'settings.detail.concise', hint: 'settings.detail.conciseHint' },
  { value: 'balanced', label: 'settings.detail.balanced', hint: 'settings.detail.balancedHint' },
  { value: 'detailed', label: 'settings.detail.detailed', hint: 'settings.detail.detailedHint' },
  { value: 'exhaustive', label: 'settings.detail.exhaustive', hint: 'settings.detail.exhaustiveHint' },
]
const retentionKinds = ['video', 'audio', 'srt', 'note', 'screenshot']
const retentionPolicies = ['permanent', '7d', '30d']
const tabs = computed(() => {
  // 订阅 Pinia locale，确保运行时切换语言会重算页签文案。
  const locale = config.locale
  return [
    { id: 'general', label: i18n.global.t('settings.tab.general', locale) },
    { id: 'llm', label: i18n.global.t('settings.tab.llm', locale) },
    { id: 'note', label: i18n.global.t('settings.tab.note', locale) },
    { id: 'storage', label: i18n.global.t('settings.tab.storage', locale) },
    { id: 'advanced', label: i18n.global.t('settings.tab.advanced', locale) },
    { id: 'about', label: i18n.global.t('settings.tab.about', locale) },
  ]
})
const currentProvider = computed(() => providers.value.find(item => item.id === activeProvider.value))
const currentProfile = computed(() => profiles[activeProvider.value])
const hasApiKeyField = computed(() => currentProvider.value?.credential_fields?.some(field => field.id === 'api_key'))
const extractImages = computed({
  get: () => String(s['note.extract_images']).toLowerCase() === 'true',
  set: value => { s['note.extract_images'] = value ? 'true' : 'false'; dirty.value = true },
})
const masterKeyLabel = computed(() => i18n.global.t(`settings.keySource.${storageInfo.master_key_source || 'generated'}`))

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
function setSetting(key, value) {
  s[key] = value
  markDirty()
}
function setLocale(value) {
  config.changeLocale(value)
  s['ui.language'] = value
  markDirty()
}
function setBackground(value) {
  config.setBackground(value)
  setSetting('ui.background', value)
}
function applyTheme() {
  config.setTheme(s['ui.theme'])
  markDirty()
}
function credentialState(provider) {
  return credentials[provider]?.api_key || { configured: false, masked: '', source: 'none' }
}
function providerTone(provider) {
  if (provider === 'ollama') return 'success'
  return credentialState(provider).configured ? 'success' : 'neutral'
}
function providerStateLabel(provider) {
  if (provider === 'ollama') return i18n.global.t('settings.localReady')
  return credentialState(provider).configured ? i18n.global.t('settings.configured') : i18n.global.t('settings.notConfigured')
}
function storageBytes(kind) {
  const value = storage.value?.by_kind?.[kind]
  return typeof value === 'number' ? value : (value?.bytes || 0)
}
function formatBytes(bytes) {
  const value = Number(bytes || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(2)} GB`
}
function publicProfiles() {
  return Object.fromEntries(Object.entries(profiles).filter(([provider, profile]) => (
    provider !== 'custom' || profile.model || profile.base_url
  )))
}
async function load() {
  loading.value = true
  try {
    const [response, stats] = await Promise.all([getSettings(), storageStats().catch(() => null)])
    config.adoptSettings(response)
    Object.assign(s, defaults, response.settings || {})
    Object.keys(profiles).forEach(key => delete profiles[key])
    Object.assign(profiles, response.profiles || {})
    Object.keys(credentials).forEach(key => delete credentials[key])
    Object.assign(credentials, response.credentials || {})
    providers.value = response.providers || []
    Object.assign(storageInfo, response.storage || {})
    storage.value = stats
    activeProvider.value = s['llm.provider'] || 'deepseek'
    dirty.value = false
  } catch (error) {
    Object.assign(s, defaults)
    notify(error.message || i18n.global.t('common.loadFail'), 'danger')
  } finally {
    loading.value = false
  }
}
async function persistPublicSettings() {
  const selectedProfile = profiles[s['llm.provider']]
  const payload = {
    'ui.language': s['ui.language'],
    'ui.theme': s['ui.theme'],
    'ui.background': s['ui.background'],
    'llm.provider': s['llm.provider'],
    'llm.model': selectedProfile?.model || s['llm.model'],
    'llm.providers': publicProfiles(),
    'note.output_language': s['note.output_language'],
    'note.detail_level': s['note.detail_level'],
    'note.extract_images': s['note.extract_images'],
    'note.image_quality': s['note.image_quality'],
    'pdf.mode': s['pdf.mode'],
    'retention.video': s['retention.video'],
    'retention.audio': s['retention.audio'],
    'retention.srt': s['retention.srt'],
    'retention.note': s['retention.note'],
    'retention.screenshot': s['retention.screenshot'],
    'concurrency.max': s['concurrency.max'],
    'advanced.chunk_size': s['advanced.chunk_size'],
    'advanced.temperature': s['advanced.temperature'],
    'advanced.max_retries': s['advanced.max_retries'],
  }
  return putSettings(payload)
}
async function persistDraftKeys() {
  for (const [provider, value] of Object.entries(keyDrafts)) {
    if (value?.trim()) await saveCredential(provider, 'api_key', value.trim())
  }
}
async function saveAll({ silent = false } = {}) {
  saving.value = true
  try {
    const response = await persistPublicSettings()
    config.adoptSettings(response)
    await persistDraftKeys()
    Object.keys(keyDrafts).forEach(key => { keyDrafts[key] = '' })
    if (silent) {
      dirty.value = false
    } else {
      await load()
    }
    if (!silent) notify(i18n.global.t('common.saved'))
  } catch (error) {
    notify(error.message, 'danger')
    throw error
  } finally {
    saving.value = false
  }
}
function setDefaultProvider() {
  s['llm.provider'] = activeProvider.value
  s['llm.model'] = currentProfile.value?.model || ''
  markDirty()
}
async function revealKey(provider) {
  revealingProvider.value = provider
  hideSecrets()
  try {
    const response = await revealCredential(provider, 'api_key')
    revealedKeys[provider] = response.value
    revealTimers.set(provider, setTimeout(() => hideSecrets(), 60000))
  } catch (error) {
    notify(error.message, 'danger')
  } finally {
    revealingProvider.value = ''
  }
}
function hideSecrets() {
  revealTimers.forEach(timer => clearTimeout(timer))
  revealTimers.clear()
  Object.keys(revealedKeys).forEach(key => delete revealedKeys[key])
}
async function clearKey(provider) {
  try {
    await clearCredential(provider, 'api_key')
    keyDrafts[provider] = ''
    hideSecrets()
    await load()
    notify(i18n.global.t('settings.cleared'))
  } catch (error) {
    notify(error.message, 'danger')
  }
}
async function testProvider() {
  const provider = activeProvider.value
  testingProvider.value = provider
  connectionResults[provider] = null
  try {
    await saveAll({ silent: true })
    connectionResults[provider] = await testLlm(provider)
  } catch (error) {
    connectionResults[provider] = { ok: false, message: error.message }
  } finally {
    testingProvider.value = ''
  }
}

watch(activeProvider, hideSecrets)
watch(activeTab, hideSecrets)
onMounted(load)
onBeforeUnmount(hideSecrets)
</script>
