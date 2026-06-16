<template>
  <div class="settings">
    <el-page-header @back="$router.push('/')" content="设置" />

    <!-- LLM 配置 -->
    <el-card class="section">
      <template #header><span>LLM 大模型</span></template>
      <el-form label-width="160px" :model="form">
        <el-form-item label="LLM 提供商">
          <el-select v-model="form.llm_provider" @change="saveField('llm_provider', form.llm_provider)">
            <el-option v-for="p in providers.llm" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" placeholder="sk-..." show-password>
            <template #append>
              <el-button :loading="verifying" @click="verifyKey">验证</el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="Ollama 状态">
          <el-tag :type="ollama.running ? 'success' : 'info'">
            {{ ollama.running ? '运行中' : '未运行' }}
          </el-tag>
          <el-button size="small" link @click="checkOllama">刷新</el-button>
          <div v-if="ollama.models?.length" class="ollama-models">
            本地模型：{{ ollama.models.join(', ') }}
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ASR 配置 -->
    <el-card class="section">
      <template #header><span>ASR 语音识别</span></template>
      <el-form label-width="160px" :model="form">
        <el-form-item label="ASR 提供商">
          <el-select v-model="form.asr_provider" @change="saveField('asr_provider', form.asr_provider)">
            <el-option v-for="p in providers.asr" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="本地模型管理">
          <div class="model-mgmt">
            <div class="model-row" v-for="m in asrAvailable" :key="m.name">
              <span class="model-name">{{ m.name }} ({{ m.size }})</span>
              <el-tag size="small" :type="isInstalled(m.name) ? 'success' : 'info'">
                {{ isInstalled(m.name) ? '已下载' : '未下载' }}
              </el-tag>
              <el-button
                v-if="!isInstalled(m.name)"
                size="small"
                type="primary"
                plain
                :loading="downloading === m.name"
                @click="downloadModel(m.name)"
              >下载</el-button>
            </div>
            <el-empty v-if="!asrAvailable.length" description="暂无可用模型" />
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Cookie 管理 -->
    <el-card class="section">
      <template #header><span>Cookie 管理（用于会员视频下载）</span></template>
      <el-form label-width="160px">
        <el-form-item label="Bilibili Cookie">
          <el-input v-model="form.bilibili_cookie" type="textarea" :rows="3" placeholder="SESSDATA=...; bili_jct=..." />
        </el-form-item>
        <el-form-item label="YouTube Cookie">
          <el-input v-model="form.youtube_cookie" type="textarea" :rows="3" placeholder="cookies.txt 内容或 cookie 字符串" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveCookies">保存 Cookie</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 保留策略 -->
    <el-card class="section">
      <template #header><span>保留策略</span></template>
      <el-form label-width="160px" :model="form">
        <el-form-item label="保留视频文件">
          <el-switch v-model="form.keep_video" @change="saveField('keep_video', form.keep_video)" />
          <span class="hint">关闭则处理后自动删除视频（节省空间）</span>
        </el-form-item>
        <el-form-item label="保留音频文件">
          <el-switch v-model="form.keep_audio" @change="saveField('keep_audio', form.keep_audio)" />
        </el-form-item>
        <el-form-item label="保留 SRT 字幕">
          <el-switch v-model="form.keep_srt" @change="saveField('keep_srt', form.keep_srt)" />
          <span class="hint">始终建议保留</span>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getConfig, updateConfig, verifyApiKey } from '../api/config'
import { listModels, listAsrAvailable, listAsrInstalled, getOllamaStatus } from '../api/models'

const providers = reactive({ llm: [], asr: [] })
const ollama = reactive({ running: false, models: [] })
const asrAvailable = ref([])
const asrInstalled = ref([])
const verifying = ref(false)
const downloading = ref(null)

const form = reactive({
  llm_provider: 'qwen',
  asr_provider: 'asrtools-b',
  api_key: '',
  bilibili_cookie: '',
  youtube_cookie: '',
  keep_video: false,
  keep_audio: false,
  keep_srt: true,
})

const isInstalled = (name) => asrInstalled.value.some((m) => m.name === name || m === name)

const loadConfig = async () => {
  try {
    const cfg = await getConfig()
    Object.assign(form, cfg)
  } catch (e) {
    ElMessage.warning('加载配置失败')
  }
}

const loadProviders = async () => {
  try {
    const data = await listModels()
    providers.llm = data.llm_providers || []
    providers.asr = data.asr_providers || []
  } catch (e) {
    // 后端未就绪时静默
  }
}

const loadAsrModels = async () => {
  try {
    const [avail, inst] = await Promise.all([listAsrAvailable(), listAsrInstalled()])
    asrAvailable.value = avail.models || []
    asrInstalled.value = inst.models || []
  } catch (e) {
    // 静默
  }
}

const checkOllama = async () => {
  try {
    const s = await getOllamaStatus()
    ollama.running = s.running
    ollama.models = s.models || []
  } catch (e) {
    ollama.running = false
  }
}

const verifyKey = async () => {
  if (!form.api_key) return ElMessage.warning('请输入 API Key')
  verifying.value = true
  try {
    const res = await verifyApiKey(form.llm_provider, form.api_key)
    ElMessage[res.valid ? 'success' : 'error'](res.valid ? '验证通过' : `验证失败：${res.error}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    verifying.value = false
  }
}

const downloadModel = async (name) => {
  downloading.value = name
  ElMessage.info(`开始下载 ${name}（后台进行，请稍后在本地模型列表刷新）`)
  downloading.value = null
}

const saveField = async (field, value) => {
  try {
    await updateConfig({ [field]: value })
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const saveCookies = async () => {
  try {
    await updateConfig({
      bilibili_cookie: form.bilibili_cookie,
      youtube_cookie: form.youtube_cookie,
    })
    ElMessage.success('Cookie 已保存')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  await Promise.all([loadConfig(), loadProviders(), loadAsrModels(), checkOllama()])
})
</script>

<style scoped>
.settings {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}
.section {
  margin-top: 16px;
}
.hint {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}
.model-mgmt {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.model-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.model-name {
  font-size: 13px;
  min-width: 200px;
}
.ollama-models {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}
</style>
