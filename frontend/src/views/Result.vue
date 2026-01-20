<template>
  <div class="result-container">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button @click="goBack" circle>
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <span class="file-name">{{ fileName }}</span>
      </div>
      <div class="toolbar-right">
        <el-button type="primary" @click="downloadExcel">
          <el-icon><Download /></el-icon>
          导出Excel
        </el-button>
      </div>
    </div>
    
    <!-- 主内容区 - 三栏布局 -->
    <div class="main-content">
      <!-- 左：PDF查看器 -->
      <div class="left-panel">
        <PDFViewer
          ref="pdfViewerRef"
          :pdf-url="pdfUrl"
          :highlighted-positions="highlightedPositions"
        />
      </div>
      
      <!-- 中：文档树 -->
      <div class="middle-panel">
        <div class="panel-header">
          <el-icon><FolderOpened /></el-icon>
          <span>文档结构</span>
        </div>
        <DocumentTree
          :tree-data="documentTree"
          :active-node-id="activeNodeId"
          @node-click="handleNodeClick"
        />
      </div>
      
      <!-- 右：条款列表 -->
      <div class="right-panel">
        <div class="panel-header">
          <el-icon><List /></el-icon>
          <span>条款列表 ({{ clauses.length }})</span>
        </div>
        
        <!-- 质量报告卡片（可折叠） -->
        <div v-if="qualityReport" class="quality-report-card">
          <div class="quality-header" @click="toggleQualityReport">
            <div class="quality-title">
              <el-icon><DataAnalysis /></el-icon>
              <span>质量报告</span>
            </div>
            <el-icon class="toggle-icon" :class="{ expanded: showQualityReport }">
              <ArrowDown />
            </el-icon>
          </div>
          
          <transition name="slide-fade">
            <div v-show="showQualityReport" class="quality-content">
              <el-row :gutter="8">
                <el-col :span="12">
                  <div class="quality-item">
                    <div class="quality-label">解析置信度</div>
                    <div class="quality-value" :class="getQualityClass(qualityReport.avg_parse_confidence)">
                      {{ (qualityReport.avg_parse_confidence * 100).toFixed(1) }}%
                    </div>
                    <el-progress 
                      :percentage="qualityReport.avg_parse_confidence * 100" 
                      :color="getProgressColor(qualityReport.avg_parse_confidence)"
                      :show-text="false"
                      :stroke-width="4"
                    />
                  </div>
                </el-col>
                <el-col :span="12">
                  <div class="quality-item">
                    <div class="quality-label">原文抽取率</div>
                    <div class="quality-value" :class="getQualityClass(qualityReport.content_extraction_success_rate)">
                      {{ (qualityReport.content_extraction_success_rate * 100).toFixed(1) }}%
                    </div>
                    <el-progress 
                      :percentage="qualityReport.content_extraction_success_rate * 100" 
                      :color="getProgressColor(qualityReport.content_extraction_success_rate)"
                      :show-text="false"
                      :stroke-width="4"
                    />
                  </div>
                </el-col>
              </el-row>
              
              <el-row :gutter="8" style="margin-top: 8px;">
                <el-col :span="12">
                  <div class="quality-item">
                    <div class="quality-label">原文定位率</div>
                    <div class="quality-value" :class="getQualityClass(qualityReport.content_bbox_match_rate)">
                      {{ (qualityReport.content_bbox_match_rate * 100).toFixed(1) }}%
                    </div>
                    <el-progress 
                      :percentage="qualityReport.content_bbox_match_rate * 100" 
                      :color="getProgressColor(qualityReport.content_bbox_match_rate)"
                      :show-text="false"
                      :stroke-width="4"
                    />
                  </div>
                </el-col>
                <el-col :span="12">
                  <div class="quality-item">
                    <div class="quality-label">条款定位率</div>
                    <div class="quality-value" :class="getQualityClass(qualityReport.clause_bbox_match_rate)">
                      {{ (qualityReport.clause_bbox_match_rate * 100).toFixed(1) }}%
                    </div>
                    <el-progress 
                      :percentage="qualityReport.clause_bbox_match_rate * 100" 
                      :color="getProgressColor(qualityReport.clause_bbox_match_rate)"
                      :show-text="false"
                      :stroke-width="4"
                    />
                  </div>
                </el-col>
              </el-row>
            </div>
          </transition>
        </div>
        
        <ClauseList
          :clauses="clauses"
          :active-clause-id="activeClauseId"
          :active-node-id="activeNodeId"
          @clause-click="handleClauseClick"
        />
      </div>
    </div>
    
    <!-- 加载状态 -->
    <el-loading
      v-if="loading"
      fullscreen
      text="加载中..."
    />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataAnalysis, ArrowDown, List, TrendCharts } from '@element-plus/icons-vue'
import api from '@/api'
import PDFViewer from '@/components/PDFViewer.vue'
import DocumentTree from '@/components/DocumentTree.vue'
import ClauseList from '@/components/ClauseList.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const taskInfo = ref(null)
const pdfUrl = ref('')
const clauses = ref([])
const documentTree = ref(null)
const activeNodeId = ref('')
const activeClauseId = ref('')
const highlightedPositions = ref([])
const pdfViewerRef = ref()
const qualityReport = ref(null)
const showQualityReport = ref(true) // 默认展开

const fileName = computed(() => {
  return taskInfo.value?.file_name || '文档分析结果'
})

const taskId = route.params.taskId

onMounted(async () => {
  await loadTaskData()
})

const loadTaskData = async () => {
  try {
    loading.value = true
    
    // 并行加载所有数据
    const [taskData, pdfData, clausesData] = await Promise.all([
      api.getTaskInfo(taskId),
      api.getPdfUrl(taskId),
      api.getClauses(taskId)
    ])
    
    // 设置任务信息
    taskInfo.value = taskData
    
    // 设置PDF URL（直接使用MinIO URL）
    pdfUrl.value = pdfData.minio_url || pdfData.proxy_url
    console.log('PDF URL设置为:', pdfUrl.value)
    
    // 设置条款列表
    clauses.value = clausesData || []
    console.log('加载的条款数:', clauses.value.length)
    if (clauses.value.length > 0) {
      console.log('第一个条款示例:', clauses.value[0])
    }
    
    // 设置文档树
    if (taskData.document_tree) {
      documentTree.value = taskData.document_tree.structure || []
    }
    
    // ✅ 设置质量报告（从taskData中获取）
    if (taskData.quality_report) {
      qualityReport.value = taskData.quality_report
      console.log('质量报告已加载:', qualityReport.value)
    } else {
      console.log('该任务没有质量报告数据')
      qualityReport.value = null
    }
    
    ElMessage.success('数据加载完成')
  } catch (error) {
    console.error('加载数据失败:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

const handleNodeClick = (node) => {
  activeNodeId.value = node.node_id
  activeClauseId.value = '' // 清空，让所有该节点下的条款在列表中高亮显示
  
  console.log('节点点击:', node.title, 'node_id:', node.node_id)
  
  // ✅ 业务逻辑：点击标题时，只高亮标题自己的原文区域（node.positions）
  // 不掺加条款的positions，避免重叠
  // 条款会在右侧列表中高亮显示（通过activeNodeId），但不在PDF中高亮
  
  if (node.positions && node.positions.length > 0) {
    // 使用节点自己的positions
    highlightedPositions.value = node.positions
    
    const firstPos = node.positions[0]
    console.log('高亮节点原文区域，位置数:', node.positions.length)
    
    // 跳转到第一个位置
    if (pdfViewerRef.value && firstPos && firstPos.length >= 5) {
      const [pageIdx, x1, y1, x2, y2] = firstPos
      pdfViewerRef.value.jumpToPosition(pageIdx, x1, y1, x2, y2)
    }
  } else {
    console.warn('节点没有positions数据')
    highlightedPositions.value = []
  }
}

const handleClauseClick = (clause) => {
  activeClauseId.value = clause.matrix_id
  activeNodeId.value = clause.node_id // 同时激活所属节点，在树中高亮显示
  
  console.log('条款点击:', clause.matrix_id)
  
  // ✅ 业务逻辑：点击条款时，只高亮条款自己的原文区域（clause.positions）
  // 不掺加标题的positions，避免重叠
  // 标题会在左侧树中高亮显示（通过activeNodeId），但不在PDF中高亮
  
  if (clause.positions && clause.positions.length > 0) {
    highlightedPositions.value = clause.positions
    
    const firstPos = clause.positions[0]
    console.log('高亮条款原文区域，位置数:', clause.positions.length)
    
    // 跳转到第一个位置
    if (pdfViewerRef.value && firstPos && firstPos.length >= 5) {
      const [pageIdx, x1, y1, x2, y2] = firstPos
      pdfViewerRef.value.jumpToPosition(pageIdx, x1, y1, x2, y2)
    }
  } else {
    console.warn('条款没有positions数据')
    highlightedPositions.value = []
  }
}

// 切换质量报告展开/收起
const toggleQualityReport = () => {
  showQualityReport.value = !showQualityReport.value
}

// 根据质量指标返回颜色类名
const getQualityClass = (value) => {
  if (value >= 0.9) return 'excellent'
  if (value >= 0.7) return 'good'
  if (value >= 0.5) return 'medium'
  return 'poor'
}

// 根据质量指标返回进度条颜色
const getProgressColor = (value) => {
  if (value >= 0.9) return '#67c23a'
  if (value >= 0.7) return '#409eff'
  if (value >= 0.5) return '#e6a23c'
  return '#f56c6c'
}

const downloadExcel = () => {
  window.open(api.downloadExcel(taskId), '_blank')
}

const goBack = () => {
  router.back()
}
</script>

<style lang="scss" scoped>
.result-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

.toolbar {
  height: 60px;
  background: white;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  z-index: 10;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 15px;
  
  .file-name {
    font-size: 16px;
    font-weight: 500;
    color: var(--text-primary);
  }
}

.main-content {
  flex: 1;
  display: flex;
  gap: 1px;
  overflow: hidden;
  background: #e4e7ed;
}

.left-panel {
  flex: 0 0 45%;
  background: white;
  overflow: hidden;
}

.middle-panel {
  flex: 0 0 25%;
  background: white;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-panel {
  flex: 1;
  background: white;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 质量报告卡片 */
.quality-report-card {
  margin: 0 12px 12px 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.quality-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.3s;
}

.quality-header:hover {
  background-color: rgba(64, 158, 255, 0.05);
}

.quality-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.quality-title .el-icon {
  color: #409eff;
}

.toggle-icon {
  transition: transform 0.3s;
  color: #909399;
}

.toggle-icon.expanded {
  transform: rotate(180deg);
}

.quality-content {
  padding: 12px;
  padding-top: 4px;
}

.quality-item {
  margin-bottom: 4px;
}

.quality-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 4px;
}

.quality-value {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.quality-value.excellent {
  color: #67c23a;
}

.quality-value.good {
  color: #409eff;
}

.quality-value.fair {
  color: #e6a23c;
}

.quality-value.poor {
  color: #f56c6c;
}

/* 折叠动画 */
.slide-fade-enter-active {
  transition: all 0.3s ease;
}

.slide-fade-leave-active {
  transition: all 0.3s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

.panel-header {
  height: 50px;
  padding: 0 20px;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
  background: #fafafa;
  
  .el-icon {
    font-size: 18px;
    color: var(--primary-color);
  }
}

@media (max-width: 1200px) {
  .left-panel {
    flex: 0 0 40%;
  }
  
  .middle-panel {
    flex: 0 0 30%;
  }
}
</style>
