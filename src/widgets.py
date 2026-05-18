"""
ITL Control Plane Dashboard - Widget System

Role-based widget system for dashboard customization.
Widgets can be shown/hidden based on user roles.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from enum import Enum


class WidgetRole(str, Enum):
    """Roles that can view widgets"""
    ANONYMOUS = "anonymous"           # Anyone, no login required
    AUTHENTICATED = "authenticated"   # Any logged-in user
    PLATFORM_ADMIN = "platform_admin" # Full platform administration
    TENANT_ADMIN = "tenant_admin"     # Tenant-level administration
    SUBSCRIPTION_ADMIN = "subscription_admin"
    READER = "reader"


class WidgetSize(str, Enum):
    """Widget size classes"""
    SMALL = "col-md-3"    # 25% width
    MEDIUM = "col-md-4"   # 33% width
    LARGE = "col-md-6"    # 50% width
    FULL = "col-12"       # Full width


@dataclass
class Widget:
    """Dashboard widget definition"""
    id: str
    title: str
    icon: str  # Bootstrap icon class
    template: str  # Template snippet name (e.g., "widgets/stats.html")
    
    # Visibility
    roles: List[WidgetRole] = field(default_factory=lambda: [WidgetRole.AUTHENTICATED])
    order: int = 100  # Lower = higher position
    
    # Layout
    size: WidgetSize = WidgetSize.MEDIUM
    
    # Data
    data_key: Optional[str] = None  # Key in context for widget data
    refresh_interval: int = 0  # Auto-refresh in seconds (0 = no refresh)
    
    # Features
    collapsible: bool = True
    closable: bool = False  # User can hide the widget
    
    def can_view(self, user_roles: List[str]) -> bool:
        """Check if user can view this widget based on roles"""
        # Anonymous widgets visible to all
        if WidgetRole.ANONYMOUS in self.roles:
            return True
        
        # Authenticated check for logged-in users
        if WidgetRole.AUTHENTICATED in self.roles and user_roles:
            return True
        
        # Check specific roles
        for role in self.roles:
            if role.value in user_roles:
                return True
        
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Widget Registry
# ═══════════════════════════════════════════════════════════════════════════

DASHBOARD_WIDGETS: List[Widget] = [
    # Platform Stats - visible to all
    Widget(
        id="platform_stats",
        title="Platform Overview",
        icon="bi-bar-chart",
        template="widgets/stats.html",
        roles=[WidgetRole.ANONYMOUS],
        order=10,
        size=WidgetSize.FULL,
        data_key="stats",
    ),
    
    # Service Status - platform admins only
    Widget(
        id="service_status",
        title="Service Status",
        icon="bi-activity",
        template="widgets/service_status.html",
        roles=[WidgetRole.PLATFORM_ADMIN],
        order=15,
        size=WidgetSize.FULL,
        data_key="services",
        refresh_interval=30,
    ),
    
    # Container Stack - platform admins only (shows Docker containers or K8s pods)
    Widget(
        id="container_stack",
        title="Platform Stack",
        icon="bi-box-seam",
        template="widgets/container_stack.html",
        roles=[WidgetRole.PLATFORM_ADMIN],
        order=20,
        size=WidgetSize.FULL,
        data_key="infra",
        refresh_interval=30,
    ),
    
    # Quick Links - authenticated users
    Widget(
        id="quick_links",
        title="Quick Links",
        icon="bi-collection",
        template="widgets/quick_links.html",
        roles=[WidgetRole.ANONYMOUS],
        order=30,
        size=WidgetSize.LARGE,
    ),
    
    # Infrastructure Links - platform admins
    Widget(
        id="infra_links",
        title="Infrastructure",
        icon="bi-gear",
        template="widgets/infra_links.html",
        roles=[WidgetRole.PLATFORM_ADMIN],
        order=40,
        size=WidgetSize.LARGE,
    ),
    
    # Recent Activity - authenticated users
    Widget(
        id="recent_activity",
        title="Recent Activity",
        icon="bi-clock-history",
        template="widgets/recent_activity.html",
        roles=[WidgetRole.AUTHENTICATED],
        order=50,
        size=WidgetSize.FULL,
        data_key="recent_activity",
        refresh_interval=60,
    ),
]


def get_widgets_for_user(user_roles: List[str]) -> List[Widget]:
    """Get list of widgets user can view, sorted by order"""
    visible = [w for w in DASHBOARD_WIDGETS if w.can_view(user_roles)]
    return sorted(visible, key=lambda w: w.order)


def get_user_roles(user: Optional[Any]) -> List[str]:
    """
    Extract roles from user session.
    For now, if user is logged in they get platform_admin role.
    TODO: Implement proper role extraction from Keycloak token.
    """
    if not user:
        return []
    
    # For MVP: logged in users are platform admins
    # Later: extract from access_token claims
    roles = ["authenticated"]
    
    # Check if user email is admin (simple check for now)
    email = getattr(user, "email", "") or ""
    if email:
        # All authenticated users get platform_admin for now
        # TODO: Replace with proper Keycloak role extraction
        roles.append("platform_admin")
    
    return roles
