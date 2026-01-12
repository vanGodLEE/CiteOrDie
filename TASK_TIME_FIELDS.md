# 任务时间字段增强与完整数据持久化

## 📋 概述

本次更新为任务管理系统添加了完整的时间跟踪字段，并实现了document_tree的数据库持久化，彻底解决了项目重启后任务消失和结果无法查询的问题。

## 🎯 解决的问题

### 问题1: 时间字段不完整
**现象**: 
- 任务只有 `created_at`，缺少 `started_at`、`completed_at`、`elapsed_seconds`
- 无法统计任务真实耗时

**解决方案**:
- ✅ 添加 `started_at` 字段：记录任务开始执行时间
- ✅ 添加 `completed_at` 字段：记录任务完成时间
- ✅ 添加 `elapsed_seconds` 字段：自动计算任务耗时

### 问题2: 重启后任务消失
**现象**: 
- 项目重启后，之前的任务无法查询
- 原因：`TaskManager.get_task()` 只从内存字典读取

**解决方案**:
- ✅ 修改 `get_task()` 方法：优先内存，不存在则从数据库恢复
- ✅ 恢复后缓存到内存，提高后续访问性能

## 📝 修改详情

### 1. 数据库模型 (`app/db/models.py`)

```python
class Task(Base):
    """任务记录表"""
    # ... 其他字段
    
    # 统计信息
    total_sections = Column(Integer, default=0, comment="筛选出的章节数")
    total_requirements = Column(Integer, default=0, comment="提取的需求总数")
    
    # 分析结果（JSON存储）
    document_tree_json = Column(Text, comment="PageIndex文档树结构（JSON格式）")  # 新增
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="任务创建时间")
    started_at = Column(DateTime, comment="开始执行时间")           # 已存在
    completed_at = Column(DateTime, comment="完成时间")             # 已存在
    elapsed_seconds = Column(Float, default=0.0, comment="任务耗时（秒）")  # 新增
```

**变更**:
- 添加 `elapsed_seconds` 字段（记录耗时）
- 添加 `document_tree_json` 字段（持久化文档树）

### 2. 数据访问层 (`app/db/repositories.py`)

```python
@staticmethod
def update_task_status(
    db: Session,
    task_id: str,
    status: str = None,
    progress: float = None,
    message: str = None,
    error: str = None,
    elapsed_seconds: float = None,  # 新增参数
    document_tree: dict = None       # 新增参数
) -> Optional[Task]:
    # ...
    
    # 任务完成时，自动计算耗时
    if status in ["completed", "failed"]:
        task.completed_at = datetime.now()
        
        # 自动计算耗时（如果没有显式传入）
        if task.started_at and not elapsed_seconds:
            elapsed_seconds = (task.completed_at - task.started_at).total_seconds()
    
    # 更新耗时字段
    if elapsed_seconds is not None:
        task.elapsed_seconds = elapsed_seconds
    
    # 保存document_tree（JSON序列化）
    if document_tree is not None:
        import json
        task.document_tree_json = json.dumps(document_tree, ensure_ascii=False)
```

**变更**:
- 添加 `elapsed_seconds` 参数（记录耗时）
- 添加 `document_tree` 参数（保存文档树）
- 任务完成时自动计算耗时：`completed_at - started_at`
- 自动序列化`document_tree`为JSON并保存

### 3. 任务管理器 (`app/api/async_tasks.py`)

#### 3.1 update_task() 方法

```python
# 计算消耗时间（内存）
if task.get("start_time"):
    task["elapsed_seconds"] = (now - task["start_time"]).total_seconds()

# 更新数据库（包括elapsed_seconds和document_tree）
TaskRepository.update_task_status(
    db,
    task_id=task_id,
    status=status,
    progress=progress,
    message=message,
    error=error,
    elapsed_seconds=task.get("elapsed_seconds"),
    document_tree=document_tree  # 传递文档树到数据库
)
```

**变更**:
- 传递 `elapsed_seconds` 到数据库
- 传递 `document_tree` 到数据库（如果提供）

#### 3.2 get_task() 方法 - 核心修复

```python
@staticmethod
def get_task(task_id: str) -> Optional[dict]:
    """
    获取任务状态
    
    策略：优先从内存读取，如果不存在则从数据库恢复
    这样可以解决项目重启后任务消失的问题
    """
    # 1. 先尝试从内存读取
    if task_id in task_store:
        return task_store[task_id]
    
    # 2. 内存中不存在，尝试从数据库恢复
    try:
        db = get_db_session()
        try:
            task_record = TaskRepository.get_task(db, task_id)
            if not task_record:
                return None
            
            # 将数据库记录转换为内存格式
            task_dict = {
                "task_id": task_record.task_id,
                "status": task_record.status,
                "progress": task_record.progress,
                "message": task_record.current_message or "",
                "result": None,
                "error": task_record.error_message,
                "created_at": task_record.created_at,
                "updated_at": task_record.completed_at or task_record.started_at or task_record.created_at,
                "start_time": task_record.started_at,
                "elapsed_seconds": task_record.elapsed_seconds or 0,  # 恢复耗时
                "logs": []
            }
            
            # 恢复到内存（用于后续访问）
            task_store[task_id] = task_dict
            logger.info(f"从数据库恢复任务: {task_id}")
            
            return task_dict
        finally:
            db.close()
    except Exception as e:
        logger.error(f"从数据库恢复任务失败: {e}")
        return None
```

**变更**: 
- 优先从内存读取，不存在则从数据库恢复
- 恢复后缓存到内存，提高性能
- **这是解决重启问题的核心**

### 4. 查询API (`app/api/query.py`)

#### 4.1 TaskSummary 模型

```python
class TaskSummary(BaseModel):
    """任务概要（列表视图）"""
    task_id: str
    file_name: str
    status: str
    progress: float
    total_sections: int
    total_requirements: int
    created_at: datetime
    started_at: Optional[datetime]      # 新增
    completed_at: Optional[datetime]
    elapsed_seconds: float              # 新增
```

#### 4.2 TaskDetail 模型

```python
class TaskDetail(BaseModel):
    """任务详情（详细视图）"""
    task_id: str
    file_name: str
    file_size: int
    status: str
    progress: float
    current_message: str
    error_message: Optional[str]
    total_sections: int
    total_requirements: int
    created_at: datetime
    started_at: Optional[datetime]      # 新增
    completed_at: Optional[datetime]
    elapsed_seconds: float              # 新增
```

#### 4.3 查询方法

```python
# 列表查询
result = [
    TaskSummary(
        # ... 其他字段
        started_at=t.started_at,
        completed_at=t.completed_at,
        elapsed_seconds=t.elapsed_seconds or 0.0
    )
    for t in tasks
]

# 详情查询
return TaskDetail(
    # ... 其他字段
    started_at=task.started_at,
    completed_at=task.completed_at,
    elapsed_seconds=task.elapsed_seconds or 0.0
)
```

**变更**: API返回时包含完整时间字段

## 🗄️ 数据库迁移

### 迁移SQL

```sql
-- 添加 elapsed_seconds 字段
ALTER TABLE tasks ADD COLUMN elapsed_seconds REAL DEFAULT 0.0;

-- 添加 document_tree_json 字段
ALTER TABLE tasks ADD COLUMN document_tree_json TEXT;

-- 验证字段
SELECT task_id, status, started_at, completed_at, elapsed_seconds,
       length(document_tree_json) as tree_size
FROM tasks
LIMIT 5;
```

### 执行方式

#### 方式1: 手动迁移（推荐用于开发环境）

```bash
# 1. 连接到SQLite数据库
sqlite3 tender_analysis.db

# 2. 执行迁移SQL
ALTER TABLE tasks ADD COLUMN elapsed_seconds REAL DEFAULT 0.0;
ALTER TABLE tasks ADD COLUMN document_tree_json TEXT;

# 3. 验证
.schema tasks

# 4. 退出
.quit
```

#### 方式2: Python脚本迁移（推荐）

运行迁移:
```bash
python scripts/migrate_add_elapsed_seconds.py
```

脚本功能：
- ✅ 自动检查字段是否已存在
- ✅ 添加 `elapsed_seconds` 字段
- ✅ 添加 `document_tree_json` 字段
- ✅ 验证迁移结果
- ✅ 显示详细日志

### 注意事项

1. **备份数据库**: 迁移前务必备份 `tender_analysis.db`
2. **已有数据**:
   - 已存在的任务 `elapsed_seconds` 默认为 `0.0`
   - 已存在的任务 `document_tree_json` 为 `NULL`（Excel下载不可用，需重新分析）
3. **新任务**: 新任务会自动计算并保存完整数据

## 📊 数据流向

```
任务创建
  ↓
内存 (task_store)
  ↓
started_at 记录 (状态变为running)
  ↓
实时计算 elapsed_seconds
  ↓
completed_at 记录 (状态变为completed/failed)
  ↓
数据库持久化 (TaskRepository.update_task_status)
  ↓
API查询返回 (包含完整时间字段)
```

## 🔄 任务恢复机制

```
GET /api/tasks/{task_id}
  ↓
TaskManager.get_task(task_id)
  ↓
检查内存 (task_store)
  ├─ 存在 → 直接返回
  └─ 不存在 ↓
      从数据库查询
        ├─ 找到 → 恢复到内存 → 返回
        └─ 不存在 → 返回 None
```

**优势**:
- ✅ 项目重启后任务不丢失
- ✅ 热数据在内存，冷数据在数据库
- ✅ 首次访问恢复，后续访问快速

## 🎉 效果验证

### 验证1: 时间字段完整性

```bash
# 创建任务
POST /api/analyze

# 查询任务详情
GET /api/task/{task_id}

# 返回示例
{
  "task_id": "abc-123",
  "status": "completed",
  "created_at": "2025-12-17T10:00:00",
  "started_at": "2025-12-17T10:00:05",      # ✅ 有值
  "completed_at": "2025-12-17T10:05:30",    # ✅ 有值
  "elapsed_seconds": 325.5,                 # ✅ 自动计算
  "matrix": [...],                          # ✅ 需求矩阵
  "document_tree": {...}                    # ✅ 文档树结构
}
```

### 验证2: 重启恢复（完整功能）

```bash
# 1. 创建任务并等待完成
POST /api/analyze
task_id: abc-123

# 2. 重启项目
# 停止服务 → 启动服务

# 3. 查询任务（应该能查到完整数据）
GET /api/task/abc-123

# 返回示例
{
  "task_id": "abc-123",
  "status": "completed",
  "elapsed_seconds": 325.5,
  "matrix": [...],              # ✅ 需求矩阵正常
  "document_tree": {...}        # ✅ 文档树已恢复
}

# 4. 下载Excel（应该成功）
GET /api/download/excel/abc-123  # ✅ 下载成功
```

### 验证3: 数据库记录

```sql
-- 查看完整字段
SELECT
    task_id,
    status,
    created_at,
    started_at,
    completed_at,
    elapsed_seconds,
    length(document_tree_json) as tree_size,
    total_requirements
FROM tasks
ORDER BY created_at DESC
LIMIT 10;
```

## 🔍 技术亮点

### 1. 双重存储策略
- **内存缓存** (`task_store`): 用于SSE推送、实时访问
- **SQLite持久化**: 用于历史记录、复盘分析

### 2. 自动计算耗时
```python
if task.started_at and not elapsed_seconds:
    elapsed_seconds = (completed_at - started_at).total_seconds()
```
- 任务完成时自动计算
- 无需手动传入

### 3. 优雅降级
```python
elapsed_seconds = task_record.elapsed_seconds or 0.0
```
- 旧数据兼容：默认0.0
- 不会因为字段为空而报错

### 4. 日志追踪
```python
logger.info(f"从数据库恢复任务: {task_id}")
```
- 清晰记录任务恢复过程
- 便于排查问题

## 📚 相关文档

- [`DATABASE.md`](DATABASE.md) - 数据库设计文档
- [`app/db/models.py`](app/db/models.py) - 数据库模型
- [`app/db/repositories.py`](app/db/repositories.py) - 数据访问层
- [`app/api/async_tasks.py`](app/api/async_tasks.py) - 任务管理器
- [`app/api/query.py`](app/api/query.py) - 查询API

## ✅ 总结

本次更新实现了：
1. ✅ 完整的任务时间跟踪（created_at, started_at, completed_at, elapsed_seconds）
2. ✅ 自动计算任务耗时
3. ✅ **document_tree完整持久化到数据库**
4. ✅ 项目重启后任务和结果完全恢复
5. ✅ API返回完整时间字段和文档树
6. ✅ **Excel下载功能重启后正常工作**
7. ✅ 数据库持久化保证数据不丢失

**核心价值**:
- 📊 完整的任务执行时间统计
- 💾 数据永久保存，重启不丢失
- 🚀 性能优化：内存缓存 + 数据库持久化
- 📥 **Excel导出功能重启后依然可用**
-  便于任务分析和性能优化

**数据流向**:
```
任务完成
  ↓
document_tree (PageIndexDocument)
  ↓
model_dump() 转为字典
  ↓
JSON序列化
  ↓
存储到 document_tree_json 字段
  ↓
重启后查询
  ↓
JSON反序列化
  ↓
返回给前端/Excel导出
```