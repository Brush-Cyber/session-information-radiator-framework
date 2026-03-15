"""
SIRM Upstream Sync — Continuously synchronize SIRM code to the standalone repo.

Target: Brush-Cyber/session-information-radiator-framework

This module pushes SIRM core files from Orion to the standalone repo via
the GitHub API. It can be triggered:
  - Manually via API: POST /api/sirm/sync
  - Programmatically: from sirm.sync_upstream import sync_to_upstream; sync_to_upstream()
  - On a schedule: via agent_worker or cron

The sync is idempotent — it computes SHA of each file and only pushes changes.
It never pulls from upstream. Orion is the source of truth.
"""

import os
import json
import base64
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

UPSTREAM_REPO = "Brush-Cyber/session-information-radiator-framework"
UPSTREAM_BRANCH = "main"
API_BASE = "https://api.github.com"

SYNC_FILES = {
    "sirm/__init__.py": "sirm/__init__.py",
    "sirm/models.py": "sirm/models.py",
    "sirm/pipeline.py": "sirm/pipeline.py",
    "sirm/swarm.py": "sirm/swarm.py",
    "sirm/central_api.py": "sirm/central_api.py",
    "sirm/agent_memory.py": "sirm/agent_memory.py",
    "sirm/triage.py": "sirm/triage.py",
    "sirm/templates_engine.py": "sirm/templates_engine.py",
    "sirm/radiator.py": "sirm/radiator.py",
    "sirm/sprint_engine.py": "sirm/sprint_engine.py",
    "sirm/foundry.py": "sirm/foundry.py",
    "sirm/orchestration.py": "sirm/orchestration.py",
    "sirm/agent_context.py": "sirm/agent_context.py",
    "sirm/pg_store.py": "sirm/pg_store.py",
    "sirm/db.py": "sirm/db.py",
    "sirm/store.py": "sirm/store.py",
    "sirm/linear_client.py": "sirm/linear_client.py",
    "sirm/linear_sync.py": "sirm/linear_sync.py",
    "sirm/export.py": "sirm/export.py",
    "sirm/sync_upstream.py": "sirm/sync_upstream.py",
}

SYNC_DOCS = {
    "docs/sirm_g0_g7.md": "docs/sirm_g0_g7.md",
    "docs/agent_coordination.md": "docs/agent_coordination.md",
    "docs/vision.md": "docs/vision.md",
    "docs/product_bootstrap_template.md": "docs/product_bootstrap_template.md",
}

GENERATED_FILES = {
    "setup_db.py": None,
    "app.py": None,
    "requirements.txt": None,
    "Makefile": None,
    "README.md": None,
    "manifest.json": None,
}


def _get_token():
    from sirm.github_client import _get_token as gt
    return gt()


def _headers():
    token = _get_token()
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _get_remote_sha(path: str) -> Optional[str]:
    r = requests.get(
        f"{API_BASE}/repos/{UPSTREAM_REPO}/contents/{path}",
        headers=_headers(),
        params={"ref": UPSTREAM_BRANCH},
    )
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def _compute_git_blob_sha(content_bytes: bytes) -> str:
    header = f"blob {len(content_bytes)}\0".encode()
    return hashlib.sha1(header + content_bytes).hexdigest()


def _push_file(remote_path: str, content: bytes, message: str) -> dict:
    existing_sha = _get_remote_sha(remote_path)
    content_b64 = base64.b64encode(content).decode()

    payload = {
        "message": message,
        "content": content_b64,
        "branch": UPSTREAM_BRANCH,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    r = requests.put(
        f"{API_BASE}/repos/{UPSTREAM_REPO}/contents/{remote_path}",
        headers=_headers(),
        json=payload,
    )

    if r.status_code in (200, 201):
        return {"path": remote_path, "status": "updated" if existing_sha else "created"}
    else:
        logger.error(f"Failed to push {remote_path}: {r.status_code} {r.text[:200]}")
        return {"path": remote_path, "status": "error", "code": r.status_code, "detail": r.text[:200]}


def sync_to_upstream(source_root: str = ".", force: bool = False, dry_run: bool = False) -> dict:
    source = Path(source_root)
    results = {"synced": [], "skipped": [], "errors": [], "generated": []}
    timestamp = datetime.now(timezone.utc).isoformat()

    for local_path, remote_path in SYNC_FILES.items():
        src = source / local_path
        if not src.exists():
            results["skipped"].append({"path": local_path, "reason": "file not found"})
            continue

        content = src.read_bytes()

        if not force:
            local_sha = _compute_git_blob_sha(content)
            remote_sha = _get_remote_sha(remote_path)
            if remote_sha and remote_sha == local_sha:
                results["skipped"].append({"path": local_path, "reason": "unchanged"})
                continue

        if dry_run:
            results["synced"].append({"path": remote_path, "status": "would_sync"})
            continue

        r = _push_file(remote_path, content, f"sync: {remote_path} from Orion [{timestamp[:19]}]")
        if r["status"] == "error":
            results["errors"].append(r)
        else:
            results["synced"].append(r)

    for local_path, remote_path in SYNC_DOCS.items():
        src = source / local_path
        if not src.exists():
            results["skipped"].append({"path": local_path, "reason": "file not found"})
            continue
        content = src.read_bytes()
        if not force:
            local_sha = _compute_git_blob_sha(content)
            remote_sha = _get_remote_sha(remote_path)
            if remote_sha and remote_sha == local_sha:
                results["skipped"].append({"path": local_path, "reason": "unchanged"})
                continue
        if dry_run:
            results["synced"].append({"path": remote_path, "status": "would_sync"})
            continue
        r = _push_file(remote_path, content, f"sync: {remote_path} from Orion [{timestamp[:19]}]")
        if r["status"] == "error":
            results["errors"].append(r)
        else:
            results["synced"].append(r)

    if not dry_run:
        _sync_generated_files(results, timestamp)

    results["timestamp"] = timestamp
    results["summary"] = (
        f"Synced {len(results['synced'])} files, "
        f"skipped {len(results['skipped'])}, "
        f"errors {len(results['errors'])}, "
        f"generated {len(results['generated'])}"
    )
    return results


def _sync_generated_files(results: dict, timestamp: str):
    from sirm.export import (
        STANDALONE_README, STANDALONE_REQUIREMENTS,
        STANDALONE_SETUP_PY, STANDALONE_APP, STANDALONE_MAKEFILE,
    )

    generated = {
        "README.md": STANDALONE_README,
        "requirements.txt": STANDALONE_REQUIREMENTS.strip() + "\n",
        "setup_db.py": STANDALONE_SETUP_PY,
        "app.py": STANDALONE_APP,
        "Makefile": STANDALONE_MAKEFILE.strip() + "\n",
    }

    manifest = {
        "name": "SIRM",
        "version": "1.0.0",
        "description": "Secure Intelligent Release Management — Multi-Agent Factory Orchestration",
        "author": "Brush Cyber, LLC",
        "synced_at": timestamp,
        "synced_from": "Orion Unified Management Plane",
        "upstream_repo": "Brush-Cyber/orion",
    }
    generated["manifest.json"] = json.dumps(manifest, indent=2)

    for remote_path, content in generated.items():
        content_bytes = content.encode()
        local_sha = _compute_git_blob_sha(content_bytes)
        remote_sha = _get_remote_sha(remote_path)
        if remote_sha and remote_sha == local_sha:
            continue
        r = _push_file(remote_path, content_bytes,
                       f"sync: {remote_path} (generated) [{timestamp[:19]}]")
        results["generated"].append(r)


def check_sync_status(source_root: str = ".") -> dict:
    source = Path(source_root)
    status = {"in_sync": [], "out_of_sync": [], "missing_local": [], "missing_remote": []}

    all_files = {**SYNC_FILES, **SYNC_DOCS}
    for local_path, remote_path in all_files.items():
        src = source / local_path
        if not src.exists():
            status["missing_local"].append(local_path)
            continue

        content = src.read_bytes()
        local_sha = _compute_git_blob_sha(content)
        remote_sha = _get_remote_sha(remote_path)

        if not remote_sha:
            status["missing_remote"].append(remote_path)
        elif remote_sha == local_sha:
            status["in_sync"].append(remote_path)
        else:
            status["out_of_sync"].append(remote_path)

    status["summary"] = (
        f"{len(status['in_sync'])} in sync, "
        f"{len(status['out_of_sync'])} out of sync, "
        f"{len(status['missing_remote'])} missing remote, "
        f"{len(status['missing_local'])} missing local"
    )
    return status


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync SIRM to upstream repo")
    parser.add_argument("--force", action="store_true", help="Force push all files regardless of SHA match")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without pushing")
    parser.add_argument("--check", action="store_true", help="Check sync status without pushing")
    args = parser.parse_args()

    if args.check:
        result = check_sync_status()
        print(json.dumps(result, indent=2))
    else:
        result = sync_to_upstream(force=args.force, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
