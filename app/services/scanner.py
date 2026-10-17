"""File pre-filter + OpenAI structured-output scan."""
import asyncio
import os
import re
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

from app import config
from app.services import github

ALLOWED_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".vue", ".svelte"}
SKIP_DIRS = {"node_modules", "dist", "build", ".next", "venv", ".venv", "__pycache__", ".git"}
CANDIDATE_CAP = 100
BATCH_SIZE = 6
CONFIDENCE_THRESHOLD = 0.6

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "scanner_system.txt")

_NAME_RE = re.compile(r"chat|assistant|bot|server|api|main|app", re.I)
_CONTENT_SIGNALS = [
    re.compile(r"\b(openai|anthropic|groq|langchain)\b", re.I),
    re.compile(r"(fetch|axios)[^\n]*(/chat|/api/ai)", re.I),
    re.compile(r"['\"]/(chat|api/ai)[^'\"]*['\"]", re.I),
    re.compile(r"(console\.log|logger\.\w+|logging\.\w+|print)\s*\([^\n]*(email|phone|message|user)",
               re.I),
]


class ScanError(Exception):
    pass


class RawFinding(BaseModel):
    rule_id: Literal["AIA-50-1", "GDPR-13", "GDPR-5-1C"]
    title: str
    explanation: str
    severity: Literal["low", "medium", "high"]
    confidence: float
    file_path: str
    original_snippet: str
    suggested_patch: str


class ScanOutput(BaseModel):
    findings: list[RawFinding]
    risk_signals: list[Literal["hiring", "credit", "education", "health", "biometrics",
                               "critical_infrastructure"]]


def is_candidate(path: str) -> bool:
    parts = path.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return False
    name = parts[-1]
    if ".min." in name or name.endswith(("-lock.json", ".lock")):
        return False
    return os.path.splitext(name)[1].lower() in ALLOWED_EXT


def score_file(path: str, content: str) -> int:
    score = 2 if _NAME_RE.search(os.path.basename(path)) else 0
    for rx in _CONTENT_SIGNALS:
        if rx.search(content):
            score += 3
    return score if score >= 3 else 0  # name alone is not enough


def choose_files(all_files: dict[str, str]) -> tuple[dict[str, str], dict]:
    """Keep only files with compliance-relevant signals, best first, capped at MAX_FILES."""
    scored = [(score_file(p, c), p, c) for p, c in all_files.items()]
    relevant = sorted((x for x in scored if x[0] > 0), key=lambda x: -x[0])
    chosen = relevant[: config.MAX_FILES]
    stats = {
        "files_scanned": len(chosen),
        "skipped_over_cap": max(0, len(relevant) - len(chosen)),
        "skipped_not_relevant": len(scored) - len(relevant),
    }
    return {p: c for _, p, c in chosen}, stats


async def select_files(owner: str, repo: str, ref: str,
                       token: str | None = None) -> tuple[dict[str, str], dict]:
    """Fetch candidate files from GitHub, then choose the relevant ones."""
    tree = await github.list_tree(owner, repo, ref, token=token)
    cands = [t for t in tree if is_candidate(t["path"])]
    too_big = [t for t in cands if t.get("size", 0) > config.MAX_FILE_BYTES]
    cands = [t for t in cands if t.get("size", 0) <= config.MAX_FILE_BYTES]
    cands.sort(key=lambda t: -bool(_NAME_RE.search(os.path.basename(t["path"]))))
    fetched_list = cands[:CANDIDATE_CAP]

    sem = asyncio.Semaphore(8)

    async def fetch(t):
        async with sem:
            try:
                text, _ = await github.get_file(owner, repo, t["path"], ref, token=token)
                return t["path"], text
            except github.GitHubError:
                return t["path"], None

    fetched = await asyncio.gather(*(fetch(t) for t in fetched_list))
    files, stats = choose_files({p: c for p, c in fetched if c is not None})
    stats["code_files_in_repo"] = len(cands) + len(too_big)
    stats["skipped_too_large"] = len(too_big)
    stats["skipped_over_cap"] += max(0, len(cands) - CANDIDATE_CAP)
    return files, stats


def align_snippet(content: str, original: str, patch: str) -> tuple[str, str] | None:
    """Repair a near-miss snippet so it matches the file exactly once. Returns (original, patch)
    or None. Handles whitespace differences and up to 3 stray trailing characters."""
    if original and content.count(original) == 1:
        return original, patch
    stripped = original.strip()
    if stripped and content.count(stripped) == 1:
        return stripped, patch.strip()
    for cut in (1, 2, 3):  # model appended a few characters that are not in the file
        prefix = stripped[:-cut].rstrip()
        if len(prefix) >= 10 and content.count(prefix) == 1 and patch.strip().startswith(prefix):
            return prefix, patch.strip()
    return None


def process_findings(raw: list[RawFinding], files: dict[str, str]) -> list[dict]:
    """Validate snippets against fetched files and assign statuses."""
    out = []
    for f in raw:
        content = files.get(f.file_path)
        if content is None:
            continue  # model invented a file
        d = f.model_dump()
        d["confidence"] = max(0.0, min(1.0, d["confidence"]))
        reasons = []
        aligned = align_snippet(content, f.original_snippet, f.suggested_patch)
        if aligned:
            d["original_snippet"], d["suggested_patch"] = aligned
        else:
            reasons.append("AI's snippet could not be located exactly — edit the patch manually.")
        if d["confidence"] < CONFIDENCE_THRESHOLD:
            reasons.append(f"AI confidence is low ({d['confidence']:.2f}).")
        d["status"] = "needs_human" if reasons else "pending"
        d["needs_human_reason"] = " ".join(reasons) or None
        out.append(d)
    return out


PROVIDERS = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google", "groq": "Groq",
             "self_hosted": "a self-hosted model", "other": "another provider"}


def build_context(q: dict | None) -> str:
    """Short orientation block from the questionnaire. The code remains the source of truth."""
    if not q:
        return ""
    lines = []
    if q.get("product_name"):
        lines.append(f"Product name: {q['product_name']}")
    lines.append(f"What it does: {q.get('description', '')}")
    if q.get("ai_provider") in PROVIDERS:
        lines.append(f"AI provider according to the team: {PROVIDERS[q['ai_provider']]}")
    if q.get("user_groups"):
        lines.append("Users: " + ", ".join(g.replace("_", " ") for g in q["user_groups"]))
    return ("Context from the team (for orientation only; judge the code itself):\n- "
            + "\n- ".join(lines) + "\n\n")


async def _scan_batch(client: AsyncOpenAI, system: str, batch: dict[str, str],
                      context: str = "") -> ScanOutput | None:
    user = context + "\n".join(f"=== FILE: {p} ===\n{c}\n" for p, c in batch.items())
    resp = await client.beta.chat.completions.parse(
        model=config.OPENAI_MODEL,
        temperature=0.1,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format=ScanOutput,
    )
    return resp.choices[0].message.parsed


def describe_error(e: Exception) -> str:
    """Safe diagnostic: class, HTTP status and provider error code. Never the message (may echo key)."""
    parts = [type(e).__name__]
    if getattr(e, "status_code", None):
        parts.append(f"HTTP {e.status_code}")
    if getattr(e, "code", None):
        parts.append(f"code={e.code}")
    return ", ".join(parts)


def _batches(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


async def analyse(files: dict[str, str], stats: dict, questionnaire: dict | None = None) -> dict:
    """Send chosen files to the model. Returns findings, risk signals, stats, warnings, files."""
    with open(_PROMPT_PATH, encoding="utf-8") as fh:
        system = fh.read()
    context = build_context(questionnaire)
    client = AsyncOpenAI(api_key=config.OPENAI_API_KEY, timeout=60, max_retries=2)
    raw: list[RawFinding] = []
    signals: set[str] = set()
    warnings: list[str] = []
    items = list(files.items())
    batches = list(_batches(items, BATCH_SIZE))
    failures = 0
    last_error = ""
    for batch in batches:
        try:
            parsed = await _scan_batch(client, system, dict(batch), context)
        except Exception as e:  # never leak provider error text (may echo key fragments)
            failures += 1
            last_error = describe_error(e)
            print(f"[scanner] OpenAI batch failed: {last_error}", flush=True)
            warnings.append(f"AI request failed for a batch of {len(batch)} file(s) ({last_error}).")
            continue
        if parsed is None:
            warnings.append("AI returned no parsable result for a batch.")
            continue
        raw.extend(parsed.findings)
        signals.update(parsed.risk_signals)
    if batches and failures == len(batches):
        raise ScanError("The AI service could not be reached or rejected the request. "
                        f"Check OPENAI_API_KEY / OPENAI_MODEL and try again. ({last_error})")
    if stats.get("skipped_too_large") or stats.get("skipped_over_cap"):
        warnings.append(f"Some files were skipped (too large: {stats.get('skipped_too_large', 0)}, "
                        f"over file cap: {stats.get('skipped_over_cap', 0)}).")
    return {"findings": process_findings(raw, files), "risk_signals": sorted(signals),
            "stats": stats, "warnings": warnings, "files": files}


async def scan_repo(owner: str, repo: str, ref: str, token: str | None = None,
                    questionnaire: dict | None = None) -> dict:
    files, stats = await select_files(owner, repo, ref, token=token)
    return await analyse(files, stats, questionnaire)


async def scan_archive(all_files: dict[str, str], questionnaire: dict | None = None) -> dict:
    files, stats = choose_files(all_files)
    stats["code_files_in_repo"] = len(all_files)
    return await analyse(files, stats, questionnaire)
