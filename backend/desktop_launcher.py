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
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

APP_DIR_NAME = "SmartInvigilation"
DEFAULT_INSTITUTION = "local"
DEFAULT_USERNAME = "super_admin"
_OUTPUT_SINKS = []


def _ensure_output_streams() -> None:
    """PyInstaller --windowed 下 stdout/stderr 可能为 None。"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            sink = open(os.devnull, "w", encoding="utf-8", errors="replace")
            _OUTPUT_SINKS.append(sink)
            setattr(sys, name, sink)


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


def _set_common_environment(root: Path, *, password: str | None) -> Path:
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
    os.environ["DESKTOP_MODE"] = "1"
    os.environ["SECRET_KEY"] = _read_or_create_secret(root)
    if password:
        os.environ["ADMIN_PASSWORD"] = password
    else:
        os.environ.pop("ADMIN_PASSWORD", None)
    return auth_db


def _configure_environment() -> tuple[Path, Path]:
    root = _app_data_root()
    auth_db = root / "data" / "auth.db"
    password = None
    if not _admin_exists(auth_db, DEFAULT_USERNAME):
        password = _ask_first_run_password()
    auth_db = _set_common_environment(root, password=password)
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


def _self_test() -> int:
    """CI 对打包后的 exe 做真实 import/native-library 自检。"""
    try:
        with tempfile.TemporaryDirectory(prefix="smart-invigilation-test-") as tmp:
            root = Path(tmp)
            _set_common_environment(root, password="SelfTest-Only-123")
            dist = _frontend_dist()
            if not (dist / "index.html").exists():
                raise RuntimeError("前端资源未打包")

            import server_app as backend_server
            app = backend_server.app
            _attach_desktop_frontend(app, dist)

            # FastAPI 0.137+ keeps included APIRouters as a route tree. Public
            # endpoint validation must not rely on top-level app.routes[].path.
            api_paths = set(app.openapi().get("paths", {}).keys())
            required_api_paths = {
                "/api/health",
                "/api/invigilation/roles",
                "/api/invigilation/batches",
                "/api/invigilation/solve/{batch_id}",
                "/api/invigilation/export/{batch_id}/xlsx",
            }
            missing = sorted(required_api_paths - api_paths)
            if missing:
                actual = sorted(path for path in api_paths if "invigilation" in path)
                raise RuntimeError(
                    f"OpenAPI 缺少监考路由: {missing}; "
                    f"server_app={getattr(backend_server, '__file__', None)!r}; "
                    f"invigilation_openapi_paths={actual!r}"
                )

            # /invigilation is intentionally include_in_schema=False. It is a
            # direct desktop shell route, so verify it separately.
            direct_paths = {getattr(route, "path", None) for route in app.routes}
            if "/invigilation" not in direct_paths:
                raise RuntimeError("桌面前端入口 /invigilation 未注册")

            from ortools.sat.python import cp_model
            model = cp_model.CpModel()
            x = model.new_bool_var("x")
            model.add(x == 1)
            solver = cp_model.CpSolver()
            if solver.solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                raise RuntimeError("OR-Tools CP-SAT 自检失败")

            from routes.invigilation_export import _register_chinese_font
            if not _register_chinese_font():
                raise RuntimeError("PDF 中文字体模块自检失败")
        return 0
    except Exception as exc:
        try:
            (Path(tempfile.gettempdir()) / "smart-invigilation-selftest-error.txt").write_text(
                repr(exc), encoding="utf-8"
            )
        except Exception:
            pass
        return 2


def main() -> int:
    _ensure_output_streams()

    if "--self-test" in sys.argv:
        return _self_test()

    try:
        _configure_environment()
        dist = _frontend_dist()

        from server_app import app
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
