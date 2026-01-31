# bigtree/inc/scope_registry.py
# Scans @route decorators and builds a scope -> routes mapping
# Provides documentation on what each scope grants access to

from __future__ import annotations
from typing import Dict, List, Set, Optional
from dataclasses import dataclass

@dataclass
class ScopeInfo:
    scope: str
    routes: List[str]
    description: str = ""

_scope_cache: Optional[Dict[str, ScopeInfo]] = None


def _default_scope_descriptions() -> Dict[str, str]:
    """Human-readable descriptions of common scopes."""
    return {
        "*": "Full admin access to all routes",
        "tarot:admin": "Create, manage, and moderate tarot sessions",
        "tarot:read": "Read-only access to tarot sessions",
        "gallery:admin": "Upload, manage, and moderate gallery items",
        "gallery:read": "Read-only access to gallery",
        "contest:admin": "Create and manage contests",
        "bingo:admin": "Create and manage bingo games",
        "admin:web": "Web administration panel access",
        "admin:api": "API key management",
        "admin:*": "All admin functions",
    }


def extract_scopes_from_routes(routes: List) -> Dict[str, ScopeInfo]:
    """
    Extract scopes from APIRoute objects (from webserver._registry).
    Returns dict of scope -> ScopeInfo (with list of routes that require it).
    """
    scope_map: Dict[str, Set[str]] = {}
    
    for route in routes:
        method = getattr(route, "method", "GET").upper()
        path = getattr(route, "path", "")
        scopes = getattr(route, "scopes", set()) or set()
        allow_public = getattr(route, "allow_public", False)
        
        # Format route as "METHOD /path"
        route_str = f"{method} {path}"
        
        if allow_public:
            # Public routes don't require scopes
            if "*" not in scope_map:
                scope_map["*"] = set()
            continue
        
        if not scopes:
            # Routes with no explicit scopes require "*" (admin-only)
            if "*" not in scope_map:
                scope_map["*"] = set()
            scope_map["*"].add(route_str)
        else:
            # Add route to each of its scopes
            for scope in scopes:
                if scope not in scope_map:
                    scope_map[scope] = set()
                scope_map[scope].add(route_str)
    
    # Convert to ScopeInfo objects with descriptions
    descriptions = _default_scope_descriptions()
    result: Dict[str, ScopeInfo] = {}
    for scope, routes_set in scope_map.items():
        result[scope] = ScopeInfo(
            scope=scope,
            routes=sorted(list(routes_set)),
            description=descriptions.get(scope, "")
        )
    
    return result


def get_scope_registry() -> Dict[str, ScopeInfo]:
    """
    Get cached scope registry. Loads from routes on first call.
    """
    global _scope_cache
    if _scope_cache is not None:
        return _scope_cache
    
    try:
        from bigtree.inc import webserver
        _scope_cache = extract_scopes_from_routes(webserver._registry)
    except Exception:
        _scope_cache = {}
    
    return _scope_cache


def scope_to_dict(scope_info: ScopeInfo) -> dict:
    """Convert ScopeInfo to JSON-serializable dict."""
    return {
        "scope": scope_info.scope,
        "description": scope_info.description,
        "routes": scope_info.routes,
        "route_count": len(scope_info.routes),
    }
