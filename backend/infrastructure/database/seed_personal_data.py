# 个人动态数据导入脚本
# 用法：python -m infrastructure.database.seed_personal_data [--reset]
# 读取 backend/data/personal_data/*.json 写入 MySQL；--reset 先清空 5 张表再导入
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text

from config.settings import PROJECT_ROOT
from infrastructure.database.init_db import init_database
from infrastructure.database.models import (
    Employee, LeaveBalance, LeaveRequest, AttendanceRecord, EquipmentBorrow,
)
from infrastructure.database.session import SessionLocal

DATA_DIR = PROJECT_ROOT / "data" / "personal_data"

# 文件 -> 目标模型 映射（顺序保证 employees 先导入）
_SOURCES = [
    ("employees.json", Employee),
    ("leave_balances.json", LeaveBalance),
    ("leave_requests.json", LeaveRequest),
    ("attendance_records.json", AttendanceRecord),
    ("equipment_borrows.json", EquipmentBorrow),
]


def _load(name: str) -> list:
    """读取 JSON 种子文件，缺失/空文件返回空列表"""
    path = DATA_DIR / name
    if not path.exists():
        print(f"[warn] 缺少种子文件: {path}")
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_user_id(db, username: str):
    """按用户名解析 users.id，未注册返回 None"""
    return db.execute(
        text("SELECT id FROM users WHERE username = :u"), {"u": username}
    ).scalar()


def _seed_employees(db, rows: list) -> dict:
    """导入员工档案，并同步 users.role（支持管理员账号）"""
    mapping = {}  # username -> employee.id
    for row in rows:
        uid = _resolve_user_id(db, row["user_username"])
        if uid is None:
            print(f"[warn] 用户不存在，跳过员工: {row.get('name')} ({row['user_username']})")
            continue
        emp = Employee(
            user_id=uid,
            emp_no=row["emp_no"],
            name=row["name"],
            department=row["department"],
            position=row["position"],
            rank=row["rank"],
            hire_date=date.fromisoformat(row["hire_date"]),
            workstation=row.get("workstation"),
            status=row.get("status", "active"),
        )
        db.add(emp)
        db.flush()  # 先取到自增 id
        mapping[row["user_username"]] = emp.id
        # 同步角色（若种子数据声明了 role）
        role = row.get("role")
        if role:
            db.execute(
                text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid}
            )
            print(f"[ok] 设置角色 {role}: {row['user_username']}")
    return mapping


def _seed_domain(db, rows: list, mapping: dict, build):
    """通用导入：按 username 绑定 employee_id 后插入"""
    count = 0
    for row in rows:
        emp_id = mapping.get(row["user_username"])
        if emp_id is None:
            print(f"[warn] 员工未导入，跳过: {row['user_username']}")
            continue
        db.add(build(emp_id, row))
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="导入个人动态种子数据")
    parser.add_argument("--reset", action="store_true", help="先清空 5 张表再导入")
    args = parser.parse_args()

    # 1. 确保库和表存在（复用 init_db 的建表逻辑）
    init_database()

    db = SessionLocal()
    try:
        if args.reset:
            for _, model in reversed(_SOURCES):
                db.execute(text(f"DELETE FROM `{model.__tablename__}`"))
            print("[ok] 已清空 5 张表")

        # 2. 导入员工档案（含角色同步）
        emp_rows = _load("employees.json")
        mapping = _seed_employees(db, emp_rows)
        db.commit()
        print(f"[ok] 员工档案 {len(emp_rows)} 条")

        # 3. 导入其余 4 张表
        n = _seed_domain(db, _load("leave_balances.json"), mapping,
                         lambda e, r: LeaveBalance(
                             employee_id=e, year=r["year"], total_days=r["total_days"],
                             used_days=r["used_days"], remaining_days=r["remaining_days"],
                             carryover_days=r.get("carryover_days", 0.0)))
        print(f"[ok] 年假余额 {n} 条")

        n = _seed_domain(db, _load("leave_requests.json"), mapping,
                         lambda e, r: LeaveRequest(
                             employee_id=e, leave_type=r["leave_type"],
                             start_date=date.fromisoformat(r["start_date"]),
                             end_date=date.fromisoformat(r["end_date"]),
                             days=r["days"], reason=r.get("reason"),
                             status=r["status"], current_approver=r.get("current_approver"),
                             approval_progress=r.get("approval_progress")))
        print(f"[ok] 请假申请 {n} 条")

        n = _seed_domain(db, _load("attendance_records.json"), mapping,
                         lambda e, r: AttendanceRecord(
                             employee_id=e, date=date.fromisoformat(r["date"]),
                             status=r["status"], remark=r.get("remark")))
        print(f"[ok] 考勤记录 {n} 条")

        n = _seed_domain(db, _load("equipment_borrows.json"), mapping,
                         lambda e, r: EquipmentBorrow(
                             employee_id=e, equipment_name=r["equipment_name"],
                             borrow_time=datetime.fromisoformat(r["borrow_time"]),
                             due_time=datetime.fromisoformat(r["due_time"]),
                             return_time=datetime.fromisoformat(r["return_time"]) if r.get("return_time") else None,
                             status=r["status"], deposit=r.get("deposit", 0.0)))
        print(f"[ok] 设备借用 {n} 条")

        db.commit()
        print("[ok] 个人动态数据导入完成")
    finally:
        db.close()


if __name__ == "__main__":
    main()
