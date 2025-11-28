# 智能招标书分析系统 (Intelligent Tender Analysis Agent)

## 项目简介

这是一个基于 LangGraph 的智能招标书分析系统，能够自动解析PDF招标文件，识别关键需求条款，并生成结构化的需求矩阵。

## 核心功能

- **智能文档解析**: 使用 MinerU 精准识别文档结构、表格和文本
- **战略规划**: Planner节点自动识别关键章节，过滤无关内容
- **并行提取**: 多个Worker节点并发提取需求条款
- **智能汇总**: Auditor节点去重、排序并生成最终需求矩阵

## 技术架构

- **工作流编排**: LangGraph (支持并行节点和状态管理)
- **PDF解析**: MinerU (本地部署)
- **LLM推理**: OpenAI API / DeepSeek (支持Structured Output)
- **Web框架**: FastAPI
- **数据模型**: Pydantic v2

### 支持的LLM提供商

- ✅ **OpenAI** - gpt-4o系列
- ✅ **DeepSeek** - deepseek-chat (更便宜，中文友好)

### 架构模式

```
PDF文档 → MinerU解析 → Planner(战略规划)
                           ↓
                    Map(并行Workers)
                           ↓
                    Auditor(综合校验)
                           ↓
                    需求矩阵(JSON)
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
cp .env.example .env
# 编辑 .env 文件，填入你的 OpenAI API Key
```

### 3. 运行开发服务器

```bash
# 使用Mock数据进行开发测试
uvicorn app.api.main:app --reload --port 8000
```

### 4. 访问API文档

打开浏览器访问: http://localhost:8000/docs

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

### 分析招标文档

```bash
curl -X POST "http://localhost:8000/analyze" \
  -F "file=@tender.pdf" \
  -F "use_mock=false"
```

### 响应格式

```json
{
  "status": "success",
  "requirements_count": 45,
  "matrix": [
    {
      "section_id": "3.1.2",
      "section_title": "数据库性能要求",
      "page_number": 15,
      "matrix_id": "3.1.2-REQ-001",
      "original_text": "数据库并发用户数应不少于1000个",
      "summary": "数据库支持1000+并发",
      "importance": "CRITICAL",
      "score_points": null,
      "keywords": ["数据库", "并发", "性能"],
      "suggested_evidence": "DEMO",
      "confidence": 0.95
    }
  ],
  "processing_time": 23.5
}
```

## 需求矩阵数据模型

每个需求条款包含四个维度：

### 1. 溯源维度 (Traceability)
- `section_id`: 章节编号
- `section_title`: 章节标题
- `page_number`: 页码

### 2. 需求维度 (Requirement)
- `matrix_id`: 需求唯一ID
- `original_text`: 需求原文
- `summary`: 需求归纳

### 3. 约束维度 (Constraints)
- `importance`: 重要性级别 (CRITICAL/SCORING/NORMAL)
- `score_points`: 评分项分值
- `keywords`: 关键词列表

### 4. 响应建议维度 (Response Hint)
- `suggested_evidence`: 建议的证明材料类型
- `confidence`: AI置信度

## MinerU集成

### 安装MinerU

```bash
# 克隆仓库
git clone https://github.com/opendatalab/MinerU.git
cd MinerU

# 创建conda环境
conda create -n mineru python=3.10
conda activate mineru

# 安装依赖
pip install -r requirements.txt

# 下载模型
python -m magic_pdf.tools.download_models

# 测试
magic-pdf -p test.pdf -o ./output
```

## 开发路线图

- [x] Phase 1: 项目初始化与领域建模
- [ ] Phase 2: PDF解析服务抽象
- [ ] Phase 3: LangGraph工作流构建
- [ ] Phase 4: Web API开发
- [ ] Phase 5: MinerU真实集成

## 贡献指南

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
