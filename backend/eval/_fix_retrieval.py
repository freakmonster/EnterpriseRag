"""修复 retrieval_tools.py：添加 Rerank None 降级逻辑"""
import pathlib

p = pathlib.Path('tools/retrieval_tools.py')
content = p.read_text(encoding='utf-8')

old1 = """            _track_rerank(response)
            for result in response.output.results:
                idx = result.index
                if idx < len(vec_results):
                    doc = vec_results[idx]
                    key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                    if key not in seen:
                        seen.add(key)
                        merged_docs.append(doc)"""

new1 = """            if response and response.output:
                _track_rerank(response)
                for result in response.output.results:
                    idx = result.index
                    if idx < len(vec_results):
                        doc = vec_results[idx]
                        key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                        if key not in seen:
                            seen.add(key)
                            merged_docs.append(doc)
            else:
                for doc in vec_results[:2]:
                    key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                    if key not in seen:
                        seen.add(key)
                        merged_docs.append(doc)"""

if old1 not in content:
    print("WARNING: old1 not found!")
else:
    content = content.replace(old1, new1)
    print("OK: vector branch fixed")

old2 = """        _track_rerank(response)
        for result in response.output.results:
            idx = result.index
            if idx < len(es_results):
                doc = es_results[idx]
                key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                if key not in seen:
                    seen.add(key)
                    merged_docs.append(doc)"""

new2 = """        if response and response.output:
            _track_rerank(response)
            for result in response.output.results:
                idx = result.index
                if idx < len(es_results):
                    doc = es_results[idx]
                    key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                    if key not in seen:
                        seen.add(key)
                        merged_docs.append(doc)
        else:
            for doc in es_results[:2]:
                key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                if key not in seen:
                    seen.add(key)
                    merged_docs.append(doc)"""

if old2 not in content:
    print("WARNING: old2 not found!")
else:
    content = content.replace(old2, new2)
    print("OK: BM25 branch fixed")

p.write_text(content, encoding='utf-8')
print("Done")
