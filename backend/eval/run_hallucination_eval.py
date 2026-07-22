"""
幻觉抑制策略评测脚本

对比四种配置在 Faithfulness（忠实度）和拒答准确率上的表现：
  A. 无防护 — 无 System Prompt，LLM 直接回答（无工具）
  B. 仅 Prompt — 防幻觉 System Prompt，但无检索工具
  C. Prompt + ReAct — System Prompt + ReAct 强制检索（无引用编号）
  D. 全量 — System Prompt + ReAct + 引用注入（当前生产环境）

评测指标：
  - 拒答准确率: 正则匹配拒答关键词（out_of_kb + trap 类型）
  - Faithfulness: LLM Judge 逐条对比源文档
  - 幻觉陈述数: verdict=unsupported 的 claims 总和

用法：
  cd backend
  python eval/run_hallucination_eval.py
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows SSL 兼容
import ssl as _ssl
_orig_load_certs = _ssl.SSLContext.load_default_certs
def _safe_load_certs(self, purpose=_ssl.Purpose.SERVER_AUTH):
    try:
        return _orig_load_certs(self, purpose)
    except _ssl.SSLError:
        pass
_ssl.SSLContext.load_default_certs = _safe_load_certs

os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
os.environ["CHROMA_SKIP_TELEMETRY"] = "true"

from langchain_core.messages import HumanMessage, SystemMessage

from models.llm_providers.deepseek_client import create_llm
from models.prompts.system_prompts import SYSTEM_PROMPT
from agents.workflows.support_agent import agent_graph
from tools.citation import init_citation_ctx
from retrieval.vectorstores.chroma_store import search_no_rerank
from retrieval.retrievers.bm25_retriever import bm25_search


# ═══════════════════════════════════════════════════
#  拒答检测（正则匹配，不依赖 LLM Judge）
# ═══════════════════════════════════════════════════

REFUSAL_PATTERNS = [
    r'不知道',
    r'不了解',
    r'没有相关',
    r'未找到',
    r'无法回答',
    r'抱歉',
    r'不包含',
    r'未提及',
    r'暂无',
    r'无明确规定',
    r'不在.*范围',
    r'请咨询',
    r'建议.*确认',
    r'无法提供',
]


def detect_refusal(answer: str) -> bool:
    """检查回答是否包含拒答关键词"""
    return any(re.search(pat, answer) for pat in REFUSAL_PATTERNS)


# ═══════════════════════════════════════════════════
#  LLM Judge — Faithfulness 评测
# ═══════════════════════════════════════════════════

JUDGE_PROMPT = """你是一个事实核查专家。请根据提供的【源文档】判断以下【AI 回答】是否包含幻觉内容（杜撰的、源文档中不存在的事实）。

## 判断规则
1. 找出 AI 回答中所有的**事实性陈述**（排除寒暄、免责声明、引导性语句如"让我为您查一下"）
2. 对于每个事实陈述，严格检查【源文档】中是否有原文支撑（语义相同即可，不需要逐字一致）
3. 源文档中**完全找不到**对应内容的陈述，标记为 unsupported（幻觉）
4. 如果 AI 回答明确表示"不知道"、"没有相关规定"或拒绝回答，且源文档确实没有相关内容 → total_claims=0, hallucinated_claims=0, overall_faithful=true
5. 如果源文档为空或只有"(本次检索未获取到相关内容)"，AI 回答却给出了具体答案 → 明显幻觉

## 源文档
{source_docs}

## AI 回答
{answer}

## 输出格式（严格 JSON，不要添加任何解释）
```json
{{
  "claims": [
    {{"statement": "事实陈述原文", "verdict": "supported|unsupported", "evidence": "源文档中的支撑原文（unsupported时填 无）"}}
  ],
  "total_claims": 数字,
  "hallucinated_claims": 数字,
  "overall_faithful": true或false
}}
```

注意：
- 如果 AI 回答了完全没有依据的内容，overall_faithful 必须是 false
- 如果 AI 回答是正确的拒答，total_claims=0, hallucinated_claims=0, overall_faithful=true
"""


def judge_answer(answer: str, source_docs: str) -> Dict:
    """用 LLM Judge 评估 Faithfulness，失败时降级为空（不扣分）"""
    judge_llm = create_llm(temperature=0.0)
    prompt = JUDGE_PROMPT.format(
        source_docs=source_docs[:8000],
        answer=answer[:4000],
    )

    try:
        response = judge_llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except Exception as e:
        print(f"  Judge 解析失败: {str(e)[:80]}")

    # 降级：不扣分
    return {
        "total_claims": 0, "hallucinated_claims": 0,
        "overall_faithful": True, "claims": []
    }


# ═══════════════════════════════════════════════════
#  加载数据
# ═══════════════════════════════════════════════════

def load_test_dataset() -> List[Dict]:
    path = Path(__file__).resolve().parent / "hallucination_test_dataset.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_source_docs(query: str) -> str:
    """检索相关源文档，作为 Judge 的 ground truth"""
    vec_results = search_no_rerank(query, top_k=5)
    bm25_results = bm25_search(query, top_k=5)

    seen = set()
    docs = []
    for r in vec_results + bm25_results:
        key = (r["metadata"]["file_name"], r["metadata"]["chunk_idx"])
        if key not in seen:
            seen.add(key)
            title = r["metadata"].get("title", r["metadata"]["file_name"])
            docs.append(f"[{title}]\n{r['content']}")

    return "\n\n---\n\n".join(docs[:5]) if docs else "（本次检索未获取到相关内容）"


# ═══════════════════════════════════════════════════
#  四组实验
# ═══════════════════════════════════════════════════

def run_group_a(cases: List[Dict]) -> List[Dict]:
    """A 组：无防护 — 无 System Prompt，无工具"""
    llm = create_llm(temperature=0.0)
    results = []
    for i, case in enumerate(cases):
        query = case["query"]
        print(f"  [{i+1}/{len(cases)}] {query[:40]}")
        try:
            response = llm.invoke([HumanMessage(content=query)])
            answer = response.content
        except Exception as e:
            answer = f"[ERROR] {e}"

        source_docs = get_source_docs(query)
        judge = judge_answer(answer, source_docs)
        refusal = detect_refusal(answer)

        results.append({
            "query": query, "type": case["type"],
            "expected": case.get("expected_behavior", ""),
            "answer": answer[:500], "judge": judge, "refusal_detected": refusal,
        })
    return results


def run_group_b(cases: List[Dict]) -> List[Dict]:
    """B 组：仅 Prompt — 防幻觉 System Prompt，无检索工具"""
    llm = create_llm(temperature=0.0)
    results = []
    for i, case in enumerate(cases):
        query = case["query"]
        print(f"  [{i+1}/{len(cases)}] {query[:40]}")
        try:
            response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=query)])
            answer = response.content
        except Exception as e:
            answer = f"[ERROR] {e}"

        source_docs = get_source_docs(query)
        judge = judge_answer(answer, source_docs)
        refusal = detect_refusal(answer)

        results.append({
            "query": query, "type": case["type"],
            "expected": case.get("expected_behavior", ""),
            "answer": answer[:500], "judge": judge, "refusal_detected": refusal,
        })
    return results


async def run_group_c(cases: List[Dict]) -> List[Dict]:
    """C 组：Prompt + ReAct — System Prompt + 工具检索，无引用编号"""
    results = []
    for i, case in enumerate(cases):
        query = case["query"]
        print(f"  [{i+1}/{len(cases)}] {query[:40]}")
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=query)]
        initial_state = {"messages": messages, "user_id": "eval_c", "session_id": "eval_c"}

        try:
            final_state = await agent_graph.ainvoke(
                initial_state, config={"recursion_limit": 8}
            )
            answer = final_state["messages"][-1].content
        except Exception as e:
            answer = f"[ERROR] {e}"

        source_docs = get_source_docs(query)
        judge = judge_answer(answer, source_docs)
        refusal = detect_refusal(answer)

        results.append({
            "query": query, "type": case["type"],
            "expected": case.get("expected_behavior", ""),
            "answer": answer[:500], "judge": judge, "refusal_detected": refusal,
        })
    return results


async def run_group_d(cases: List[Dict]) -> List[Dict]:
    """D 组：全量 — System Prompt + ReAct + 引用注入（当前生产环境）"""
    results = []
    for i, case in enumerate(cases):
        query = case["query"]
        print(f"  [{i+1}/{len(cases)}] {query[:40]}")
        init_citation_ctx()
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=query)]
        initial_state = {"messages": messages, "user_id": "eval_d", "session_id": "eval_d"}

        try:
            final_state = await agent_graph.ainvoke(
                initial_state, config={"recursion_limit": 8}
            )
            answer = final_state["messages"][-1].content
        except Exception as e:
            answer = f"[ERROR] {e}"

        source_docs = get_source_docs(query)
        judge = judge_answer(answer, source_docs)
        refusal = detect_refusal(answer)

        results.append({
            "query": query, "type": case["type"],
            "expected": case.get("expected_behavior", ""),
            "answer": answer[:500], "judge": judge, "refusal_detected": refusal,
        })
    return results


# ═══════════════════════════════════════════════════
#  指标计算
# ═══════════════════════════════════════════════════

def compute_metrics(results: List[Dict]) -> Dict:
    total = len(results)
    faithful_count = sum(1 for r in results if r["judge"].get("overall_faithful", True))
    total_claims = sum(r["judge"].get("total_claims", 0) for r in results)
    hallu_claims = sum(r["judge"].get("hallucinated_claims", 0) for r in results)

    faithfulness = 1 - (hallu_claims / total_claims) if total_claims > 0 else 1.0

    # 拒答准确率（正则）：out_of_kb + trap 类型
    refuse_cases = [r for r in results if r["expected"] == "refuse"]
    correct_refusals = sum(1 for r in refuse_cases if r["refusal_detected"])
    refusal_rate = correct_refusals / len(refuse_cases) if refuse_cases else 0.0

    return {
        "faithfulness": faithfulness,
        "answer_faithful_rate": faithful_count / total,
        "total_claims": total_claims,
        "hallucinated_claims": hallu_claims,
        "refusal_rate": refusal_rate,
        "correct_refusals": correct_refusals,
        "total_refuse_cases": len(refuse_cases),
    }


def compute_by_type(results: List[Dict], qtype: str) -> Dict:
    subset = [r for r in results if r["type"] == qtype]
    return compute_metrics(subset) if subset else {}


# ═══════════════════════════════════════════════════
#  输出
# ═══════════════════════════════════════════════════

def print_summary(all_results: Dict):
    print(f"\n{'=' * 85}")
    print(f"  幻觉抑制策略评测总结")
    print(f"{'=' * 85}")

    header = (
        f"{'实验组':<20} | {'拒答准确率':>8} | {'幻觉陈述数':>8} | "
        f"{'Faithfulness':>12} | {'判定为可信':>8}"
    )
    sep = "-" * 20 + "-|-" + "-" * 8 + "-|-" + "-" * 8 + "-|-" + "-" * 12 + "-|-" + "-" * 8
    print(header)
    print(sep)
    for name, results in all_results.items():
        m = compute_metrics(results)
        print(
            f"{name:<20} | {m['refusal_rate']:>7.0%} | "
            f"{m['hallucinated_claims']:>8} | "
            f"{m['faithfulness']:>11.0%} | "
            f"{m['answer_faithful_rate']:>7.0%}"
        )

    # 按类型分组
    for qtype in ["out_of_kb", "factual", "trap"]:
        print(f"\n  --- 类型: {qtype} ---")
        print(header)
        print(sep)
        for name, results in all_results.items():
            m = compute_by_type(results, qtype)
            if m:
                print(
                    f"{name:<20} | {m['refusal_rate']:>7.0%} | "
                    f"{m['hallucinated_claims']:>8} | "
                    f"{m['faithfulness']:>11.0%} | "
                    f"{m['answer_faithful_rate']:>7.0%}"
                )

    print()


def print_detail(results: List[Dict], name: str):
    print(f"\n--- {name} 逐条详情 ---")
    for r in results:
        j = r["judge"]
        status = "✓" if j.get("overall_faithful") else "✗"
        refusal_tag = " [拒答]" if r["refusal_detected"] else ""
        print(f"  {status} [{r['type']:>8}] {r['query'][:45]}{refusal_tag}")
        for c in j.get("claims", []):
            if c.get("verdict") == "unsupported":
                print(f"         ❌ 幻觉: {c.get('statement', '')[:60]}")


# ═══════════════════════════════════════════════════
#  主函数
# ═══════════════════════════════════════════════════

async def main_async():
    test_cases = load_test_dataset()
    print(f"\n幻觉评测数据集: {len(test_cases)} 条")
    print(f"  类型: out_of_kb={sum(1 for c in test_cases if c['type']=='out_of_kb')}, "
          f"factual={sum(1 for c in test_cases if c['type']=='factual')}, "
          f"trap={sum(1 for c in test_cases if c['type']=='trap')}")

    groups = [
        ("A - 无防护", run_group_a, False),
        ("B - 仅Prompt", run_group_b, False),
        ("C - Prompt+ReAct", run_group_c, True),
        ("D - 全量（生产）", run_group_d, True),
    ]

    all_results = {}
    for name, fn, is_async in groups:
        print(f"\n{'=' * 60}")
        print(f"  评测 {name}")
        print(f"{'=' * 60}")
        t0 = time.perf_counter()
        if is_async:
            results = await fn(test_cases)
        else:
            results = fn(test_cases)
        elapsed = time.perf_counter() - t0
        all_results[name] = results
        m = compute_metrics(results)
        print(f"  耗时: {elapsed:.0f}s")
        print(f"  拒答准确率: {m['refusal_rate']:.0%} | 幻觉陈述: {m['hallucinated_claims']}/{m['total_claims']} | Faithfulness: {m['faithfulness']:.0%}")

    print_summary(all_results)

    # 逐条详情
    for name, results in all_results.items():
        print_detail(results, name)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
