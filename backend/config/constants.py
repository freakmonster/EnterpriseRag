# 领域值对象 — 业务常量与值对象定义
from dataclasses import dataclass


@dataclass(frozen=True)
class Quota:
    """配额值对象"""
    daily_requests: int
    daily_tokens: int
    rpm_requests: int


# 记忆压缩阈值常量
MEMORY_COMPRESS_THRESHOLD = 20
MEMORY_KEEP_LAST_N = 6
SESSION_TITLE_MAX_LEN = 15
