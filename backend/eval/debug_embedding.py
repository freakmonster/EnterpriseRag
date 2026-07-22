"""快速验证 _get_text_embedding 是否正常工作"""
import ssl as _ssl
_orig_load_certs = _ssl.SSLContext.load_default_certs
def _safe_load_certs(self, purpose=_ssl.Purpose.SERVER_AUTH):
    try:
        return _orig_load_certs(self, purpose)
    except _ssl.SSLError:
        pass
_ssl.SSLContext.load_default_certs = _safe_load_certs

import os
os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
os.environ["CHROMA_SKIP_TELEMETRY"] = "true"

from retrieval.vectorstores.chroma_store import search_no_rerank, search

# 测试1: search_no_rerank
print("=== 测试 search_no_rerank ===")
try:
    r = search_no_rerank("公司上班时间", top_k=3)
    print(f"成功: {len(r)} 个结果")
    for d in r:
        fn = d["metadata"]["file_name"]
        c = d["content"][:60]
        print(f"  [{fn}] {c}")
except Exception as e:
    print(f"失败: {e}")

# 测试2: search (with Rerank)
print("\n=== 测试 search (with Rerank) ===")
try:
    r = search("公司上班时间", top_k=3)
    print(f"成功: {len(r)} 个结果")
    for d in r:
        fn = d["metadata"]["file_name"]
        c = d["content"][:60]
        print(f"  [{fn}] {c}")
except Exception as e:
    print(f"失败: {e}")
