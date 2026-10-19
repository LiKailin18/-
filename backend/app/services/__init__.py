"""业务逻辑层。

约定（CLAUDE.md §5.1）：只接收 db 与参数，不认识 Request / HTTP 状态码；
错误通过 app.core.exceptions 抛业务异常；事务在这里控制。
"""
