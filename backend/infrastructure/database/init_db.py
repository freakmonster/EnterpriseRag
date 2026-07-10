"""
数据库初始化脚本：自动创建数据库和表
可通过 `python -m src.infrastructure.database.init_db` 独立运行
"""
from sqlalchemy import create_engine, text, inspect  # type: ignore

from config.settings import settings
from infrastructure.database.models import Base


def init_database():
    """
    1. 连接 MySQL（不指定数据库），创建数据库（如不存在）
    2. 连接目标数据库，自动创建所有表
    """
    # Step 1: 创建数据库（如不存在）
    root_url = (
        f"mysql+pymysql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}?charset=utf8mb4"
    )
    root_engine = create_engine(root_url, pool_pre_ping=True)
    with root_engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.db_name}` "
                f"DEFAULT CHARACTER SET utf8mb4"
            )
        )
        conn.commit()
    root_engine.dispose()
    print(f"[OK] 数据库 `{settings.db_name}` 已就绪")

    # Step 2: 创建所有表
    target_url = (
        f"mysql+pymysql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}?charset=utf8mb4"
    )
    target_engine = create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=target_engine)
    print("[OK] 所有表已创建")

    # 打印表清单
    inspector = inspect(target_engine)
    tables = inspector.get_table_names()
    print(f"[OK] 共 {len(tables)} 张表: {', '.join(tables)}")

    target_engine.dispose()


if __name__ == "__main__":
    print("=== 数据库初始化开始 ===")
    init_database()
    print("=== 数据库初始化完成 ===")
