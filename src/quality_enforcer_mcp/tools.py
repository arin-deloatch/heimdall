"""MCP tool definitions for quality enforcement."""

import asyncio
from pathlib import Path

import httpx
import yaml
from fastmcp import Context

from .logging import get_logger
from .scanner import (
    format_drift_report,
    generate_drift_report,
    scan_github_repo,
    scan_repo,
)
from .server import get_app_context, mcp

logger = get_logger(__name__)


# --- Repo resolvers ---


def _parse_github_ref(ref: str) -> tuple[str, str]:
    parts = ref.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GitHub ref '{ref}': expected 'owner/repo' format")
    return parts[0], parts[1]


def _looks_like_github_refs(repo_paths: list[str]) -> bool:
    """Return True if all paths look like 'owner/repo' GitHub refs (not local paths)."""
    return bool(repo_paths) and all(
        not Path(p).is_absolute() and "/" in p and not Path(p).exists()
        for p in repo_paths
    )


def _load_github_refs(
    repos_config: Path, repo_paths: list[str] | None
) -> list[tuple[str, str]]:
    """Resolve GitHub owner/repo pairs from explicit args or repos.yaml.

    Raises:
        ValueError: If the config is unreadable or no refs are configured.
    """
    if repo_paths:
        refs = [_parse_github_ref(r) for r in repo_paths]
        logger.info("Scanning specific GitHub repos", count=len(refs))
        return refs

    if not repos_config.exists():
        raise ValueError("No repos config found and no repo_paths provided")

    with repos_config.open() as f:
        config = yaml.safe_load(f)

    raw = config.get("github_repos", [])
    if not raw:
        raise ValueError(
            "No GitHub repositories configured. "
            "Add entries under 'github_repos' in repos.yaml (format: owner/repo)."
        )

    refs = [_parse_github_ref(r) for r in raw]
    logger.info("Loaded GitHub repos from config", count=len(refs))
    return refs


def _load_local_paths(
    repos_config: Path, projects_root: Path, repo_paths: list[str] | None
) -> list[Path]:
    """Resolve local repo paths from explicit args, repos.yaml, or auto-discovery.

    Raises:
        ValueError: If projects_root doesn't exist.
    """
    if repo_paths:
        paths = [Path(p).expanduser().resolve() for p in repo_paths]
        logger.info("Scanning specific repos", count=len(paths))
        return paths

    if repos_config.exists():
        with repos_config.open() as f:
            config = yaml.safe_load(f)
        repo_names = config.get("repos", [])
        paths = [
            projects_root / name
            for name in repo_names
            if (projects_root / name).exists()
        ]
        logger.info("Loaded repos from config", count=len(paths))
        return paths

    if not projects_root.exists():
        raise ValueError(f"Projects root not found: {projects_root}")

    paths = [p for p in projects_root.iterdir() if p.is_dir() and (p / ".git").exists()]
    logger.info("Auto-discovered repos", count=len(paths))
    return paths


# --- Scan orchestrators ---


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _scan_github(
    repos_config: Path,
    github_token: str | None,
    repo_paths: list[str] | None,
) -> str:
    try:
        github_refs = _load_github_refs(repos_config, repo_paths)
    except ValueError as e:
        return str(e)

    async with httpx.AsyncClient(headers=_github_headers(github_token)) as client:
        results = await asyncio.gather(
            *[scan_github_repo(client, owner, repo) for owner, repo in github_refs],
            return_exceptions=True,
        )

    scanned = []
    for (owner, repo), result in zip(github_refs, results, strict=True):
        if isinstance(result, Exception):
            logger.warning(
                "Failed to scan GitHub repo",
                ref=f"{owner}/{repo}",
                error=str(result),
            )
        else:
            scanned.append(result)

    if not scanned:
        return "No repositories successfully scanned"

    return format_drift_report(generate_drift_report(scanned))


def _scan_local(
    repos_config: Path,
    projects_root: Path,
    repo_paths: list[str] | None,
) -> str:
    try:
        repos_to_scan = _load_local_paths(repos_config, projects_root, repo_paths)
    except ValueError as e:
        return str(e)

    if not repos_to_scan:
        return "No repositories found to scan"

    scanned = []
    for repo_path in repos_to_scan:
        try:
            scanned.append(scan_repo(repo_path))
        except Exception as e:
            logger.warning("Failed to scan repo", repo=str(repo_path), error=str(e))

    if not scanned:
        return "No repositories successfully scanned"

    return format_drift_report(generate_drift_report(scanned))


# --- MCP tool ---


@mcp.tool()
async def scan_quality_drift(
    ctx: Context,
    repo_paths: list[str] | None = None,
) -> str:
    """Scan repositories for quality infrastructure drift.

    Analyzes repos for pre-commit configs, CodeRabbit configs, Makefiles,
    type checkers, and complexity gates.

    Args:
        repo_paths: Optional list of repos to scan. In local mode: filesystem
                   paths. In GitHub mode: 'owner/repo' strings. If None, reads
                   from repos.yaml ('repos' key for local, 'github_repos' key
                   for GitHub mode).

    Returns:
        Markdown report with drift analysis and missing infrastructure
    """
    app_ctx = get_app_context(ctx)

    use_github = app_ctx.use_github or _looks_like_github_refs(repo_paths or [])
    if use_github:
        return await _scan_github(
            app_ctx.repos_config, app_ctx.github_token, repo_paths
        )
    return _scan_local(app_ctx.repos_config, app_ctx.projects_root, repo_paths)
