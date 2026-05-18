"""Navigation and sidebar configuration for the ITL Control Plane Dashboard"""
from typing import List, Optional


def build_sidebar(active_type: str, tenant_context: Optional[str] = None, running_in_kubernetes: bool = False) -> List[dict]:
    """Build sidebar navigation items with optional tenant prefix in URLs.
    
    Args:
        active_type: The currently active resource type (e.g., "subscriptions")
        tenant_context: Optional tenant name for Azure-style tenant-scoped URLs
        running_in_kubernetes: Whether running in K8s (affects infra label)
    
    Returns:
        List of sidebar item dicts with type, label, icon, href, and active flag
    """
    # URL prefix for tenant-aware navigation (Azure-style)
    prefix = f"/{tenant_context}" if tenant_context else ""
    
    items = [
        # ── Resource Manager ──────────────────────────────────────
        {"type": "", "label": "Resource Manager", "icon": "bi-grid", "is_header": True},
        {"type": "all", "label": "All Resources", "icon": "bi-collection", "href": f"{prefix}/resources/all"},
        {"type": "tenants", "label": "Tenants", "icon": "bi-building", "href": "/resources/tenants"},  # Global: no prefix
        {"type": "managementgroups", "label": "Management Groups", "icon": "bi-diagram-3", "href": f"{prefix}/resources/managementgroups"},
        {"type": "subscriptions", "label": "Subscriptions", "icon": "bi-credit-card", "href": f"{prefix}/resources/subscriptions"},
        {"type": "resourcegroups", "label": "Resource Groups", "icon": "bi-folder", "href": f"{prefix}/resources/resourcegroups"},
        {"type": "locations", "label": "Locations", "icon": "bi-geo-alt", "href": "/resources/locations"},  # Global: no prefix
        {"type": "", "label": "", "icon": "", "is_divider": True},
        {"type": "tags", "label": "Tags", "icon": "bi-tags", "href": "#"},
        {"type": "deployments", "label": "Deployments", "icon": "bi-rocket", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Management ────────────────────────────────────────────
        {"type": "", "label": "Management", "icon": "bi-sliders", "is_header": True},
        {"type": "subscription-mgmt", "label": "Subscription Settings", "icon": "bi-credit-card-2-front", "href": "#"},
        {"type": "resource-providers", "label": "Resource Providers", "icon": "bi-plugin", "href": "#"},
        {"type": "resource-locks", "label": "Resource Locks", "icon": "bi-lock", "href": "#"},
        {"type": "governance", "label": "Governance", "icon": "bi-clipboard2-data", "href": "#"},
        {"type": "compliance", "label": "Compliance", "icon": "bi-patch-check", "href": "#"},
        {"type": "quotas", "label": "Quotas & Limits", "icon": "bi-speedometer", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Identity ──────────────────────────────────────────────
        {"type": "", "label": "Identity", "icon": "bi-person-badge", "is_header": True},
        {"type": "users", "label": "Users", "icon": "bi-people", "href": "#"},
        {"type": "groups", "label": "Groups", "icon": "bi-people-fill", "href": "#"},
        {"type": "roles", "label": "Roles", "icon": "bi-person-lock", "href": "#"},
        {"type": "service-principals", "label": "Service Principals", "icon": "bi-robot", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Compute ───────────────────────────────────────────────
        {"type": "", "label": "Compute", "icon": "bi-cpu", "is_header": True},
        {"type": "talos-clusters", "label": "Secure Talos Clusters", "icon": "bi-shield-lock", "href": "/talos-clusters"},
        {"type": "proxmox-clusters", "label": "Proxmox Clusters", "icon": "bi-hdd-stack", "href": "#"},
        {"type": "virtual-machines", "label": "Virtual Machines", "icon": "bi-pc-display", "href": "/virtual-machines"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Networking ────────────────────────────────────────────
        {"type": "", "label": "Networking", "icon": "bi-diagram-2", "is_header": True},
        {"type": "virtual-networks", "label": "Virtual Networks", "icon": "bi-hdd-network", "href": "#"},
        {"type": "subnets", "label": "Subnets", "icon": "bi-bezier2", "href": "#"},
        {"type": "nsgs", "label": "Network Security Groups", "icon": "bi-shield-exclamation", "href": "#"},
        {"type": "load-balancers", "label": "Load Balancers", "icon": "bi-arrows-expand", "href": "#"},
        {"type": "dns-zones", "label": "DNS Zones", "icon": "bi-globe", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Storage ───────────────────────────────────────────────
        {"type": "", "label": "Storage", "icon": "bi-database", "is_header": True},
        {"type": "storage-accounts", "label": "Storage Accounts", "icon": "bi-archive", "href": "#"},
        {"type": "blob-containers", "label": "Blob Containers", "icon": "bi-box", "href": "#"},
        {"type": "file-shares", "label": "File Shares", "icon": "bi-folder2-open", "href": "#"},
        {"type": "disks", "label": "Managed Disks", "icon": "bi-disc", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Databases ─────────────────────────────────────────────
        {"type": "", "label": "Databases", "icon": "bi-server", "is_header": True},
        {"type": "postgresql", "label": "PostgreSQL", "icon": "bi-database-fill", "href": "#"},
        {"type": "mysql", "label": "MySQL", "icon": "bi-database", "href": "#"},
        {"type": "redis", "label": "Redis Cache", "icon": "bi-lightning", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Security ──────────────────────────────────────────────
        {"type": "", "label": "Security", "icon": "bi-shield-lock", "is_header": True},
        {"type": "key-vaults", "label": "Key Vaults", "icon": "bi-key", "href": "#"},
        {"type": "secrets", "label": "Secrets", "icon": "bi-file-lock", "href": "#"},
        {"type": "certificates", "label": "Certificates", "icon": "bi-award", "href": "#"},
        {"type": "policies", "label": "Policies", "icon": "bi-clipboard-check", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Monitoring ────────────────────────────────────────────
        {"type": "", "label": "Monitoring", "icon": "bi-graph-up", "is_header": True},
        {"type": "activity-logs", "label": "Activity Logs", "icon": "bi-clock-history", "href": "/activity-logs"},
        {"type": "alerts", "label": "Alerts", "icon": "bi-bell", "href": "#"},
        {"type": "metrics", "label": "Metrics", "icon": "bi-speedometer2", "href": "#"},
        {"type": "log-analytics", "label": "Log Analytics", "icon": "bi-journal-text", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Cost Management ───────────────────────────────────────
        {"type": "", "label": "Cost Management", "icon": "bi-currency-dollar", "is_header": True},
        {"type": "budgets", "label": "Budgets", "icon": "bi-piggy-bank", "href": "#"},
        {"type": "cost-analysis", "label": "Cost Analysis", "icon": "bi-pie-chart", "href": "#"},
        {"type": "usage-reports", "label": "Usage Reports", "icon": "bi-bar-chart-line", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Automation ────────────────────────────────────────────
        {"type": "", "label": "Automation", "icon": "bi-gear-wide-connected", "is_header": True},
        {"type": "runbooks", "label": "Runbooks", "icon": "bi-journal-code", "href": "#"},
        {"type": "schedules", "label": "Schedules", "icon": "bi-calendar-event", "href": "#"},
        {"type": "pipelines", "label": "Pipelines", "icon": "bi-arrow-left-right", "href": "#"},
        {"type": "jobs", "label": "Jobs", "icon": "bi-play-circle", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Kubernetes ────────────────────────────────────────────
        {"type": "", "label": "Kubernetes", "icon": "bi-box-seam", "is_header": True},
        {"type": "k8s-clusters", "label": "Clusters", "icon": "bi-boxes", "href": "#"},
        {"type": "k8s-namespaces", "label": "Namespaces", "icon": "bi-layers", "href": "#"},
        {"type": "k8s-workloads", "label": "Workloads", "icon": "bi-stack", "href": "#"},
        {"type": "k8s-services", "label": "Services", "icon": "bi-signpost-2", "href": "#"},
        {"type": "", "label": "", "icon": "", "is_divider": True},
        
        # ── Infrastructure ────────────────────────────────────────
        {"type": "", "label": "Infrastructure", "icon": "bi-hdd-rack", "is_header": True},
        {"type": "infra", "label": "Kubernetes" if running_in_kubernetes else "Docker Stack", "icon": "bi-boxes" if running_in_kubernetes else "bi-box-seam", "href": "/infra"},
    ]
    
    # Mark active item
    for item in items:
        item["active"] = item.get("type") == active_type
    
    return items


# Resource type metadata for list/detail views
RESOURCE_TYPE_LIST_CONFIG = {
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

RESOURCE_TYPE_DETAIL_CONFIG = {
    "tenants": {"title": "Tenant", "plural": "Tenants", "endpoint": "/tenants", "icon": "bi-building", "color": "primary"},
    "managementgroups": {"title": "Management Group", "plural": "Management Groups", "endpoint": "/resources/managementgroups", "icon": "bi-diagram-3", "color": "success"},
    "subscriptions": {"title": "Subscription", "plural": "Subscriptions", "endpoint": "/resources/subscriptions", "icon": "bi-credit-card", "color": "info"},
    "resourcegroups": {"title": "Resource Group", "plural": "Resource Groups", "endpoint": "/resources/resourcegroups", "icon": "bi-folder", "color": "warning"},
    "locations": {"title": "Location", "plural": "Locations", "endpoint": "/resources/locations", "icon": "bi-geo-alt", "color": "secondary"},
}

# Type labels for the 'all resources' view
RESOURCE_TYPE_LABELS = {
    "tenants": "Tenant",
    "managementgroups": "Management Group",
    "subscriptions": "Subscription",
    "resourcegroups": "Resource Group",
    "locations": "Location",
}

# Detail sidebar menu (Azure-style)
RESOURCE_DETAIL_SIDEBAR = [
    {"label": "Overview", "icon": "bi-speedometer2", "section": "overview", "active": True},
    {"label": "Activity log", "icon": "bi-clock-history", "section": "activity"},
    {"label": "Access control (IAM)", "icon": "bi-shield-lock", "section": "iam"},
    {"label": "Tags", "icon": "bi-tags", "section": "tags"},
    {"label": "Resource visualizer", "icon": "bi-diagram-3", "section": "visualizer"},
    {"is_divider": True},
    {"label": "Settings", "icon": "bi-gear", "section": "settings"},
    {"label": "Properties", "icon": "bi-list-ul", "section": "properties"},
]
