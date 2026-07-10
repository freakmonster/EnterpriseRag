# 成本追踪统计查询
from datetime import date, datetime, timedelta

from infrastructure.database.session import engine
from sqlalchemy import text


def _parse_date_range(from_: str | None, to_: str | None) -> tuple[date, date]:
    """解析日期范围，默认最近 7 天"""
    if to_:
        end = datetime.strptime(to_, "%Y-%m-%d").date()
    else:
        end = date.today()
    if from_:
        start = datetime.strptime(from_, "%Y-%m-%d").date()
    else:
        start = end - timedelta(days=6)
    return start, end


def get_overview(from_: str | None = None, to: str | None = None) -> dict:
    """时段总览：活跃用户/会话/总调用/总成本"""
    start, end = _parse_date_range(from_, to)
    with engine.connect() as conn:
        r = conn.execute(text("""
            SELECT
                COUNT(DISTINCT user_id) AS active_users,
                COUNT(DISTINCT session_id) AS active_sessions,
                COUNT(*) AS total_calls,
                COALESCE(SUM(cost), 0) AS total_cost,
                COALESCE(SUM(input_tokens), 0) AS total_input,
                COALESCE(SUM(output_tokens), 0) AS total_output,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS error_count,
                COALESCE(AVG(latency_ms), 0) AS avg_latency
            FROM llm_call_logs
            WHERE created_at >= :start AND created_at < :end2
        """), {"start": start, "end2": end + timedelta(days=1)}).fetchone()
        return {
            "active_users": r[0], "active_sessions": r[1],
            "total_calls": r[2], "total_cost": round(float(r[3]), 4),
            "total_input_tokens": r[4], "total_output_tokens": r[5],
            "error_count": r[6], "avg_latency_ms": int(r[7] or 0),
        }


def get_trend(from_: str | None = None, to: str | None = None) -> dict:
    """每日趋势：按日期 + 模型类型聚合"""
    start, end = _parse_date_range(from_, to)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DATE(created_at) AS d, model_type,
                   COUNT(*) AS calls,
                   COALESCE(SUM(input_tokens), 0) AS itok,
                   COALESCE(SUM(output_tokens), 0) AS otok,
                   COALESCE(SUM(cost), 0) AS cost,
                   COALESCE(AVG(latency_ms), 0) AS avg_lat,
                   COUNT(DISTINCT user_id) AS users,
                   COUNT(DISTINCT session_id) AS sessions
            FROM llm_call_logs
            WHERE created_at >= :start AND created_at < :end2
            GROUP BY d, model_type
            ORDER BY d
        """), {"start": start, "end2": end + timedelta(days=1)}).fetchall()

        days = {}
        for row in rows:
            d = str(row[0])
            if d not in days:
                days[d] = {"date": d, "models": {}, "active_users": 0, "active_sessions": 0}
            days[d]["models"][row[1]] = {
                "calls": row[2], "input_tokens": row[3],
                "output_tokens": row[4], "cost": round(float(row[5]), 4),
                "avg_latency_ms": int(row[6] or 0),
            }
            days[d]["active_users"] = max(days[d]["active_users"], row[7])
            days[d]["active_sessions"] = max(days[d]["active_sessions"], row[8])

        return {"days": list(days.values())}


def get_trend_hourly() -> dict:
    """小时趋势：过去 24h"""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DATE_FORMAT(created_at, '%Y-%m-%d %H:00') AS h, model_type,
                   COUNT(*) AS calls,
                   COALESCE(SUM(input_tokens), 0) AS itok,
                   COALESCE(SUM(output_tokens), 0) AS otok,
                   COALESCE(SUM(cost), 0) AS cost,
                   COALESCE(AVG(latency_ms), 0) AS avg_lat
            FROM llm_call_logs
            WHERE created_at >= NOW() - INTERVAL 24 HOUR
            GROUP BY h, model_type
            ORDER BY h
        """)).fetchall()

        hours = {}
        for row in rows:
            h = row[0]
            if h not in hours:
                hours[h] = {"hour": h, "models": {}}
            hours[h]["models"][row[1]] = {
                "calls": row[2], "input_tokens": row[3],
                "output_tokens": row[4], "cost": round(float(row[5]), 4),
                "avg_latency_ms": int(row[6] or 0),
            }

        return {"hours": list(hours.values())}


def get_aggregation(from_: str | None = None, to: str | None = None) -> dict:
    """时段聚合：每用户/每会话平均"""
    start, end = _parse_date_range(from_, to)
    with engine.connect() as conn:
        u = conn.execute(text("""
            SELECT AVG(calls), AVG(itok), AVG(otok), AVG(cost), AVG(alat)
            FROM (
                SELECT user_id, COUNT(*) AS calls,
                       COALESCE(SUM(input_tokens), 0) AS itok,
                       COALESCE(SUM(output_tokens), 0) AS otok,
                       COALESCE(SUM(cost), 0) AS cost,
                       COALESCE(AVG(latency_ms), 0) AS alat
                FROM llm_call_logs
                WHERE created_at >= :start AND created_at < :end2
                GROUP BY user_id
            ) t
        """), {"start": start, "end2": end + timedelta(days=1)}).fetchone()

        s = conn.execute(text("""
            SELECT AVG(calls), AVG(itok), AVG(otok), AVG(cost), AVG(alat)
            FROM (
                SELECT session_id, COUNT(*) AS calls,
                       COALESCE(SUM(input_tokens), 0) AS itok,
                       COALESCE(SUM(output_tokens), 0) AS otok,
                       COALESCE(SUM(cost), 0) AS cost,
                       COALESCE(AVG(latency_ms), 0) AS alat
                FROM llm_call_logs
                WHERE created_at >= :start AND created_at < :end2
                GROUP BY session_id
            ) t
        """), {"start": start, "end2": end + timedelta(days=1)}).fetchone()

        return {
            "per_user": {
                "avg_calls": round(float(u[0] or 0), 1),
                "avg_input_tokens": int(u[1] or 0),
                "avg_output_tokens": int(u[2] or 0),
                "avg_cost": round(float(u[3] or 0), 4),
                "avg_latency_ms": int(u[4] or 0),
            },
            "per_session": {
                "avg_calls": round(float(s[0] or 0), 1),
                "avg_input_tokens": int(s[1] or 0),
                "avg_output_tokens": int(s[2] or 0),
                "avg_cost": round(float(s[3] or 0), 4),
                "avg_latency_ms": int(s[4] or 0),
            },
        }
