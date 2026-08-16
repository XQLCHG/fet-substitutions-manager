"""Source-runtime diagnostics for the invigilation FastAPI routers.

The script is intentionally plain Python so both Linux and Windows workflows can
print exact module origins, router contents and FastAPI registration behavior.
"""
from __future__ import annotations

import importlib
import sys

from fastapi import FastAPI


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

    expected_full_paths = set()
    for name in module_names:
        module = importlib.import_module(name)
        short_name = name.rsplit(".", 1)[-1]
        server_module = getattr(server_app, short_name, None)
        router = getattr(module, "router", None)
        route_paths = [getattr(route, "path", None) for route in getattr(router, "routes", [])]

        print(f"{name}=", getattr(module, "__file__", None))
        print(f"{name}.server_identity=", server_module is module)
        print(f"{name}.router_identity=", getattr(server_module, "router", None) is router)
        print(f"{name}.prefix=", getattr(router, "prefix", None))
        print(f"{name}.route_count=", len(route_paths))
        print(f"{name}.paths=", route_paths)

        prefix = getattr(router, "prefix", "") or ""
        expected_full_paths.update(f"{prefix}{path}" for path in route_paths if path)

        # Independent FastAPI probe: verifies that the router itself can be
        # included under the currently installed FastAPI/Starlette versions.
        probe = FastAPI()
        probe.include_router(router)
        probe_paths = sorted(
            path for path in {getattr(route, "path", None) for route in probe.routes}
            if path and "invigilation" in path
        )
        print(f"{name}.probe_paths=", probe_paths)

    app_paths = {getattr(route, "path", None) for route in server_app.app.routes}
    app_paths_clean = sorted(path for path in app_paths if path)
    invigilation_paths = [path for path in app_paths_clean if "invigilation" in path]
    print("app_route_count=", len(app_paths_clean))
    print("app_invigilation_routes=", invigilation_paths)
    print("app_all_routes=", app_paths_clean)

    required = {
        "/api/health",
        "/api/invigilation/roles",
        "/api/invigilation/batches",
        "/api/invigilation/solve/{batch_id}",
        "/api/invigilation/export/{batch_id}/xlsx",
    }
    missing = sorted(required - app_paths)
    if missing:
        print("expected_full_paths=", sorted(expected_full_paths))
        print("missing=", missing)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
