# 前端调试指南

## 当前问题

1. **PDF不显示** - API返回200但PDF不渲染
2. **点击不定位** - 点击条款/节点时不跳转到PDF对应位置

## 已添加的调试日志

### 1. PDF加载调试 (`PDFViewer.vue`)

```javascript
console.log('开始加载PDF:', props.pdfUrl)
console.log('PDF加载成功，总页数:', totalPages.value)
```

### 2. URL设置调试 (`Result.vue`)

```javascript
console.log('PDF URL设置为:', pdfUrl.value)
```

### 3. 点击事件调试 (`Result.vue`)

```javascript
console.log('节点点击:', node.title, 'positions:', node.positions)
console.log('条款点击:', clause.matrix_id, 'positions:', clause.positions)
console.log('跳转到位置:', firstPos)
```

### 4. 高亮绘制调试 (`PDFViewer.vue`)

```javascript
console.log('绘制高亮，当前页:', currentPage.value)
console.log('当前页匹配的positions:', currentPagePositions.length)
console.log('高亮:', { pageIdx, x1, y1, x2, y2 })
console.log('绘制坐标:', { vx1, vy1, vx2, vy2, width, height })
```

## 调试步骤

### 1. 检查PDF加载问题

打开浏览器开发者工具（F12） → Console标签页，查看：

1. **PDF URL是否正确？**
   ```
   PDF URL设置为: http://localhost:9000/tender-pdf/...
   ```
   - URL应该以 `http://localhost:9000` 开头
   - 应该包含 MinIO 签名参数（`X-Amz-Signature=...`）

2. **PDF是否加载成功？**
   ```
   开始加载PDF: http://localhost:9000/...
   PDF加载成功，总页数: 21
   ```
   - 如果没有看到"PDF加载成功"，说明加载失败
   - 查看是否有CORS错误或网络错误

3. **可能的错误：**
   - **CORS错误**：MinIO未配置CORS，前端无法跨域访问
     ```
     Access to fetch at 'http://localhost:9000/...' from origin 'http://localhost:3000' 
     has been blocked by CORS policy
     ```
     **解决**：配置MinIO CORS（见下方）
   
   - **404错误**：PDF文件不存在
     **解决**：检查后端MinIO配置，确认文件已上传

### 2. 检查positions定位问题

查看Console中的positions数据：

1. **点击条款时查看：**
   ```
   条款点击: 0010-CLS-002 positions: [[0, 100, 200, 400, 220]]
   ```
   - `positions` 格式应为：`[[page_idx, x1, y1, x2, y2], ...]`
   - `page_idx` 是 0-based（第一页是0）
   - `x1, y1, x2, y2` 应该是PDF坐标（单位：points）

2. **查看高亮绘制：**
   ```
   绘制高亮，当前页: 1
   当前页匹配的positions: 1
   高亮 0: {pageIdx: 0, x1: 100, y1: 200, x2: 400, y2: 220}
   绘制坐标 0: {vx1: 150, vy1: 300, vx2: 600, vy2: 330, width: 450, height: 30}
   ```
   - 如果 `当前页匹配的positions: 0`，说明页码匹配失败
   - 如果坐标很大或很小，说明坐标转换有问题

3. **可能的问题：**
   - **没有positions数据**：后端未正确保存或返回positions
   - **坐标不对**：后端坐标转换有问题
   - **页码不匹配**：page_idx计算错误

## MinIO CORS配置

如果遇到CORS错误，需要配置MinIO：

### 方法1：使用mc命令（推荐）

```bash
# 1. 配置mc连接
mc alias set local http://localhost:9000 minioadmin minioadmin

# 2. 设置CORS
mc admin config set local api \
  cors_allow_origin="http://localhost:3000,http://localhost:8000"

# 3. 重启MinIO
mc admin service restart local
```

### 方法2：使用MinIO Console

1. 访问 http://localhost:9001
2. 登录（minioadmin/minioadmin）
3. Settings → API → CORS Allowed Origins
4. 添加：`http://localhost:3000,http://localhost:8000`
5. Save并重启

## 坐标系统说明

### 后端（MinerU → PDF坐标）

后端已经将MinerU的归一化坐标（0-1000）转换为PDF页面坐标：

- **原点**：左上角 (0, 0)
- **单位**：points（1 point ≈ 1/72 英寸）
- **坐标**：`[page_idx, x1, y1, x2, y2]`
  - `page_idx`：页码（0-based）
  - `x1, y1`：左上角坐标
  - `x2, y2`：右下角坐标

### 前端（PDF → Canvas）

前端需要将PDF坐标映射到Canvas：

```javascript
const vx1 = x1 * scale.value  // PDF坐标 × 缩放比例
const vy1 = y1 * scale.value
const vx2 = x2 * scale.value
const vy2 = y2 * scale.value
```

## 检查API返回数据

### 1. 检查PDF URL

访问：`http://localhost:8000/api/pdf/YOUR_TASK_ID`

应该返回：
```json
{
  "status": "success",
  "task_id": "...",
  "file_name": "...",
  "minio_url": "http://localhost:9000/tender-pdf/...",
  "proxy_url": "/tender-minio/tender-pdf/...",
  "message": "PDF文件URL获取成功（24小时有效）"
}
```

### 2. 检查条款数据

访问：`http://localhost:8000/api/tasks/YOUR_TASK_ID/clauses/all`

应该返回条款数组，每个条款应有：
```json
{
  "matrix_id": "0010-CLS-002",
  "original_text": "...",
  "positions": [[0, 100.5, 200.3, 400.2, 220.8]],
  ...
}
```

### 3. 检查文档树

访问：`http://localhost:8000/api/task/YOUR_TASK_ID`

应该返回任务信息，包含 `document_tree.structure`

## 常见问题排查

### Q: PDF完全不显示，没有任何错误

**检查：**
1. Canvas元素是否存在？（检查Elements面板）
2. CSS是否隐藏了Canvas？
3. PDF URL是否为空？

### Q: PDF加载很慢

**原因：**
- MinIO网络延迟
- PDF文件很大
- CDN的PDF.js worker加载慢

**解决：**
- 本地安装pdf.js-dist的worker文件
- 优化MinIO网络

### Q: 高亮框位置不对

**检查：**
1. 后端返回的positions坐标是否正确
2. 页码（page_idx）是否匹配
3. 缩放比例（scale）是否计算正确

### Q: 点击条款没有反应

**检查：**
1. Console中是否有"条款点击"日志
2. positions数据是否存在
3. `jumpToPosition`方法是否被调用

## 联系支持

如果以上方法都无法解决问题，请提供：

1. 浏览器Console的完整日志
2. Network面板中API请求的响应数据
3. 具体的错误信息截图
