"""Infrastructure Service - Docker and Kubernetes infrastructure data gathering"""
import os
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

# ── Runtime Detection (Docker vs Kubernetes) ─────────────────────────────
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None
    logger.warning("Docker SDK not available — Docker infra will be disabled")

try:
    from kubernetes import client as k8s_client, config as k8s_config
    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False
    k8s_client = None
    k8s_config = None
    logger.warning("Kubernetes SDK not available — K8s infra will be disabled")

# Auto-detect runtime environment
RUNNING_IN_KUBERNETES = os.environ.get("KUBERNETES_SERVICE_HOST") is not None
if RUNNING_IN_KUBERNETES:
    logger.info("Detected Kubernetes environment")
else:
    logger.info("Detected Docker/local environment")


# Service name mapping for health status display
SERVICE_NAME_MAP = {
    "api-gateway": "API Gateway",
    "itl-api-gateway": "API Gateway",
    "postgres": "PostgreSQL",
    "itl-postgres": "PostgreSQL",
    "redis": "Redis",
    "itl-redis": "Redis",
    "neo4j": "Neo4j",
    "itl-neo4j": "Neo4j",
    "rabbitmq": "RabbitMQ",
    "itl-rabbitmq": "RabbitMQ",
}

SERVICE_DISPLAY_ORDER = ["API Gateway", "PostgreSQL", "Redis", "Neo4j", "RabbitMQ"]


def get_service_status() -> dict:
    """Get health status of key platform services from Docker containers."""
    services = []
    
    if not DOCKER_AVAILABLE:
        return {"services": services}
    
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True)
        
        for c in containers:
            svc = c.labels.get("com.docker.compose.service", "")
            name = c.name
            friendly_name = SERVICE_NAME_MAP.get(svc) or SERVICE_NAME_MAP.get(name)
            
            if friendly_name:
                # Get health status
                health_data = c.attrs.get("State", {}).get("Health", {})
                health_status = health_data.get("Status", "none") if health_data else "none"
                
                if c.status == "running":
                    if health_status == "healthy":
                        status = "healthy"
                        detail = "Healthy"
                    elif health_status == "unhealthy":
                        status = "error"
                        detail = "Unhealthy"
                    elif health_status == "starting":
                        status = "warning"
                        detail = "Starting"
                    else:
                        status = "healthy"
                        detail = "Running"
                else:
                    status = "error"
                    detail = c.status.capitalize()
                
                services.append({
                    "name": friendly_name,
                    "status": status,
                    "detail": detail,
                })
        
        # Sort services for consistent display
        services.sort(key=lambda s: SERVICE_DISPLAY_ORDER.index(s["name"]) if s["name"] in SERVICE_DISPLAY_ORDER else 999)
        
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
    
    return {"services": services}


def get_infra_data() -> dict:
    """Auto-detect runtime environment and return infrastructure data."""
    if RUNNING_IN_KUBERNETES and KUBERNETES_AVAILABLE:
        return _get_k8s_infra_data()
    elif DOCKER_AVAILABLE:
        return _get_docker_infra_data()
    else:
        return {
            "error": "No infrastructure backend available",
            "runtime": "unknown",
            "containers": [],
            "networks": [],
            "volumes": [],
        }


def _get_k8s_infra_data() -> dict:
    """Get infrastructure data from Kubernetes API."""
    try:
        # Load in-cluster config (works when running as a pod)
        k8s_config.load_incluster_config()
    except Exception:
        try:
            # Fallback to kubeconfig (for local development)
            k8s_config.load_kube_config()
        except Exception as e:
            logger.error(f"Cannot load Kubernetes config: {e}")
            return {"error": str(e), "runtime": "kubernetes", "pods": [], "services": [], "deployments": []}

    v1 = k8s_client.CoreV1Api()
    apps_v1 = k8s_client.AppsV1Api()

    # Get current namespace (from mounted serviceaccount or default)
    namespace = os.environ.get("POD_NAMESPACE", "default")
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as f:
            namespace = f.read().strip()
    except Exception:
        pass

    pods = []
    services = []
    deployments = []

    try:
        # List pods in namespace
        pod_list = v1.list_namespaced_pod(namespace)
        for pod in pod_list.items:
            # Parse container statuses
            container_statuses = []
            for cs in (pod.status.container_statuses or []):
                container_statuses.append({
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "image": cs.image,
                    "state": "running" if cs.state.running else ("waiting" if cs.state.waiting else "terminated"),
                })

            # Calculate uptime
            uptime = ""
            if pod.status.start_time:
                delta = datetime.now(timezone.utc) - pod.status.start_time
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                if hours > 24:
                    uptime = f"{hours // 24}d {hours % 24}h"
                else:
                    uptime = f"{hours}h {minutes}m"

            pods.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "ip": pod.status.pod_ip or "",
                "node": pod.spec.node_name or "",
                "containers": container_statuses,
                "uptime": uptime,
                "labels": dict(pod.metadata.labels or {}),
            })

        # List services in namespace
        svc_list = v1.list_namespaced_service(namespace)
        for svc in svc_list.items:
            ports = []
            for port in (svc.spec.ports or []):
                ports.append({
                    "name": port.name or "",
                    "port": port.port,
                    "target_port": str(port.target_port),
                    "protocol": port.protocol,
                })
            services.append({
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "type": svc.spec.type,
                "cluster_ip": svc.spec.cluster_ip or "",
                "external_ip": (svc.status.load_balancer.ingress[0].ip if svc.status.load_balancer and svc.status.load_balancer.ingress else ""),
                "ports": ports,
            })

        # List deployments in namespace
        deploy_list = apps_v1.list_namespaced_deployment(namespace)
        for deploy in deploy_list.items:
            deployments.append({
                "name": deploy.metadata.name,
                "namespace": deploy.metadata.namespace,
                "replicas": deploy.spec.replicas or 0,
                "ready_replicas": deploy.status.ready_replicas or 0,
                "available_replicas": deploy.status.available_replicas or 0,
                "image": deploy.spec.template.spec.containers[0].image if deploy.spec.template.spec.containers else "",
            })

    except Exception as e:
        logger.error(f"Error fetching Kubernetes resources: {e}")
        return {"error": str(e), "runtime": "kubernetes", "pods": [], "services": [], "deployments": []}

    return {
        "runtime": "kubernetes",
        "namespace": namespace,
        "pods": pods,
        "services": services,
        "deployments": deployments,
    }


def _get_docker_infra_data() -> dict:
    """Auto-detect the Docker Compose stack by querying the Docker daemon."""
    if not DOCKER_AVAILABLE:
        return {"error": "Docker SDK not installed", "runtime": "docker", "containers": [], "networks": [], "volumes": []}

    try:
        client = docker.from_env()
    except Exception as e:
        logger.error(f"Cannot connect to Docker daemon: {e}")
        return {"error": str(e), "runtime": "docker", "containers": [], "networks": [], "volumes": []}

    # Auto-detect compose project from this container's labels
    my_hostname = os.environ.get("HOSTNAME", "")
    compose_project = None
    try:
        me = client.containers.get(my_hostname)
        compose_project = me.labels.get("com.docker.compose.project", None)
    except Exception:
        # Fallback: find project from any itl- container
        for c in client.containers.list(all=True):
            proj = c.labels.get("com.docker.compose.project")
            if proj:
                compose_project = proj
                break

    # List all containers in this compose project
    all_containers = client.containers.list(all=True)
    compose_containers = []
    other_containers = []

    for c in all_containers:
        proj = c.labels.get("com.docker.compose.project", "")
        svc = c.labels.get("com.docker.compose.service", "")

        # Parse port bindings
        ports = []
        port_bindings = c.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        for container_port, bindings in port_bindings.items():
            if bindings:
                for b in bindings:
                    host_port = b.get("HostPort", "")
                    if host_port:
                        ports.append({"host": host_port, "container": container_port})

        # Parse health status
        health_status = "none"
        health_data = c.attrs.get("State", {}).get("Health", {})
        if health_data:
            health_status = health_data.get("Status", "none")

        # Started at
        started_at = c.attrs.get("State", {}).get("StartedAt", "")
        uptime = ""
        if started_at and c.status == "running":
            try:
                start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - start_dt
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                if hours > 24:
                    uptime = f"{hours // 24}d {hours % 24}h"
                elif hours > 0:
                    uptime = f"{hours}h {minutes}m"
                else:
                    uptime = f"{minutes}m"
            except Exception:
                pass

        # Safely resolve image tag — image may no longer exist after rebuild
        try:
            img = c.image
            image_name = img.tags[0] if img.tags else c.attrs.get("Config", {}).get("Image", "unknown")
        except Exception:
            image_name = c.attrs.get("Config", {}).get("Image", "unknown")

        # Get environment variables (filter sensitive)
        env_vars = []
        for env in c.attrs.get("Config", {}).get("Env", []) or []:
            key = env.split("=")[0] if "=" in env else env
            # Hide sensitive values
            if any(s in key.lower() for s in ["password", "secret", "key", "token", "credential"]):
                env_vars.append(f"{key}=***")
            else:
                env_vars.append(env)

        # Get mounts
        mounts = []
        for m in c.attrs.get("Mounts", []) or []:
            mounts.append({
                "type": m.get("Type", ""),
                "source": m.get("Source", ""),
                "destination": m.get("Destination", ""),
                "mode": m.get("Mode", "rw"),
            })

        # Get resource limits
        host_config = c.attrs.get("HostConfig", {})
        resources = {
            "memory_limit": host_config.get("Memory", 0),
            "cpu_shares": host_config.get("CpuShares", 0),
            "cpu_quota": host_config.get("CpuQuota", 0),
        }

        # Get network info
        network_settings = c.attrs.get("NetworkSettings", {})
        container_networks = []
        for net_name, net_info in (network_settings.get("Networks", {}) or {}).items():
            container_networks.append({
                "name": net_name,
                "ip": net_info.get("IPAddress", ""),
                "gateway": net_info.get("Gateway", ""),
            })

        # Get command
        cmd = c.attrs.get("Config", {}).get("Cmd", []) or []
        entrypoint = c.attrs.get("Config", {}).get("Entrypoint", []) or []

        info = {
            "id": c.short_id,
            "full_id": c.id,
            "name": c.name,
            "service": svc or c.name,
            "image": image_name,
            "status": c.status,
            "health": health_status,
            "ports": ports,
            "uptime": uptime,
            "started_at": started_at,
            "compose_project": proj,
            "labels": {k: v for k, v in c.labels.items() if k.startswith("com.docker.compose.")},
            "env_vars": env_vars,
            "mounts": mounts,
            "resources": resources,
            "networks": container_networks,
            "command": cmd,
            "entrypoint": entrypoint,
        }

        if proj == compose_project:
            compose_containers.append(info)
        else:
            other_containers.append(info)

    # Sort: compose containers by service name
    compose_containers.sort(key=lambda x: x["service"])
    other_containers.sort(key=lambda x: x["name"])

    # List compose networks
    networks = []
    for n in client.networks.list():
        proj = (n.attrs.get("Labels") or {}).get("com.docker.compose.project", "")
        if proj == compose_project:
            try:
                net_detail = client.networks.get(n.id)
                connected = list(net_detail.attrs.get("Containers", {}).values())
                connected = [c.get("Name", "") for c in connected]
            except Exception:
                connected = []
            networks.append({
                "name": n.name,
                "driver": n.attrs.get("Driver", "unknown"),
                "scope": n.attrs.get("Scope", ""),
                "containers": connected,
            })

    # List compose volumes
    volumes = []
    for v in client.volumes.list():
        proj = (v.attrs.get("Labels") or {}).get("com.docker.compose.project", "")
        if proj == compose_project:
            volumes.append({
                "name": v.name,
                "driver": v.attrs.get("Driver", "local"),
                "mountpoint": v.attrs.get("Mountpoint", ""),
            })

    # Docker host info
    host_info = {}
    try:
        info = client.info()
        host_info = {
            "docker_version": client.version().get("Version", "unknown"),
            "os": info.get("OperatingSystem", "unknown"),
            "architecture": info.get("Architecture", "unknown"),
            "cpus": info.get("NCPU", 0),
            "memory_gb": round(info.get("MemTotal", 0) / (1024 ** 3), 1),
            "containers_running": info.get("ContainersRunning", 0),
            "containers_total": info.get("Containers", 0),
            "images": info.get("Images", 0),
        }
    except Exception as e:
        logger.error(f"Error fetching Docker host info: {e}")

    return {
        "runtime": "docker",
        "compose_project": compose_project,
        "host": host_info,
        "containers": compose_containers,
        "other_containers": other_containers,
        "networks": networks,
        "volumes": volumes,
    }


def get_container_detail(container_id: str) -> dict:
    """Get full detail for a single container by short ID or name."""
    if not DOCKER_AVAILABLE:
        return {"error": "Docker SDK not installed"}

    try:
        client = docker.from_env()
    except Exception as e:
        return {"error": f"Cannot connect to Docker daemon: {e}"}

    try:
        c = client.containers.get(container_id)
    except Exception as e:
        return {"error": f"Container not found: {e}"}

    attrs = c.attrs
    config = attrs.get("Config", {})
    state = attrs.get("State", {})
    host_config = attrs.get("HostConfig", {})
    network_settings = attrs.get("NetworkSettings", {})

    # ── Basics ──
    svc = c.labels.get("com.docker.compose.service", "")
    proj = c.labels.get("com.docker.compose.project", "")

    try:
        img = c.image
        image_name = img.tags[0] if img.tags else config.get("Image", "unknown")
    except Exception:
        image_name = config.get("Image", "unknown")

    # ── Ports ──
    ports = []
    port_bindings = network_settings.get("Ports", {}) or {}
    for container_port, bindings in port_bindings.items():
        if bindings:
            for b in bindings:
                hp = b.get("HostPort", "")
                if hp:
                    ports.append({"host": hp, "container": container_port})

    # ── Health ──
    health_status = "none"
    health_log = []
    health_data = state.get("Health", {})
    if health_data:
        health_status = health_data.get("Status", "none")
        for entry in (health_data.get("Log") or [])[-5:]:
            health_log.append({
                "start": entry.get("Start", ""),
                "end": entry.get("End", ""),
                "exit_code": entry.get("ExitCode", -1),
                "output": (entry.get("Output") or "")[:500],
            })

    # ── Uptime ──
    started_at = state.get("StartedAt", "")
    uptime = ""
    if started_at and c.status == "running":
        try:
            start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - start_dt
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            if hours > 24:
                uptime = f"{hours // 24}d {hours % 24}h {minutes}m"
            elif hours > 0:
                uptime = f"{hours}h {minutes}m"
            else:
                uptime = f"{minutes}m"
        except Exception:
            pass

    # ── Environment variables (mask sensitive values) ──
    env_vars = []
    sensitive_keys = {"password", "secret", "key", "token", "credentials", "auth"}
    for e in (config.get("Env") or []):
        parts = e.split("=", 1)
        k = parts[0]
        v = parts[1] if len(parts) > 1 else ""
        masked = any(s in k.lower() for s in sensitive_keys)
        env_vars.append({"key": k, "value": "••••••••" if masked else v})

    # ── Mounts / Volumes ──
    mounts = []
    for m in (attrs.get("Mounts") or []):
        mounts.append({
            "type": m.get("Type", ""),
            "source": m.get("Source", ""),
            "destination": m.get("Destination", ""),
            "mode": m.get("Mode", ""),
            "rw": m.get("RW", True),
        })

    # ── Networks ──
    networks = []
    for net_name, net_info in (network_settings.get("Networks") or {}).items():
        networks.append({
            "name": net_name,
            "ip": net_info.get("IPAddress", ""),
            "gateway": net_info.get("Gateway", ""),
            "mac": net_info.get("MacAddress", ""),
        })

    # ── Resource limits ──
    nano_cpus = host_config.get("NanoCpus", 0)
    memory_limit = host_config.get("Memory", 0)
    resources = {
        "cpu_limit": f"{nano_cpus / 1e9:.1f} cores" if nano_cpus else "unlimited",
        "memory_limit": f"{memory_limit / (1024**2):.0f} MB" if memory_limit else "unlimited",
        "restart_policy": host_config.get("RestartPolicy", {}).get("Name", "no"),
        "restart_count": attrs.get("RestartCount", 0),
    }

    # ── Logs (last 80 lines) ──
    logs = ""
    try:
        logs = c.logs(tail=80, timestamps=True).decode("utf-8", errors="replace")
    except Exception as e:
        logs = f"Error fetching logs: {e}"

    # ── All labels ──
    labels = dict(c.labels)

    # ── Depends on (from compose label) ──
    depends_on_raw = c.labels.get("com.docker.compose.depends_on", "")
    depends_on = [d.split(":")[0] for d in depends_on_raw.split(",") if d] if depends_on_raw else []

    return {
        "id": c.short_id,
        "full_id": c.id,
        "name": c.name,
        "service": svc or c.name,
        "compose_project": proj,
        "image": image_name,
        "status": c.status,
        "health": health_status,
        "health_log": health_log,
        "ports": ports,
        "uptime": uptime,
        "started_at": started_at,
        "created": attrs.get("Created", ""),
        "platform": config.get("Image", ""),
        "command": " ".join(config.get("Cmd") or []) if config.get("Cmd") else config.get("Entrypoint", ""),
        "entrypoint": " ".join(config.get("Entrypoint") or []) if isinstance(config.get("Entrypoint"), list) else (config.get("Entrypoint") or ""),
        "working_dir": config.get("WorkingDir", ""),
        "env": env_vars,
        "mounts": mounts,
        "networks": networks,
        "resources": resources,
        "depends_on": depends_on,
        "labels": labels,
        "logs": logs,
    }


def container_action(container_id: str, action: str) -> dict:
    """Perform an action on a container: start, stop, restart, pause, unpause."""
    if not DOCKER_AVAILABLE:
        raise RuntimeError("Docker SDK not installed")

    allowed = {"start", "stop", "restart", "pause", "unpause"}
    if action not in allowed:
        raise ValueError(f"Invalid action. Allowed: {', '.join(sorted(allowed))}")

    try:
        client = docker.from_env()
        c = client.containers.get(container_id)
    except Exception as e:
        raise ValueError(f"Container not found: {e}")

    try:
        getattr(c, action)()
        c.reload()
        return {"status": "ok", "action": action, "container": c.name, "new_status": c.status}
    except Exception as e:
        raise RuntimeError(f"Action failed: {e}")


def get_container_logs(container_id: str, tail: int = 200) -> dict:
    """Return container logs."""
    if not DOCKER_AVAILABLE:
        raise RuntimeError("Docker SDK not installed")
    
    try:
        client = docker.from_env()
        c = client.containers.get(container_id)
        logs = c.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
        return {"logs": logs, "container": c.name}
    except Exception as e:
        raise RuntimeError(str(e))
