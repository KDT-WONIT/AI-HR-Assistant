"""실행: python -m uvicorn main:app --reload"""
"""cloudflared tunnel --url http://localhost:8000  """

from app.main import app

__all__ = ["app"]
