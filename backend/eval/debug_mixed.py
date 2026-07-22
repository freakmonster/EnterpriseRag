"""快速验证 multi_retrieve_v2 是否正常工作"""
import ssl as _ssl
_orig_load_certs = _ssl.SSLContext.load_default_certs
def _safe_load_certs(self, purpose=_ssl.Purpose.SERVER_AUTH):
    try:
        return _orig_load_certs(self, purpose)
    except _ssl.SSLError:
        pass
_ssl.SSLContext.load_default_certs = _safe_load_certs

import os, sys
os.environ["CHROMA_TELEMETRY_ENABLED"] = "false"
os.environ["CHROMA_SKIP_TELEMETRY"] = "true"
sys.path.insert(0, str(__file__).parent.parent)

from tools.retrieval_tools import multi_retrieve_v2

q = "公司上班时间是几点到几点？"
print(f"测试 multi_retrieve_v2([{q!r}], {q!r})")
try:
    results = multi_retrieve_v2([q], q)
    print(f"成功: {len(results)} 个结果")
    for r in results:
        print(f"  [{r['metadata']['file_name']}] {r['content'][:60]}")
except Exception as e:
    import traceback
    traceback.print_exc()
