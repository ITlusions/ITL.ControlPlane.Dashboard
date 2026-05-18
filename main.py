"""ITL Control Plane Dashboard - Main Application"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import httpx
from loguru import logger
import os

# Authentication imports
from src.config import get_settings
from src.middleware.audit import AuditLogMiddleware
from src.routers.auth import router as auth_router
from src.routers.resources import router as resources_router, init_resources_router
from src.auth.session import UserSession, get_session_manager
from src.auth.oidc import get_oidc_client
from src.widgets import get_widgets_for_user, get_user_roles

# Extracted modules
from src.utils import extract_name, safe_list
from src.navigation import (
    build_sidebar,
    RESOURCE_TYPE_LIST_CONFIG,
    RESOURCE_TYPE_DETAIL_CONFIG,
    RESOURCE_TYPE_LABELS,
    RESOURCE_DETAIL_SIDEBAR,
)
from src.services.sample_queries import (
    get_all_sample_queries,
    load_user_sample_queries,
    save_user_sample_queries,
    create_sample_query,
    delete_sample_query,
)
from src.services.infrastructure import (
    DOCKER_AVAILABLE,
    KUBERNETES_AVAILABLE,
    RUNNING_IN_KUBERNETES,
    get_service_status as _get_service_status,
    get_infra_data as _get_infra_data,
    get_container_detail as _get_container_detail,
    container_action as _container_action,
    get_container_logs as _get_container_logs,
)

# Load settings
settings = get_settings()

app = FastAPI(title="ITL Control Plane Dashboard")

# Add middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
)
app.add_middleware(AuditLogMiddleware)

# Simple in-memory circuit-breaker / cache for infra calls
_INFRA_STATE = {
    "failures": 0,
    "last_failure": None,
    "open_until": None,
    "last_value": None,
    "last_success": None,
}
_INFRA_TIMEOUT = 2.5  # seconds
_INFRA_FAILURE_THRESHOLD = 3
_INFRA_COOLDOWN = 60  # seconds

# Include auth routes
app.include_router(auth_router)

# Mount static files
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")


def get_current_user(request: Request) -> Optional[UserSession]:
    """Get current user from session cookie"""
    cookie_value = request.cookies.get(settings.session_cookie_name)
    if not cookie_value:
        return None
    session_manager = get_session_manager()
    return session_manager.decode_session(cookie_value)


def get_selected_tenant(request: Request) -> Optional[str]:
    """Get currently selected tenant from session"""
    return request.session.get("selected_tenant")


def set_selected_tenant(request: Request, tenant: Optional[str]):
    """Set the selected tenant in session"""
    if tenant:
        request.session["selected_tenant"] = tenant
    elif "selected_tenant" in request.session:
        del request.session["selected_tenant"]


async def fetch_available_tenants() -> list:
    """Fetch list of available tenants from API"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{API_GATEWAY_URL}/tenants")
            if resp.status_code == 200:
                data = resp.json()
                # API returns tenants under "resources" key
                tenants = data.get("resources", []) if isinstance(data, dict) else data
                return [t.get("name", "") for t in tenants if t.get("name")]
    except Exception as e:
        logger.warning(f"Failed to fetch tenants: {e}")
    return []


def get_auth_context(request: Request) -> dict:
    """Get authentication context for templates"""
    user = get_current_user(request)
    oidc = get_oidc_client()
    return {
        "auth_enabled": oidc.enabled,
        "user": user,
        "is_authenticated": user is not None,
        "selected_tenant": get_selected_tenant(request),
    }


def require_auth(request: Request) -> Optional[RedirectResponse]:
    """
    Check if authentication is required and user is logged in.
    Returns RedirectResponse to login if auth required but not logged in.
    Returns None if access should be granted.
    """
    oidc = get_oidc_client()
    if not oidc.enabled:
        # Auth not configured - allow anonymous access
        return None
    
    user = get_current_user(request)
    if user:
        # User is logged in
        return None
    
    # Auth required but not logged in - redirect to login
    next_url = str(request.url)
    return RedirectResponse(url=f"/login?next={next_url}", status_code=302)


def is_authenticated(request: Request) -> bool:
    """
    Check if user is authenticated (for API endpoints).
    Returns True if auth is disabled OR user is logged in.
    """
    oidc = get_oidc_client()
    if not oidc.enabled:
        # Auth not configured - allow anonymous access
        return True
    return get_current_user(request) is not None


# Templates
templates = Jinja2Templates(directory="templates")

# Dashboard connects ONLY via API Gateway - never directly to providers
# NOTE: Docker Compose maps 8081->8080, so use 8081 for local dev
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://localhost:8081")

# Initialize and include resources router
init_resources_router(templates, API_GATEWAY_URL, get_auth_context, require_auth)
app.include_router(resources_router)

# Stats cache: store stats with TTL to avoid repeated slow calls
_stats_cache = {"data": None, "timestamp": None, "ttl": 300}  # 5 minute TTL

async def _fetch_landing_stats() -> dict:
    """Fetch counts for the landing page stats with caching"""
    import time
    current_time = time.time()
    
    # Return cached stats if still valid
    if _stats_cache["data"] and _stats_cache["timestamp"]:
        age = current_time - _stats_cache["timestamp"]
        if age < _stats_cache["ttl"]:
            logger.debug(f"Returning cached stats (age: {age:.1f}s)")
            return _stats_cache["data"]
    
    stats = {
        "tenants": 0,
        "management_groups": 0,
        "subscriptions": 0,
        "resource_groups": 0,
        "locations": 0,
        "providers": 0,
    }
    
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            async def fetch_stat(key, url, timeout=3.0):
                """Fetch a single stat endpoint"""
                try:
                    resp = await client.get(url, timeout=timeout)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            return (key, len(data))
                        elif isinstance(data, dict):
                            count = data.get("count", len(data.get("resources", [])))
                            return (key, count)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout fetching {key} stats")
                    return (key, -1)
                except Exception as e:
                    logger.warning(f"Failed to fetch {key}: {e}")
                    return (key, 0)
                return (key, 0)
            
            # Fetch all endpoints in parallel
            tasks = [
                fetch_stat("tenants", f"{API_GATEWAY_URL}/tenants", 3.0),
                fetch_stat("management_groups", f"{API_GATEWAY_URL}/resources/managementgroups", 3.0),
                fetch_stat("subscriptions", f"{API_GATEWAY_URL}/resources/subscriptions", 3.0),
                fetch_stat("resource_groups", f"{API_GATEWAY_URL}/resources/resourcegroups", 2.0),
                fetch_stat("locations", f"{API_GATEWAY_URL}/resources/locations", 3.0),
                fetch_stat("providers", f"{API_GATEWAY_URL}/providers/", 3.0),
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=False)
            for key, value in results:
                stats[key] = value
    
    except Exception as e:
        logger.warning(f"Failed to fetch landing stats: {e}")
    
    # Cache the results
    _stats_cache["data"] = stats
    _stats_cache["timestamp"] = current_time
    
    return stats

# API endpoint for stats (can be called via AJAX)
@app.get("/api/stats", tags=["API"])
async def get_stats_api():
    """Get platform statistics (used by frontend) - cached for 5 minutes"""
    stats = await _fetch_landing_stats()
    # Add HTTP cache headers: cache for 5 minutes (same as server-side TTL)
    return JSONResponse(
        content=stats,
        headers={
            "Cache-Control": "public, max-age=300",  # 5 minutes browser cache
            "Expires": "Thu, 15 Feb 2026 07:25:00 GMT",
        }
    )


async def _async_get_infra_data(timeout: float = None) -> dict:
    """Call the blocking `_get_infra_data` in a thread with timeout and a simple circuit-breaker.

    Returns cached last successful value while circuit is open.
    """
    if timeout is None:
        timeout = _INFRA_TIMEOUT

    now = datetime.now().timestamp()
    open_until = _INFRA_STATE.get("open_until")
    if open_until and now < open_until:
        # Circuit is open - return last known good value if available
        last = _INFRA_STATE.get("last_value")
        if last:
            logger.debug("Infra circuit open - returning cached infra data")
            return last
        return {"error": "Infra temporarily unavailable", "runtime": "unknown", "containers": [], "networks": [], "volumes": []}

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_get_infra_data), timeout=timeout)
        # success -> reset failure counter and cache result
        _INFRA_STATE["failures"] = 0
        _INFRA_STATE["last_success"] = now
        _INFRA_STATE["last_value"] = result
        return result
    except Exception as e:
        # record failure
        _INFRA_STATE["failures"] = _INFRA_STATE.get("failures", 0) + 1
        _INFRA_STATE["last_failure"] = now
        if _INFRA_STATE["failures"] >= _INFRA_FAILURE_THRESHOLD:
            _INFRA_STATE["open_until"] = now + _INFRA_COOLDOWN
            logger.warning("Infra circuit opened due to repeated failures")
        logger.error(f"Infra retrieval failed: {e}", exc_info=True)
        return {"error": str(e), "runtime": "unknown", "containers": [], "networks": [], "volumes": []}


# API endpoint for infrastructure data (lazy-loaded on frontend)
@app.get("/api/infra", tags=["API"])
async def get_infra_api(request: Request):
    """Get infrastructure and service data (used by frontend for lazy-loading)"""
    infra_data = {
        "infra": await _async_get_infra_data(),
        "services": await asyncio.to_thread(_get_service_status),
        "recent_activity": []
    }
    
    # Fetch recent activity
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{API_GATEWAY_URL}/activity-logs", params={"limit": 5})
            if resp.status_code == 200:
                data = resp.json()
                infra_data["recent_activity"] = data.get("value", [])
    except Exception as e:
        logger.warning(f"Failed to fetch activity logs: {e}")
    
    return JSONResponse(
        content=infra_data,
        headers={
            "Cache-Control": "public, max-age=10",  # 10 second cache for infra data
        }
    )


# Startup event: Pre-warm the stats cache
@app.on_event("startup")
async def startup_warm_cache():
    """Pre-fetch and cache stats on startup for fast initial page loads"""
    try:
        logger.info("Pre-warming stats cache on startup...")
        await _fetch_landing_stats()
        logger.info("Stats cache pre-warmed successfully")
    except Exception as e:
        logger.warning(f"Failed to pre-warm stats cache during startup: {e}")
        # Don't fail startup if cache warming fails, just continue


@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Public landing page with role-based widgets - renders immediately (no blocking infra fetches)"""
    # Get auth context and user
    auth_ctx = get_auth_context(request)
    user = auth_ctx.get("user")
    
    # Get user roles and visible widgets
    user_roles = get_user_roles(user)
    widgets = get_widgets_for_user(user_roles)
    
    # Return initial page with loading state - stats and infra will be fetched via AJAX
    widget_data = {
        "stats": {
            "tenants": None,  # Will be loaded via JS
            "management_groups": None,
            "subscriptions": None,
            "resource_groups": None,
            "locations": None,
            "providers": None,
        },
    }
    
    # DO NOT fetch infra data here - it blocks page render
    # Instead, lazy-load via /api/infra endpoint
    widget_data["infra"] = None  # Will be loaded via JS
    widget_data["services"] = None  # Will be loaded via JS
    widget_data["recent_activity"] = []  # Will be loaded via JS
    
    return templates.TemplateResponse("landing.html", {
        "request": request,
        **auth_ctx,
        "widgets": widgets,
        "widget_data": widget_data,
        "user_roles": user_roles,
        "is_admin": "platform_admin" in user_roles,
    })


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "ITL Control Plane Dashboard"}


# ════════════════════════════════════════════════════════════════════
# Tenant Switcher API
# ════════════════════════════════════════════════════════════════════

@app.get("/api/tenants")
async def get_tenants_api():
    """Get available tenants for switcher dropdown"""
    tenants = await fetch_available_tenants()
    return {"tenants": tenants}


@app.post("/api/tenant/select")
async def select_tenant(request: Request):
    """Set the selected tenant in session"""
    body = await request.json()
    tenant = body.get("tenant")
    set_selected_tenant(request, tenant)
    return {"selected_tenant": tenant}


@app.post("/api/tenant/clear")
async def clear_tenant(request: Request):
    """Clear the selected tenant from session"""
    set_selected_tenant(request, None)
    return {"selected_tenant": None}


@app.get("/api/tenant/current")
async def get_current_tenant_api(request: Request):
    """Get the currently selected tenant"""
    return {"selected_tenant": get_selected_tenant(request)}


@app.get("/api/graph")
async def graph_data(
    rg_limit: int = 1000,
    depth: int = 4,  # 1=tenant, 2=+mg, 3=+sub, 4=+rg, 5=+location
):
    """Return graph nodes and links for D3.js visualization from the resource hierarchy.
    
    Args:
        rg_limit: Maximum number of resource groups to include (default 1000)
        depth: Hierarchy depth to show (1=tenant, 2=+mg, 3=+sub, 4=+rg, 5=+location)
    """
    nodes = []
    links = []
    node_ids = set()

    def _extract_name(resource_path: str) -> str:
        """Extract the short name from a full resource path like /providers/ITL.Core/tenants/ITL -> ITL"""
        if not resource_path:
            return ""
        return resource_path.rstrip("/").split("/")[-1]

    def _safe_list(data):
        """Normalize API response to a list of resources"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # ARM style uses 'value', also support legacy 'resources'/'items'
            return data.get("value", data.get("resources", data.get("items", [])))
        return []

    location_names = set()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Always fetch tenants (depth >= 1)
            t_resp = await client.get(f"{API_GATEWAY_URL}/tenants")
            tenants = _safe_list(t_resp.json())
            
            # Fetch based on depth
            mgs, subs, rgs, locations = [], [], [], []
            if depth >= 2:
                mg_resp = await client.get(f"{API_GATEWAY_URL}/resources/managementgroups")
                mgs = _safe_list(mg_resp.json())
            if depth >= 3:
                s_resp = await client.get(f"{API_GATEWAY_URL}/resources/subscriptions")
                subs = _safe_list(s_resp.json())
            if depth >= 4:
                rg_resp = await client.get(f"{API_GATEWAY_URL}/resources/resourcegroups")
                rgs = _safe_list(rg_resp.json())
            if depth >= 5:
                loc_resp = await client.get(f"{API_GATEWAY_URL}/resources/locations")
                locations = _safe_list(loc_resp.json())

        # Build location nodes first (they will be linked from RGs)
        for loc in locations:
            loc_name = loc.get("name", "")
            if loc_name and loc_name not in node_ids:
                props = loc.get("properties", {})
                nodes.append({"id": loc_name, "label": props.get("display_name", loc_name), "type": "location"})
                node_ids.add(loc_name)
                location_names.add(loc_name)

        # Build tenant nodes
        for t in tenants:
            tid = t.get("name", "")
            if tid and tid not in node_ids:
                nodes.append({"id": tid, "label": t.get("properties", {}).get("display_name", tid), "type": "tenant"})
                node_ids.add(tid)

        # Build management group nodes + links to parent MG or tenant
        for mg in mgs:
            mg_name = mg.get("name", "")
            props = mg.get("properties", {})
            tenant = _extract_name(props.get("tenant_id", ""))
            parent_mg = _extract_name(props.get("parent_id", ""))
            if mg_name and mg_name not in node_ids:
                nodes.append({"id": mg_name, "label": props.get("display_name", mg_name), "type": "managementgroup"})
                node_ids.add(mg_name)
            if mg_name:
                # Link to parent MG if exists, otherwise link to tenant
                if parent_mg and parent_mg in node_ids:
                    links.append({"source": parent_mg, "target": mg_name})
                elif tenant and tenant in node_ids:
                    links.append({"source": tenant, "target": mg_name})

        # Build subscription nodes + links to management group
        for s in subs:
            s_name = s.get("name", "")
            props = s.get("properties", {})
            mg_parent = _extract_name(props.get("management_group_id", ""))
            if s_name and s_name not in node_ids:
                nodes.append({"id": s_name, "label": props.get("display_name", s_name), "type": "subscription"})
                node_ids.add(s_name)
            if s_name and mg_parent and mg_parent in node_ids:
                links.append({"source": mg_parent, "target": s_name})

        # Build resource group nodes + links to subscription
        rg_count = 0
        for rg in rgs:
            if rg_count >= rg_limit:
                break
            rg_name = rg.get("name", "")
            props = rg.get("properties", {})
            sub_parent = _extract_name(props.get("subscription_id", ""))
            rg_location = rg.get("location", "")
            if rg_name and rg_name not in node_ids:
                nodes.append({"id": rg_name, "label": rg_name, "type": "resourcegroup"})
                node_ids.add(rg_name)
                rg_count += 1
            if rg_name and sub_parent and sub_parent in node_ids:
                links.append({"source": sub_parent, "target": rg_name})
            # Link RG to its location (only if depth includes locations)
            if depth >= 5 and rg_name and rg_location and rg_location in location_names:
                links.append({"source": rg_name, "target": rg_location})

    except Exception as e:
        logger.error(f"Error building graph data: {e}", exc_info=True)

    return {"nodes": nodes, "links": links}


@app.get("/api/activity-logs")
async def get_activity_logs(
    scope: str = "/",
    action: str = None,
    resource_type: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    Proxy activity logs from Core Provider with scope-based filtering.
    
    Scope follows ARM hierarchy:
    - "/" or empty: All events (tenant level)
    - "/subscriptions/{name}": Subscription + children
    - "/subscriptions/{sub}/resourceGroups/{rg}": Resource group + children
    - Full resource ID: Single resource
    """
    try:
        params = {"scope": scope, "limit": limit, "offset": offset}
        if action:
            params["action"] = action
        if resource_type:
            params["resource_type"] = resource_type
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{API_GATEWAY_URL}/activity-logs", params=params)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"Activity logs request failed: {resp.status_code} {resp.text}")
                return {"value": [], "count": 0, "total_count": 0, "scope": scope, "error": resp.text}
    except Exception as e:
        logger.error(f"Error fetching activity logs: {e}", exc_info=True)
        return {"value": [], "count": 0, "total_count": 0, "scope": scope, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# Sample Queries API
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/sample-queries")
async def get_sample_queries():
    """Get all sample queries (built-in + user-defined) grouped by category"""
    return get_all_sample_queries()


@app.post("/api/sample-queries")
async def save_sample_query(request: Request):
    """Save a new user-defined sample query"""
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        query = body.get("query", "").strip()
        category = body.get("category", "My Queries").strip()
        description = body.get("description", "").strip()
        
        if not name or not query:
            return JSONResponse({"error": "Name and query are required"}, status_code=400)
        
        # Load existing user queries
        user_queries = load_user_sample_queries()
        
        # Check for duplicate name
        existing_names = [q.get("name", "").lower() for q in user_queries]
        if name.lower() in existing_names:
            return JSONResponse({"error": f"Query with name '{name}' already exists"}, status_code=409)
        
        # Add new query
        new_query = {
            "name": name,
            "query": query,
            "category": category,
            "description": description,
            "created": datetime.now(timezone.utc).isoformat(),
        }
        user_queries.append(new_query)
        
        if save_user_sample_queries(user_queries):
            new_query["source"] = "user"
            return {"success": True, "query": new_query}
        else:
            return JSONResponse({"error": "Failed to save query"}, status_code=500)
    except Exception as e:
        logger.error(f"Error saving sample query: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/sample-queries/{name}")
async def delete_sample_query(name: str):
    """Delete a user-defined sample query by name"""
    try:
        user_queries = load_user_sample_queries()
        original_count = len(user_queries)
        
        # Filter out the query with matching name (case-insensitive)
        user_queries = [q for q in user_queries if q.get("name", "").lower() != name.lower()]
        
        if len(user_queries) == original_count:
            return JSONResponse({"error": f"Query '{name}' not found"}, status_code=404)
        
        if save_user_sample_queries(user_queries):
            return {"success": True, "deleted": name}
        else:
            return JSONResponse({"error": "Failed to delete query"}, status_code=500)
    except Exception as e:
        logger.error(f"Error deleting sample query: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/activity-logs", response_class=HTMLResponse)
async def activity_logs_page(
    request: Request,
    scope: str = "/",
    action: str = None,
    resource_type: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """Render the Activity Logs page under Security/Monitoring"""
    # Require authentication
    auth_redirect = require_auth(request)
    if auth_redirect:
        return auth_redirect
    
    # Fetch activity logs
    logs = []
    total_count = 0
    error = None
    
    try:
        params = {"scope": scope, "limit": limit, "offset": offset}
        if action:
            params["action"] = action
        if resource_type:
            params["resource_type"] = resource_type
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{API_GATEWAY_URL}/activity-logs", params=params)
            if resp.status_code == 200:
                data = resp.json()
                logs = data.get("value", [])
                total_count = data.get("total_count", len(logs))
            else:
                error = f"API returned {resp.status_code}"
    except Exception as e:
        logger.error(f"Error fetching activity logs: {e}", exc_info=True)
        error = str(e)
    
    # Available filters
    actions = ["CREATE", "UPDATE", "DELETE", "READ"]
    resource_types = [
        "ITL.Core/tenants", "ITL.Core/managementgroups", 
        "ITL.Core/subscriptions", "ITL.Core/resourcegroups", "ITL.Core/locations"
    ]
    
    return templates.TemplateResponse("activity_logs.html", {
        "request": request,
        **get_auth_context(request),
        "title": "Activity Logs",
        "icon": "bi-clock-history",
        "logs": logs,
        "total_count": total_count,
        "error": error,
        "sidebar_items": _build_sidebar("activity-logs"),
        "filters": {
            "scope": scope,
            "action": action,
            "resource_type": resource_type,
            "limit": limit,
            "offset": offset,
        },
        "actions": actions,
        "resource_types": resource_types,
    })


@app.get("/talos-clusters", response_class=HTMLResponse)
async def talos_clusters_page(request: Request):
    """Render the Talos Clusters page"""
    # Require authentication
    auth_redirect = require_auth(request)
    if auth_redirect:
        return auth_redirect
    
    # Mock data for Talos clusters
    clusters = [
        {
            "name": "talos-prod-eu-west",
            "status": "healthy",
            "nodes": 5,
            "pods": 127,
            "cpu_usage": 42,
            "k8s_version": "1.29.2",
            "talos_version": "1.6.4",
            "region": "eu-west-1",
            "created": "2024-01-15",
            "node_list": [
                {"name": "cp-1", "role": "control-plane", "status": "ready"},
                {"name": "cp-2", "role": "control-plane", "status": "ready"},
                {"name": "cp-3", "role": "control-plane", "status": "ready"},
                {"name": "worker-1", "role": "worker", "status": "ready"},
                {"name": "worker-2", "role": "worker", "status": "ready"},
            ]
        },
        {
            "name": "talos-staging-eu-west",
            "status": "healthy",
            "nodes": 3,
            "pods": 45,
            "cpu_usage": 28,
            "k8s_version": "1.29.2",
            "talos_version": "1.6.4",
            "region": "eu-west-1",
            "created": "2024-02-01",
            "node_list": [
                {"name": "cp-1", "role": "control-plane", "status": "ready"},
                {"name": "worker-1", "role": "worker", "status": "ready"},
                {"name": "worker-2", "role": "worker", "status": "ready"},
            ]
        },
        {
            "name": "talos-dev-local",
            "status": "warning",
            "nodes": 3,
            "pods": 23,
            "cpu_usage": 65,
            "k8s_version": "1.28.5",
            "talos_version": "1.6.2",
            "region": "local",
            "created": "2024-03-10",
            "node_list": [
                {"name": "dev-cp", "role": "control-plane", "status": "ready"},
                {"name": "dev-worker-1", "role": "worker", "status": "ready"},
                {"name": "dev-worker-2", "role": "worker", "status": "not-ready"},
            ]
        },
    ]
    
    return templates.TemplateResponse("talos_clusters.html", {
        "request": request,
        **get_auth_context(request),
        "clusters": clusters,
        "sidebar_items": _build_sidebar("talos-clusters"),
    })


@app.get("/virtual-machines", response_class=HTMLResponse)
async def virtual_machines_page(request: Request):
    """Render the Virtual Machines page"""
    # Require authentication
    auth_redirect = require_auth(request)
    if auth_redirect:
        return auth_redirect
    
    # Mock data for VMs
    vms = [
        {
            "name": "vm-app-server-prod-01",
            "status": "running",
            "os_type": "linux",
            "os_name": "Ubuntu 22.04",
            "size": "Standard_D4s_v3",
            "ip_address": "10.0.1.10",
            "resource_group": "rg-production",
            "location": "westeurope",
        },
        {
            "name": "vm-app-server-prod-02",
            "status": "running",
            "os_type": "linux",
            "os_name": "Ubuntu 22.04",
            "size": "Standard_D4s_v3",
            "ip_address": "10.0.1.11",
            "resource_group": "rg-production",
            "location": "westeurope",
        },
        {
            "name": "vm-db-server-prod",
            "status": "running",
            "os_type": "linux",
            "os_name": "Debian 12",
            "size": "Standard_E8s_v3",
            "ip_address": "10.0.2.10",
            "resource_group": "rg-production",
            "location": "westeurope",
        },
        {
            "name": "vm-jumpbox-mgmt",
            "status": "stopped",
            "os_type": "windows",
            "os_name": "Windows Server 2022",
            "size": "Standard_B2s",
            "ip_address": "10.0.3.10",
            "resource_group": "rg-management",
            "location": "westeurope",
        },
        {
            "name": "vm-dev-workstation-01",
            "status": "deallocated",
            "os_type": "linux",
            "os_name": "Ubuntu 24.04",
            "size": "Standard_D8s_v3",
            "ip_address": "10.0.4.10",
            "resource_group": "rg-development",
            "location": "northeurope",
        },
        {
            "name": "vm-ci-runner-01",
            "status": "running",
            "os_type": "linux",
            "os_name": "Ubuntu 22.04",
            "size": "Standard_D2s_v3",
            "ip_address": "10.0.5.10",
            "resource_group": "rg-development",
            "location": "northeurope",
        },
    ]
    
    # Calculate summary
    running = sum(1 for vm in vms if vm["status"] == "running")
    stopped = sum(1 for vm in vms if vm["status"] in ("stopped", "deallocated"))
    
    summary = {
        "total": len(vms),
        "running": running,
        "stopped": stopped,
        "vcpus": 32,  # Mock value
        "memory_gb": 128,  # Mock value
    }
    
    return templates.TemplateResponse("virtual_machines.html", {
        "request": request,
        **get_auth_context(request),
        "vms": vms,
        "summary": summary,
        "sidebar_items": _build_sidebar("virtual-machines"),
    })


def _build_sidebar(active_type: str, tenant_context: Optional[str] = None) -> list:
    """Build sidebar navigation items with optional tenant prefix in URLs"""
    return build_sidebar(active_type, tenant_context, RUNNING_IN_KUBERNETES)


# ── Infrastructure Routes (functions extracted to src/services/infrastructure.py) ──

@app.get("/api/infra")
async def infra_api(request: Request):
    """Return infrastructure data as JSON (requires authentication)"""
    # Require authentication for infrastructure API
    if not is_authenticated(request):
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    try:
        data = await _async_get_infra_data()
        return data
    except Exception as e:
        logger.error(f"Infra API error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/infra", response_class=HTMLResponse)
async def infra_page(request: Request):
    """Render the infrastructure overview page"""
    # Require authentication
    auth_redirect = require_auth(request)
    if auth_redirect:
        return auth_redirect
    
    infra = await _async_get_infra_data()
    return templates.TemplateResponse("infra.html", {
        "request": request,
        **get_auth_context(request),
        "infra": infra,
        "sidebar_items": _build_sidebar("infra"),
    })


@app.get("/api/infra/{container_id}")
async def container_detail_api(container_id: str, request: Request):
    """Return detailed container info as JSON (requires authentication)"""
    # Require authentication for container details
    if not is_authenticated(request):
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    try:
        detail = await asyncio.to_thread(_get_container_detail, container_id)
        if "error" in detail:
            return JSONResponse(detail, status_code=404 if "not found" in detail.get("error", "").lower() else 500)
        return detail
    except Exception as e:
        logger.error(f"Error fetching container detail: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/infra/{container_id}/action")
async def container_action_route(container_id: str, request: Request):
    """Perform an action on a container: start, stop, restart, pause, unpause (requires authentication)"""
    if not is_authenticated(request):
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    
    try:
        body = await request.json()
        action = body.get("action", "")
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    try:
        result = await asyncio.to_thread(_container_action, container_id, action)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400 if "Invalid action" in str(e) else 404)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/infra/{container_id}/logs")
async def container_logs_api(container_id: str, request: Request, tail: int = 200):
    """Return container logs as plain text (requires authentication)"""
    if not is_authenticated(request):
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    
    try:
        result = await asyncio.to_thread(_get_container_logs, container_id, tail)
        return JSONResponse(result)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/infra/{container_id}", response_class=HTMLResponse)
async def container_detail_page(container_id: str, request: Request):
    """Render the container detail page"""
    # Require authentication
    auth_redirect = require_auth(request)
    if auth_redirect:
        return auth_redirect
    
    detail = await asyncio.to_thread(_get_container_detail, container_id)
    if "error" in detail:
        return RedirectResponse("/infra", status_code=302)

    # Get all containers for the left pane list
    infra = await _async_get_infra_data()
    all_containers = infra.get("containers", []) + infra.get("other_containers", [])

    return templates.TemplateResponse("container_detail.html", {
        "request": request,
        **get_auth_context(request),
        "container": detail,
        "all_containers": all_containers,
        "sidebar_items": _build_sidebar("infra"),
    })


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8090))
    uvicorn.run(app, host="0.0.0.0", port=port)
