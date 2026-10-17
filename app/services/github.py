"""Minimal GitHub REST client. Error messages never include the token."""
import base64
import re

import httpx

from app import config

API = "https://api.github.com"
_URL_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def parse_repo_url(url: str) -> tuple[str, str]:
    m = _URL_RE.match((url or "").strip())
    if not m:
        raise ValueError("Only public repo URLs like https://github.com/owner/repo are accepted.")
    return m.group(1), m.group(2)


async def _request(method: str, path: str, token: str | None = None, **kwargs):
    headers = {
        "Authorization": f"Bearer {(token or config.GITHUB_TOKEN)}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, API + path, headers=headers, **kwargs)
    except httpx.HTTPError as e:
        raise GitHubError(f"Could not reach GitHub ({type(e).__name__}).") from None
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("message", "")
        except ValueError:
            msg = ""
        hint = ""
        if resp.status_code in (401, 403, 404):
            hint = (" Check the repository URL and that the access token can reach this "
                    "repository (Contents and Pull requests permissions).")
        raise GitHubError(f"GitHub returned {resp.status_code}: {msg}.{hint}".strip(), resp.status_code)
    return resp.json()


async def get_repo(owner: str, repo: str, token: str | None = None) -> dict:
    return await _request("GET", f"/repos/{owner}/{repo}", token=token)


async def get_branch_sha(owner: str, repo: str, branch: str, token: str | None = None) -> str:
    data = await _request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token=token)
    return data["object"]["sha"]


async def list_tree(owner: str, repo: str, ref: str, token: str | None = None) -> list[dict]:
    data = await _request("GET", f"/repos/{owner}/{repo}/git/trees/{ref}", token=token,
                          params={"recursive": "1"})
    return [t for t in data.get("tree", []) if t.get("type") == "blob"]


async def get_file(owner: str, repo: str, path: str, ref: str, token: str | None = None) -> tuple[str, str]:
    """Returns (text, blob_sha)."""
    data = await _request("GET", f"/repos/{owner}/{repo}/contents/{path}", token=token, params={"ref": ref})
    if data.get("encoding") != "base64":
        raise GitHubError(f"File {path} is too large or not readable via the contents API.")
    try:
        text = base64.b64decode(data["content"]).decode("utf-8")
    except UnicodeDecodeError:
        raise GitHubError(f"File {path} is not valid UTF-8 text.") from None
    return text, data["sha"]


async def create_branch(owner: str, repo: str, name: str, from_sha: str, token: str | None = None) -> None:
    await _request("POST", f"/repos/{owner}/{repo}/git/refs", token=token,
                   json={"ref": f"refs/heads/{name}", "sha": from_sha})


async def put_file(owner: str, repo: str, path: str, content: str, sha: str,
                   branch: str, message: str, token: str | None = None) -> None:
    await _request("PUT", f"/repos/{owner}/{repo}/contents/{path}", token=token, json={
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode(),
        "sha": sha,
        "branch": branch,
    })


async def create_pr(owner: str, repo: str, head: str, base: str, title: str, body: str,
                    token: str | None = None) -> str:
    data = await _request("POST", f"/repos/{owner}/{repo}/pulls", token=token,
                          json={"title": title, "head": head, "base": base, "body": body})
    return data["html_url"]
