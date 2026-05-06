"""Vercel Serverless 入口：将 FastAPI app 暴露给 Vercel Python Runtime。"""

import sys
import os

# 确保 backend 根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

# Vercel Python Runtime 会自动识别名为 `app` 的 ASGI/WSGI 应用
