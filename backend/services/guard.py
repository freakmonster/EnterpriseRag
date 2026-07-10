# 提示词防注入守卫：正则预过滤 + LLM 语义判断
# 在 chat_service.py 中调用 check_message()，在图之前拦截
import json
import re
from langchain_core.messages import HumanMessage

from models.llm_providers.deepseek_client import create_llm
from models.prompts.system_prompts import GUARD_PROMPT, GUARD_REGEX_FALLBACK, GUARD_REGEX_REPLY_PROMPT


# ── 正则预过滤 ──────────────────────────────────────────

_INJECTION_PATTERNS = [
    # 英文注入
    r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|directives?)",
    r"(?i)forget\s+(everything|all)\s+(you\s+were\s+told|above)",
    r"(?i)you\s+are\s+now\s+(DAN|an?\s+unfiltered|a\s+different)",
    r"(?i)(act\s+as|pretend\s+to\s+be|role\s*play)\s+(a\s+different|an?\s+unethical)",
    r"(?i)(system\s*prompt|developer\s*(message|prompt))\s*(leak|reveal|display|show|print|输出|泄露)",
    r"(?i)jail\s*break",
    r"(?i)do\s+not\s+follow\s+(your\s+)?instructions",
    r"(?i)you\s+are\s+(a\s+)?(evil|malicious|unethical|immoral)",

    # 中文注入
    r"忽略(之前|上面|所有|一切)(的)?(指令|提示|规则|要求|对话)",
    r"忘记(之前|上面|一切|所有)(的)?(内容|对话|指令|规则)",
    r"从现在开始[你你]是",
    r"(泄露|输出|显示|告诉我)(你的)?(系统|预设)?(提示词|提示|指令|prompt)",
    r"不要(遵守|遵循|按照|理会)(你的)?(规则|指令|限制|约束)",
    r"扮演.*角色",
    r"越狱|脱缰|解除.*限制",

    # 分隔符滥用
    r"[=\-_]{20,}",
    r"<\|im_start\|>|<\|im_end\|>",
    r"\[system\]|\[/system\]|\[assistant\]|\[/assistant\]",
    r"<<SYS>>|<\/SYS>>",

    # 套取工具定义
    r"(列出|显示|告诉我|输出)(你(可以|能)使用的)?(所有)?(工具|函数|function|tool)",
]

_compiled = [re.compile(p) for p in _INJECTION_PATTERNS]


def _regex_check(text: str) -> str | None:
    for i, pattern in enumerate(_compiled):
        m = pattern.search(text)
        if m:
            return f"regex_{i}: {m.group()[:60]}"
    return None


def _generate_regex_reply(query: str) -> str:
    prompt = GUARD_REGEX_REPLY_PROMPT.format(query=query[:200])
    try:
        llm = create_llm(temperature=0.5)
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception:
        return GUARD_REGEX_FALLBACK


def check_message(message: str) -> tuple[bool, str | None]:
    """检查用户消息是否安全。

    Returns:
        (True, None) — 安全，可以正常处理
        (False, reply) — 不安全，reply 是自然拒答文本
    """
    # 1. 正则预过滤
    regex_hit = _regex_check(message)
    if regex_hit:
        reply = _generate_regex_reply(message)
        return False, reply

    # 2. LLM 语义判断
    try:
        llm = create_llm(temperature=0.5)
        prompt = GUARD_PROMPT.format(query=message)
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
        result = json.loads(raw)
    except (json.JSONDecodeError, KeyError):
        return False, GUARD_REGEX_FALLBACK

    if result.get("safe"):
        return True, None
    else:
        return False, result.get("reply", GUARD_REGEX_FALLBACK)
