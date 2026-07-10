# 配额检查 Depends — RPM / 日请求数 / 日 Token 三层限流
# 配额按角色（user/vip）存储，Redis 热读取，DB 持久化
import json
from datetime import date, datetime, timedelta

from fastapi import HTTPException, Depends

from services.security import get_current_user
from config.quota_defaults import QUOTA_DEFAULTS
from infrastructure.cache.redis import redis_client
from infrastructure.database.session import SessionLocal
from infrastructure.database.models import User, RoleQuotaConfig
from infrastructure.database.mapper import BaseMapper


def _load_role_quota(role: str) -> dict:
    """从 Redis 读取角色配额，miss 时用默认值"""
    key = f"quota:config:{role}"
    raw = redis_client.get(key)
    if raw:
        return json.loads(raw)
    # fallback to defaults
    return dict(QUOTA_DEFAULTS.get(role, QUOTA_DEFAULTS["user"]))


def seed_quota_config():
    """启动时调用：从 DB 加载配额到 Redis，DB 无记录则从默认值初始化"""
    db = SessionLocal()
    try:
        mapper = BaseMapper(RoleQuotaConfig, db)
        configs = mapper.list_all()
        db_configs = {c.role: c for c in configs}
    finally:
        db.close()

    for role, defaults in QUOTA_DEFAULTS.items():
        if role in db_configs:
            c = db_configs[role]
            data = {"daily_requests": c.daily_requests, "daily_tokens": c.daily_tokens, "rpm_requests": c.rpm_requests}
        else:
            data = dict(defaults)
        redis_client.set(f"quota:config:{role}", json.dumps(data))
        print(f"[quota] seeded {role}: {data}")


async def check_quota(user_id: str = Depends(get_current_user)) -> dict:
    """检查用户配额，超额返回 429"""
    # 查用户角色
    db = SessionLocal()
    try:
        user_mapper = BaseMapper(User, db)
        user = user_mapper.get_by_id(int(user_id))
        role = user.role if user else "user"
    finally:
        db.close()

    quota = _load_role_quota(role)
    today = date.today().isoformat()

    # 1. RPM 检查
    rpm_key = f"ratelimit:rpm:{user_id}"
    rpm_count = redis_client.incr(rpm_key)
    if rpm_count == 1:
        redis_client.expire(rpm_key, 60)
    if rpm_count > quota["rpm_requests"]:
        raise HTTPException(status_code=429, detail=f"请求过于频繁，每分钟最多 {quota['rpm_requests']} 次")

    # 2. 日请求数检查
    req_key = f"quota:daily:req:{user_id}:{today}"
    req_count = redis_client.incr(req_key)
    if req_count == 1:
        tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        redis_client.expireat(req_key, tomorrow)
    if req_count > quota["daily_requests"]:
        raise HTTPException(status_code=429, detail=f"今日请求次数已用完（上限 {quota['daily_requests']} 次）")

    # 3. 日 Token 检查
    tok_key = f"quota:daily:tok:{user_id}:{today}"
    tok_used = int(redis_client.get(tok_key) or 0)
    if tok_used >= quota["daily_tokens"]:
        raise HTTPException(status_code=429, detail=f"今日 Token 额度已用完（上限 {quota['daily_tokens']}）")

    return {
        "role": role,
        "daily_requests_limit": quota["daily_requests"],
        "daily_requests_used": req_count,
        "daily_tokens_limit": quota["daily_tokens"],
        "daily_tokens_used": tok_used,
        "rpm_limit": quota["rpm_requests"],
    }


# ── 角色配额 CRUD（供 admin 路由调用） ──────────────────

def list_role_quotas() -> dict:
    """列出所有角色的配额配置（合并默认值 + DB 覆盖）"""
    db = SessionLocal()
    try:
        mapper = BaseMapper(RoleQuotaConfig, db)
        configs = mapper.list_all()
        result = {}
        for role, defaults in QUOTA_DEFAULTS.items():
            entry = {"role": role, "daily_requests": defaults["daily_requests"],
                     "daily_tokens": defaults["daily_tokens"], "rpm_requests": defaults["rpm_requests"],
                     "source": "default"}
            for c in configs:
                if c.role == role:
                    entry["daily_requests"] = c.daily_requests
                    entry["daily_tokens"] = c.daily_tokens
                    entry["rpm_requests"] = c.rpm_requests
                    entry["source"] = "custom"
                    break
            result[role] = entry
        return result
    finally:
        db.close()


def update_role_quota(role: str, daily_requests: int, daily_tokens: int, rpm_requests: int):
    """更新角色配额（写 DB + 更新 Redis）"""
    if role not in QUOTA_DEFAULTS:
        raise ValueError(f"无效角色: {role}")

    db = SessionLocal()
    try:
        mapper = BaseMapper(RoleQuotaConfig, db)
        configs = mapper.list_by_field("role", role)
        if configs:
            c = configs[0]
            c.daily_requests = daily_requests
            c.daily_tokens = daily_tokens
            c.rpm_requests = rpm_requests
            db.commit()
        else:
            mapper.save(RoleQuotaConfig(
                role=role, daily_requests=daily_requests,
                daily_tokens=daily_tokens, rpm_requests=rpm_requests,
            ))
    finally:
        db.close()

    redis_client.set(f"quota:config:{role}", json.dumps({
        "daily_requests": daily_requests,
        "daily_tokens": daily_tokens,
        "rpm_requests": rpm_requests,
    }))


def reset_role_quota(role: str):
    """重置角色配额为默认值"""
    if role not in QUOTA_DEFAULTS:
        raise ValueError(f"无效角色: {role}")

    db = SessionLocal()
    try:
        mapper = BaseMapper(RoleQuotaConfig, db)
        configs = mapper.list_by_field("role", role)
        if configs:
            db.delete(configs[0])
            db.commit()
    finally:
        db.close()

    defaults = QUOTA_DEFAULTS[role]
    redis_client.set(f"quota:config:{role}", json.dumps(dict(defaults)))
