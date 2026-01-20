<template>
  <div class="home-container">
    <div class="hero-section">
      <div class="hero-content">
        <h1 class="title">
          <el-icon class="title-icon"><Document /></el-icon>
          可执行条款抽取系统
        </h1>
        <p class="subtitle">
          智能识别文档中的可执行条款，支持标书、合同、合规制度、SOP等多种文档类型
        </p>
        <div class="features">
          <div class="feature-item">
            <el-icon class="feature-icon"><CircleCheck /></el-icon>
            <span>结构化提取</span>
          </div>
          <div class="feature-item">
            <el-icon class="feature-icon"><Edit /></el-icon>
            <span>7维分析</span>
          </div>
          <div class="feature-item">
            <el-icon class="feature-icon"><Location /></el-icon>
            <span>精准定位</span>
          </div>
        </div>
        <div class="action-buttons">
          <el-button type="primary" size="large" @click="goToUpload">
            <el-icon><Upload /></el-icon>
            开始分析
          </el-button>
          <el-button size="large" @click="goToHistory">
            <el-icon><FolderOpened /></el-icon>
            历史记录
          </el-button>
        </div>
      </div>
    </div>
    
    <div class="info-section">
      <el-row :gutter="30">
        <el-col :xs="24" :sm="8">
          <div class="info-card card-shadow-hover">
            <div class="card-icon primary">
              <el-icon><DocumentCopy /></el-icon>
            </div>
            <h3>支持多种文档</h3>
            <p>标书、合同、合规制度、SOP、标准规范、政策文件等</p>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="info-card card-shadow-hover">
            <div class="card-icon success">
              <el-icon><DataAnalysis /></el-icon>
            </div>
            <h3>智能结构化</h3>
            <p>自动提取条款类型、执行主体、动作、对象等7个维度</p>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="info-card card-shadow-hover">
            <div class="card-icon warning">
              <el-icon><Position /></el-icon>
            </div>
            <h3>精准定位</h3>
            <p>自动标注条款在原文中的位置，支持一键定位和高亮</p>
          </div>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const goToUpload = () => {
  router.push('/upload')
}

const goToHistory = () => {
  router.push('/history')
}
</script>

<style lang="scss" scoped>
.home-container {
  height: 100vh;
  overflow-y: auto;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.hero-section {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: white;
}

.hero-content {
  text-align: center;
  max-width: 800px;
}

.title {
  font-size: 48px;
  font-weight: 700;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 15px;
  
  .title-icon {
    font-size: 56px;
  }
}

.subtitle {
  font-size: 20px;
  margin-bottom: 40px;
  opacity: 0.9;
  line-height: 1.6;
}

.features {
  display: flex;
  gap: 40px;
  justify-content: center;
  margin-bottom: 50px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  
  .feature-icon {
    font-size: 24px;
    color: #ffd700;
  }
}

.action-buttons {
  display: flex;
  gap: 20px;
  justify-content: center;
  
  :deep(.el-button) {
    padding: 15px 40px;
    font-size: 16px;
  }
}

.info-section {
  padding: 60px 20px;
  background: white;
  border-radius: 30px 30px 0 0;
  margin-top: -30px;
}

.info-card {
  padding: 40px 30px;
  border-radius: 12px;
  background: white;
  text-align: center;
  height: 100%;
  cursor: pointer;
  
  .card-icon {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 25px;
    font-size: 40px;
    
    &.primary {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
    }
    
    &.success {
      background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      color: white;
    }
    
    &.warning {
      background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
      color: white;
    }
  }
  
  h3 {
    font-size: 22px;
    margin-bottom: 15px;
    color: var(--text-primary);
  }
  
  p {
    font-size: 15px;
    color: var(--text-secondary);
    line-height: 1.6;
  }
}

@media (max-width: 768px) {
  .title {
    font-size: 32px;
    
    .title-icon {
      font-size: 36px;
    }
  }
  
  .subtitle {
    font-size: 16px;
  }
  
  .features {
    flex-direction: column;
    gap: 20px;
  }
  
  .action-buttons {
    flex-direction: column;
    
    :deep(.el-button) {
      width: 100%;
    }
  }
}
</style>
