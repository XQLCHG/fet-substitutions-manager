"""Source-runtime diagnostics for the invigilation FastAPI routers.

FastAPI 0.137+ keeps included routers as a route tree instead of flattening every
child endpoint into ``app.routes``. Therefore final endpoint validation uses the
OpenAPI path table, which represents the public API regardless of the internal
route-tree representation.
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

        # Independent include probe. OpenAPI is intentionally used here too,
        # because the internal route tree is not a stable public inspection API.
        probe = FastAPI()
        probe.include_router(router)
        probe_paths = sorted(probe.openapi().get("paths", {}).keys())
        print(f"{name}.probe_openapi_paths=", probe_paths)

    top_level_types = [type(route).__name__ for route in server_app.app.routes]
    print("app_top_level_route_types=", top_level_types)

    openapi_paths = set(server_app.app.openapi().get("paths", {}).keys())
    invigilation_paths = sorted(path for path in openapi_paths if "invigilation" in path)
    print("openapi_path_count=", len(openapi_paths))
    print("openapi_invigilation_routes=", invigilation_paths)

    required = {
        "/api/health",
        "/api/invigilation/roles",
        "/api/invigilation/batches",
        "/api/invigilation/solve/{batch_id}",
        "/api/invigilation/export/{batch_id}/xlsx",
    }
    missing = sorted(required - openapi_paths)
    if missing:
        print("missing_openapi_paths=", missing)
        return 2

    print("ROUTE_SMOKE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
