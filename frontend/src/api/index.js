import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 300000 // 5分钟超时
})

// 请求拦截器
request.interceptors.request.use(
  config => {
    return config
  },
  error => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    const message = error.response?.data?.detail || error.response?.data?.message || error.message || '请求失败'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default {
  // 上传文件并开始分析
  uploadFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  // 获取任务进度（SSE）
  getProgressStream(taskId) {
    return `/api/progress/${taskId}`
  },

  // 获取任务详情
  getTaskInfo(taskId) {
    return request.get(`/task/${taskId}`)
  },

  // 获取任务列表
  getTasks(params) {
    return request.get('/tasks', { params })
  },

  // 获取PDF URL
  getPdfUrl(taskId) {
    return request.get(`/pdf/${taskId}`)
  },

  // 获取所有条款
  getClauses(taskId) {
    return request.get(`/tasks/${taskId}/clauses/all`)
  },

  // 下载Excel
  downloadExcel(taskId) {
    return `/api/download/excel/${taskId}`
  },

  // 删除任务
  deleteTask(taskId) {
    return request.delete(`/task/${taskId}`)
  },

  // 通用方法（供其他地方使用）
  get(url, config) {
    return request.get(url, config)
  },

  post(url, data, config) {
    return request.post(url, data, config)
  },

  delete(url, config) {
    return request.delete(url, config)
  }
}
