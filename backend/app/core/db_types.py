"""数据库类型兼容层：让 ORM 模型同时兼容 SQLite 和 PostgreSQL。"""

import json
from sqlalchemy import TypeDecorator, Text, String
from sqlalchemy.types import TypeEngine


class JSONType(TypeDecorator):
    """跨数据库 JSON 类型：SQLite 用 TEXT 存 JSON 字符串，PostgreSQL 用原生 JSONB。"""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return None


class ArrayType(TypeDecorator):
    """跨数据库数组类型：SQLite 用 TEXT 存 JSON 数组，PostgreSQL 用原生 ARRAY。"""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        return "[]"

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return []
