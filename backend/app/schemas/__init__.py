"""响应/请求模型包。

约定（CLAUDE.md §5.1）：api 层返回的对象一律来自本包，不直接用表模型做响应，
避免把 password_hash、extracted_text 之类的字段意外暴露出去。
"""
