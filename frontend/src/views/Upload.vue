<template>
  <div class="upload-container">
    <el-card class="upload-card card-shadow">
      <template #header>
        <div class="card-header">
          <el-icon class="header-icon"><Upload /></el-icon>
          <span>上传文档</span>
        </div>
      </template>
      
      <!-- 上传区域 -->
      <div v-if="!taskId" class="upload-section">
        <el-upload
          ref="uploadRef"
          class="upload-dragger"
          drag
          :auto-upload="false"
          :on-change="handleFileChange"
          :limit="1"
          accept=".pdf"
          :show-file-list="false"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            拖拽文件到此处或 <em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              支持 PDF 格式，文件大小不超过 100MB
            </div>
          </template>
        </el-upload>
        
        <div v-if="selectedFile" class="file-info">
          <el-icon><Document /></el-icon>
          <span class="file-name">{{ selectedFile.name }}</span>
          <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
        </div>
        
        <el-button
          type="primary"
          size="large"
          :disabled="!selectedFile"
          :loading="uploading"
          @click="startUpload"
          class="submit-btn"
        >
          <el-icon><Upload /></el-icon>
          开始分析
        </el-button>
      </div>
      
      <!-- 进度展示 -->
      <div v-else class="progress-section">
        <el-progress
          :percentage="progress"
          :status="progressStatus"
          :stroke-width="20"
        />
        <div class="progress-message">{{ progressMessage }}</div>
        
        <!-- 详细日志区域 -->
        <div class="progress-logs">
          <div class="logs-header">
            <el-icon><Document /></el-icon>
            <span>处理日志</span>
            <span class="log-count">({{ logs.length }})</span>
          </div>
          <div class="logs-content" ref="logsRef">
            <div
              v-for="(log, index) in logs"
              :key="index"
              class="log-item"
              :class="['log-level-' + log.level, { 'log-latest': index === logs.length - 1 }]"
            >
              <span class="log-time">{{ log.time }}</span>
              <el-icon class="log-icon" v-if="log.level === 'success'"><CircleCheck /></el-icon>
              <el-icon class="log-icon" v-else-if="log.level === 'error'"><CircleClose /></el-icon>
              <el-icon class="log-icon spinning" v-else><Loading /></el-icon>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </div>
        
        <!-- 统计信息 -->
        <div v-if="stats" class="progress-stats">
          <div class="stat-item">
            <el-icon><Clock /></el-icon>
            <span>{{ stats.elapsed }}秒</span>
          </div>
          <div class="stat-item" v-if="stats.sections">
            <el-icon><FolderOpened /></el-icon>
            <span>{{ stats.sections }}章节</span>
          </div>
          <div class="stat-item" v-if="stats.clauses">
            <el-icon><Document /></el-icon>
            <span>{{ stats.clauses }}条款</span>
          </div>
        </div>
        
        <el-button
          v-if="taskStatus === 'completed'"
          type="success"
          size="large"
          @click="viewResult"
          class="result-btn"
        >
          <el-icon><View /></el-icon>
          查看结果
        </el-button>
        
        <el-button
          v-if="taskStatus === 'failed'"
          type="warning"
          size="large"
          @click="resetUpload"
          class="result-btn"
        >
          <el-icon><RefreshRight /></el-icon>
          重新上传
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Clock, FolderOpened } from '@element-plus/icons-vue'
import api from '@/api'

const router = useRouter()
const uploadRef = ref()
const selectedFile = ref(null)
const uploading = ref(false)
const taskId = ref('')
const progress = ref(0)
const progressMessage = ref('')
const logs = ref([])
const taskStatus = ref('')
const logsRef = ref()
const stats = ref(null)

const progressStatus = computed(() => {
  if (taskStatus.value === 'completed') return 'success'
  if (taskStatus.value === 'failed') return 'exception'
  return undefined
})

const handleFileChange = (file) => {
  selectedFile.value = file.raw
}

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

const startUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  
  uploading.value = true
  
  try {
    // 上传文件
    const response = await api.uploadFile(selectedFile.value)
    
    if (response.status === 'success') {
      taskId.value = response.task_id
      ElMessage.success('文件上传成功，开始分析...')
      
      // 开始监听进度
      subscribeProgress(response.task_id)
    } else {
      throw new Error(response.message || '上传失败')
    }
  } catch (error) {
    ElMessage.error(error.message || '上传失败')
    uploading.value = false
  }
}

const subscribeProgress = (taskId) => {
  const eventSource = new EventSource(api.getProgressStream(taskId))
  let lastMessage = ''
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      
      if (data.status === 'done') {
        eventSource.close()
        return
      }
      
      if (data.error) {
        eventSource.close()
        taskStatus.value = 'failed'
        addLog(data.error, 'error')
        ElMessage.error(data.error)
        return
      }
      
      // 更新进度
      progress.value = Math.round(data.progress || 0)
      progressMessage.value = data.message || '处理中...'
      taskStatus.value = data.status
      
      // 更新统计信息
      if (data.elapsed_seconds !== undefined) {
        stats.value = {
          elapsed: data.elapsed_seconds,
          sections: data.sections_count || 0,
          clauses: data.clauses_count || 0
        }
      }
      
      // 添加日志（避免重复）
      if (data.message && data.message !== lastMessage) {
        addLog(
          data.message, 
          data.status === 'completed' ? 'success' : 
          data.status === 'failed' ? 'error' : 'info'
        )
        lastMessage = data.message
      }
      
      // 完成或失败时关闭连接
      if (data.status === 'completed' || data.status === 'failed') {
        eventSource.close()
        uploading.value = false
      }
    } catch (error) {
      console.error('解析进度数据失败:', error)
    }
  }
  
  eventSource.onerror = (error) => {
    console.error('SSE连接错误:', error)
    addLog('连接中断，请检查网络', 'error')
    eventSource.close()
    uploading.value = false
  }
}

// 添加日志条目
const addLog = (message, level = 'info') => {
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
  
  logs.value.push({
    time,
    message,
    level
  })
  
  // 自动滚动到最新日志
  setTimeout(() => {
    if (logsRef.value) {
      logsRef.value.scrollTop = logsRef.value.scrollHeight
    }
  }, 50)
}

const viewResult = () => {
  router.push(`/result/${taskId.value}`)
}

const resetUpload = () => {
  selectedFile.value = null
  taskId.value = ''
  progress.value = 0
  progressMessage.value = ''
  logs.value = []
  taskStatus.value = ''
  uploading.value = false
}
</script>

<style lang="scss" scoped>
.upload-container {
  min-height: 100vh;
  padding: 40px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-card {
  width: 100%;
  max-width: 800px;
  border-radius: 16px;
  
  :deep(.el-card__header) {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px;
  }
  
  :deep(.el-card__body) {
    padding: 40px;
  }
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 20px;
  font-weight: 600;
  
  .header-icon {
    font-size: 24px;
  }
}

.upload-section {
  .upload-dragger {
    :deep(.el-upload-dragger) {
      padding: 60px 40px;
      border: 2px dashed #d9d9d9;
      border-radius: 12px;
      transition: all 0.3s;
      
      &:hover {
        border-color: var(--primary-color);
      }
    }
    
    :deep(.el-icon--upload) {
      font-size: 67px;
      color: #c0c4cc;
      margin-bottom: 16px;
    }
    
    :deep(.el-upload__text) {
      font-size: 16px;
      color: #606266;
      
      em {
        color: var(--primary-color);
        font-style: normal;
      }
    }
    
    :deep(.el-upload__tip) {
      margin-top: 12px;
      color: #909399;
      font-size: 14px;
    }
  }
  
  .file-info {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 20px;
    margin: 20px 0;
    background: #f5f7fa;
    border-radius: 8px;
    font-size: 14px;
    
    .el-icon {
      font-size: 24px;
      color: var(--primary-color);
    }
    
    .file-name {
      flex: 1;
      font-weight: 500;
      color: var(--text-primary);
    }
    
    .file-size {
      color: var(--text-secondary);
    }
  }
  
  .submit-btn {
    width: 100%;
    margin-top: 20px;
    height: 50px;
    font-size: 16px;
  }
}

.progress-section {
  .el-progress {
    margin-bottom: 30px;
  }
  
  .progress-message {
    text-align: center;
    font-size: 16px;
    color: var(--text-primary);
    margin-bottom: 30px;
    font-weight: 500;
  }
  
  .progress-logs {
    max-height: 300px;
    overflow-y: auto;
    margin-bottom: 30px;
    padding: 20px;
    background: #f5f7fa;
    border-radius: 8px;
  }
  
  // 优化后的日志区域样式
  .progress-logs {
    margin-top: 20px;
    border: 1px solid #e4e7ed;
    border-radius: 8px;
    overflow: hidden;
    background: white;
    
    .logs-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 15px;
      background: #f5f7fa;
      border-bottom: 1px solid #e4e7ed;
      font-weight: 500;
      color: #606266;
      
      .log-count {
        margin-left: auto;
        font-size: 12px;
        color: #909399;
      }
    }
    
    .logs-content {
      max-height: 300px;
      overflow-y: auto;
      padding: 10px;
      scroll-behavior: smooth;
    }
  }
  
  .log-item {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 12px;
    margin-bottom: 4px;
    border-radius: 6px;
    font-size: 13px;
    transition: all 0.3s ease;
    animation: slideIn 0.3s ease;
    
    .log-time {
      font-family: 'Courier New', monospace;
      color: #909399;
      font-size: 11px;
      min-width: 60px;
      flex-shrink: 0;
    }
    
    .log-icon {
      flex-shrink: 0;
      font-size: 14px;
      
      &.spinning {
        animation: spin 1s linear infinite;
      }
    }
    
    .log-message {
      flex: 1;
      line-height: 1.5;
    }
    
    &.log-level-success {
      background: #f0f9ff;
      border-left: 3px solid #67c23a;
      
      .log-icon {
        color: #67c23a;
      }
      .log-message {
        color: #67c23a;
        font-weight: 500;
      }
    }
    
    &.log-level-error {
      background: #fef0f0;
      border-left: 3px solid #f56c6c;
      
      .log-icon {
        color: #f56c6c;
      }
      .log-message {
        color: #f56c6c;
        font-weight: 500;
      }
    }
    
    &.log-level-info {
      background: #fafafa;
      border-left: 3px solid #409eff;
      
      .log-icon {
        color: #409eff;
      }
      .log-message {
        color: #606266;
      }
    }
    
    &.log-latest {
      background: #e6f7ff;
      border-left-color: #409eff;
      box-shadow: 0 2px 4px rgba(64, 158, 255, 0.2);
    }
  }
  
  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateX(-10px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }
  
  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
  
  .progress-stats {
    display: flex;
    gap: 20px;
    justify-content: center;
    margin-top: 20px;
    padding: 15px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 8px;
    color: white;
    
    .stat-item {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 14px;
      font-weight: 500;
      
      .el-icon {
        font-size: 16px;
      }
    }
  }
  
  .result-btn {
    width: 100%;
    height: 50px;
    font-size: 16px;
    margin-top: 20px;
  }
}
</style>
