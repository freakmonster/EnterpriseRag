# 基础Mapper封装（类似MyBatis Plus）
from typing import TypeVar, Type, List, Optional, Any, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, Row, RowMapping

ModelType = TypeVar("ModelType")


class BaseMapper:
    """基础Mapper类，提供通用CRUD操作"""

    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def save(self, entity: ModelType) -> ModelType:
        """保存实体"""
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_by_id(self, id: int) -> Optional[ModelType]:
        """根据ID查询"""
        return self.db.get(self.model, id)

    def list_all(self) -> Sequence[Row[Any] | RowMapping | Any]:
        """查询所有"""
        return self.db.execute(select(self.model)).scalars().all()

    def list_by_field(self, field_name: str, value) -> Sequence[Row[Any] | RowMapping | Any]:
        """根据字段查询列表"""
        field = getattr(self.model, field_name)
        return self.db.execute(select(self.model).where(field == value)).scalars().all()

    def list_order_by(self, order_field: str, ascending: bool = True) -> Sequence[Row[Any] | RowMapping | Any]:
        """排序查询"""
        field = getattr(self.model, order_field)
        if not ascending:
            field = desc(field)
        return self.db.execute(select(self.model).order_by(field)).scalars().all()


class ChatHistoryMapper(BaseMapper):
    """ChatHistory Mapper"""

    def __init__(self, db: Session):
        from infrastructure.database.models import ChatHistory
        super().__init__(ChatHistory, db)

    def list_by_session_id(self, session_id: str):
        """根据会话ID查询，按创建时间升序"""
        from infrastructure.database.models import ChatHistory
        return self.db.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.asc())
        ).scalars().all()

    def list_session_ids_by_user_id(self, user_id: str):
        """获取用户的会话ID列表及标题，按最后消息时间倒序
        Returns: list of (session_id, title) tuples
        """
        from infrastructure.database.models import ChatHistory
        from sqlalchemy import func

        subquery = (
            select(
                ChatHistory.session_id,
                func.max(ChatHistory.created_at).label("last_time"),
                func.max(ChatHistory.title).label("title")
            )
            .where(ChatHistory.user_id == user_id)
            .group_by(ChatHistory.session_id)
            .subquery()
        )

        return self.db.execute(
            select(subquery.c.session_id, subquery.c.title)
            .order_by(desc(subquery.c.last_time))
        ).all()
