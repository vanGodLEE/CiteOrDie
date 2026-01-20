<template>
  <div class="document-tree">
    <el-tree
      ref="treeRef"
      :data="treeData"
      :props="treeProps"
      node-key="node_id"
      :highlight-current="true"
      :expand-on-click-node="false"
      :current-node-key="activeNodeId"
      @node-click="handleNodeClick"
    >
      <template #default="{ node, data }">
        <div class="tree-node">
          <span class="node-title" :title="data.title">
            {{ data.title }}
          </span>
          <el-tag v-if="data.clauses && data.clauses.length > 0" size="small" type="primary">
            {{ data.clauses.length }}
          </el-tag>
        </div>
      </template>
    </el-tree>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  treeData: {
    type: Array,
    default: () => []
  },
  activeNodeId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['node-click'])
const treeRef = ref(null)

const treeProps = {
  children: 'nodes',
  label: 'title'
}

const handleNodeClick = (data) => {
  emit('node-click', data)
}

// 监听activeNodeId变化，滚动到对应节点
watch(() => props.activeNodeId, (newId) => {
  if (newId && treeRef.value) {
    nextTick(() => {
      treeRef.value.setCurrentKey(newId)
      // 滚动到当前节点
      const currentNode = document.querySelector('.el-tree-node.is-current')
      if (currentNode) {
        currentNode.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center' 
        })
        console.log('滚动到高亮节点:', newId)
      }
    })
  }
})
</script>

<style lang="scss" scoped>
.document-tree {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  
  :deep(.el-tree) {
    background: transparent;
    
    .el-tree-node__content {
      height: auto;
      min-height: 36px;
      padding: 6px 0;
      
      &:hover {
        background-color: #f5f7fa;
      }
    }
    
    .el-tree-node.is-current > .el-tree-node__content {
      background-color: #e6f7ff;
      color: var(--primary-color);
      font-weight: 500;
    }
  }
}

.tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-right: 10px;
  
  .node-title {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
    line-height: 1.5;
  }
  
  .el-tag {
    flex-shrink: 0;
  }
}
</style>
