<template>
  <div class="page">
    <div class="set-tabs">
      <button class="tab" :class="{active: tab === 'asr'}" @click="tab = 'asr'">ASR 语音识别</button>
      <button class="tab" :class="{active: tab === 'llm'}" @click="tab = 'llm'">LLM 大模型</button>
      <button class="tab" :class="{active: tab === 'proc'}" @click="tab = 'proc'">处理选项</button>
      <button class="tab" :class="{active: tab === 'keep'}" @click="tab = 'keep'">保留策略</button>
      <button class="tab" :class="{active: tab === 'adv'}" @click="tab = 'adv'">高级</button>
      <button class="tab" :class="{active: tab === 'about'}" @click="tab = 'about'">关于</button>
    </div>
    <div class="set-grid">
      <div>
        <!-- ASR -->
        <div v-show="tab === 'asr'" class="card card-pad reveal">
          <div class="section-title"><h2>语音识别引擎 (ASR)</h2><span class="tag">默认 asrtools-b</span></div>
          <div class="opt-grid">
            <div v-for="p in asrProviders" :key="p.name" class="opt-card" :class="{sel: form.asr_provider === p.name}" @click="selectAsr(p.name)">
              <span class="opt-radio"></span>
              <div><div class="o-name">{{ p.name }}</div><div class="o-meta">{{ p.meta }}</div></div>
            </div>
          </div>
          <div class="divider-h"></div>
          <div class="form-row">
            <div><div class="fr-label">ASR 密钥</div><div class="fr-desc">当前 ASR（asrtools-b）为免费云端接口（B站必剪/剪映/快手），无需 API 密钥。</div></div>
            <div class="fr-control">
              <span class="mono-sm muted">— 免接口密钥 —</span>
            </div>
          </div>
        </div>

        <!-- LLM -->
        <div v-show="tab === 'llm'" class="card card-pad reveal">
          <div class="section-title"><h2>大语言模型 (LLM)</h2><span class="muted mono-sm">{{ llmProviders.length }} 个提供商 · 当前 {{ form.llm_provider }}</span></div>
          <div class="col" style="gap:10px">
            <div v-for="p in llmProviders" :key="p" class="prov-card" :class="{selected: form.llm_provider === p}" @click="selectLlm(p)">
              <div class="prov-head"><span class="prov-radio"></span><span class="prov-name">{{ p }}</span><span class="prov-model">{{ defaultModel(p) }}</span></div>
              <div v-if="form.llm_provider === p" class="prov-body" style="display:block">
                <div class="grid grid-2" style="padding-top:14px">
                  <div class="field"><span class="label">API Key</span><input class="input" type="password" v-model="form.llm_keys[p]" placeholder="sk-…"></div>
                  <div class="field"><span class="label">模型</span><input class="input" :value="defaultModel(p)" disabled></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 处理选项 -->
        <div v-show="tab === 'proc'" class="card card-pad reveal">
          <div class="section-title"><h2>处理选项</h2></div>
          <div class="toggle-row"><div><div class="t-label">提取视频关键帧图片</div><div class="t-desc">在笔记中嵌入视频关键帧。</div></div><label class="switch"><input type="checkbox" v-model="form.extract_images"><span class="track"></span><span class="thumb"></span></label></div>
          <div class="form-row"><div><div class="fr-label">输出语言</div><div class="fr-desc">整理笔记使用的语言。</div></div><div class="seg"><button :class="{active: form.language === 'zh'}" @click="form.language = 'zh'">中文</button><button :class="{active: form.language === 'en'}" @click="form.language = 'en'">English</button></div></div>
        </div>

        <!-- 保留策略 -->
        <div v-show="tab === 'keep'" class="card card-pad reveal">
          <div class="section-title"><h2>文件保留策略</h2><span class="muted mono-sm">cleanup 节点依据</span></div>
          <div class="toggle-row"><div><div class="t-label">保留原始视频</div><div class="t-desc">保留 video.mp4（占用空间较大）。</div></div><label class="switch"><input type="checkbox" v-model="form.keep_video"><span class="track"></span><span class="thumb"></span></label></div>
          <div class="toggle-row"><div><div class="t-label">保留音频</div><div class="t-desc">保留 audio.wav。</div></div><label class="switch"><input type="checkbox" v-model="form.keep_audio"><span class="track"></span><span class="thumb"></span></label></div>
          <div class="toggle-row"><div><div class="t-label">保留字幕 SRT</div><div class="t-desc">保留 transcript.srt。</div></div><label class="switch"><input type="checkbox" v-model="form.keep_srt"><span class="track"></span><span class="thumb"></span></label></div>
        </div>

        <!-- 高级 -->
        <div v-show="tab === 'adv'" class="card card-pad reveal">
          <div class="section-title"><h2>高级参数</h2></div>
          <div class="form-row"><div><div class="fr-label">分块大小 (chunk_size)</div><div class="fr-desc">送入 LLM 的单块最大 token 数。</div></div><div class="fr-control" style="max-width:280px"><div class="row gap-s"><input class="range" type="range" min="1000" max="8000" step="500" v-model.number="form.chunk_size"><span class="mono" style="min-width:64px">{{ form.chunk_size }}</span></div></div></div>
          <div class="form-row"><div><div class="fr-label">温度 (temperature)</div><div class="fr-desc">生成随机性。建议 0.2–0.4。</div></div><div class="fr-control" style="max-width:280px"><div class="row gap-s"><input class="range" type="range" min="0" max="1" step="0.1" v-model.number="form.temperature"><span class="mono" style="min-width:48px">{{ form.temperature }}</span></div></div></div>
        </div>

        <!-- 关于 -->
        <div v-show="tab === 'about'" class="card card-pad reveal">
          <div class="section-title"><h2>关于 vid2note</h2></div>
          <div class="form-row"><div class="fr-label">版本</div><div class="mono">v0.1.0</div></div>
          <div class="form-row"><div class="fr-label">运行模式</div><div class="mono">electron · macOS arm64</div></div>
          <div class="form-row"><div class="fr-label">服务地址</div><div class="mono">http://localhost:8765</div></div>
          <div class="form-row" style="border:0"><div class="fr-label">开源协议</div><div class="mono">MIT</div></div>
        </div>
      </div>

      <aside class="set-side">
        <div class="card card-pad reveal">
          <div class="kicker" style="margin-bottom:10px">当前配置</div>
          <dl class="kv">
            <dt>ASR</dt><dd>{{ form.asr_provider }}</dd>
            <dt>LLM</dt><dd>{{ form.llm_provider }}</dd>
            <dt>语言</dt><dd>{{ form.language === 'zh' ? '中文' : 'English' }}</dd>
            <dt>分块</dt><dd>{{ form.chunk_size }}</dd>
            <dt>温度</dt><dd>{{ form.temperature }}</dd>
            <dt>保留</dt><dd>{{ form.keep_srt ? 'SRT' : '无' }}</dd>
          </dl>
          <div class="divider-h"></div>
          <div class="kicker" style="margin-bottom:8px">安全提示</div>
          <p class="muted" style="font-size:12px; line-height:1.6">所有 API Key 通过系统钥匙串加密存储，绝不写入明文配置或日志。</p>
          <div style="margin-top:14px"><button class="btn btn-primary btn-sm" @click="save">保存配置</button></div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getConfig, updateConfig, verifyApiKey } from '../api/config'
import { listModels } from '../api/models'

const tab = ref('asr')
const asrProviders = [
  { name: 'asrtools-b', meta: '云端 · 高精度 · 中文最佳' },
  { name: 'funasr', meta: '本地 · paraformer-small' },
]
const llmProviders = ref([])
const verifyMsg = ref('')
const verifyOk = ref(false)

const form = reactive({
  asr_provider: 'asrtools-b',
  llm_provider: 'qwen',
  api_key: '',
  llm_keys: {},
  language: 'zh',
  extract_images: true,
  keep_video: false,
  keep_audio: false,
  keep_srt: true,
  chunk_size: 4000,
  temperature: 0.3,
})

const defaultModel = (p) => ({ qwen: 'qwen-turbo', deepseek: 'deepseek-chat', glm: 'glm-4-flash', moonshot: 'moonshot-v1-8k', ollama: 'llama3', mock: 'mock' }[p] || p)
const selectAsr = (name) => { form.asr_provider = name; saveField('asr_provider', name) }
const selectLlm = (name) => { form.llm_provider = name; saveField('llm_provider', name) }

async function saveField(field, value) {
  try { await updateConfig({ [field]: value }) } catch (e) {}
}
async function save() {
  try {
    await updateConfig({
      llm_provider: form.llm_provider,
      asr_provider: form.asr_provider,
      keep_video: form.keep_video,
      keep_audio: form.keep_audio,
      keep_srt: form.keep_srt,
    })
  } catch (e) {}
}
async function verifyKey() {
  verifyMsg.value = '验证中…'
  try {
    const res = await verifyApiKey(form.llm_provider, form.api_key)
    verifyOk.value = res.valid
    verifyMsg.value = res.valid ? '✓ 验证通过' : `✗ ${res.error || '验证失败'}`
  } catch (e) {
    verifyOk.value = false
    verifyMsg.value = `✗ ${e.message}`
  }
}

onMounted(async () => {
  try {
    const cfg = await getConfig()
    Object.assign(form, cfg)
  } catch (e) {}
  try {
    const data = await listModels()
    llmProviders.value = data.llm_providers || []
  } catch (e) {}
})
</script>

<style scoped>
.set-tabs { display:flex; gap:2px; border-bottom:1px solid var(--border); margin-bottom:24px; }
.set-grid { display:grid; grid-template-columns: 1fr 290px; gap:24px; align-items:start; }
.set-side { position:sticky; top:18px; }
.form-row { display:grid; grid-template-columns: 220px 1fr; gap:18px 24px; align-items:start; padding:16px 0; border-bottom:1px solid var(--border); }
.form-row:last-child { border:0; }
.form-row .fr-label { font-size:13px; font-weight:600; color:var(--fg-strong); }
.form-row .fr-desc { font-size:12px; color:var(--muted); margin-top:4px; line-height:1.5; }
.fr-control { display:flex; flex-direction:column; gap:10px; }
.opt-card { border:1px solid var(--border-strong); border-radius:var(--radius-sm); padding:12px 14px; cursor:pointer; transition: all var(--t-fast) var(--ease); display:flex; align-items:center; gap:12px; }
.opt-card:hover { border-color:var(--muted-2); }
.opt-card.sel { border-color:var(--accent); background:var(--accent-soft); }
.opt-radio { width:18px; height:18px; border-radius:50%; border:2px solid var(--border-strong); flex-shrink:0; display:grid; place-items:center; transition:all var(--t-fast) var(--ease); }
.opt-card.sel .opt-radio { border-color:var(--accent); }
.opt-card.sel .opt-radio::after { content:""; width:9px; height:9px; border-radius:50%; background:var(--accent); }
.opt-card .o-name { font-weight:600; font-size:13px; }
.opt-card .o-meta { font-size:11.5px; color:var(--muted); }
.opt-grid { display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; }
.prov-card { border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; transition: all var(--t) var(--ease); }
.prov-card.selected { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }
.prov-head { display:flex; align-items:center; gap:12px; padding:13px 15px; cursor:pointer; }
.prov-radio { width:18px; height:18px; border-radius:50%; border:2px solid var(--border-strong); flex-shrink:0; display:grid; place-items:center; transition:all var(--t-fast) var(--ease); }
.prov-card.selected .prov-radio { border-color:var(--accent); }
.prov-card.selected .prov-radio::after { content:""; width:9px; height:9px; border-radius:50%; background:var(--accent); }
.prov-name { font-weight:600; font-size:13px; }
.prov-model { font-family:var(--font-mono); font-size:11.5px; color:var(--muted); margin-left:auto; }
.prov-body { padding:4px 15px 15px; border-top:1px solid var(--border); }
.toggle-row { display:flex; align-items:center; justify-content:space-between; padding:13px 0; border-bottom:1px solid var(--border); }
.toggle-row:last-child { border:0; }
.toggle-row .t-label { font-size:13px; font-weight:500; }
.toggle-row .t-desc { font-size:12px; color:var(--muted); margin-top:2px; }
.kv { display:grid; grid-template-columns: 70px 1fr; gap:6px 12px; font-size:12.5px; }
.kv dt { color:var(--muted-2); }
.kv dd { color:var(--fg); font-family:var(--font-mono); }
</style>
