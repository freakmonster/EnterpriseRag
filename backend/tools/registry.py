# 工具层 — 统一工具导出
from config.settings import settings
from tools.retrieval_tools import simple_retrieve_policy, es_retrieve_policy, complex_retrieve_policy
from tools.skill_tools import view_file

tools = [simple_retrieve_policy, es_retrieve_policy, complex_retrieve_policy, view_file]

# 个人数据工具链路开关：关闭后只走 RAG 链路，与原有行为一致
if settings.enable_personal_tools:
    from tools.personal_tools import (
        query_employee_profile, query_my_leave, query_my_attendance, query_my_equipment,
    )
    tools += [query_employee_profile, query_my_leave, query_my_attendance, query_my_equipment]
