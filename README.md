# EU-Bridge

EU-Bridge finds what blocks your AI product from the EU market, drafts the code fix, and puts a human in charge of every change.

Built for Agentika 2.0 (NaSCon 2026). Theme: *Human + AI: Better Together*.

> EU-Bridge offers decision support, not legal advice.

## The problem

Since 2 August 2026, AI products used in the EU must meet the EU AI Act's transparency rules (for example, telling users they are talking to an AI, Article 50) on top of GDPR. This applies to companies outside the EU as well. Small teams with no legal staff don't know which rules apply or what to change in their code.

Most compliance tools produce a report. EU-Bridge produces a **human-reviewed pull request** and a **tamper-evident record of who approved what**.

## How it works

![EU-Bridge workflow](docs/workflow.svg)

1. A reviewer chooses **public repository** or **private code**, then answers a three-step questionnaire (the code, the product, and the data and AI it uses). Private code can be read with a fine-grained access token, or uploaded as a ZIP.
2. The app reads the repo, keeps the files that contain AI-related code, and asks OpenAI for structured findings. The AI only drafts. It never changes code.
3. The app discards suggestions that lack evidence: the quoted code must exist in the file, UI notices only apply to files that serve end users (not libraries or SDKs), log findings must involve user data, and a fix must change real behaviour (no comment-only patches, no calls to helpers that do not exist). It then checks that each remaining snippet exists exactly once in the file. Findings it can't place, or that the AI is unsure about, are marked `needs_human`.
4. Risk triage is deterministic. Hiring, credit, education, health, biometrics and critical-infrastructure products are **escalated**, and the AI doesn't decide the tier. A person confirms it.
5. A reviewer approves, edits then approves, or rejects each finding, one at a time, with a name and a reason.
6. When nothing is pending and at least one fix is approved, the app commits the approved fixes to a new branch and opens a pull request that lists each fix and who approved it. For uploaded ZIPs, the reviewer downloads a ZIP with the fixed files, a patch and the approval list instead.
7. Every step is written to a hash-chained audit log that can be verified and exported.

### Where a human is in the loop

| Gate | Rule |
|---|---|
| Risk tier | Escalated scans need a reviewer's name and reason before the tier counts as confirmed. |
| Every fix | Approve, edit then approve, or reject. Reviewer name and a reason of 5+ characters are enforced by the server. There is no bulk approve. |
| Unsure findings | Low confidence (under 0.6) or an unmatched snippet becomes `needs_human`. |
| Pull request | Blocked while any finding is pending. Failed patches are reported, not dropped. |
| Merge | A person merges the PR on GitHub. |

## The four checks

| ID | Check | Source |
|---|---|---|
| `AIA-50-1` | A chatbot tells users it is an AI | EU AI Act Art. 50(1) |
| `GDPR-13` | Users are told their data goes to a third-party AI | GDPR Art. 13, Art. 28 |
| `GDPR-5-1C` | No personal data in logs | GDPR Art. 5(1)(c), Art. 32 |
| `AIA-RISK` | Risk-tier triage (escalation only, no code fix) | EU AI Act Art. 5, Annex III, Art. 14 |

## Audit log

Each entry stores `sha256(prev_hash + canonical_json(entry))`, starting from 64 zeros. `GET /api/audit/verify` recomputes the chain and reports `{ok, broken_at}`. The log is **tamper-evident**, not immutable: editing or removing an earlier entry is detected, while removing the newest entries is not.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Health check |
| POST | `/api/scans` | Scan a GitHub repo: `{source: public \| private_token, repo_url, access_token?, questionnaire}` |
| POST | `/api/assessments` | No-code assessment from the questionnaire alone |
| GET | `/api/scans/{id}/checklist` | Assessments only: download the accepted checklist |
| DELETE | `/api/scans/{id}/files` | ZIP scans: delete the uploaded files from the server |
| POST | `/api/scans/upload` | Scan an uploaded ZIP (multipart: `questionnaire` JSON, `file`) |
| GET | `/api/scans/{id}` | Scan, findings and counters |
| POST | `/api/findings/{id}/review` | `{action: approve \| edit_and_approve \| reject, reviewer, reason, final_patch?}` |
| POST | `/api/regulations/match` | Which EU rules apply: `{offers[], eu_users, size, personal_data}` |
| POST | `/api/scans/{id}/risk-review` | Confirm the risk tier: `{reviewer, reason}` |
| POST | `/api/scans/{id}/pr` | Apply approved fixes and open the PR (`{access_token}` for private repos) |
| GET | `/api/scans/{id}/patch` | ZIP scans only: download fixed files, patch and approvals |
| GET | `/api/audit/verify` | Verify the hash chain |
| GET | `/api/audit/export` | Download the log as JSON |

Example scan request:

```bash
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/Ayesha123-kh/eu-bridge-demo-chatbot","questionnaire":{"description":"CV screening bot","uses_llm":true,"processes_personal_data":true,"domain":"hiring"}}'
```

## Input checks

The scan form requires a company name, a business website, a real description (not keyboard mashing), who uses the product, what the AI does, which AI providers it uses, and which personal data it handles. If the area is "none of the listed", an industry is required. "Not applicable" for human review is refused when the AI affects people. The same rules run on the server, so the API cannot skip them. Set `REQUIRE_LOGIN=true` to require an account before any scan.

## Accounts and history

- **Sign in is optional.** Anyone can use EU-Bridge as a guest. Creating an account (name, email, password) keeps history across devices, and scans made as a guest on that device move into the account.
- **Each owner sees only their own scans,** dashboard and audit entries. Other people get a 404 for your scan links.
- **Signed-in decisions are recorded under the account name,** and the server ignores any other name sent by the browser.
- Passwords are hashed with scrypt, sessions are random tokens stored hashed, and cookies are HttpOnly and SameSite=Lax.
- **Storage:** SQLite lives in `DATA_DIR`. Mount a persistent volume there (Railway: volume at `/data`, `DATA_DIR=/data`), otherwise history is lost on every redeploy.

## Pages

| Page | Purpose |
|---|---|
| `/` | Interactive dashboard: clickable totals, search and filters, scan history by scan or company, expandable details, findings by check, recent activity |
| `/signin` | Sign in or create an account |
| `/explore` | Pick what your business offers and see which EU rules apply (AI Act, GDPR, NIS2, CRA and more), what each asks, and key dates |
| `/new` | Three-step form: public repo, private code (token or ZIP) or no code (assessment) |
| `/scans/{id}` | Review page: the four checks, diffs, approve / edit / reject, pull request or download |
| `/audit` | Audit log with filters by company, person and action, Verify and Export |

## Not sharing code

Some businesses will not hand over source code. EU-Bridge supports three levels:

1. **No code (assessment):** answer the questionnaire and get the risk tier, the rules that apply, and a checklist with ready-to-use wording and a redaction helper. A person accepts or rejects each item and downloads the checklist. Nothing is read or sent to an AI provider.
2. **Private code, token or ZIP:** the relevant files are sent to OpenAI to find issues, after secrets (API keys, tokens, passwords, private keys) are masked. Tokens are never stored. Uploaded ZIP files can be deleted from the server at any time.
3. **Public repositories:** the licence is shown, and the app warns when there is none. Open pull requests only on code you own or have permission to change.

## Private code

- **Access token:** a fine-grained token limited to one repository with Contents and Pull requests set to read and write. It is held in memory for the request, never written to the database or logs, and must be entered again to open the pull request.
- **ZIP upload:** source files only, up to 8 MB. Unsafe paths and symlinks are rejected. The scanned files are kept in the database only to prepare the download.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the two secrets
uvicorn app.main:app --port 8000
pytest
```

## Configuration

| Variable | Required | Notes |
|---|---|---|
| `OPENAI_API_KEY` | yes | Never logged or displayed. |
| `GITHUB_TOKEN` | yes | Fine-grained token for the **public repo** used by default, with Contents and Pull requests set to read and write. Private repos use a token entered by the reviewer instead. |
| `OPENAI_MODEL` | no | Default `gpt-4o-mini`. |
| `PORT` | no | Default `8000`. |
| `APP_ENV` | no | `staging` or `production`. |
| `DATA_DIR` | no | SQLite location, default `./data`. Resets on redeploy. |
| `MAX_FILES` / `MAX_FILE_BYTES` | no | Defaults `40` / `40000`. |

The app exits at startup with `Missing env var: NAME` if a required variable is unset.

## Deployment

| Environment | Branch | Host | Notes |
|---|---|---|---|
| Staging | `staging` | Railway | Redeploys on every push. Used for testing. |
| Production | `main` | Alternate Clouds | One service. A push does not redeploy: click **Rebuild**, then **Deploy**. Set PORT to `8000` in the Source tab. |

The Docker image runs `uvicorn app.main:app` on `$PORT`.

## Demo target

[`eu-bridge-demo-chatbot`](https://github.com/Ayesha123-kh/eu-bridge-demo-chatbot) is a deliberately non-compliant chatbot. It logs user emails, sends messages to OpenAI with no notice, and has no AI disclosure. Its README describes it as a CV-screening assistant, which triggers escalation when the domain is "hiring".

## Out of scope

User accounts, GitLab, background queues, scanning live websites, and full coverage of the AI Act or GDPR. Four checks, done well.
