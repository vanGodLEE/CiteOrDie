"""
数据库连接和初始化

使用SQLite作为持久化存储
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session
from sqlalchemy.pool import NullPool
from pathlib import Path
from loguru import logger

from app.core.config import settings

# 创建Base类
Base = declarative_base()

# 数据库文件路径
DB_DIR = Path("data")
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "tender_analysis.db"

# 创建引擎
# check_same_thread=False: 允许多线程访问
# poolclass=NullPool: 每次都创建新连接，避免跨线程共享连接
# isolation_level="SERIALIZABLE": 使用串行化隔离级别，避免并发冲突
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={
        "check_same_thread": False,
        "timeout": 30  # 增加超时时间，避免锁等待
    },
    poolclass=NullPool,  # 关键：不使用连接池，每次创建新连接
    echo=False  # 设为True可以看到SQL语句
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    初始化数据库，创建所有表
    """
    logger.info(f"初始化数据库: {DB_PATH}")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库初始化完成")


def get_db():
    """
    获取数据库会话（依赖注入用）
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """
    获取数据库会话（直接使用）
    """
    return SessionLocal()

