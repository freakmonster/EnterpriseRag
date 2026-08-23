# 个人动态数据查询工具（员工档案/年假请假/考勤/设备借用）
# 隐私隔离：普通员工只能查本人，管理员可查所有人
import json

from langchain_core.tools import tool

from config.settings import settings
from services import personal_data as svc
from services.security import get_identity


def _to_json(data) -> str:
    """序列化为 JSON 文本（保证中文可读）"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _not_found(identity: dict, target: str) -> str:
    """未命中档案时的提示（区分原因）"""
    if identity.get("role") == "admin" and target and target.strip():
        return f"未找到员工档案：{target.strip()}"
    return "未找到当前账号的员工档案，请先由管理员在人事系统中完成档案绑定"


@tool
def query_employee_profile(target: str = "") -> str:
    """查询员工的档案信息：姓名、工号、部门、岗位、职级、工龄、入职日期、工位。
    当用户询问"我的工位在哪里""我的工龄""我入职几年了""我的职级/部门"时使用。
    管理员可指定目标员工（姓名或工号）查询他人档案；普通用户忽略 target 只能查本人。

    Args:
        target: 目标员工姓名或工号；留空表示当前登录用户
    """
    if not settings.enable_personal_tools:
        return "个人数据查询功能未启用"
    identity = get_identity()
    info = svc.get_employee_info(identity, target)
    if info is None:
        return _not_found(identity, target)
    return _to_json({"employee": info})


@tool
def query_my_leave(target: str = "", year: int = 0) -> str:
    """查询员工的年假余额、请假记录与审批进度。
    当用户询问"我今年还有几天年假""我的年假还剩几天""我的请假审批到哪一步了""我今年请过几次假"时使用。
    管理员可指定目标员工（姓名或工号）；普通用户忽略 target 只能查本人。

    Args:
        target: 目标员工姓名或工号；留空表示当前登录用户
        year: 查询年度，0 表示当前年份
    """
    if not settings.enable_personal_tools:
        return "个人数据查询功能未启用"
    identity = get_identity()
    data = svc.get_leave_summary(identity, target, year)
    if data is None:
        return _not_found(identity, target)
    return _to_json(data)


@tool
def query_my_attendance(target: str = "", month: str = "") -> str:
    """查询员工的考勤记录与统计：迟到、早退、旷工、未打卡次数及明细。
    当用户询问"我这个月迟到几次""我的缺勤情况""我有哪些考勤异常"时使用。
    管理员可指定目标员工（姓名或工号）；普通用户忽略 target 只能查本人。

    Args:
        target: 目标员工姓名或工号；留空表示当前登录用户
        month: 查询月份，格式 YYYY-MM；留空表示本月
    """
    if not settings.enable_personal_tools:
        return "个人数据查询功能未启用"
    identity = get_identity()
    data = svc.get_attendance_summary(identity, target, month)
    if data is None:
        return _not_found(identity, target)
    return _to_json(data)


@tool
def query_my_equipment(target: str = "") -> str:
    """查询员工的设备领用与借用信息：设备名称、借用时间、应还时间、归还状态。
    当用户询问"我借的设备什么时候到期""我名下有哪些设备""我的设备归还了吗"时使用。
    管理员可指定目标员工（姓名或工号）；普通用户忽略 target 只能查本人。

    Args:
        target: 目标员工姓名或工号；留空表示当前登录用户
    """
    if not settings.enable_personal_tools:
        return "个人数据查询功能未启用"
    identity = get_identity()
    data = svc.get_equipment_summary(identity, target)
    if data is None:
        return _not_found(identity, target)
    return _to_json(data)
