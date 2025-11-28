# 数据库设计文档

## 📊 架构概览

### 双重存储策略

```
┌─────────────────────────────────────────────────────────┐
│                    内存存储 (task_store)                  │
│  • 用途：SSE实时推送，快速访问当前任务状态                 │
│  • 生命周期：任务运行期间                                 │
│  • 特点：速度快，支持并发                                 │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  SQLite持久化 (tender_analysis.db)       │
│  • 用途：历史记录、复盘分析、需求复用                      │
│  • 生命周期：永久存储                                     │
│  • 特点：可查询，可分析，支持全文搜索                      │
└─────────────────────────────────────────────────────────┘
```

---

## 🗄️ 表结构设计

### 1. tasks - 任务主表

记录每次分析任务的元数据和状态。

| 字段 | 类型 | 说明 | 索引 |
|------|------|------|------|
| task_id | String(36) | 主键，UUID | PK |
| file_name | String(255) | 原始文件名 | |
| file_size | Integer | 文件大小（字节） | |
| pdf_path | String(500) | PDF存储路径 | |
| use_mock | Integer | 是否使用Mock数据 0/1 | |
| status | String(20) | 任务状态 | idx_task_status |
| progress | Float | 进度百分比 0-100 | |
| current_message | String(500) | 当前状态消息 | |
| error_message | Text | 错误信息 | |
| total_sections | Integer | 筛选出的章节数 | |
| total_requirements | Integer | 提取的需求总数 | |
| created_at | DateTime | 任务创建时间 | idx_task_created_at |
| started_at | DateTime | 开始执行时间 | |
| completed_at | DateTime | 完成时间 | |

**业务意义**：
- 任务追踪：查看历史分析任务
- 状态监控：pending → running → completed/failed
- 性能分析：completed_at - started_at = 执行时长
- 统计分析：成功率、平均提取需求数

---

### 2. task_logs - 任务日志表

记录SSE推送的所有消息，用于复盘和错误排查。

| 字段 | 类型 | 说明 | 索引 |
|------|------|------|------|
| id | Integer | 主键，自增 | PK |
| task_id | String(36) | 外键 → tasks | idx_log_task_id |
| log_level | String(10) | 日志级别 info/debug/warning/error | |
| progress | Float | 当时的进度百分比 | |
| message | Text | 日志消息 | |
| created_at | DateTime | 日志时间 | idx_log_created_at |

**业务意义**：
- 故障排查：查看失败任务的详细日志
- 性能分析：识别耗时步骤
- 流程复盘：重现任务执行过程

**查询示例**：
```sql
-- 查看某个任务的错误日志
SELECT * FROM task_logs 
WHERE task_id = 'xxx' AND log_level = 'error'
ORDER BY created_at;

-- 查看最慢的步骤
SELECT message, AVG(created_at - LAG(created_at) OVER (ORDER BY id)) as avg_duration
FROM task_logs
GROUP BY message;
```

---

### 3. sections - 章节表

记录每次分析中筛选出的关键章节。

| 字段 | 类型 | 说明 | 索引 |
|------|------|------|------|
| id | Integer | 主键，自增 | PK |
| task_id | String(36) | 外键 → tasks | idx_section_task_id |
| section_id | String(50) | 章节编号（如 SEC_130） | |
| title | String(500) | 章节标题 | idx_section_title |
| reason | Text | 为什么选择这个章节 | |
| priority | Integer | 优先级 | |
| start_page | Integer | 起始页码 | |
| end_page | Integer | 结束页码 | |
| start_index | Integer | 在content_list中的起始索引 | |
| created_at | DateTime | 创建时间 | |

**业务意义**：
- 标题分析：哪些标题容易被筛选
- 模式识别：识别常见的需求章节模式
- 优化Planner：基于历史数据优化筛选规则

**查询示例**：
```sql
-- 查看最常被选中的章节标题
SELECT title, COUNT(*) as count
FROM sections
GROUP BY title
ORDER BY count DESC
LIMIT 20;

-- 查看某次任务筛选出的章节
SELECT section_id, title, priority, start_page
FROM sections
WHERE task_id = 'xxx'
ORDER BY priority;
```

---

### 4. requirements - 需求表

存储提取的需求矩阵，支持后续查询和复用。

| 字段 | 类型 | 说明 | 索引 |
|------|------|------|------|
| id | Integer | 主键，自增 | PK |
| task_id | String(36) | 外键 → tasks | idx_req_task_id |
| matrix_id | String(50) | 需求唯一ID | idx_req_matrix_id |
| section_id | String(50) | 章节编号 | idx_req_section_id |
| section_title | String(500) | 章节标题 | |
| page_number | Integer | 页码 | |
| requirement | Text | 需求内容 | |
| original_text | Text | 原文 | |
| response_suggestion | Text | 应答方向 | |
| risk_warning | Text | 风险提示 | |
| notes | Text | 备注 | |
| created_at | DateTime | 创建时间 | |

**业务意义**：
- 需求复用：查找历史相似需求
- 全文搜索：按关键词搜索需求
- 知识积累：构建需求知识库
- 分析报告：导出需求矩阵

**查询示例**：
```sql
-- 搜索包含"性能"的所有需求
SELECT task_id, section_title, requirement, page_number
FROM requirements
WHERE requirement LIKE '%性能%'
LIMIT 50;

-- 统计某个章节类型的需求数量
SELECT section_title, COUNT(*) as req_count
FROM requirements
GROUP BY section_title
ORDER BY req_count DESC;
```

---

## 🔗 关系图

```
┌─────────────┐
│    Task     │ 1
├─────────────┤
│ task_id (PK)│◄──────────┐
│ file_name   │            │
│ status      │            │
│ progress    │            │
└─────────────┘            │
       │                   │
       │ 1                 │
       │                   │
       │ *                 │ *
       │                   │
┌──────▼──────┐      ┌────▼────────┐
│  TaskLog    │      │   Section   │
├─────────────┤      ├─────────────┤
│ id (PK)     │      │ id (PK)     │
│ task_id (FK)│      │ task_id (FK)│
│ message     │      │ section_id  │
│ progress    │      │ title       │
└─────────────┘      └─────────────┘
       
       │
       │ 1
       │
       │ *
       │
┌──────▼──────────┐
│  Requirement    │
├─────────────────┤
│ id (PK)         │
│ task_id (FK)    │
│ matrix_id       │
│ requirement     │
│ original_text   │
└─────────────────┘
```

---

## 📡 API接口

### 查询API (GET)

#### 1. 获取任务列表
```http
GET /api/tasks?status=completed&limit=50&offset=0
```

**响应示例**：
```json
[
  {
    "task_id": "xxx",
    "file_name": "招标文件.pdf",
    "status": "completed",
    "progress": 100.0,
    "total_sections": 15,
    "total_requirements": 42,
    "created_at": "2025-11-27T14:00:00",
    "completed_at": "2025-11-27T14:05:00"
  }
]
```

#### 2. 获取任务详情
```http
GET /api/tasks/{task_id}
```

#### 3. 获取任务日志（复盘）
```http
GET /api/tasks/{task_id}/logs
```

**响应示例**：
```json
[
  {
    "id": 1,
    "log_level": "info",
    "progress": 15.0,
    "message": "正在识别文档标题...",
    "created_at": "2025-11-27T14:00:10"
  },
  {
    "id": 2,
    "log_level": "info",
    "progress": 30.0,
    "message": "已筛选出 113 个技术需求章节",
    "created_at": "2025-11-27T14:00:45"
  }
]
```

#### 4. 获取任务筛选的章节
```http
GET /api/tasks/{task_id}/sections
```

#### 5. 获取任务提取的需求
```http
GET /api/tasks/{task_id}/requirements
```

#### 6. 搜索需求（跨任务）
```http
GET /api/requirements/search?keyword=性能&limit=50
```

---

## 🛠️ 工程实践

### 1. 索引优化

```python
# 任务查询优化
__table_args__ = (
    Index("idx_task_status", "status"),      # WHERE status = ?
    Index("idx_task_created_at", "created_at"), # ORDER BY created_at
)

# 日志查询优化
Index("idx_log_task_id", "task_id"),  # JOIN on task_id
Index("idx_log_created_at", "created_at"),  # 时序查询

# 章节查询优化
Index("idx_section_task_id", "task_id"),
Index("idx_section_title", "title"),  # GROUP BY title

# 需求查询优化
Index("idx_req_task_id", "task_id"),
Index("idx_req_matrix_id", "matrix_id"),  # 唯一需求查询
Index("idx_req_section_id", "section_id"),  # 按章节筛选
```

### 2. 事务管理

```python
# Repository层使用Session上下文管理
db = get_db_session()
try:
    # 批量插入
    SectionRepository.batch_create_sections(db, task_id, sections_data)
    RequirementRepository.batch_create_requirements(db, task_id, requirements_data)
    db.commit()
finally:
    db.close()
```

### 3. 数据完整性

- 外键约束：保证数据关联正确
- 级联删除：删除任务时自动删除关联数据
- 非空约束：关键字段必须填写

### 4. 性能优化

- **批量插入**：使用 `db.add_all()` 而非多次 `db.add()`
- **连接池**：SQLite使用StaticPool避免锁竞争
- **索引覆盖**：常用查询字段都建立索引
- **分页查询**：使用 `limit` 和 `offset` 避免大结果集

---

## 📈 数据分析示例

### 1. 系统性能分析

```sql
-- 平均执行时长
SELECT 
    AVG((julianday(completed_at) - julianday(started_at)) * 24 * 60) as avg_minutes,
    COUNT(*) as total_tasks
FROM tasks
WHERE status = 'completed';

-- 失败率统计
SELECT 
    status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM tasks), 2) as percentage
FROM tasks
GROUP BY status;
```

### 2. 需求热点分析

```sql
-- 最常见的章节标题
SELECT 
    section_title,
    COUNT(*) as req_count
FROM requirements
GROUP BY section_title
ORDER BY req_count DESC
LIMIT 10;

-- 平均每个任务提取的需求数
SELECT AVG(total_requirements) as avg_req_per_task
FROM tasks
WHERE status = 'completed';
```

### 3. 故障排查

```sql
-- 查找失败任务的错误模式
SELECT 
    error_message,
    COUNT(*) as occurrences
FROM tasks
WHERE status = 'failed'
GROUP BY error_message
ORDER BY occurrences DESC;
```

---

## 🔐 安全性考虑

1. **SQL注入防护**：使用ORM参数绑定
2. **文件路径验证**：防止路径遍历攻击
3. **数据清理**：定期清理过期任务
4. **备份策略**：定期备份SQLite文件

---

## 📦 数据库文件位置

```
TenderAnalysis/
├── data/                          # 数据目录
│   └── tender_analysis.db         # SQLite数据库文件
├── app/
│   └── db/
│       ├── database.py            # 数据库连接
│       ├── models.py              # ORM模型
│       └── repositories.py        # 数据访问层
└── DATABASE.md                    # 本文档
```

---

## 🚀 快速开始

### 1. 启动服务（自动初始化数据库）

```bash
python -m uvicorn app.api.main:app --reload
```

### 2. 查看API文档

访问：http://localhost:8000/docs

### 3. 查询示例

```bash
# 获取最近10个任务
curl http://localhost:8000/api/tasks?limit=10

# 获取任务详情
curl http://localhost:8000/api/tasks/{task_id}

# 搜索需求
curl http://localhost:8000/api/requirements/search?keyword=性能
```

---

## 📝 未来扩展

1. **全文搜索**：集成FTS5支持中文全文检索
2. **数据可视化**：提供Dashboard展示统计图表
3. **导出功能**：支持导出Excel/Word格式
4. **版本管理**：支持需求矩阵的版本控制
5. **协作功能**：多用户标注和审核

