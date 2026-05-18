"""
ITL Control Plane Dashboard - Resource Routes

Handles ARM-style resource list and detail pages.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx
from loguru import logger

from src.utils import extract_name, safe_list
from src.navigation import build_sidebar
from src.services.infrastructure import RUNNING_IN_KUBERNETES

router = APIRouter(tags=["resources"])

# Templates - initialized by init_templates()
templates: Jinja2Templates = None
API_GATEWAY_URL: str = None
get_auth_context = None
require_auth = None


def init_resources_router(
    tpl: Jinja2Templates,
    api_url: str,
    auth_context_fn,
    require_auth_fn,
):
    """Initialize the resources router with dependencies from main app."""
    global templates, API_GATEWAY_URL, get_auth_context, require_auth
    templates = tpl
    API_GATEWAY_URL = api_url
    get_auth_context = auth_context_fn
    require_auth = require_auth_fn


def _build_sidebar(active_type: str, tenant_context: Optional[str] = None) -> list:
    """Build sidebar navigation items with optional tenant prefix in URLs"""
    return build_sidebar(active_type, tenant_context, RUNNING_IN_KUBERNETES)


# ════════════════════════════════════════════════════════════════════════════════
# Resource Type Configurations
# ════════════════════════════════════════════════════════════════════════════════

RESOURCE_LIST_TYPE_MAP = {
    "all": {
        "title": "All Resources",
        "singular": "Resource",
        "endpoint": None,  # special: fetches all types
        "icon": "bi-collection",
        "color": "primary",
        "columns": [
            {"key": "name", "label": "Name", "link": True},
            {"key": "display_name", "label": "Display Name"},
            {"key": "_resource_type", "label": "Type", "badge": True, "badge_color": "primary"},
            {"key": "_resolved_tenant", "label": "Tenant", "badge": True, "badge_color": "primary"},
            {"key": "location", "label": "Location"},
            {"key": "state", "label": "State", "badge": True},
        ],
    },
    "tenants": {
        "title": "Tenants",
        "singular": "Tenant",
        "endpoint": "/tenants",
        "icon": "bi-building",
        "color": "primary",
        "columns": [
            {"key": "name", "label": "Name", "link": True},
            {"key": "display_name", "label": "Display Name"},
            {"key": "state", "label": "State", "badge": True},
            {"key": "id", "label": "Resource ID", "code": True},
        ],
    },
    "managementgroups": {
        "title": "Management Groups",
        "singular": "Management Group",
        "endpoint": "/resources/managementgroups",
        "icon": "bi-diagram-3",
        "color": "success",
        "columns": [
            {"key": "name", "label": "Name", "link": True},
            {"key": "display_name", "label": "Display Name"},
            {"key": "_resolved_tenant", "label": "Tenant", "badge": True, "badge_color": "primary"},
            {"key": "_resolved_parent", "label": "Parent"},
            {"key": "state", "label": "State", "badge": True},
        ],
    },
    "subscriptions": {
        "title": "Subscriptions",
        "singular": "Subscription",
        "endpoint": "/resources/subscriptions",
        "icon": "bi-credit-card",
        "color": "info",
        "columns": [
            {"key": "name", "label": "Name", "link": True},
            {"key": "display_name", "label": "Display Name"},
            {"key": "_resolved_mg", "label": "Management Group"},
            {"key": "_resolved_tenant", "label": "Tenant", "badge": True, "badge_color": "primary"},
            {"key": "state", "label": "State", "badge": True},
        ],
    },
    "resourcegroups": {
        "title": "Resource Groups",
        "singular": "Resource Group",
        "endpoint": "/resources/resourcegroups",
        "icon": "bi-folder",
        "color": "warning",
        "columns": [
            {"key": "name", "label": "Name", "link": True},
            {"key": "_resolved_subscription", "label": "Subscription"},
            {"key": "_resolved_tenant", "label": "Tenant", "badge": True, "badge_color": "primary"},
            {"key": "location", "label": "Location"},
            {"key": "state", "label": "State", "badge": True},
        ],
    },
    "locations": {
        "title": "Locations",
        "singular": "Location",
        "endpoint": "/resources/locations",
        "icon": "bi-geo-alt",
        "color": "secondary",
        "columns": [
            {"key": "name", "label": "Name", "link": True},
            {"key": "display_name", "label": "Display Name"},
            {"key": "type", "label": "Type"},
            {"key": "state", "label": "State", "badge": True},
        ],
    },
}

RESOURCE_DETAIL_TYPE_MAP = {
    "tenants": {"title": "Tenant", "plural": "Tenants", "endpoint": "/tenants", "icon": "bi-building", "color": "primary"},
    "managementgroups": {"title": "Management Group", "plural": "Management Groups", "endpoint": "/resources/managementgroups", "icon": "bi-diagram-3", "color": "success"},
    "subscriptions": {"title": "Subscription", "plural": "Subscriptions", "endpoint": "/resources/subscriptions", "icon": "bi-credit-card", "color": "info"},
    "resourcegroups": {"title": "Resource Group", "plural": "Resource Groups", "endpoint": "/resources/resourcegroups", "icon": "bi-folder", "color": "warning"},
    "locations": {"title": "Location", "plural": "Locations", "endpoint": "/resources/locations", "icon": "bi-geo-alt", "color": "secondary"},
}

TYPE_LABELS = {
    "tenants": "Tenant",
    "managementgroups": "Management Group",
    "subscriptions": "Subscription",
    "resourcegroups": "Resource Group",
    "locations": "Location",
}


# ════════════════════════════════════════════════════════════════════════════════
# Resource List Routes
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/{tenant}/resources/{resource_type}", response_class=HTMLResponse)
async def resource_list_with_tenant(request: Request, tenant: str, resource_type: str):
    """Render a resource list page filtered by tenant (Azure Portal-style URL)"""
    return await _render_resource_list(request, resource_type, tenant_context=tenant)


@router.get("/resources/{resource_type}", response_class=HTMLResponse)
async def resource_list(request: Request, resource_type: str):
    """Render a resource list page for a given resource type"""
    return await _render_resource_list(request, resource_type, tenant_context=None)


async def _render_resource_list(request: Request, resource_type: str, tenant_context: Optional[str] = None):
    """Internal: Render resource list with optional tenant filtering"""
    # Require authentication
    auth_redirect = require_auth(request)
    if auth_redirect:
        return auth_redirect
    
    meta = RESOURCE_LIST_TYPE_MAP.get(resource_type)
    if not meta:
        return templates.TemplateResponse("resources.html", {
            "request": request,
            **get_auth_context(request),
            "title": resource_type.title(),
            "singular": resource_type.title(),
            "icon": "bi-question-circle",
            "color": "dark",
            "resources": [],
            "count": 0,
            "resource_type": resource_type,
            "columns": [{"key": "name", "label": "Name", "link": True}],
            "sidebar_items": _build_sidebar(resource_type),
            "filters": {},
        })

    # Fetch dashboard stats + graph for the 'all' view
    dashboard_stats = None
    if resource_type == "all":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                stats_resp = await client.get(f"{API_GATEWAY_URL}/admin/stats")
                dashboard_stats = stats_resp.json()
        except Exception as e:
            logger.error(f"Error fetching stats: {e}")
            dashboard_stats = {
                "postgresql": {"total": 0, "tenants": 0, "management_groups": 0, "subscriptions": 0, "resource_groups": 0, "locations": 0},
                "neo4j": {"connected": False, "total_nodes": 0, "total_relationships": 0}
            }

    resources = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if resource_type == "all":
                # Fetch all resource types in parallel
                t_resp, mg_resp, s_resp, rg_resp, l_resp = await asyncio.gather(
                    client.get(f"{API_GATEWAY_URL}/tenants"),
                    client.get(f"{API_GATEWAY_URL}/resources/managementgroups"),
                    client.get(f"{API_GATEWAY_URL}/resources/subscriptions"),
                    client.get(f"{API_GATEWAY_URL}/resources/resourcegroups"),
                    client.get(f"{API_GATEWAY_URL}/resources/locations"),
                )
                all_tenants = safe_list(t_resp.json())
                all_mgs = safe_list(mg_resp.json())
                all_subs = safe_list(s_resp.json())
                all_rgs = safe_list(rg_resp.json())
                all_locs = safe_list(l_resp.json())

                # Tag each resource with its type for link routing
                for r in all_tenants: r["_src_type"] = "tenants"
                for r in all_mgs: r["_src_type"] = "managementgroups"
                for r in all_subs: r["_src_type"] = "subscriptions"
                for r in all_rgs: r["_src_type"] = "resourcegroups"
                for r in all_locs: r["_src_type"] = "locations"

                resources = all_tenants + all_mgs + all_subs + all_rgs + all_locs
            else:
                response = await client.get(f"{API_GATEWAY_URL}{meta['endpoint']}")
                data = response.json()
                resources = safe_list(data)

            # Resolve lookups for MGs (needed by subscriptions and resource groups)
            mg_tenant_map = {}
            mg_display_map = {}
            if resource_type in ("all", "resourcegroups", "subscriptions", "managementgroups"):
                if resource_type == "all":
                    mgs = all_mgs  # Already fetched above
                else:
                    mg_resp = await client.get(f"{API_GATEWAY_URL}/resources/managementgroups")
                    mgs = safe_list(mg_resp.json())
                for mg in mgs:
                    mg_name = mg.get("name", "")
                    tenant = extract_name(mg.get("properties", {}).get("tenant_id", ""))
                    display = mg.get("properties", {}).get("display_name", mg_name)
                    if mg_name:
                        mg_tenant_map[mg_name] = tenant
                        mg_display_map[mg_name] = display

            # Resolve subscription lookup (needed by resource groups)
            sub_tenant_map = {}
            sub_display_map = {}
            if resource_type in ("all", "resourcegroups"):
                if resource_type == "all":
                    subs = all_subs  # Already fetched above
                else:
                    sub_resp = await client.get(f"{API_GATEWAY_URL}/resources/subscriptions")
                    subs = safe_list(sub_resp.json())
                for s in subs:
                    s_name = s.get("name", "")
                    mg_name = extract_name(s.get("properties", {}).get("management_group_id", ""))
                    tenant = mg_tenant_map.get(mg_name, "")
                    display = s.get("properties", {}).get("display_name", s_name)
                    if s_name:
                        sub_tenant_map[s_name] = tenant
                        sub_display_map[s_name] = display

            # Enrich each resource with resolved fields
            for res in resources:
                props = res.get("properties", {}) or {}
                flat = {"name": res.get("name", ""), "type": res.get("type", ""), "location": res.get("location", "")}

                # Display name
                flat["display_name"] = props.get("display_name", "")

                # State
                flat["state"] = props.get("state", "") or props.get("provisioning_state", "")

                # Resource-type-specific resolved fields
                src_type = res.get("_src_type", resource_type)
                flat["_src_type"] = src_type

                if resource_type == "all":
                    flat["_resource_type"] = TYPE_LABELS.get(src_type, src_type)

                if src_type == "tenants":
                    flat["_resolved_tenant"] = res.get("name", "")
                    # Use GUID for tenant links
                    flat["_link_id"] = res.get("resource_guid") or props.get("tenant_id") or res.get("name", "")

                elif src_type == "managementgroups":
                    flat["_resolved_tenant"] = extract_name(props.get("tenant_id", ""))
                    parent_name = extract_name(props.get("parent_id", ""))
                    flat["_resolved_parent"] = mg_display_map.get(parent_name, parent_name)

                elif src_type == "subscriptions":
                    mg_name = extract_name(props.get("management_group_id", ""))
                    flat["_resolved_mg"] = mg_display_map.get(mg_name, mg_name)
                    # Tenant from management group chain, or direct tenant_id field
                    flat["_resolved_tenant"] = mg_tenant_map.get(mg_name, "") or res.get("tenant_id", "") or extract_name(props.get("tenant_id", ""))
                    # Use GUID for subscription links
                    flat["_link_id"] = res.get("subscription_id") or res.get("resource_guid") or props.get("subscription_id") or res.get("name", "")

                elif src_type == "resourcegroups":
                    sub_name = extract_name(props.get("subscription_id", ""))
                    flat["_resolved_subscription"] = sub_display_map.get(sub_name, sub_name)
                    flat["_resolved_tenant"] = sub_tenant_map.get(sub_name, "")

                res["_flat"] = flat

    except Exception as e:
        logger.error(f"Error fetching {resource_type}: {e}", exc_info=True)
        resources = []

    # Filter by tenant if tenant_context is specified
    if tenant_context:
        resources = [r for r in resources if r.get("_flat", {}).get("_resolved_tenant", "") == tenant_context]

    # Collect unique values for filters
    tenants = sorted(set(r.get("_flat", {}).get("_resolved_tenant", "") for r in resources if r.get("_flat", {}).get("_resolved_tenant")))
    locations = sorted(set(r.get("_flat", {}).get("location", "") for r in resources if r.get("_flat", {}).get("location")))

    return templates.TemplateResponse("resources.html", {
        "request": request,
        **get_auth_context(request),
        "title": meta["title"],
        "singular": meta["singular"],
        "icon": meta["icon"],
        "color": meta["color"],
        "resources": resources,
        "count": len(resources),
        "resource_type": resource_type,
        "columns": meta["columns"],
        "sidebar_items": _build_sidebar(resource_type, tenant_context),
        "filters": {"tenants": tenants, "locations": locations},
        "dashboard_stats": dashboard_stats,
        "tenant_context": tenant_context,  # Azure-style tenant in URL
    })


# ════════════════════════════════════════════════════════════════════════════════
# Resource Detail Routes
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/{tenant}/resources/{resource_type}/{resource_name}", response_class=HTMLResponse)
async def resource_detail_with_tenant(request: Request, tenant: str, resource_type: str, resource_name: str):
    """Render a resource detail page filtered by tenant (Azure Portal-style URL)"""
    return await _render_resource_detail(request, resource_type, resource_name, tenant_context=tenant)


@router.get("/resources/{resource_type}/{resource_name}", response_class=HTMLResponse)
async def resource_detail(request: Request, resource_type: str, resource_name: str):
    """Render a resource detail page with Azure-style split-pane layout"""
    return await _render_resource_detail(request, resource_type, resource_name, tenant_context=None)


async def _render_resource_detail(request: Request, resource_type: str, resource_name: str, tenant_context: Optional[str] = None):
    """Internal: Render resource detail with optional tenant context"""
    # Require authentication
    auth_redirect = require_auth(request)
    if auth_redirect:
        return auth_redirect
    
    meta = RESOURCE_DETAIL_TYPE_MAP.get(resource_type, {
        "title": resource_type,
        "plural": resource_type,
        "endpoint": f"/resources/{resource_type}",
        "icon": "bi-question-circle",
        "color": "dark"
    })

    resource = None
    siblings = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Always fetch the full list (we need siblings anyway)
            list_resp = await client.get(f"{API_GATEWAY_URL}{meta['endpoint']}")
            all_items = safe_list(list_resp.json())
            
            # For tenants, add link_id field (use GUID for URL)
            if resource_type == "tenants":
                for item in all_items:
                    item["link_id"] = item.get("resource_guid") or item.get("properties", {}).get("tenant_id") or item.get("name")
            
            # For subscriptions, add link_id field (subscription_id is snake_case in API response)
            if resource_type == "subscriptions":
                for item in all_items:
                    item["link_id"] = item.get("subscription_id") or item.get("resource_guid") or item.get("properties", {}).get("subscription_id") or item.get("name")
            
            siblings = all_items

            # Find the selected resource (by name or by GUID for tenants/subscriptions)
            for item in all_items:
                if item.get("name") == resource_name:
                    resource = item
                    break
                # For tenants and subscriptions, also match by GUID
                if resource_type in ("tenants", "subscriptions") and item.get("link_id") == resource_name:
                    resource = item
                    break

            # If not found in list, try direct endpoint
            if not resource:
                detail_url = f"{API_GATEWAY_URL}{meta['endpoint']}/{resource_name}"
                resp = await client.get(detail_url)
                if resp.status_code == 200:
                    resource = resp.json()

    except Exception as e:
        logger.error(f"Error fetching {resource_type}/{resource_name}: {e}", exc_info=True)

    # Build the detail sidebar menu (Azure-style)
    detail_sidebar = [
        {"label": "Overview", "icon": "bi-speedometer2", "section": "overview", "active": True},
        {"label": "Activity log", "icon": "bi-clock-history", "section": "activity"},
        {"label": "Access control (IAM)", "icon": "bi-shield-lock", "section": "iam"},
        {"label": "Tags", "icon": "bi-tags", "section": "tags"},
        {"label": "Resource visualizer", "icon": "bi-diagram-3", "section": "visualizer"},
        {"is_divider": True},
        {"label": "Settings", "icon": "bi-gear", "section": "settings"},
        {"label": "Properties", "icon": "bi-list-ul", "section": "properties"},
    ]

    # Build essentials — key-value pairs shown at the top of the detail
    essentials = []
    if resource:
        props = resource.get("properties", {}) or {}

        if props.get("subscription_id"):
            sub_name = extract_name(props["subscription_id"])
            essentials.append({"label": "Subscription", "value": sub_name, "link": f"/resources/subscriptions/{sub_name}"})

        if props.get("management_group_id"):
            mg_name = extract_name(props["management_group_id"])
            essentials.append({"label": "Management Group", "value": mg_name, "link": f"/resources/managementgroups/{mg_name}"})

        if props.get("tenant_id"):
            t_name = extract_name(props["tenant_id"])
            essentials.append({"label": "Tenant ID", "value": t_name, "link": f"/resources/tenants/{t_name}"})

        if props.get("parent_id"):
            p_name = extract_name(props["parent_id"])
            essentials.append({"label": "Parent", "value": p_name, "link": f"/resources/{resource_type}/{p_name}"})

        if props.get("provisioning_state"):
            essentials.append({"label": "Status", "value": props["provisioning_state"]})

        if props.get("state"):
            essentials.append({"label": "State", "value": props["state"]})

        if resource.get("location"):
            essentials.append({"label": "Location", "value": resource["location"]})

        # For subscriptions, show the subscription_id GUID
        if resource_type == "subscriptions" and resource.get("subscription_id"):
            essentials.append({"label": "Subscription ID", "value": resource["subscription_id"]})

        # Display name - use context-appropriate label
        if props.get("display_name"):
            if resource_type == "tenants":
                essentials.append({"label": "Tenant", "value": props["display_name"]})
            elif resource_type == "subscriptions":
                essentials.append({"label": "Subscription", "value": props["display_name"]})
            else:
                essentials.append({"label": "Display Name", "value": props["display_name"]})

        if props.get("created_at"):
            essentials.append({"label": "Created", "value": props["created_at"][:19].replace("T", " ")})

    return templates.TemplateResponse("resource_detail.html", {
        "request": request,
        **get_auth_context(request),
        "title": meta["title"],
        "plural": meta["plural"],
        "icon": meta["icon"],
        "color": meta["color"],
        "resource": resource,
        "resource_name": resource_name,
        "resource_type": resource_type,
        "siblings": siblings,
        "detail_sidebar": detail_sidebar,
        "essentials": essentials,
        "tenant_context": tenant_context,  # Azure-style tenant in URL
    })
