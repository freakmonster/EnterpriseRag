# 角色默认配额
QUOTA_DEFAULTS = {
    "user": {
        "daily_requests": 100,
        "daily_tokens": 200_000,
        "rpm_requests": 10,
    },
    "vip": {
        "daily_requests": 500,
        "daily_tokens": 1_000_000,
        "rpm_requests": 30,
    },
}
