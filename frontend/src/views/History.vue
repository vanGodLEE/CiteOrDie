<template>
  <div class="history-container">
    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon><FolderOpened /></el-icon>
            <span>历史记录</span>
          </div>
          <el-button type="primary" @click="goToUpload">
            <el-icon><Plus /></el-icon>
            新建任务
          </el-button>
        </div>
      </template>
      
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-select v-model="statusFilter" placeholder="任务状态" clearable style="width: 150px">
          <el-option label="全部" value="" />
          <el-option label="进行中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button @click="loadTasks" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
      
      <!-- 任务列表 -->
      <el-table
        :data="tasks"
        v-loading="loading"
        style="width: 100%"
        :default-sort="{ prop: 'created_at', order: 'descending' }"
      >
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag
              :type="getStatusType(row.status)"
              effect="plain"
            >
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="progress" label="进度" width="150">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.round(row.progress)"
              :status="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'exception' : undefined"
            />
          </template>
        </el-table-column>
        
        <el-table-column prop="total_clauses" label="条款数" width="100" align="center">
          <template #default="{ row }">
            {{ row.total_clauses || 0 }}
          </template>
        </el-table-column>
        
        <el-table-column prop="elapsed_seconds" label="耗时" width="100">
          <template #default="{ row }">
            {{ formatTime(row.elapsed_seconds) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              type="primary"
              link
              @click="viewResult(row.task_id)"
            >
              查看结果
            </el-button>
            <el-button
              v-else-if="row.status === 'running'"
              type="warning"
              link
            >
              进行中...
            </el-button>
            <el-button
              v-else
              type="info"
              link
              disabled
            >
              {{ row.status }}
            </el-button>
            <el-button
              type="danger"
              link
              @click="confirmDelete(row)"
              :loading="row.deleting"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadTasks"
          @current-change="loadTasks"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const router = useRouter()

const loading = ref(false)
const tasks = ref([])
const statusFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

onMounted(() => {
  loadTasks()
})

const loadTasks = async () => {
  try {
    loading.value = true
    
    // 添加时间戳防止缓存
    const response = await api.getTasks({
      status: statusFilter.value,
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
      _t: Date.now()  // 防止浏览器缓存
    })
    
    console.log('加载任务列表:', response)
    
    tasks.value = response || []
    // 注意：后端需要返回total字段，这里暂时用tasks长度
    total.value = tasks.value.length
  } catch (error) {
    console.error('加载任务列表失败:', error)
    ElMessage.error('加载任务列表失败')
  } finally {
    loading.value = false
  }
}

const getStatusType = (status) => {
  const map = {
    completed: 'success',
    running: 'warning',
    failed: 'danger',
    pending: 'info'
  }
  return map[status] || 'info'
}

const getStatusText = (status) => {
  const map = {
    completed: '已完成',
    running: '进行中',
    failed: '失败',
    pending: '等待中'
  }
  return map[status] || status
}

const formatTime = (seconds) => {
  if (!seconds) return '-'
  if (seconds < 60) return `${Math.round(seconds)}秒`
  const minutes = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${minutes}分${secs}秒`
}

const formatDate = (dateString) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const viewResult = (taskId) => {
  router.push(`/result/${taskId}`)
}

const goToUpload = () => {
  router.push('/upload')
}

const confirmDelete = async (task) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除任务"${task.file_name}"吗？此操作将删除：
      
• 数据库记录（任务、日志、章节、条款）
• MinIO中的PDF文件
• 本地PDF文件
• MinerU输出目录
• 日志文件
• 中间JSON文件

此操作不可恢复！`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
        dangerouslyUseHTMLString: false,
        distinguishCancelAndClose: true
      }
    )
    
    // 用户确认删除
    await deleteTask(task)
    
  } catch (error) {
    // 用户取消或关闭对话框
    if (error !== 'cancel' && error !== 'close') {
      console.error('删除确认失败:', error)
    }
  }
}

const deleteTask = async (task) => {
  const taskId = task.task_id
  
  try {
    // 添加删除中状态
    task.deleting = true
    
    // 调用删除API
    const result = await api.deleteTask(taskId)
    
    console.log('删除结果:', result)
    
    ElMessage.success(result.message || '任务已删除')
    
    // 重新加载任务列表（确保数据同步）
    await loadTasks()
    
  } catch (error) {
    console.error('删除任务失败:', error)
    ElMessage.error(error.response?.data?.detail || '删除任务失败')
    task.deleting = false
  }
}
</script>

<style lang="scss" scoped>
.history-container {
  min-height: 100vh;
  padding: 40px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.history-card {
  max-width: 1400px;
  margin: 0 auto;
  border-radius: 16px;
  
  :deep(.el-card__header) {
    background: white;
    border-bottom: 2px solid #f0f0f0;
    padding: 20px 30px;
  }
  
  :deep(.el-card__body) {
    padding: 30px;
  }
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  
  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
    
    .el-icon {
      font-size: 24px;
      color: var(--primary-color);
    }
  }
}

.filter-bar {
  display: flex;
  gap: 15px;
  margin-bottom: 20px;
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 30px;
}

:deep(.el-table) {
  font-size: 14px;
  
  .el-table__header th {
    background: #fafafa;
    color: var(--text-primary);
    font-weight: 600;
  }
}
</style>
