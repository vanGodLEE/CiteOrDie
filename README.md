# CiteOrDie - 智能文档条款提取系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.0+-brightgreen.svg)](https://vuejs.org/)

> 🚀 基于 LangGraph 和 MinerU 的智能文档条款提取系统，自动解析PDF文档、识别结构、提取可执行条款并生成结构化矩阵。

## ✨ 特性

- 🤖 **智能解析**: 自动识别文档结构、表格、图片和文本
- 📊 **结构化提取**: 提取条款的7个维度（type, actor, action, object, condition, deadline, metric）
- ⚡ **并行处理**: 多节点并发提取，充分利用LLM并发能力
- 🎯 **精准定位**: 自动定位每个条款在原文PDF中的精确位置
- 📈 **质量评估**: 提供解析置信度、原文抽取成功率等质量指标
- 🔌 **多LLM支持**: 支持OpenAI、DeepSeek、Qwen等多种LLM提供商

## 🏗️ 技术架构

- **工作流编排**: LangGraph
- **PDF解析**: MinerU + PageIndex
- **后端框架**: FastAPI
- **前端框架**: Vue 3 + Element Plus
- **对象存储**: MinIO
- **数据库**: SQLite

## 📋 系统要求

- Python 3.10+
- Node.js 18+
- MinIO（对象存储，用于PDF文件管理）

## 💡 推荐配置

**LLM模型选择**：

本系统需要处理长文档和复杂结构，**强烈推荐使用长上下文模型**以获得最佳效果：

| 推荐模型 | 上下文长度 | 优势 | 提供商 |
|---------|-----------|------|--------|
| **qwen-max-latest** | 32K | 综合性能强，中文友好 | 阿里云 |
| **qwen-long** | 1M | 超长上下文，适合大文档 | 阿里云 |
| gpt-4o | 128K | 性能稳定 | OpenAI |
| deepseek-chat | 64K | 价格实惠 | DeepSeek |

> 💡 **提示**：长上下文模型能更好地理解文档全局结构，显著提升条款提取的准确性和完整性。

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/CiteOrDie.git
cd CiteOrDie
```

### 2. 后端设置

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置LLM API密钥
```

### 3. 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 4. 安装和启动MinIO

**为什么需要MinIO？**
- MinIO用作对象存储，管理上传的PDF文件和解析结果
- 提供文件的持久化存储和高效访问
- 支持预签名URL，方便前端直接访问PDF文件

**安装MinIO：**

```bash
# Windows
# 1. 下载: https://dl.min.io/server/minio/release/windows-amd64/minio.exe
# 2. 创建数据目录
mkdir D:\minio-data

# 3. 启动MinIO
minio.exe server D:\minio-data --console-address ":9001"

# Linux/macOS
# 1. 下载
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio

# 2. 创建数据目录
mkdir -p ~/minio-data

# 3. 启动MinIO
./minio server ~/minio-data --console-address ":9001"
```

**首次使用：**
1. 访问 MinIO 控制台：http://localhost:9001
2. 使用默认账号登录：`minioadmin` / `minioadmin`
3. 创建存储桶：`tender-pdf`（或在 `.env` 中配置的名称）
4. MinIO 会自动处理文件的上传、存储和访问

> 💡 **提示**：数据存储在 `minio-data` 目录，重启电脑后数据不会丢失。

### 5. 启动后端

```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate

uvicorn app.api.main:app --reload --port 8000
```

### 6. 访问应用

- 前端界面: http://localhost:3000
- 后端API文档: http://localhost:8000/docs
- MinIO控制台: http://localhost:9001 (minioadmin/minioadmin)

## ⚙️ 配置说明

### 环境变量配置 (backend/.env)

```bash
# LLM配置（必需）
LLM_API_KEY=your_api_key_here
LLM_API_BASE=https://api.openai.com/v1

# 模型配置
STRUCTURIZER_MODEL=gpt-4o
TEXT_FILLER_MODEL=gpt-4o-mini
SUMMARY_MODEL=gpt-4o-mini
EXTRACTOR_MODEL=gpt-4o
VISION_MODEL=gpt-4o
FALLBACK_MODELS=gpt-4o-mini,gpt-3.5-turbo

# MinIO配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=tender-pdf
MINIO_SECURE=false
```

### LLM提供商配置

#### 通义千问 Qwen（推荐，长上下文）⭐

**最佳选择**：qwen-max-latest 或 qwen-long

```bash
LLM_API_KEY=sk-xxxxx
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

# 推荐配置 - 长上下文模型
STRUCTURIZER_MODEL=qwen-max-latest     # 32K上下文
TEXT_FILLER_MODEL=qwen-max-latest
SUMMARY_MODEL=qwen-plus                # 经济型选择
EXTRACTOR_MODEL=qwen-max-latest        # 条款提取核心
VISION_MODEL=qwen-vl-max               # 图表识别

# 或使用超长上下文版本（处理大文档）
# EXTRACTOR_MODEL=qwen-long             # 1M上下文
```

**获取API密钥**：https://dashscope.console.aliyun.com/

**优势**：
- ✅ 超长上下文（32K-1M）
- ✅ 中文理解能力强
- ✅ 性价比高
- ✅ 响应速度快

#### OpenAI（稳定可靠）

```bash
LLM_API_KEY=sk-xxxxx
LLM_API_BASE=https://api.openai.com/v1

STRUCTURIZER_MODEL=gpt-4o
TEXT_FILLER_MODEL=gpt-4o-mini
EXTRACTOR_MODEL=gpt-4o                 # 128K上下文
VISION_MODEL=gpt-4o
```

#### DeepSeek（经济实惠）

```bash
LLM_API_KEY=sk-xxxxx
LLM_API_BASE=https://api.deepseek.com/v1

EXTRACTOR_MODEL=deepseek-chat          # 64K上下文
```

> **💡 性能对比**：
> - **qwen-max-latest**: 最佳中文文档处理能力，32K上下文
> - **qwen-long**: 适合超大文档（100+页），1M上下文
> - **gpt-4o**: 综合性能强，128K上下文
> - **deepseek-chat**: 价格最低，64K上下文

## 📚 项目结构

```
CiteOrDie/
├── backend/                  # 后端项目
│   ├── app/                  # 应用代码
│   │   ├── api/              # API路由
│   │   ├── nodes/            # LangGraph节点
│   │   ├── services/         # 业务服务
│   │   ├── db/               # 数据库模型
│   │   └── utils/            # 工具函数
│   ├── pageindex/            # PDF结构解析
│   ├── requirements.txt      # Python依赖
│   └── .env.example          # 环境变量模板
├── frontend/                 # 前端项目
│   ├── src/                  # 源代码
│   │   ├── components/       # Vue组件
│   │   ├── views/            # 页面
│   │   └── api/              # API客户端
│   ├── package.json          # Node依赖
│   └── index.html
├── docs/                     # 文档目录
├── README.md                 # 本文档
├── LICENSE                   # MIT许可证
└── CONTRIBUTING.md           # 贡献指南
```

## 🔧 开发指南

### 后端开发

```bash
# 运行测试
pytest tests/

# 代码格式化
black app/

# 类型检查
mypy app/
```

### 前端开发

```bash
cd frontend

# 开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览构建
npm run preview
```

## 📖 API文档

启动后端服务后访问：http://localhost:8000/docs

主要接口：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/analyze` | POST | 上传PDF并分析 |
| `/api/tasks` | GET | 获取任务列表 |
| `/api/task/{task_id}` | GET | 获取任务详情 |
| `/api/task/{task_id}` | DELETE | 删除任务 |
| `/api/task/{task_id}/progress` | GET (SSE) | 获取任务进度 |
| `/api/task/{task_id}/export` | GET | 导出为Excel |

## 🤝 贡献指南

欢迎贡献代码！请查看 [CONTRIBUTING.md](CONTRIBUTING.md)

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 📊 性能指标

- **解析速度**: ~30秒/10页文档（取决于LLM响应速度）
- **并发处理**: 最多4个章节并行提取
- **支持文档**: PDF（最大100MB）
- **提取准确率**: >90%（使用长上下文模型）

> **💡 提示**：使用 qwen-max-latest 或 qwen-long 等长上下文模型可显著提升大文档的处理质量。

## 🔍 故障排查

### 常见问题

**Q: MinIO连接失败？**
```bash
# 1. 检查MinIO是否运行
curl http://localhost:9000/minio/health/live

# 2. 检查端口是否被占用
netstat -ano | findstr "9000"    # Windows
lsof -i :9000                    # Linux/macOS

# 3. 重启MinIO
# Windows
minio.exe server D:\minio-data --console-address ":9001"

# Linux/macOS
./minio server ~/minio-data --console-address ":9001"

# 4. 检查环境变量配置
# 确保 backend/.env 中的 MINIO_ENDPOINT 正确
MINIO_ENDPOINT=localhost:9000
```

**Q: MinIO存储桶不存在？**
- 访问 http://localhost:9001 登录MinIO控制台
- 点击 "Buckets" → "Create Bucket"
- 创建名为 `tender-pdf` 的存储桶（或与 `.env` 中配置一致的名称）

**Q: LLM API调用失败？**
```bash
# 检查API密钥
cat .env | grep LLM_API_KEY

# 测试API连接
curl -H "Authorization: Bearer $LLM_API_KEY" \
  https://api.openai.com/v1/models
```

**Q: 前端无法访问后端？**
```bash
# 1. 检查后端是否运行
curl http://localhost:8000/health

# 2. 检查前端API配置
# frontend/src/api/index.js 中的 API_BASE_URL

# 3. 检查CORS设置
# backend/app/api/main.py 中的 CORS 配置
```

**Q: 长文档处理效果不好？**
- 建议使用长上下文模型：`qwen-max-latest`（32K）或 `qwen-long`（1M）
- 对于100页以上的文档，强烈推荐 `qwen-long`
- 长上下文模型能更好地理解文档全局结构，提升提取准确性

**Q: 模型选择建议？**

| 文档大小 | 推荐模型 | 原因 |
|---------|---------|------|
| <20页 | qwen-plus, gpt-4o-mini | 经济实惠 |
| 20-50页 | qwen-max-latest, gpt-4o | 平衡性能和成本 |
| 50-100页 | qwen-max-latest | 32K上下文足够 |
| >100页 | qwen-long | 1M超长上下文 |

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 工作流编排
- [MinerU](https://github.com/opendatalab/MinerU) - PDF解析
- [FastAPI](https://fastapi.tiangolo.com/) - Web框架
- [Vue.js](https://vuejs.org/) - 前端框架
- [Element Plus](https://element-plus.org/) - UI组件库

## 📮 联系方式

- **Issues**: https://github.com/YOUR_USERNAME/CiteOrDie/issues
- **Discussions**: https://github.com/YOUR_USERNAME/CiteOrDie/discussions
- **Email**: your-email@example.com

---

⭐ 如果这个项目对你有帮助，请给个Star！

## 📸 预览

<img src="docs/images/screenshot-upload.png" width="45%"/> <img src="docs/images/screenshot-result.png" width="45%"/>

---

**开发中**: 我们正在积极开发新功能，欢迎贡献想法和代码！
