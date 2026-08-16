"""Windows source-runtime diagnostics for the invigilation FastAPI routers.

This is intentionally a plain Python script (not pytest) so the Windows desktop
workflow can print exact module origins before PyInstaller runs.
"""
from __future__ import annotations

import importlib
import sys


def main() -> int:
    import routes
    import server_app

    module_names = [
        "routes.invigilation_config",
        "routes.invigilation_exams",
        "routes.invigilation_import",
        "routes.invigilation_solver",
        "routes.invigilation_export",
    ]

    print("python=", sys.executable)
    print("sys.path[0]=", sys.path[0])
    print("routes_module=", getattr(routes, "__file__", None))
    print("server_app=", getattr(server_app, "__file__", None))

    expected_router_paths = set()
    for name in module_names:
        module = importlib.import_module(name)
        router = getattr(module, "router", None)
        paths = [getattr(route, "path", None) for route in getattr(router, "routes", [])]
        print(f"{name}=", getattr(module, "__file__", None))
        print(f"{name}.prefix=", getattr(router, "prefix", None))
        print(f"{name}.route_count=", len(paths))
        print(f"{name}.paths=", paths)
        expected_router_paths.update(path for path in paths if path)

    app_paths = {getattr(route, "path", None) for route in server_app.app.routes}
    invigilation_paths = sorted(path for path in app_paths if path and "invigilation" in path)
    print("app_route_count=", len(app_paths))
    print("app_invigilation_routes=", invigilation_paths)

    required = {
        "/api/health",
        "/api/invigilation/roles",
        "/api/invigilation/batches",
        "/api/invigilation/solve/{batch_id}",
        "/api/invigilation/export/{batch_id}/xlsx",
    }
    missing = sorted(required - app_paths)
    if missing:
        print("expected_router_paths=", sorted(expected_router_paths))
        print("missing=", missing)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
