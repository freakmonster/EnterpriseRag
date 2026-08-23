# 临时验证：查看最新 chat 调用记录的缓存 token 与成本
from sqlalchemy import text
from infrastructure.database.session import engine

conn = engine.connect()
rows = conn.execute(text(
    "SELECT id, input_tokens, input_cache_hit_tokens, input_cache_miss_tokens, "
    "output_tokens, cost, created_at FROM llm_call_logs "
    "WHERE model_type='chat' ORDER BY id DESC LIMIT 4"
)).fetchall()
for r in rows:
    print(r)

agg = conn.execute(text(
    "SELECT model_type, COUNT(*) c, SUM(cost) cost FROM llm_call_logs GROUP BY model_type"
)).fetchall()
print("--- by type ---")
for r in agg:
    print(r)
