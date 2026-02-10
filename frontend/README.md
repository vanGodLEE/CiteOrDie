# CiteOrDie Frontend

可执行条款抽取系统 - 前端界面

## 技术栈

- Vue 3
- Vite
- Element Plus
- PDF.js
- Axios
- Vue Router
- Pinia

## 安装

```bash
cd D:\dev\CiteOrDieFrontend
npm install
```

## 运行

```bash
npm run dev
```

访问 http://localhost:3000

## 功能特性

### 1. 文档上传
- 支持拖拽上传PDF文件
- 实时显示上传进度
- SSE实时推送分析进度

### 2. 结果展示（三栏布局）

**左侧 - PDF查看器**
- 显示原始PDF文档
- 支持翻页、缩放
- 高亮显示选中的条款位置

**中间 - 文档树**
- 层级展示文档结构
- 显示每个章节的条款数量
- 点击章节定位到PDF位置

**右侧 - 条款列表**
- 显示所有提取的条款
- 7维结构化展示：
  - type: 条款类型
  - actor: 执行主体
  - action: 执行动作
  - object: 作用对象
  - condition: 触发条件
  - deadline: 时间要求
  - metric: 量化指标
- 点击条款定位到PDF原文

### 3. 历史记录
- 查看所有分析任务
- 筛选任务状态
- 快速查看历史结果

### 4. 交互功能
- 点击文档树节点 → 定位PDF + 高亮显示
- 点击条款 → 定位PDF原文 + 高亮显示
- 导出Excel格式的条款矩阵

## 项目结构

```
src/
├── api/              # API接口
├── components/       # 公共组件
│   ├── PDFViewer.vue      # PDF查看器
│   ├── DocumentTree.vue   # 文档树
│   └── ClauseList.vue     # 条款列表
├── views/            # 页面
│   ├── Home.vue           # 首页
│   ├── Upload.vue         # 上传页
│   ├── Result.vue         # 结果页
│   └── History.vue        # 历史记录
├── router/           # 路由配置
├── styles/           # 全局样式
├── App.vue
└── main.js
```

## API接口说明

后端地址：http://localhost:8000

主要接口：
- `POST /api/analyze` - 上传文件并开始分析
- `GET /api/progress/{task_id}` - SSE进度推送
- `GET /api/task/{task_id}` - 获取任务详情
- `GET /api/tasks/{task_id}/clauses/all` - 获取所有条款
- `GET /api/pdf/{task_id}` - 获取PDF访问URL
- `GET /api/tasks` - 获取任务列表
- `GET /api/download/excel/{task_id}` - 下载Excel

## 开发说明

### 添加新功能
1. 在 `src/components/` 创建新组件
2. 在 `src/views/` 创建新页面
3. 在 `src/router/index.js` 添加路由
4. 在 `src/api/index.js` 添加API方法

### 样式定制
- 全局样式在 `src/styles/index.scss`
- Element Plus主题色已设置为蓝紫渐变
- 所有组件支持响应式布局

## 构建生产版本

```bash
npm run build
```

构建产物在 `dist/` 目录

## License

MIT
