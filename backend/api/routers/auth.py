# 认证API路由 - 注册/登录
import datetime
import bcrypt
import jwt
from fastapi import APIRouter, HTTPException

from api.schemas.auth import AuthRequest
from infrastructure.database.session import SessionLocal
from infrastructure.database.models import User
from infrastructure.database.mapper import BaseMapper
from config.settings import settings

router = APIRouter()


def _create_token(user: User) -> str:
    """生成 JWT，有效期 7 天"""
    payload = {
        "user_id": user.id,
        "username": user.username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/register")
def register(req: AuthRequest):
    """注册新用户，返回 JWT token"""
    db = SessionLocal()
    try:
        mapper = BaseMapper(User, db)
        existing = mapper.list_by_field("username", req.username)
        if existing:
            raise HTTPException(status_code=409, detail="Username already exists")

        user = User(
            username=req.username,
            password_hash=bcrypt.hashpw(
                req.password.encode('utf-8'), bcrypt.gensalt()
            ).decode('utf-8'),
        )
        mapper.save(user)
        return {"token": _create_token(user)}
    finally:
        db.close()


@router.post("/login")
def login(req: AuthRequest):
    """登录，返回 JWT token"""
    db = SessionLocal()
    try:
        mapper = BaseMapper(User, db)
        users = mapper.list_by_field("username", req.username)
        if not users or not bcrypt.checkpw(
            req.password.encode('utf-8'),
            users[0].password_hash.encode('utf-8')
        ):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        return {"token": _create_token(users[0])}
    finally:
        db.close()
