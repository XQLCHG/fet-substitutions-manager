"""Compatibility entry point.

The real FastAPI application is defined in ``server_app.py``. Keeping this thin
wrapper preserves existing commands such as ``uvicorn main:app`` while giving
PyInstaller desktop builds a unique, unambiguous module name to import.
"""
from server_app import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
