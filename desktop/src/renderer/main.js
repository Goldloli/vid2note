import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
// vid2note 自研回执设计系统（OKLCH 调色 + Space Grotesk / JetBrains Mono）
import './styles/app.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
