import { createApp } from 'vue'
import ElDialog from 'element-plus/es/components/dialog/index'
import ElTooltip from 'element-plus/es/components/tooltip/index'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/tooltip/style/css'
import 'element-plus/es/components/message/style/css'
import 'katex/dist/katex.min.css'
import './shared/style.css'
import App from './App.vue'

createApp(App).use(ElDialog).use(ElTooltip).mount('#app')
