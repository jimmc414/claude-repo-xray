"""
Repo X-Ray: HTTP Route Detection

Detects HTTP API routes from decorator patterns on functions/methods.
Recognizes FastAPI, Flask, Django, Starlette, and aiohttp patterns.

Uses decorator_details (name, args, kwargs) from ast_analysis to
extract HTTP method, URL path, and handler information.

Usage:
    from route_analysis import analyze_routes

    routes = analyze_routes(ast_results)
"""

from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# Framework Route Patterns
# =============================================================================

# Maps (decorator_full_name_suffix, or decorator_short_name) to HTTP method.
# The decorator's first positional arg is the route path.
ROUTE_DECORATOR_PATTERNS = {
    # FastAPI: @app.get("/path"), @router.get("/path")
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "delete": "DELETE",
    "patch": "PATCH",
    "head": "HEAD",
    "options": "OPTIONS",
    # FastAPI: @app.websocket("/path"), @router.websocket("/path")
    "websocket": "WEBSOCKET",
    # Flask: @app.route("/path", methods=["GET"])
    "route": None,  # Method extracted from kwargs
    # FastAPI: @app.api_route("/path", methods=["GET"])
    "api_route": None,
}

# Decorators that indicate a Django URL conf or class-based view
DJANGO_PATTERNS = {
    "api_view": True,  # DRF: @api_view(["GET", "POST"])
}

# Known router/app object patterns
ROUTER_PREFIXES = {
    "app", "router", "api", "blueprint", "bp", "route", "web",
    "v1", "v2", "admin", "auth",
}


# =============================================================================
# Route Extraction
# =============================================================================

def _extract_route_from_decorator(
    decorator: Dict[str, Any],
    func_name: str,
    is_async: bool,
) -> Optional[Dict[str, Any]]:
    """Try to extract an HTTP route from a single decorator detail.

    Returns a route dict or None if the decorator doesn't match a route pattern.
    """
    name = decorator.get("name", "")
    full_name = decorator.get("full_name", "")
    args = decorator.get("args", [])
    kwargs = decorator.get("kwargs", {})

    name_lower = name.lower()

    # Check if this looks like a route decorator
    # The full_name should have a prefix like "app.get" or "router.post"
    parts = full_name.split(".")
    if len(parts) >= 2:
        prefix = parts[-2].lower()
        method_part = parts[-1].lower()
    elif len(parts) == 1:
        prefix = ""
        method_part = parts[0].lower()
    else:
        return None

    # Must have a recognizable prefix or be a known pattern.
    # Bare decorators like @patch() or @get() without a router/app prefix
    # are not HTTP routes (e.g., unittest.mock.patch is not PATCH).
    if not prefix:
        if method_part not in DJANGO_PATTERNS:
            return None
    elif prefix not in ROUTER_PREFIXES and method_part not in DJANGO_PATTERNS:
        return None

    # Check against known HTTP method decorators
    if method_part in ROUTE_DECORATOR_PATTERNS:
        http_method = ROUTE_DECORATOR_PATTERNS[method_part]

        # Extract path from first positional arg
        path = args[0] if args and isinstance(args[0], str) else None

        # For @route() and @api_route(), get methods from kwargs
        if http_method is None:
            methods_val = kwargs.get("methods", None)
            if isinstance(methods_val, str):
                http_method = methods_val
            else:
                http_method = "ANY"

        return {
            "method": http_method,
            "path": path or "/???",
            "handler": func_name,
            "is_async": is_async,
            "framework_hint": _guess_framework(full_name, prefix),
        }

    # DRF @api_view(["GET", "POST"])
    if method_part in DJANGO_PATTERNS:
        methods = []
        for a in args:
            if isinstance(a, str):
                methods.append(a.upper())
        return {
            "method": ", ".join(methods) if methods else "ANY",
            "path": None,  # Django routes are in urls.py, not decorators
            "handler": func_name,
            "is_async": is_async,
            "framework_hint": "django-rest-framework",
        }

    return None


def _guess_framework(full_name: str, prefix: str) -> str:
    """Guess the web framework from decorator naming patterns."""
    full_lower = full_name.lower()
    if "fastapi" in full_lower or prefix in ("router",):
        return "fastapi"
    if "flask" in full_lower or prefix in ("blueprint", "bp"):
        return "flask"
    if "starlette" in full_lower:
        return "starlette"
    if "aiohttp" in full_lower:
        return "aiohttp"
    if prefix == "app":
        return "unknown"
    return "unknown"


# =============================================================================
# Public API
# =============================================================================

def analyze_routes(
    ast_results: Dict[str, Any],
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Detect HTTP routes from decorator patterns in the codebase.

    Args:
        ast_results: Output from analyze_codebase()
        verbose: Print progress

    Returns:
        {
            "routes": [
                {
                    "method": "GET",
                    "path": "/users/{id}",
                    "handler": "get_user",
                    "file": "routes/users.py",
                    "line": 42,
                    "is_async": True,
                    "framework_hint": "fastapi",
                    "side_effects": ["db", "api"],  # from AST side effects
                }
            ],
            "summary": {
                "total_routes": int,
                "by_method": {"GET": int, "POST": int, ...},
                "frameworks_detected": ["fastapi"],
            }
        }
    """
    files = ast_results.get("files", {})
    routes = []
    frameworks = set()
    method_counts = {}

    for filepath, file_data in files.items():
        # Check top-level functions
        for func in file_data.get("functions", []):
            _check_function_routes(func, filepath, file_data, routes, frameworks, method_counts)

        # Check class methods (for class-based views)
        for cls in file_data.get("classes", []):
            for method in cls.get("methods", []):
                _check_function_routes(method, filepath, file_data, routes, frameworks, method_counts,
                                       class_name=cls.get("name"))

    # Sort by file and line
    routes.sort(key=lambda r: (r.get("file", ""), r.get("line", 0)))

    return {
        "routes": routes,
        "summary": {
            "total_routes": len(routes),
            "by_method": method_counts,
            "frameworks_detected": sorted(frameworks - {"unknown"}),
        },
    }


def _check_function_routes(
    func: Dict, filepath: str, file_data: Dict,
    routes: List, frameworks: set, method_counts: Dict,
    class_name: Optional[str] = None,
) -> None:
    """Check a function's decorators for route patterns and append any found."""
    decorator_details = func.get("decorator_details", [])
    if not decorator_details:
        return

    func_name = func.get("name", "")
    if class_name:
        func_name = f"{class_name}.{func_name}"
    is_async = func.get("is_async", False)

    # Collect side effects for this function from file-level data
    func_side_effects = set()
    for se in file_data.get("side_effects", []):
        start = func.get("start_line", 0)
        end = func.get("end_line", 0)
        if start <= se.get("line", 0) <= end:
            func_side_effects.add(se.get("category", "unknown"))

    for dec in decorator_details:
        route = _extract_route_from_decorator(dec, func_name, is_async)
        if route:
            route["file"] = filepath
            route["line"] = func.get("start_line", 0)
            if func_side_effects:
                route["side_effects"] = sorted(func_side_effects)
            frameworks.add(route.get("framework_hint", "unknown"))
            for m in route["method"].split(", "):
                method_counts[m] = method_counts.get(m, 0) + 1
            routes.append(route)
