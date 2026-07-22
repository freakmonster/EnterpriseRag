"""
RAG 检索策略 Benchmark 评测脚本

对比以下四种策略在 HitRate@k / Precision@k / Latency 上的表现：
  A. 纯向量检索（search_no_rerank）
  B. 纯 BM25 关键词检索（bm25_search）
  C. 向量 + Rerank（search, simple_retrieve_policy 内部）
  D. 混合多路检索（multi_retrieve_v2, complex_retrieve_policy 内部）

用法：
  cd backend
  python eval/run_benchmark.py                     # 默认 k=3
  python eval/run_benchmark.py --topk 1 3 5 10     # 多个 k 值消融
  python eval/run_benchmark.py --csv                # 输出 CSV
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict

# ── 确保 backend 在 sys.path 中 ──
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 兼容层：绕过 Windows SSL 证书存储问题（aiohttp 导入时崩溃）──
import ssl as _ssl
_orig_load_certs = _ssl.SSLContext.load_default_certs
def _safe_load_certs(self, purpose=_ssl.Purpose.SERVER_AUTH):
    try:
        return _orig_load_certs(self, purpose)
    except _ssl.SSLError:
        pass  # Windows 证书存储部分损坏时静默跳过
_ssl.SSLContext.load_default_certs = _safe_load_certs

os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
os.environ["CHROMA_SKIP_TELEMETRY"] = "true"

from retrieval.vectorstores.chroma_store import search, search_no_rerank
from retrieval.retrievers.bm25_retriever import bm25_search
from tools.retrieval_tools import multi_retrieve_v2


# ═══════════════════════════════════════════════════
#  一、加载测试数据集
# ═══════════════════════════════════════════════════

def load_test_dataset(path: str = None) -> List[Dict]:
    if path is None:
        path = Path(__file__).resolve().parent / "test_dataset.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════
#  二、评测核心函数
# ═══════════════════════════════════════════════════

def is_relevant(result: Dict, relevant_files: List[str]) -> bool:
    """判断一个检索结果是否与期望的相关文件匹配"""
    file_name = result.get("metadata", {}).get("file_name", "")
    return file_name in relevant_files


def evaluate_strategy(
    name: str,
    retrieval_fn,
    test_cases: List[Dict],
    k: int,
    accept_top_k: bool = True,
    multi_query: bool = False,
) -> Dict:
    """
    对测试集执行某一种检索策略并计算指标。

    Args:
        name: 策略名称（仅用于日志）
        retrieval_fn: 检索函数
        test_cases: 测试用例列表
        k: top-k
        accept_top_k: 是否传入 top_k 参数（混合检索使用默认值，不接受 top_k）
        multi_query: 如果 True，retrieval_fn 接收 (vec_queries, bm25_query) 参数
    Returns:
        dict: {hit_rate, precision, avg_latency_ms}
    """
    hit_count = 0
    precision_sum = 0.0
    total_latency = 0.0
    total = len(test_cases)

    for case in test_cases:
        query = case["query"]
        relevant_files = case["relevant_files"]

        # ── 计时 + 调用 ──
        start = time.perf_counter()
        try:
            if multi_query:
                vec_queries = case.get("vec_queries", [query])
                bm25_query = case.get("bm25_query", query)
                results = retrieval_fn(vec_queries, bm25_query)
            elif accept_top_k:
                results = retrieval_fn(query, tk=k)
            else:
                results = retrieval_fn(query, None)  # 不使用 top_k 参数
        except Exception as e:
            print(f"  [警告] 查询失败: {query[:30]}... → {e}")
            results = []
        elapsed = time.perf_counter() - start
        total_latency += elapsed * 1000  # ms

        # ── 评估 top-k ──
        top_k = results[:k]
        hits_in_top = sum(1 for r in top_k if is_relevant(r, relevant_files))
        if hits_in_top > 0:
            hit_count += 1
        precision_sum += hits_in_top / k if k > 0 else 0.0

    return {
        "hit_rate": hit_count / total,
        "precision": precision_sum / total,
        "avg_latency_ms": total_latency / total,
    }


# ═══════════════════════════════════════════════════
#  三、按 query 类型分组评估
# ═══════════════════════════════════════════════════

def group_by_type(test_cases: List[Dict]) -> Dict[str, List[Dict]]:
    groups = {}
    for case in test_cases:
        t = case.get("type", "other")
        groups.setdefault(t, []).append(case)
    return groups


# ═══════════════════════════════════════════════════
#  四、输出格式
# ═══════════════════════════════════════════════════

# 策略定义：(名称, 检索函数, 是否接受 top_k 参数, 是否 multi_query)
#   检索函数签名:
#     fn(query, top_k=k)          — 当 accept_top_k=True, multi_query=False
#     fn([query], bm25_query)     — 当 multi_query=True (使用默认的 retrieve_top_k)
STRATEGIES = [
    ("纯向量 (no_rerank)", lambda q, tk: search_no_rerank(q, top_k=tk), True,  False),
    ("纯BM25 (or)",        lambda q, tk: bm25_search(q, top_k=tk),       True,  False),
    ("向量+Rerank",        lambda q, tk: search(q, top_k=tk),            True,  False),
    ("混合检索",           lambda q, tk: multi_retrieve_v2(q, tk),      False, True),
]


def print_table(results: List[Dict], title: str = ""):
    """打印对齐表格"""
    if title:
        print(f"\n{'=' * 70}")
        print(f"  {title}")
        print(f"{'=' * 70}")

    header = f"{'策略':<20} | {'HitRate':>8} | {'Precision':>10} | {'Latency(ms)':>10}"
    sep = "-" * 20 + "-|-" + "-" * 8 + "-|-" + "-" * 10 + "-|-" + "-" * 10
    print(header)
    print(sep)
    for r in results:
        print(
            f"{r['strategy']:<20} | "
            f"{r['hit_rate']:>7.2%} | "
            f"{r['precision']:>9.2%} | "
            f"{r['avg_latency_ms']:>8.1f}"
        )
    print()


def print_csv(results: List[Dict], k: int):
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["策略", "HitRate", "Precision", "Latency(ms)"])
    for r in results:
        writer.writerow([
            r["strategy"],
            f"{r['hit_rate']:.2%}",
            f"{r['precision']:.2%}",
            f"{r['avg_latency_ms']:.1f}",
        ])
    print(f"\n--- CSV (k={k}) ---")
    print(output.getvalue().strip())
    print("--- CSV END ---")


# ═══════════════════════════════════════════════════
#  五、主函数
# ═══════════════════════════════════════════════════

def run_benchmark(top_k_values: List[int], output_csv: bool = False):
    test_cases = load_test_dataset()
    print(f"\n测试集: {len(test_cases)} 条 query")
    print(f"   类型分布: {', '.join(f'{t}={len(cases)}' for t, cases in group_by_type(test_cases).items())}")

    for k in top_k_values:
        print(f"\n{'─' * 70}")
        print(f"  top_k = {k}")
        print(f"{'─' * 70}")

        results = []
        for name, fn, accept_top_k, multi_query in STRATEGIES:
            metrics = evaluate_strategy(
                name, fn, test_cases, k,
                accept_top_k=accept_top_k, multi_query=multi_query,
            )
            results.append({"strategy": name, **metrics})

        print_table(results)
        if output_csv:
            print_csv(results, k)

        # 按类型细分
        for qtype, cases in group_by_type(test_cases).items():
            type_results = []
            for name, fn, accept_top_k, multi_query in STRATEGIES:
                metrics = evaluate_strategy(
                    name, fn, cases, k,
                    accept_top_k=accept_top_k, multi_query=multi_query,
                )
                type_results.append({"strategy": name, **metrics})
            print_table(type_results, f"类型: {qtype} ({len(cases)} 条)")


def main():
    parser = argparse.ArgumentParser(
        description="RAG 检索策略 Benchmark"
    )
    parser.add_argument(
        "--topk", nargs="+", type=int, default=[3],
        help="待评测的 top-k 值列表，如 1 3 5 10（默认: 3）"
    )
    parser.add_argument("--csv", action="store_true", help="同时输出 CSV 格式")
    args = parser.parse_args()

    run_benchmark(top_k_values=args.topk, output_csv=args.csv)


if __name__ == "__main__":
    main()
