<template>
  <div class="clause-list">
    <div class="list-content">
      <div
        v-for="clause in clauses"
        :key="clause.matrix_id"
        class="clause-item"
        :class="{ 
          active: isClauseActive(clause)
        }"
        @click="handleClauseClick(clause)"
      >
        <div class="clause-header">
          <el-tag :type="getClauseTypeColor(clause.type)" size="small">
            {{ getClauseTypeText(clause.type) }}
          </el-tag>
          <span class="clause-id">{{ clause.matrix_id }}</span>
        </div>
        
        <div class="clause-content">
          <div class="clause-row" v-if="clause.actor || clause.action || clause.object">
            <el-icon><User /></el-icon>
            <span class="label">执行：</span>
            <span class="value">
              {{ [clause.actor, clause.action, clause.object].filter(Boolean).join(' ') }}
            </span>
          </div>
          
          <div class="clause-row" v-if="clause.condition">
            <el-icon><QuestionFilled /></el-icon>
            <span class="label">条件：</span>
            <span class="value">{{ clause.condition }}</span>
          </div>
          
          <div class="clause-row" v-if="clause.deadline">
            <el-icon><Clock /></el-icon>
            <span class="label">时间：</span>
            <span class="value">{{ clause.deadline }}</span>
          </div>
          
          <div class="clause-row" v-if="clause.metric">
            <el-icon><DataLine /></el-icon>
            <span class="label">指标：</span>
            <span class="value">{{ clause.metric }}</span>
          </div>
          
          <div class="clause-text">
            <el-icon><Document /></el-icon>
            <span class="label">原文：</span>
            <p class="text-content">{{ clause.original_text }}</p>
          </div>
        </div>
        
        <div class="clause-footer">
          <el-tag size="small" effect="plain">
            第 {{ clause.page_number }} 页
          </el-tag>
          <el-tag size="small" effect="plain">
            {{ clause.section_title }}
          </el-tag>
        </div>
      </div>
      
      <el-empty v-if="clauses.length === 0" description="暂无条款数据" />
    </div>
  </div>
</template>

<script setup>
import { watch, nextTick } from 'vue'
import { User, QuestionFilled, Clock, DataLine, Document } from '@element-plus/icons-vue'

const props = defineProps({
  clauses: {
    type: Array,
    default: () => []
  },
  activeClauseId: {
    type: String,
    default: ''
  },
  activeNodeId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['clause-click'])

// 判断条款是否应该高亮
const isClauseActive = (clause) => {
  // 如果有具体的 activeClauseId，只高亮该条款
  if (props.activeClauseId) {
    return clause.matrix_id === props.activeClauseId
  }
  // 如果有 activeNodeId，高亮该节点下的所有条款
  if (props.activeNodeId) {
    return clause.node_id === props.activeNodeId
  }
  return false
}

// 监听高亮条款变化，自动滚动到该条款
watch(() => props.activeClauseId, (newId) => {
  if (newId) {
    nextTick(() => {
      const activeElement = document.querySelector(`.clause-item.active`)
      if (activeElement) {
        activeElement.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center' 
        })
        console.log('滚动到高亮条款:', newId)
      }
    })
  }
})

// 监听节点变化，滚动到第一个匹配的条款
watch(() => props.activeNodeId, (newId) => {
  if (newId && !props.activeClauseId) {
    nextTick(() => {
      const activeElement = document.querySelector(`.clause-item.active`)
      if (activeElement) {
        activeElement.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center' 
        })
        console.log('滚动到节点的第一个条款，节点ID:', newId)
      }
    })
  }
})

const getClauseTypeColor = (type) => {
  if (!type) return 'info' // 默认类型
  
  const colorMap = {
    obligation: 'danger',
    requirement: 'primary',
    prohibition: 'warning',
    deliverable: 'success',
    deadline: 'info',
    penalty: 'danger',
    definition: 'info'
  }
  return colorMap[type] || 'info'
}

const getClauseTypeText = (type) => {
  if (!type) return '未分类'
  
  const textMap = {
    obligation: '义务',
    requirement: '需求',
    prohibition: '禁止',
    deliverable: '交付物',
    deadline: '截止时间',
    penalty: '惩罚',
    definition: '定义'
  }
  return textMap[type] || type
}

const handleClauseClick = (clause) => {
  emit('clause-click', clause)
}
</script>

<style lang="scss" scoped>
.clause-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.list-content {
  flex: 1;
  overflow-y: auto;
  padding: 15px;
}

.clause-item {
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 15px;
  cursor: pointer;
  transition: all 0.3s;
  
  &:hover {
    border-color: var(--primary-color);
    box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
  }
  
  &.active {
    border-color: var(--primary-color);
    background: #e6f7ff;
    box-shadow: 0 2px 12px rgba(64, 158, 255, 0.2);
  }
  
  &:last-child {
    margin-bottom: 0;
  }
}

.clause-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  
  .clause-id {
    font-size: 12px;
    color: var(--text-secondary);
    font-family: monospace;
  }
}

.clause-content {
  margin-bottom: 12px;
}

.clause-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 13px;
  
  .el-icon {
    margin-top: 2px;
    font-size: 14px;
    color: var(--primary-color);
    flex-shrink: 0;
  }
  
  .label {
    color: var(--text-secondary);
    flex-shrink: 0;
  }
  
  .value {
    flex: 1;
    color: var(--text-primary);
    word-break: break-word;
  }
}

.clause-text {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  
  > div:first-child {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  
  .el-icon {
    font-size: 14px;
    color: var(--primary-color);
  }
  
  .label {
    color: var(--text-secondary);
  }
  
  .text-content {
    margin: 0;
    padding-left: 20px;
    line-height: 1.6;
    color: var(--text-primary);
    word-break: break-word;
  }
}

.clause-footer {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  
  .el-tag {
    font-size: 12px;
  }
}
</style>
