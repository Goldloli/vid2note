<template>
  <div class="page">
    <div class="spread"><strong>{{ $t('settings.title') }}</strong><button class="btn btn-primary btn-sm" @click="save">{{ $t('settings.save') }}</button></div>
    <div class="card">
      <div class="kicker" style="margin-bottom:10px">{{ $t('settings.uiLang') }}</div>
      <div class="row wrap">
        <button class="chip" :class="{active: config.locale==='zh'}" @click="config.changeLocale('zh')">{{ $t('settings.zh') }}</button>
        <button class="chip" :class="{active: config.locale==='en'}" @click="config.changeLocale('en')">{{ $t('settings.en') }}</button>
      </div>
    </div>
    <div class="card">
      <div class="spread">
        <div class="kicker" style="margin-bottom:0">{{ $t('settings.asrEngine') }}</div>
        <router-link class="btn btn-ghost btn-sm" to="/asr">{{ $t('settings.asrPageLink') }}</router-link>
      </div>
      <div class="row wrap" style="margin-top:10px">
        <button v-for="e in asrEngines" :key="e.v" class="chip" :class="{active:s['asr.engine']===e.v}" @click="s['asr.engine']=e.v">{{ $t(e.l) }}</button>
      </div>
      <div class="kicker" style="margin-top:12px">{{ $t('settings.strategy') }}</div>
      <div class="row wrap" style="margin-top:8px">
        <button v-for="st in ASR_STRATEGIES" :key="st.v" class="chip btn-sm" :class="{active:(s['asr.strategy']||'online_first')===st.v}" @click="s['asr.strategy']=st.v">{{ $t(st.l) }}</button>
      </div>
    </div>
    <div class="card">
      <div class="kicker" style="margin-bottom:10px">{{ $t('settings.llm') }}</div>
      <div class="row wrap">
        <select class="select" style="width:auto" v-model="s['llm.provider']"><option v-for="p in providers" :key="p" :value="p">{{ p }}</option></select>
        <input class="input" style="flex:1" v-model="s['llm.model']" :placeholder="$t('settings.modelPh')">
      </div>
      <div class="row" style="margin-top:10px"><input class="input" style="flex:1" v-model="apiKey" :placeholder="`${s['llm.provider']||'llm'} API Key`"></div>
    </div>
    <div class="card">
      <div class="kicker" style="margin-bottom:10px">{{ $t('settings.options') }}</div>
      <div class="row wrap">
        <span class="kicker">{{ $t('settings.concurrency') }}</span><input class="input" style="width:70px" type="number" min="1" max="3" v-model.number="s['concurrency.max']">
        <span class="kicker">{{ $t('settings.pdf') }}</span><button v-for="m in ['pypdf','mineru']" :key="m" class="chip" :class="{active:s['pdf.mode']===m}" @click="s['pdf.mode']=m">{{ m === 'pypdf' ? $t('settings.pdfSimple') : $t('settings.pdfComplex') }}</button>
        <span class="kicker">{{ $t('settings.lang') }}</span><button v-for="l in ['zh','en']" :key="l" class="chip" :class="{active:s['note.output_language']===l}" @click="s['note.output_language']=l">{{ l==='zh'?$t('settings.zh'):$t('settings.en') }}</button>
      </div>
    </div>
    <div class="card">
      <div class="kicker" style="margin-bottom:10px">{{ $t('settings.bg') }}</div>
      <div class="row wrap">
        <button v-for="b in backgrounds" :key="b.v" class="chip" :class="{active:(s['ui.background']||'mesh')===b.v}" @click="s['ui.background']=b.v">{{ $t(b.k) }}</button>
      </div>
    </div>
    <div class="card">
      <div class="kicker" style="margin-bottom:10px">{{ $t('settings.retention') }}</div>
      <div v-for="k in kinds" :key="k" class="row wrap" style="margin-bottom:8px">
        <span style="width:90px">{{ k }}</span>
        <button v-for="r in ['permanent','7d','30d']" :key="r" class="chip btn-sm" :class="{active:cur(k)===r}" @click="set(k,r)">{{ r }}</button>
      </div>
    </div>
  </div>
</template>
<script setup>
import { reactive, ref, onMounted } from 'vue'
import { getSettings, putSettings } from '@/api'
import { useConfigStore } from '@/stores/config'
import { ASR_ENGINES, ASR_STRATEGIES } from '@/asr'
import { i18n } from '@/i18n'
const config = useConfigStore()
const providers = ['deepseek','qwen','glm','moonshot','minimax','doubao','baidu','ollama']
const asrEngines = ASR_ENGINES
const backgrounds = [{v:'mesh',k:'settings.bgMesh'},{v:'static',k:'settings.bgStatic'},{v:'plain',k:'settings.bgPlain'}]
const kinds = ['video','audio','srt','note','screenshot']
const s = reactive({}); const apiKey = ref('')
const def = { 'asr.engine':'asrtools', 'asr.strategy':'online_first', 'llm.provider':'deepseek', 'llm.model':'deepseek-v4-flash', 'concurrency.max':1, 'pdf.mode':'pypdf', 'note.output_language':'zh', 'ui.background':'mesh', 'retention.video':'7d','retention.audio':'7d','retention.srt':'30d','retention.note':'permanent','retention.screenshot':'30d' }
const cur = k => s[`retention.${k}`] || def[`retention.${k}`]
const set = (k,r) => s[`retention.${k}`] = r
async function load() { try { const r = await getSettings(); Object.assign(s, def, r.settings || {}) } catch(e){ Object.assign(s, def) } }
async function save() {
  const payload = { ...s }
  if (apiKey.value) payload['llm.credentials'] = { [s['llm.provider'] || 'deepseek']: { api_key: apiKey.value } }
  try { await putSettings(payload); alert(i18n.global.t('common.saved')) } catch(e){ alert(e.message) }
}
onMounted(load)
</script>
