# CiteOrDie - 智能文档条款提取系统

## 项目简介

这是一个基于 LangGraph 和 MinerU 的智能文档条款提取系统，能够自动解析PDF文档，识别和提取可执行条款，并生成结构化的条款矩阵。

**适用文档类型**：招标书、合同、合规文档、SOP、标准规范、政策文件、协议等各类包含条款的文档。

## 核心功能

- **智能文档解析**: 使用 MinerU 精准识别文档结构、表格、图片和文本
- **结构化提取**: 自动识别文档章节，提取可执行条款的7个维度（type, actor, action, object, condition, deadline, metric）
- **并行处理**: 多节点并发提取条款，充分利用LLM并发能力
- **智能定位**: 自动定位每个条款在原文PDF中的精确位置
- **质量评估**: 提供解析置信度、原文抽取成功率等质量指标
- **多LLM支持**: 支持OpenAI、DeepSeek、Qwen等多种LLM提供商

## 技术架构

- **工作流编排**: LangGraph (支持并行节点和状态管理)
- **PDF解析**: MinerU (本地部署)
- **LLM推理**: OpenAI API / DeepSeek (支持Structured Output)
- **Web框架**: FastAPI
- **数据模型**: Pydantic v2

### 支持的LLM提供商

- ✅ **OpenAI** - gpt-4o系列
- ✅ **DeepSeek** - deepseek-chat (更便宜，中文友好)

### 工作流程

```
PDF文档 → PageIndex解析文档结构 → MinerU完整解析
                                    ↓
                        并行填充各节点原文
                                    ↓
                        并行提取条款（文本+视觉）
                                    ↓
                        汇总、去重、定位
                                    ↓
                        结构化条款矩阵（JSON）
```

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，配置以下必要项：
# 1. LLM API密钥（OpenAI或DeepSeek，至少配置一个）
# 2. MinIO配置（如使用非默认配置）
# 3. 其他可选配置
```

**重要配置说明**：
- `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY`: 必须配置至少一个LLM提供商
- `MINIO_ENDPOINT`: MinIO服务地址，默认`localhost:9000`
- `MINIO_BUCKET`: 存储桶名称，默认`document-pdf`

### 3. 安装和启动MinIO（对象存储）

```bash
# 使用Docker启动MinIO
docker run -d \
  -p 9000:9000 \
  -p 9001:9001 \
  --name minio \
  minio/minio server /data --console-address ":9001"

# 或下载二进制文件：https://min.io/download
```

访问 http://localhost:9001 登录MinIO控制台（默认账号：minioadmin/minioadmin），创建存储桶`document-pdf`。

### 4. 运行开发服务器

```bash
uvicorn app.api.main:app --reload --port 8000
```

### 5. 访问API文档

打开浏览器访问: http://localhost:8000/docs

查看交互式API文档，可以直接在浏览器中测试所有接口。

## 项目结构

```
TenderAnalysis/
├── app/
│   ├── core/
│   │   ├── states.py       # 核心数据模型和State定义
│   │   ├── graph.py        # LangGraph工作流定义
│   │   └── config.py       # 配置管理
│   ├── services/
│   │   ├── pdf_parser.py   # MinerU集成服务
│   │   └── llm_service.py  # OpenAI调用封装
│   ├── nodes/
│   │   ├── planner.py      # Planner节点
│   │   ├── extractor.py    # Worker节点
│   │   └── auditor.py      # Auditor节点
│   └── api/
│       └── main.py         # FastAPI入口
├── tests/
│   └── mock_data/
│       └── sample_tender.json  # Mock MinerU输出
└── temp/                   # 临时文件目录
```

## API使用示例

### 上传文档并开始分析

```bash
curl -X POST "http://localhost:8000/api/analyze" \
  -F "file=@your_document.pdf"
```

返回任务ID，系统开始异步处理。

### 实时监控进度（SSE）

```bash
curl -N "http://localhost:8000/api/stream/{task_id}"
```

通过Server-Sent Events实时接收处理进度。

### 查询分析结果

```bash
# 获取任务信息和文档树
curl "http://localhost:8000/api/task/{task_id}"

# 获取所有提取的条款
curl "http://localhost:8000/api/tasks/{task_id}/clauses/all"

# 获取PDF文件URL
curl "http://localhost:8000/api/pdf/{task_id}"
```

## 条款数据模型

每个条款包含**结构化7维度 + 溯源信息**：

### 结构化字段（核心）
1. **type** (条款类型): `obligation`(义务) | `requirement`(需求) | `prohibition`(禁止) | `deliverable`(交付物) | `deadline`(截止时间) | `penalty`(惩罚) | `definition`(定义)
2. **actor** (执行主体): `party_a`(甲方) | `party_b`(乙方) | `provider`(提供方) | `client`(客户方) | `system`(系统) | 等
3. **action** (执行动作): `submit`(提交) | `provide`(提供) | `ensure`(确保) | `comply`(遵守) | 等
4. **object** (作用对象): `document`(文档) | `feature`(功能) | `KPI`(指标) | 等
5. **condition** (触发条件): 如"合同签订后"、"验收通过时"
6. **deadline** (时间要求): 具体日期或相对时间
7. **metric** (量化指标): 具体的数量、标准等

### 溯源信息
- `matrix_id`: 条款唯一ID
- `original_text`: 原文
- `section_id` / `section_title`: 所属章节
- `page_number`: 页码
- `positions`: PDF中的精确位置坐标（用于高亮显示）
- `image_caption` / `table_caption`: 图片/表格描述（如有）

## MinerU安装

MinerU是本项目的核心PDF解析引擎，提供高精度的文档结构识别。

### 使用pip安装（推荐）

```bash
pip install mineru[all]==2.7.1
```

### 下载模型文件

```bash
# 下载MinerU所需的AI模型
python -m magic_pdf.tools.download_models
```

### 验证安装

```bash
magic-pdf --version
```

更多信息请参考：https://github.com/opendatalab/MinerU

## 功能特性

- [x] PageIndex文档结构解析
- [x] MinerU完整PDF解析（文本、图片、表格）
- [x] LangGraph多节点并行工作流
- [x] 7维度结构化条款提取
- [x] 精确条款位置定位
- [x] 质量评估报告
- [x] 任务历史管理和删除
- [x] 文件上传幂等性（SHA256去重）
- [x] RESTful API + SSE实时推送
- [x] 支持多种LLM提供商
- [ ] Web前端界面（Vue3，独立仓库）
- [ ] 更多文档类型适配
- [ ] 批量处理和导出

## 项目结构

```
CiteOrDie/
├── app/
│   ├── core/              # 核心配置和工作流
│   │   ├── config.py      # 配置管理
│   │   ├── graph.py       # LangGraph工作流定义
│   │   └── states.py      # 数据模型
│   ├── nodes/             # LangGraph节点
│   │   ├── pageindex_parser.py      # PageIndex解析
│   │   ├── mineru_parser.py         # MinerU解析
│   │   ├── text_filler.py           # 原文填充
│   │   ├── pageindex_enricher.py    # 条款提取
│   │   ├── auditor.py               # 汇总去重
│   │   └── requirement_locator.py   # 位置定位
│   ├── services/          # 业务服务
│   ├── api/               # FastAPI路由
│   ├── db/                # 数据库模型和操作
│   └── utils/             # 工具函数
├── pageindex/             # PageIndex模块
├── data/                  # 数据库文件
├── logs/                  # 日志文件
├── temp/                  # 临时文件
└── tests/                 # 测试

<system_reminder>
The user is aware that particularly difficult tasks will take a long time and might require multiple context windows.
You do not need to ask the user for permission to continue working on a task, even if you feel like it might not make sense.
Just continue working on the task until it is complete.
You have 1 unfinished TODO(s).
Complete them and update their status to 'completed' using the todo_write tool when finished.
DO NOT STOP with unfinished todos, unless you absolutely need user input.
Found 1 TODO(s):
1. [in_progress] 重写README.md为通用文档系统 (ID: update-readme)
</system_reminder>```

## 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 如何贡献

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

### 报告问题

如果发现bug或有功能建议，请在GitHub Issues中提交。

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 工作流编排框架
- [MinerU](https://github.com/opendatalab/MinerU) - PDF解析引擎
- [PageIndex](https://github.com/Starry-OvO/page-index) - 文档结构分析
- [FastAPI](https://fastapi.tiangolo.com/) - Web框架

## 联系方式

如有问题或合作意向，欢迎通过以下方式联系：

- 提交 [GitHub Issue](https://github.com/yourusername/CiteOrDie/issues)
- 发起 [Discussion](https://github.com/yourusername/CiteOrDie/discussions)
