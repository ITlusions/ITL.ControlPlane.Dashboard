# ITL Control Plane Dashboard

![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)
![Development](https://img.shields.io/badge/development-in%20progress-yellow?style=flat-square)

> **Alpha** — This project is under active development. APIs, data models, and behaviour may change without notice.

Modern web dashboard for the ITL Control Plane, providing real-time visibility into multi-tenant infrastructure.

## Features

- 🎯 **Multi-Tenant Overview** - View all tenants, management groups, and subscriptions
- 📊 **Real-time Stats** - Live statistics from PostgreSQL and Neo4j
- 🏗️ **Resource Explorer** - Browse resource groups and resources across all tenants
- 🔗 **Direct Integration** - Uses API Gateway and SDK for data access
- 🎨 **Modern UI** - Bootstrap 5 with ITlusions branding

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard
python main.py

# Or with custom port
PORT=8090 python main.py
```

The dashboard will be available at http://localhost:8090

## Configuration

Set environment variables:
- `API_GATEWAY_URL` - Core provider API endpoint (default: http://localhost:8000)
- `PORT` - Dashboard port (default: 8090)

## Architecture

```
┌─────────────────┐
│   Dashboard     │
│  (FastAPI)      │
└────────┬────────┘
         │
         ├─► API Gateway (port 8000)
         │   └─► Core Provider
         │       ├─► PostgreSQL
         │       └─► Neo4j
         │
         └─► Direct SDK Integration (optional)
```

## Endpoints

- `/` - Main dashboard
- `/health` - Health check

## Development

Built with the same styling as itl.website for consistent branding.
