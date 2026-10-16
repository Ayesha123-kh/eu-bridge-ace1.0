"""Exact-match patching and PR body rendering."""


class PatchError(Exception):
    pass


def apply_patch(content: str, original: str, replacement: str) -> str:
    if not original:
        raise PatchError("Empty original snippet")
    n = content.count(original)
    if n == 0:
        raise PatchError("Original snippet not found in file")
    if n > 1:
        raise PatchError(f"Original snippet matches {n} places in file (must be unique)")
    return content.replace(original, replacement, 1)


def apply_findings(content: str, findings: list[dict]) -> tuple[str, dict[str, str | None]]:
    """Apply findings sequentially. Returns (new_content, {finding_id: error_or_None})."""
    results: dict[str, str | None] = {}
    for f in findings:
        replacement = f.get("final_patch") or f["suggested_patch"]
        try:
            content = apply_patch(content, f["original_snippet"], replacement)
            results[f["id"]] = None
        except PatchError as e:
            results[f["id"]] = str(e)
    return content, results


DISCLAIMER = "EU-Bridge offers decision support, not legal advice."


def build_pr_body(scan: dict, applied: list[dict], failed: list[dict],
                  rejected: list[dict]) -> str:
    lines = ["## EU-Bridge: human-approved EU compliance fixes", "",
             "| Rule | File | Approved by | Reason |", "|---|---|---|---|"]
    for f in applied:
        lines.append(f"| {f['rule_id']} | `{f['file_path']}` | {f['reviewer']} | "
                     f"{_cell(f['review_reason'])} |")
    if failed:
        lines += ["", "### Approved but could not be applied", ""]
        lines += [f"- {f['rule_id']} in `{f['file_path']}`: {f['error']}" for f in failed]
    if rejected:
        lines += ["", "### Rejected by reviewer", ""]
        lines += [f"- {f['rule_id']} in `{f['file_path']}` — {f['reviewer']}: "
                  f"{_cell(f['review_reason'])}" for f in rejected]
    lines += ["", f"**Risk tier:** {scan['risk_tier']}"]
    if scan.get("escalation_reason"):
        reviewed = scan.get("risk_reviewed_by")
        lines.append(f"**Escalation:** {scan['escalation_reason']} "
                     + (f"(risk tier reviewed by {reviewed})" if reviewed
                        else "(risk tier NOT yet reviewed by a human — required before launch)"))
    lines += ["", f"_{DISCLAIMER}_"]
    return "\n".join(lines)


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")
