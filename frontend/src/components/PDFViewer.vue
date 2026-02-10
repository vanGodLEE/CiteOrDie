<template>
  <div class="pdf-viewer">
    <!-- PDF工具栏 -->
    <div class="pdf-toolbar">
      <span class="page-info">总页数: {{ totalPages }}</span>
      <span class="scale-info">缩放: {{ Math.round(currentScale * 100) }}%</span>
    </div>

    <!-- PDF容器 - 连续滚动模式 -->
    <div class="pdf-container" ref="pdfContainerRef">
      <!-- 每一页 -->
      <div 
        v-for="pageNum in totalPages" 
        :key="pageNum" 
        class="pdf-page"
        :ref="el => setPageRef(el, pageNum)"
        :data-page-num="pageNum"
      >
        <!-- PDF Canvas -->
        <canvas 
          :ref="el => setPdfCanvasRef(el, pageNum)"
          class="pdf-canvas"
        ></canvas>
        <!-- 高亮 Canvas -->
        <canvas 
          :ref="el => setHighlightCanvasRef(el, pageNum)"
          class="highlight-canvas"
        ></canvas>
        <!-- 页码标签 -->
        <div class="page-label">第 {{ pageNum }} 页</div>
      </div>
    </div>

    <!-- 加载提示 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner">
        <div class="spinner"></div>
        <p>加载PDF中...</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'

// 使用全局 PDF.js 2.16.105（稳定版本）
const pdfjsLib = window['pdfjs-dist/build/pdf']
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js'

console.log('PDF.js版本:', pdfjsLib.version)

const props = defineProps({
  pdfUrl: {
    type: String,
    required: true
  },
  highlightedPositions: {
    type: Array,
    default: () => []
  }
})

// Refs
const pdfContainerRef = ref(null)
const pageRefs = new Map()  // pageNum -> div element
const pdfCanvasRefs = new Map()  // pageNum -> canvas element
const highlightCanvasRefs = new Map()  // pageNum -> canvas element

// State
const loading = ref(false)
let currentPdfDoc = null
const totalPages = ref(0)
const currentScale = ref(1.0)

// Ref setter functions
const setPageRef = (el, pageNum) => {
  if (el) {
    pageRefs.set(pageNum, el)
    console.log(`设置pageRef ${pageNum}`)
  } else {
    pageRefs.delete(pageNum)
  }
}

const setPdfCanvasRef = (el, pageNum) => {
  if (el) {
    pdfCanvasRefs.set(pageNum, el)
    console.log(`设置pdfCanvasRef ${pageNum}`)
  } else {
    pdfCanvasRefs.delete(pageNum)
  }
}

const setHighlightCanvasRef = (el, pageNum) => {
  if (el) {
    highlightCanvasRefs.set(pageNum, el)
    console.log(`设置highlightCanvasRef ${pageNum}`)
  } else {
    highlightCanvasRefs.delete(pageNum)
  }
}

// 监听 props 变化
onMounted(() => {
  if (props.pdfUrl) {
    loadPDF()
  }
})

watch(() => props.pdfUrl, (newUrl) => {
  if (newUrl) {
    loadPDF()
  }
})

watch(() => props.highlightedPositions, () => {
  console.log('高亮positions变化:', props.highlightedPositions.length)
  drawHighlights()
}, { deep: true })

// ========== 核心方法 ==========

// 加载PDF - 连续滚动模式
const loadPDF = async () => {
  try {
    loading.value = true
    console.log('开始加载PDF:', props.pdfUrl)

    // 清理旧的refs
    pageRefs.clear()
    pdfCanvasRefs.clear()
    highlightCanvasRefs.clear()
    currentPdfDoc = null

    const loadingTask = pdfjsLib.getDocument(props.pdfUrl)
    currentPdfDoc = await loadingTask.promise

    console.log('PDF加载成功，总页数:', currentPdfDoc.numPages)
    totalPages.value = currentPdfDoc.numPages

    // 等待Vue的DOM更新完成
    await nextTick()
    
    console.log('DOM更新完成，开始渲染...')
    console.log('pdfCanvasRefs数量:', pdfCanvasRefs.size)
    console.log('highlightCanvasRefs数量:', highlightCanvasRefs.size)
    
    // 再等一下确保所有refs都设置好了
    await new Promise(resolve => setTimeout(resolve, 200))
    
    // 渲染所有页面
    await renderAllPages()

    loading.value = false
  } catch (error) {
    console.error('PDF加载失败:', error)
    ElMessage.error(`PDF加载失败: ${error.message}`)
    loading.value = false
  }
}

// 渲染所有页面
const renderAllPages = async () => {
  if (!currentPdfDoc) return
  
  console.log('开始渲染所有页面，总页数:', totalPages.value)
  console.log('可用的canvas数量:', pdfCanvasRefs.size)
  
  for (let pageNum = 1; pageNum <= totalPages.value; pageNum++) {
    console.log(`准备渲染第 ${pageNum} 页`)
    await renderPage(pageNum)
  }
  
  console.log('✅ 所有页面渲染完成')
  
  // 渲染完成后绘制高亮
  drawHighlights()
}

// 渲染指定页面
const renderPage = async (pageNum) => {
  const pdfCanvas = pdfCanvasRefs.get(pageNum)
  const highlightCanvas = highlightCanvasRefs.get(pageNum)
  
  if (!currentPdfDoc || !pdfCanvas || !highlightCanvas) {
    console.warn(`第 ${pageNum} 页的Canvas未准备好`)
    return
  }

  console.log(`渲染第 ${pageNum} 页`)

  try {
    // 获取页面对象
    const page = await currentPdfDoc.getPage(pageNum)

    // 计算scale：根据容器宽度自适应
    const container = pdfContainerRef.value
    const containerWidth = container?.clientWidth || 800
    const defaultViewport = page.getViewport({ scale: 1.0 })
    const scale = (containerWidth - 40) / defaultViewport.width  // 减去padding
    const scaledViewport = page.getViewport({ scale })
    
    // 第一页时更新currentScale（用于工具栏显示）
    if (pageNum === 1) {
      currentScale.value = scale
    }

    // 设置 PDF Canvas 尺寸
    const pdfCtx = pdfCanvas.getContext('2d')
    pdfCanvas.width = scaledViewport.width
    pdfCanvas.height = scaledViewport.height

    // 渲染 PDF 到 Canvas
    await page.render({
      canvasContext: pdfCtx,
      viewport: scaledViewport
    }).promise

    // 创建高亮 Canvas（尺寸与 PDF Canvas 完全一致）
    highlightCanvas.width = scaledViewport.width
    highlightCanvas.height = scaledViewport.height

    console.log(`第 ${pageNum} 页渲染完成`)

  } catch (error) {
    console.error(`第 ${pageNum} 页渲染失败:`, error)
  }
}

// 绘制高亮（支持多页）
const drawHighlights = () => {
  if (!props.highlightedPositions || props.highlightedPositions.length === 0) {
    // 清除所有页面的高亮
    highlightCanvasRefs.forEach((canvas) => {
      const ctx = canvas.getContext('2d')
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    })
    return
  }

  // 按页面分组positions
  const positionsByPage = new Map()
  props.highlightedPositions.forEach((position) => {
    if (!position || position.length < 5) return
    
    const [pageIdx, x0, y0, x1, y1] = position
    const pageNum = pageIdx + 1  // pageIdx是0-based，pageNum是1-based
    
    if (!positionsByPage.has(pageNum)) {
      positionsByPage.set(pageNum, [])
    }
    positionsByPage.get(pageNum).push({ x0, y0, x1, y1 })
  })

  console.log('高亮分布:', Array.from(positionsByPage.entries()).map(([pageNum, positions]) => 
    `第${pageNum}页: ${positions.length}个`
  ).join(', '))

  // 遍历所有页面，绘制或清除高亮
  for (let pageNum = 1; pageNum <= totalPages.value; pageNum++) {
    const canvas = highlightCanvasRefs.get(pageNum)
    if (!canvas) continue
    
    const ctx = canvas.getContext('2d')
    
    // 清除该页的高亮
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    
    // 如果该页有高亮positions，绘制
    const pagePositions = positionsByPage.get(pageNum)
    if (pagePositions && pagePositions.length > 0) {
      pagePositions.forEach(({ x0, y0, x1, y1 }) => {
        // 坐标已经是左上原点的points，直接乘以scale
        const vx0 = x0 * currentScale.value
        const vy0 = y0 * currentScale.value
        const vx1 = x1 * currentScale.value
        const vy1 = y1 * currentScale.value

        // 绘制半透明红色边框
        ctx.strokeStyle = 'rgba(255, 0, 0, 0.9)'
        ctx.lineWidth = 2
        ctx.strokeRect(vx0, vy0, vx1 - vx0, vy1 - vy0)

        // 填充半透明黄色背景
        ctx.fillStyle = 'rgba(255, 255, 0, 0.3)'
        ctx.fillRect(vx0, vy0, vx1 - vx0, vy1 - vy0)
      })
    }
  }

  console.log('✅ 高亮绘制完成')
}

// 跳转到指定位置（连续滚动模式）
const jumpToPosition = (pageIdx, x0, y0, x1, y1) => {
  const targetPageNum = pageIdx + 1 // 转换为1-based

  console.log('跳转到位置:', { pageIdx, targetPageNum, x0, y0, x1, y1 })

  // 找到目标页面的元素
  const targetPageEl = pageRefs.get(targetPageNum)
  if (!targetPageEl) {
    console.warn(`找不到第 ${targetPageNum} 页的元素`)
    return
  }

  // 计算滚动位置
  const container = pdfContainerRef.value
  if (container) {
    // 页面在容器中的偏移 + 页面内的y坐标
    const pageOffsetTop = targetPageEl.offsetTop
    const positionInPage = y0 * currentScale.value
    const scrollTop = pageOffsetTop + positionInPage - container.clientHeight / 3

    container.scrollTo({
      top: Math.max(0, scrollTop),
      behavior: 'smooth'
    })
    
    console.log('滚动到位置:', scrollTop)
  }
}

// 暴露方法给父组件
defineExpose({
  jumpToPosition
})
</script>

<style lang="scss" scoped>
.pdf-viewer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #525659;
  overflow: hidden;
}

.pdf-toolbar {
  background: #323639;
  padding: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: white;

  .page-info {
    margin: 0 10px;
  }

  .scale-info {
    margin-left: auto;
  }
}

.pdf-container {
  flex: 1;
  overflow: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px; /* 页面之间的间距 */
}

/* 每一页的容器 - 使用Grid布局实现canvas叠加 */
.pdf-page {
  position: relative;
  display: grid;
  grid-template: auto / auto;
  width: fit-content;
  margin: 0;
  padding: 0;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

/* 页码标签 */
.page-label {
  position: absolute;
  bottom: 10px;
  right: 10px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  z-index: 3;
  pointer-events: none;
}

/* Canvas - 使用grid-area叠加在同一位置 */
.pdf-canvas,
.highlight-canvas {
  display: block;
  grid-area: 1 / 1;  /* 两个canvas占据同一个grid单元格 */
  margin: 0;
  padding: 0;
}

.pdf-canvas {
  z-index: 1;
}

.highlight-canvas {
  z-index: 2;
  pointer-events: none; /* 允许鼠标事件穿透 */
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.loading-spinner {
  text-align: center;
  color: white;

  .spinner {
    width: 50px;
    height: 50px;
    border: 4px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 15px;
  }

  p {
    font-size: 16px;
    margin: 0;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
