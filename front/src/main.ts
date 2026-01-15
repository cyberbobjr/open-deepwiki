import { createPinia } from 'pinia'
import { createApp } from 'vue'

import 'highlight.js/styles/atom-one-dark.css'
import App from './App.vue'
import { router } from './router'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
