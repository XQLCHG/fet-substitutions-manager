"""Windows 本地桌面启动器。

PyInstaller 打包后：
- 首次运行弹窗设置本地 super_admin 密码；
- SECRET_KEY 自动生成并仅保存在当前 Windows 用户的 LocalAppData；
- SQLite 数据保存在 %LOCALAPPDATA%/SmartInvigilation/data；
- FastAPI 仅监听 127.0.0.1；
- 自动打开 /invigilation 工作台；
- 内置 Vite production build，无需安装 Python/Node/Docker。
"""
from __future__ import annotations

import os
import secrets
import socket
import sqlite3
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_DIR_NAME = "SmartInvigilation"
DEFAULT_INSTITUTION = "local"
DEFAULT_USERNAME = "super_admin"


def _app_data_root() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME}"


def _resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent


def _frontend_dist() -> Path:
    root = _resource_root()
    candidates = [
        root / "frontend_dist",
        Path(__file__).resolve().parents[1] / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    raise RuntimeError("找不到打包后的前端 frontend_dist/index.html")


def _read_or_create_secret(root: Path) -> str:
    secret_file = root / "secret.key"
    if secret_file.exists():
        value = secret_file.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    value = secrets.token_hex(32)
    secret_file.write_text(value, encoding="utf-8")
    return value


def _admin_exists(auth_db: Path, username: str) -> bool:
    if not auth_db.exists():
        return False
    try:
        with sqlite3.connect(auth_db) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            if not table:
                return False
            return conn.execute(
                "SELECT 1 FROM users WHERE username = ? LIMIT 1", (username,)
            ).fetchone() is not None
    except sqlite3.Error:
        return False


def _ask_first_run_password() -> str:
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog
    except Exception as exc:  # pragma: no cover - Windows packaging path
        raise RuntimeError("首次启动需要 tkinter 来设置管理员密码") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        messagebox.showinfo(
            "智能监考排班系统",
            "首次启动需要创建本地管理员。\n\n"
            f"用户名：{DEFAULT_USERNAME}\n"
            "请设置一个至少 8 位的密码。",
            parent=root,
        )
        while True:
            first = simpledialog.askstring(
                "设置管理员密码",
                "请输入至少 8 位密码：",
                show="*",
                parent=root,
            )
            if first is None:
                raise SystemExit(0)
            if len(first) < 8:
                messagebox.showwarning("密码太短", "密码至少需要 8 位。", parent=root)
                continue
            second = simpledialog.askstring(
                "确认管理员密码",
                "请再次输入密码：",
                show="*",
                parent=root,
            )
            if second is None:
                raise SystemExit(0)
            if first != second:
                messagebox.showwarning("密码不一致", "两次输入的密码不一致。", parent=root)
                continue
            return first
    finally:
        root.destroy()


def _show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror("智能监考排班系统", message, parent=root)
        root.destroy()
    except Exception:
        pass


def _configure_environment() -> tuple[Path, Path]:
    root = _app_data_root()
    data_root = root / "data"
    root.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    auth_db = data_root / "auth.db"

    os.environ["DATA_DIR"] = str(data_root)
    os.environ["AUTH_DB_PATH"] = str(auth_db)
    os.environ["APP_INSTITUCIO"] = DEFAULT_INSTITUTION
    os.environ["ADMIN_INSTITUCIO"] = DEFAULT_INSTITUTION
    os.environ["ADMIN_USERNAME"] = DEFAULT_USERNAME
    os.environ["COOKIE_SECURE"] = "false"
    os.environ["ENVIRONMENT"] = "production"
    os.environ["SECRET_KEY"] = _read_or_create_secret(root)
    os.environ["DESKTOP_MODE"] = "1"

    if not _admin_exists(auth_db, DEFAULT_USERNAME):
        os.environ["ADMIN_PASSWORD"] = _ask_first_run_password()
    else:
        os.environ.pop("ADMIN_PASSWORD", None)

    return root, auth_db


def _find_port(start: int = 8765, end: int = 8795) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("本机 8765-8795 端口均被占用")


def _attach_desktop_frontend(app, dist: Path) -> None:
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="desktop-assets")

    @app.get("/invigilation", include_in_schema=False)
    @app.get("/invigilation/{path:path}", include_in_schema=False)
    async def desktop_invigilation(path: str = ""):
        return FileResponse(dist / "index.html")


def _open_browser(port: int) -> None:
    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{port}/invigilation", new=1)


def main() -> int:
    try:
        _configure_environment()
        dist = _frontend_dist()

        # 必须在环境变量准备完成后导入：auth/config 会在 import 阶段读取环境变量。
        from main import app
        import uvicorn

        _attach_desktop_frontend(app, dist)
        port = _find_port()
        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        return 0
    except SystemExit:
        return 0
    except Exception as exc:
        _show_error(f"启动失败：\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
