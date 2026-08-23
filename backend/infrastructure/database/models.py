# 数据库模型
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON, Date, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ChatHistory(Base):
    """对话历史实体"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(50), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    title = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class User(Base):
    """用户实体"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    created_at = Column(DateTime, server_default=func.now())


class RoleQuotaConfig(Base):
    """角色配额配置（管理员可调）"""
    __tablename__ = "role_quota_config"

    role = Column(String(20), primary_key=True)
    daily_requests = Column(Integer, nullable=False)
    daily_tokens = Column(Integer, nullable=False)
    rpm_requests = Column(Integer, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LLMCallLog(Base):
    """LLM 调用日志"""
    __tablename__ = "llm_call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False)
    session_id = Column(String(128), nullable=False)
    model_name = Column(String(64), nullable=False)
    model_type = Column(String(20), nullable=False)
    node_type = Column(String(20), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    input_cache_hit_tokens = Column(Integer, default=0)   # 输入中命中缓存的 token 数（DeepSeek 计费区分）
    input_cache_miss_tokens = Column(Integer, default=0)  # 输入中未命中缓存的 token 数
    latency_ms = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    status = Column(String(10), default="success")
    error_msg = Column(String(256), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Employee(Base):
    """员工档案（绑定登录账号 user_id）"""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)  # 关联 users.id
    emp_no = Column(String(20), nullable=False, unique=True)            # 工号
    name = Column(String(50), nullable=False)                           # 姓名
    department = Column(String(50), nullable=False)                     # 部门
    position = Column(String(50), nullable=False)                       # 岗位
    rank = Column(String(20), nullable=False)                           # 职级
    hire_date = Column(Date, nullable=False)                            # 入职日期
    workstation = Column(String(100), nullable=True)                    # 工位，如 "A栋3F-305"
    status = Column(String(20), default="active")                       # 在职状态


class LeaveBalance(Base):
    """年度年假余额"""
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, nullable=False, index=True)
    year = Column(Integer, nullable=False)                              # 年度，如 2026
    total_days = Column(Float, nullable=False)                          # 当年额度（制度规定+折算）
    used_days = Column(Float, nullable=False, default=0.0)              # 已休
    remaining_days = Column(Float, nullable=False)                      # 剩余
    carryover_days = Column(Float, nullable=False, default=0.0)         # 上年度延期


class LeaveRequest(Base):
    """请假申请（含审批进度）"""
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, nullable=False, index=True)
    leave_type = Column(String(20), nullable=False)                     # annual/sick/personal/...
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Float, nullable=False)
    reason = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False)                         # processing/approved/rejected
    current_approver = Column(String(50), nullable=True)                # 当前审批人
    approval_progress = Column(String(200), nullable=True)              # 审批进度文本
    applied_at = Column(DateTime, server_default=func.now())


class AttendanceRecord(Base):
    """考勤记录"""
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, nullable=False, index=True)
    date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False)  # normal/late/early_leave/absent/no_check
    remark = Column(String(200), nullable=True)


class EquipmentBorrow(Base):
    """设备借用"""
    __tablename__ = "equipment_borrows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, nullable=False, index=True)
    equipment_name = Column(String(100), nullable=False)
    borrow_time = Column(DateTime, nullable=False)                      # 借用时间
    due_time = Column(DateTime, nullable=False)                         # 应还时间
    return_time = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)                         # borrowed/returned/overdue
    deposit = Column(Float, default=0.0)                                # 押金
