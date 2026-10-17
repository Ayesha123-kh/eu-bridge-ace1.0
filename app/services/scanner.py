"""File pre-filter + OpenAI structured-output scan."""
import asyncio
import os
import re
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel

from app import config
from app.services import github
from app.services.redact import redact

ALLOWED_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".vue", ".svelte"}
SKIP_DIRS = {"node_modules", "dist", "build", ".next", "venv", ".venv", "__pycache__", ".git",
             "tests", "test", "__tests__", "spec", "specs", "docs", "doc", "fixtures"}
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
    evidence: str
    original_snippet: str
    suggested_patch: str


class RiskSignal(BaseModel):
    signal: Literal["hiring", "credit", "education", "health", "biometrics",
                    "critical_infrastructure"]
    evidence: str


class ScanOutput(BaseModel):
    findings: list[RawFinding]
    risk_signals: list[RiskSignal]


def is_candidate(path: str) -> bool:
    parts = path.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return False
    name = parts[-1]
    if ".min." in name or name.endswith(("-lock.json", ".lock")):
        return False
    if re.match(r"(test_.*|.*_test\.py|.*\.(test|spec)\.[jt]sx?|conftest\.py)$", name):
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


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


PROVIDER_CALL = re.compile(
    r"chat\.completions\.create|completions\.create|responses\.create|messages\.create|"
    r"generate_content|generateContent|ChatCompletion|ChatOpenAI|ChatAnthropic|"
    r"api\.openai\.com|api\.anthropic\.com|api\.groq\.com|generativelanguage\.googleapis\.com")
ROUTE = re.compile(r"@\w+\.(get|post|put|route|websocket)\(|\b(app|router)\.(get|post|put|use)\(|"
                   r"render_template|render\(|res\.(send|json)|jsonify|HTMLResponse|TemplateResponse|"
                   r"createServer|NextResponse|export (default )?async function (GET|POST)")
UI_EXT = {".html", ".jsx", ".tsx", ".vue", ".svelte"}
CHATTY = re.compile(r"chat|assistant|\bbot\b|prompt|message|ask |question|reply", re.I)
LOG_CALL = re.compile(r"\b(print|console\.(log|info|warn|error|debug)|logger\.\w+|logging\.\w+|log\.\w+)\s*\(", re.I)
PII_WORD = re.compile(r"e-?mail|phone|\bmsg\b|message|\buser(name)?\b|first_?name|last_?name|full_?name|"
                      r"\bname\b|address|prompt|content|\btext\b|\bbody\b|\bquery\b|\binput\b|\bssn\b|"
                      r"\bcv\b|resume", re.I)


def has_user_surface(path: str, content: str) -> bool:
    """True if the file can show something to end users: a UI file or an HTTP handler."""
    if os.path.splitext(path)[1].lower() in UI_EXT:
        return bool(CHATTY.search(content))
    return bool(ROUTE.search(content))


def comment_only_change(path: str, original: str, patch: str) -> bool:
    """True if the patch differs from the original only by comments or whitespace."""
    ext = os.path.splitext(path)[1].lower()

    def strip(t: str) -> str:
        if ext == ".py":
            t = re.sub(r"#.*", "", t)
        elif ext in {".html", ".vue", ".svelte"}:
            t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
            t = re.sub(r"(?<!:)//.*", "", t)
        else:
            t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
            t = re.sub(r"(?<!:)//.*", "", t)
        return re.sub(r"\s+", "", t)

    return strip(original) == strip(patch)


def undefined_helper(patch: str, content: str) -> bool:
    """True if the patch calls a redact helper that the file neither defines nor imports."""
    if not re.search(r"\bredact\w*\(", patch):
        return False
    return not re.search(r"\bdef redact|\bfunction redact|\bredact\w*\s*=|import[^\n]*\bredact|"
                         r"from[^\n]*import[^\n]*\bredact", content)


def evidence_found(evidence: str, files: dict[str, str], min_len: int = 8) -> bool:
    ev = _norm(evidence)
    return len(ev) >= min_len and any(ev in _norm(c) for c in files.values())


def process_findings(raw: list[RawFinding], files: dict[str, str],
                     dropped: list[str] | None = None) -> list[dict]:
    """Discard unsupported suggestions, validate snippets, and assign statuses."""
    drop = dropped if dropped is not None else []
    provider_calls = any(PROVIDER_CALL.search(c) for c in files.values())
    out = []
    for f in raw:
        content = files.get(f.file_path)
        if content is None:
            drop.append("named a file that was not scanned")
            continue
        if _norm(f.evidence) not in _norm(content) or len(_norm(f.evidence)) < 8:
            drop.append("no matching evidence in the code")
            continue
        if f.rule_id in ("AIA-50-1", "GDPR-13") and not has_user_surface(f.file_path, content):
            drop.append("file is not a user-facing interface (library or internal code)")
            continue
        if f.rule_id == "GDPR-13" and not provider_calls:
            drop.append("no call to an outside AI provider found")
            continue
        if f.rule_id == "GDPR-5-1C" and not (LOG_CALL.search(f.original_snippet)
                                              and PII_WORD.search(f.original_snippet)):
            drop.append("the log line does not contain user data")
            continue
        if comment_only_change(f.file_path, f.original_snippet, f.suggested_patch):
            drop.append("the fix only adds a comment")
            continue
        if undefined_helper(f.suggested_patch, content):
            drop.append("the fix calls a helper that does not exist")
            continue
        d = f.model_dump()
        d.pop("evidence", None)
        d["confidence"] = max(0.0, min(1.0, d["confidence"]))
        reasons = []
        aligned = align_snippet(content, f.original_snippet, f.suggested_patch)
        if aligned:
            d["original_snippet"], d["suggested_patch"] = aligned
        else:
            reasons.append("AI's snippet could not be located exactly — edit the patch manually.")
            d["confidence"] = min(d["confidence"], 0.5)
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
    providers = q.get("ai_providers") or [q.get("ai_provider")]
    names = [PROVIDERS[p] for p in providers if p in PROVIDERS]
    if names:
        lines.append("AI providers according to the team: " + ", ".join(names))
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
    signals_raw: list[RiskSignal] = []
    warnings: list[str] = []
    masked_total = 0
    items = []
    for path, content in files.items():
        text, n = redact(content)  # secrets never leave this server
        masked_total += n
        items.append((path, text))
    stats["secrets_masked"] = masked_total
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
        signals_raw.extend(parsed.risk_signals)
    if batches and failures == len(batches):
        raise ScanError("The AI service could not be reached or rejected the request. "
                        f"Check OPENAI_API_KEY / OPENAI_MODEL and try again. ({last_error})")
    if stats.get("skipped_too_large") or stats.get("skipped_over_cap"):
        warnings.append(f"Some files were skipped (too large: {stats.get('skipped_too_large', 0)}, "
                        f"over file cap: {stats.get('skipped_over_cap', 0)}).")
    dropped: list[str] = []
    findings = process_findings(raw, files, dropped)
    signals = sorted({x.signal for x in signals_raw if evidence_found(x.evidence, files, 12)})
    if dropped:
        reasons: dict[str, int] = {}
        for d in dropped:
            reasons[d] = reasons.get(d, 0) + 1
        stats["discarded"] = [{"reason": r, "count": n} for r, n in reasons.items()]
        stats["discarded_total"] = len(dropped)
    return {"findings": findings, "risk_signals": signals,
            "stats": stats, "warnings": warnings, "files": files}


async def scan_repo(owner: str, repo: str, ref: str, token: str | None = None,
                    questionnaire: dict | None = None) -> dict:
    files, stats = await select_files(owner, repo, ref, token=token)
    return await analyse(files, stats, questionnaire)


async def scan_archive(all_files: dict[str, str], questionnaire: dict | None = None) -> dict:
    files, stats = choose_files(all_files)
    stats["code_files_in_repo"] = len(all_files)
    return await analyse(files, stats, questionnaire)
