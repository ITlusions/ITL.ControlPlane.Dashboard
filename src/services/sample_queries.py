"""Sample Queries Service - Manages built-in and user-defined sample queries"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger

# Configuration paths
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def load_builtin_sample_queries() -> list:
    """Load built-in sample queries from config/sample_queries.yaml"""
    config_file = CONFIG_DIR / "sample_queries.yaml"
    if not config_file.exists():
        logger.warning(f"Sample queries config not found: {config_file}")
        return []
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            samples = data.get("samples", [])
            # Add source marker
            for s in samples:
                s["source"] = "builtin"
            return samples
    except Exception as e:
        logger.error(f"Error loading sample queries: {e}")
        return []


def load_user_sample_queries() -> list:
    """Load user-defined sample queries from data/user_queries.json"""
    user_file = DATA_DIR / "user_queries.json"
    if not user_file.exists():
        return []
    try:
        with open(user_file, "r", encoding="utf-8") as f:
            queries = json.load(f)
            for q in queries:
                q["source"] = "user"
            return queries
    except Exception as e:
        logger.error(f"Error loading user queries: {e}")
        return []


def save_user_sample_queries(queries: list) -> bool:
    """Save user-defined sample queries to data/user_queries.json"""
    user_file = DATA_DIR / "user_queries.json"
    try:
        # Remove source markers before saving
        clean_queries = [{k: v for k, v in q.items() if k != "source"} for q in queries]
        with open(user_file, "w", encoding="utf-8") as f:
            json.dump(clean_queries, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving user queries: {e}")
        return False


def get_all_sample_queries() -> dict:
    """Get all sample queries grouped by category"""
    builtin = load_builtin_sample_queries()
    user = load_user_sample_queries()
    
    # Group by category
    categories = {}
    for q in builtin + user:
        cat = q.get("category", "Other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(q)
    
    return {
        "categories": categories,
        "builtin_count": len(builtin),
        "user_count": len(user),
    }


def create_sample_query(name: str, query: str, category: str = "My Queries", description: str = "") -> dict:
    """Create a new user-defined sample query. Returns the new query or raises ValueError."""
    name = name.strip()
    query = query.strip()
    category = category.strip() or "My Queries"
    description = description.strip()
    
    if not name or not query:
        raise ValueError("Name and query are required")
    
    # Load existing user queries
    user_queries = load_user_sample_queries()
    
    # Check for duplicate name
    existing_names = [q.get("name", "").lower() for q in user_queries]
    if name.lower() in existing_names:
        raise ValueError(f"Query with name '{name}' already exists")
    
    # Add new query
    new_query = {
        "name": name,
        "query": query,
        "category": category,
        "description": description,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    user_queries.append(new_query)
    
    if not save_user_sample_queries(user_queries):
        raise RuntimeError("Failed to save query")
    
    new_query["source"] = "user"
    return new_query


def delete_sample_query(name: str) -> bool:
    """Delete a user-defined sample query by name. Returns True if deleted."""
    user_queries = load_user_sample_queries()
    original_count = len(user_queries)
    
    # Filter out the query with matching name (case-insensitive)
    user_queries = [q for q in user_queries if q.get("name", "").lower() != name.lower()]
    
    if len(user_queries) == original_count:
        raise ValueError(f"Query '{name}' not found")
    
    if not save_user_sample_queries(user_queries):
        raise RuntimeError("Failed to delete query")
    
    return True
