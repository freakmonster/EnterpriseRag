# 个人动态数据查询服务层（含员工/管理员权限隔离）
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import and_

from infrastructure.database.models import (
    Employee, LeaveBalance, LeaveRequest, AttendanceRecord, EquipmentBorrow,
)
from infrastructure.database.session import SessionLocal


class EmployeeInfo(BaseModel):
    """员工档案信息（工龄由后端计算）"""
    name: str
    emp_no: str
    department: str
    position: str
    rank: str
    hire_date: str
    tenure_years: int          # 工龄（整年）
    workstation: Optional[str]
    status: str


class LeaveSummary(BaseModel):
    """年假余额 + 请假记录"""
    year: int
    total_days: float
    used_days: float
    remaining_days: float
    carryover_days: float
    requests: List[dict]


class AttendanceSummary(BaseModel):
    """考勤统计 + 明细"""
    month: str
    late_count: int
    early_leave_count: int
    absent_count: int
    no_check_count: int
    records: List[dict]


class EquipmentSummary(BaseModel):
    """设备借用明细"""
    records: List[dict]


def _extract(text: Optional[str], key: str, aliases: tuple, dflt) -> str:
    """按别名精确匹配规范化参数，未匹配返回默认值"""
    if not text:
        return dflt
    lowered = text.strip()
    for a in aliases:
        if lowered == a:
            return key
    return dflt


def _to_employee(emp: Employee) -> dict:
    """员工实体 -> 字典（工龄按入职日期整年计算）"""
    return {
        "name": emp.name,
        "emp_no": emp.emp_no,
        "department": emp.department,
        "position": emp.position,
        "rank": emp.rank,
        "hire_date": emp.hire_date.isoformat(),
        "tenure_years": _tenure_years(emp.hire_date),
        "workstation": emp.workstation,
        "status": emp.status,
    }


def _tenure_years(hire_date: date) -> int:
    """计算工龄（整年）"""
    today = date.today()
    years = today.year - hire_date.year
    if (today.month, today.day) < (hire_date.month, hire_date.day):
        years -= 1
    return years


def resolve_employee(identity: dict, target: Optional[str] = None, name_key: str = "name") -> Optional[Employee]:
    """权限隔离核心：按身份解析目标员工实体。

    - 普通员工：忽略 target，强制返回本人档案
    - 管理员：target 为空查本人；非空按姓名/工号查询
    """
    user_id = identity.get("user_id")
    role = identity.get("role", "user")
    db = SessionLocal()
    try:
        # 先按当前登录账号解析本人
        employee = None
        if user_id:
            try:
                employee = db.query(Employee).filter(Employee.user_id == int(user_id)).first()
            except (TypeError, ValueError):
                employee = None

        # 管理员可跨用户查询
        if role == "admin" and target and target.strip():
            keyword = target.strip()
            employee = (
                db.query(Employee)
                .filter((Employee.name == keyword) | (Employee.emp_no == keyword))
                .first()
            )
            if employee is None:
                return None
        return employee
    finally:
        db.close()


def get_employee_info(identity: dict, target: Optional[str] = None) -> Optional[dict]:
    """查询员工档案信息"""
    employee = resolve_employee(identity, target)
    return _to_employee(employee) if employee else None


def get_leave_summary(identity: dict, target: Optional[str] = None, year: int = 0) -> Optional[dict]:
    """查询年假余额与请假记录/审批进度"""
    employee = resolve_employee(identity, target)
    if employee is None:
        return None
    year = year or date.today().year
    db = SessionLocal()
    try:
        balance = (
            db.query(LeaveBalance)
            .filter(and_(LeaveBalance.employee_id == employee.id, LeaveBalance.year == year))
            .first()
        )
        balance_dict = None
        if balance:
            balance_dict = {
                "year": balance.year,
                "total_days": balance.total_days,
                "used_days": balance.used_days,
                "remaining_days": balance.remaining_days,
                "carryover_days": balance.carryover_days,
            }
        # 返回该年度申请及审批中的申请（便于展示审批进度）
        requests = [
            {
                "leave_type": r.leave_type,
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(),
                "days": r.days,
                "status": r.status,
                "current_approver": r.current_approver,
                "approval_progress": r.approval_progress,
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
            }
            for r in db.query(LeaveRequest)
            .filter(LeaveRequest.employee_id == employee.id)
            .filter(
                (LeaveRequest.start_date >= date(year, 1, 1))
                | (LeaveRequest.status == "processing")
            )
            .order_by(LeaveRequest.start_date.desc())
            .limit(10)
            .all()
        ]
        return {"employee": _to_employee(employee), "balance": balance_dict, "requests": requests}
    finally:
        db.close()


def get_attendance_summary(identity: dict, target: Optional[str] = None, month: str = "") -> Optional[dict]:
    """查询考勤统计与明细（默认本月）"""
    employee = resolve_employee(identity, target)
    if employee is None:
        return None
    month = month or date.today().strftime("%Y-%m")
    try:
        start = date.fromisoformat(f"{month}-01")
    except ValueError:
        return None
    # 月末：下月第一天减一天
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    db = SessionLocal()
    try:
        rows = (
            db.query(AttendanceRecord)
            .filter(
                and_(
                    AttendanceRecord.employee_id == employee.id,
                    AttendanceRecord.date >= start,
                    AttendanceRecord.date < end,
                )
            )
            .order_by(AttendanceRecord.date)
            .all()
        )
        counts = {"late": 0, "early_leave": 0, "absent": 0, "no_check": 0}
        records = []
        for r in rows:
            if r.status in counts:
                counts[r.status] += 1
            records.append(
                {"date": r.date.isoformat(), "status": r.status, "remark": r.remark}
            )
        return {
            "employee": _to_employee(employee),
            "month": month,
            "late_count": counts["late"],
            "early_leave_count": counts["early_leave"],
            "absent_count": counts["absent"],
            "no_check_count": counts["no_check"],
            "records": records,
        }
    finally:
        db.close()


def get_equipment_summary(identity: dict, target: Optional[str] = None) -> Optional[dict]:
    """查询设备借用信息"""
    employee = resolve_employee(identity, target)
    if employee is None:
        return None
    db = SessionLocal()
    try:
        rows = (
            db.query(EquipmentBorrow)
            .filter(EquipmentBorrow.employee_id == employee.id)
            .order_by(EquipmentBorrow.borrow_time.desc())
            .all()
        )
        records = [
            {
                "equipment_name": r.equipment_name,
                "borrow_time": r.borrow_time.isoformat(),
                "due_time": r.due_time.isoformat(),
                "return_time": r.return_time.isoformat() if r.return_time else None,
                "status": r.status,
                "deposit": r.deposit,
            }
            for r in rows
        ]
        return {"employee": _to_employee(employee), "records": records}
    finally:
        db.close()
