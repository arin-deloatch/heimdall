"""Repository scanner for quality infrastructure analysis."""

import base64
from pathlib import Path

import httpx

from .logging import get_logger
from .models import QualityDriftReport, RepoInfo

logger = get_logger(__name__)

_GITHUB_API = "https://api.github.com"


# --- Pure content parsers (no I/O) ---


def _detect_type_checker(content: str) -> str | None:
    if "tool.ty" in content or '"ty"' in content or "'ty'" in content:
        return "ty"
    if "pyright" in content or "tool.pyright" in content:
        return "pyright"
    return None


def _detect_project_type(content: str) -> str:
    if "fastmcp" in content:
        return "mcp"
    if "fastapi" in content:
        return "fastapi"
    return "python"


def _detect_radon_gate(content: str) -> bool:
    return "radon cc" in content and ("--min C" in content or "C or higher" in content)


# --- Local filesystem scanner ---


def scan_repo(repo_path: Path) -> RepoInfo:
    """Scan a single local repository for quality infrastructure."""
    logger.debug("Scanning repository", path=str(repo_path))

    has_pre_commit = (repo_path / ".pre-commit-config.yaml").exists()
    has_coderabbit = (repo_path / ".coderabbit.yaml").exists()
    has_makefile = (repo_path / "Makefile").exists()

    type_checker = None
    project_type = "python"
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        type_checker = _detect_type_checker(content)
        project_type = _detect_project_type(content)

    has_radon_gate = False
    makefile = repo_path / "Makefile"
    if makefile.exists():
        has_radon_gate = _detect_radon_gate(makefile.read_text())

    return RepoInfo(
        name=repo_path.name,
        path=repo_path,
        type=project_type,
        has_pre_commit=has_pre_commit,
        has_coderabbit=has_coderabbit,
        has_makefile=has_makefile,
        type_checker=type_checker,
        has_radon_gate=has_radon_gate,
    )


# --- GitHub API scanner ---


def _decode_github_content(data: dict) -> str:
    return base64.b64decode(data["content"]).decode()


async def scan_github_repo(
    client: httpx.AsyncClient, owner: str, repo: str
) -> RepoInfo:
    """Scan a single GitHub repository for quality infrastructure.

    Args:
        client: Shared async client; callers should use one client per tool
                invocation so the connection pool is reused across concurrent scans.
        owner: GitHub user or organization name.
        repo: Repository name.
    """
    logger.debug("Scanning GitHub repository", ref=f"{owner}/{repo}")

    resp = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}/contents")
    resp.raise_for_status()
    root_files = {item["name"] for item in resp.json() if item["type"] == "file"}

    has_pre_commit = ".pre-commit-config.yaml" in root_files
    has_coderabbit = ".coderabbit.yaml" in root_files
    has_makefile = "Makefile" in root_files

    type_checker = None
    project_type = "python"
    if "pyproject.toml" in root_files:
        resp = await client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/contents/pyproject.toml"
        )
        resp.raise_for_status()
        content = _decode_github_content(resp.json())
        type_checker = _detect_type_checker(content)
        project_type = _detect_project_type(content)

    has_radon_gate = False
    if has_makefile:
        resp = await client.get(f"{_GITHUB_API}/repos/{owner}/{repo}/contents/Makefile")
        resp.raise_for_status()
        has_radon_gate = _detect_radon_gate(_decode_github_content(resp.json()))

    return RepoInfo(
        name=repo,
        github_ref=f"{owner}/{repo}",
        type=project_type,
        has_pre_commit=has_pre_commit,
        has_coderabbit=has_coderabbit,
        has_makefile=has_makefile,
        type_checker=type_checker,
        has_radon_gate=has_radon_gate,
    )


# --- Report generation ---


def generate_drift_report(repos: list[RepoInfo]) -> QualityDriftReport:
    """Generate quality drift report from scanned repos."""
    total = len(repos)
    with_pre_commit = sum(1 for r in repos if r.has_pre_commit)
    with_coderabbit = sum(1 for r in repos if r.has_coderabbit)
    with_makefile = sum(1 for r in repos if r.has_makefile)

    type_checker_counts: dict[str, int] = {}
    for repo in repos:
        if repo.type_checker:
            type_checker_counts[repo.type_checker] = (
                type_checker_counts.get(repo.type_checker, 0) + 1
            )

    return QualityDriftReport(
        total_repos=total,
        repos_with_pre_commit=with_pre_commit,
        repos_with_coderabbit=with_coderabbit,
        repos_with_makefile=with_makefile,
        type_checker_breakdown=type_checker_counts,
        repos_missing_pre_commit=[r.name for r in repos if not r.has_pre_commit],
        repos_missing_coderabbit=[r.name for r in repos if not r.has_coderabbit],
        repos_missing_radon_gate=[r.name for r in repos if not r.has_radon_gate],
    )


def format_drift_report(report: QualityDriftReport) -> str:
    """Format drift report as markdown."""
    pre_commit_pct = report.repos_with_pre_commit / report.total_repos * 100
    coderabbit_pct = report.repos_with_coderabbit / report.total_repos * 100
    makefile_pct = report.repos_with_makefile / report.total_repos * 100

    lines = [
        "# Quality Infrastructure Drift Report",
        "",
        f"**Total Repositories:** {report.total_repos}",
        "",
        "## Coverage Summary",
        "",
        f"- **Pre-commit hooks:** {report.repos_with_pre_commit}/"
        f"{report.total_repos} ({pre_commit_pct:.1f}%)",
        f"- **CodeRabbit config:** {report.repos_with_coderabbit}/"
        f"{report.total_repos} ({coderabbit_pct:.1f}%)",
        f"- **Makefile:** {report.repos_with_makefile}/"
        f"{report.total_repos} ({makefile_pct:.1f}%)",
        "",
        "## Type Checker Distribution",
        "",
    ]

    if report.type_checker_breakdown:
        for checker, count in report.type_checker_breakdown.items():
            lines.append(f"- **{checker}:** {count} repos")
    else:
        lines.append("- No type checkers detected")

    lines.extend(["", "## Repos Missing Infrastructure", ""])

    if report.repos_missing_pre_commit:
        lines.append(
            f"### Missing Pre-commit ({len(report.repos_missing_pre_commit)} repos)"
        )
        lines.append("")
        for repo in report.repos_missing_pre_commit:
            lines.append(f"- {repo}")
        lines.append("")

    if report.repos_missing_coderabbit:
        lines.append(
            f"### Missing CodeRabbit ({len(report.repos_missing_coderabbit)} repos)"
        )
        lines.append("")
        for repo in report.repos_missing_coderabbit:
            lines.append(f"- {repo}")
        lines.append("")

    if report.repos_missing_radon_gate:
        count = len(report.repos_missing_radon_gate)
        lines.append(f"### Missing Radon Complexity Gate ({count} repos)")
        lines.append("")
        for repo in report.repos_missing_radon_gate:
            lines.append(f"- {repo}")

    return "\n".join(lines)
