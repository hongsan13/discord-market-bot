"""Read-only GitHub collection and explicit, single-attempt Discord delivery.

No trading module is imported. External PR/issue text is data only. Network
errors are deliberately redacted because request exceptions may contain tokens.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import requests


GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_PAGE_SIZE = 50
GITHUB_MAX_PAGES = 5
MAX_BODY_CHARS = 6000
MAX_SUMMARY_UNITS = 2000
MAX_SUMMARY_BYTES = 16000
MAX_PDF_BYTES = 8 * 1024 * 1024  # Conservative cap below Discord's default 10 MiB.
NETWORK_TIMEOUT = (5, 30)
REVIEW_TITLE_PREFIX = "[週次レビュー "
TRUSTED_REVIEW_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")
WEBHOOK_PATH_PATTERN = re.compile(r"/api(?:/v10)?/webhooks/[0-9]{5,25}/[A-Za-z0-9_-]{10,200}/?")


class DeliveryError(RuntimeError):
    """A safe-to-log delivery failure; never contains credentials or responses."""


class CollectionError(RuntimeError):
    """A safe-to-log GitHub collection failure."""


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _warn(result, message, *, truncated=False):
    if message not in result["warnings"]:
        result["warnings"].append(message)
    if truncated:
        result["truncated"] = True


def _github_page(session, repository, endpoint, params, headers):
    # Never follow response links/redirects with the bearer token.
    url = f"{GITHUB_API}/repos/{repository}/{endpoint}"
    try:
        response = session.get(
            url, params=params, headers=headers, timeout=NETWORK_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise CollectionError("GitHub request failed; details redacted.") from None
    if response.status_code != 200:
        raise CollectionError(f"GitHub request failed (HTTP {response.status_code}).")
    try:
        items = response.json()
    except ValueError:
        raise CollectionError("GitHub returned invalid JSON.") from None
    if not isinstance(items, list):
        raise CollectionError("GitHub returned an unexpected response shape.")
    # Only the presence of pagination is used; its destination is never followed.
    return items, bool(response.links.get("next"))


def _entry(item, repository, endpoint, result):
    number = item.get("number")
    if type(number) is not int or number <= 0:
        _warn(result, "Some GitHub records had invalid metadata and were omitted.")
        return None
    title = item.get("title") if isinstance(item.get("title"), str) else ""
    body = item.get("body") if isinstance(item.get("body"), str) else ""
    body_truncated = len(body) > MAX_BODY_CHARS
    if body_truncated or len(title) > 240:
        _warn(result, "Some GitHub text was truncated for report size limits.", truncated=True)
    state = item.get("state")
    if state not in {"open", "closed"}:
        state = "unknown"
        _warn(result, "Some GitHub records have an unknown state.")
    association = item.get("author_association")
    author = item.get("user")
    author_login = author.get("login") if isinstance(author, dict) else None
    record = {
        "number": number,
        "title": title[:240],
        "state": state,
        "author_association": association if isinstance(association, str) else None,
        "author_login": author_login if isinstance(author_login, str) else None,
        "body": body[:MAX_BODY_CHARS],
        "body_truncated": body_truncated,
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at"),
        "closed_at": item.get("closed_at"),
        "html_url": f"https://github.com/{repository}/{endpoint}/{number}",
    }
    if endpoint == "pull":
        base = item.get("base")
        base_branch = base.get("ref") if isinstance(base, dict) else None
        record["base_branch"] = base_branch if isinstance(base_branch, str) else None
        merged_at = _timestamp(item.get("merged_at"))
        record["merged_at"] = _iso(merged_at) if merged_at else None
        record["status"] = "merged" if merged_at else state
        record["draft"] = item.get("draft") is True
        # PR-body claims and mergeability are not proof of passing checks.
        # The workflow intentionally has no checks/statuses/actions permission.
        record["checks_status"] = "unknown (not collected with read-only PR/issue scope)"
    return record


def collect_github(repository, now=None, *, session=None):
    """Collect at most 250 PRs and 250 issues updated in the last seven days.

    Requires GITHUB_TOKEN. Missing credentials/API failures are visible warnings,
    not evidence that there were no changes. Does not read checks, write GitHub,
    fetch PR branches, or execute any returned text. Merged does not mean deployed.
    Matching weekly issues are accepted only from trusted repository contributors;
    a public issue title alone is not evidence that the scheduled review ran.
    """
    if (
        not isinstance(repository, str)
        or not REPOSITORY_PATTERN.fullmatch(repository)
        or repository.rsplit("/", 1)[-1] in {".", ".."}
    ):
        raise ValueError("Repository must be a GitHub owner/repository name.")
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Collection time must include a timezone.")
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(days=7)
    result = {
        "repository": repository, "collected_at": _iso(now), "since": _iso(cutoff),
        "pull_requests": [], "reviews": [], "warnings": [], "truncated": False,
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        _warn(result, "GITHUB_TOKEN is unavailable; GitHub collection was not run.")
        return result
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    owns_session = session is None
    if owns_session:
        session = requests.Session()
        session.trust_env = False
    try:
        for endpoint, output_key, link_type in (
            ("pulls", "pull_requests", "pull"), ("issues", "reviews", "issues"),
        ):
            seen = set()
            for page_number in range(1, GITHUB_MAX_PAGES + 1):
                params = {
                    "state": "all", "sort": "updated", "direction": "desc",
                    "per_page": GITHUB_PAGE_SIZE, "page": page_number,
                }
                if endpoint == "issues":
                    params["since"] = _iso(cutoff)
                try:
                    items, has_next = _github_page(session, repository, endpoint, params, headers)
                except CollectionError as error:
                    _warn(result, f"{endpoint}: {error} Collection may be incomplete.")
                    break
                crossed_cutoff = False
                for item in items[:GITHUB_PAGE_SIZE]:
                    if not isinstance(item, dict):
                        _warn(result, "Some GitHub records had invalid metadata and were omitted.")
                        continue
                    updated = _timestamp(item.get("updated_at"))
                    if updated is None or updated > now:
                        _warn(result, "Some GitHub records had invalid/out-of-window timestamps and were omitted.")
                        continue
                    if updated < cutoff:
                        crossed_cutoff = True
                        continue
                    if endpoint == "issues" and (
                        "pull_request" in item
                        or not isinstance(item.get("title"), str)
                        or not item["title"].startswith(REVIEW_TITLE_PREFIX)
                    ):
                        continue
                    if endpoint == "issues":
                        association = item.get("author_association")
                        if not isinstance(association, str) or association not in TRUSTED_REVIEW_ASSOCIATIONS:
                            _warn(result, "Matching weekly review issues from untrusted authors were omitted (requires OWNER, MEMBER or COLLABORATOR).")
                            continue
                    record = _entry(item, repository, link_type, result)
                    if record and record["number"] not in seen:
                        result[output_key].append(record)
                        seen.add(record["number"])
                if len(items) > GITHUB_PAGE_SIZE:
                    _warn(result, "GitHub response exceeded the requested page cap.", truncated=True)
                if crossed_cutoff or not has_next or not items:
                    break
                if page_number == GITHUB_MAX_PAGES:
                    _warn(result, f"{endpoint}: collection capped at {GITHUB_MAX_PAGES} pages; additional records omitted.", truncated=True)
    finally:
        if owns_session:
            session.close()
    return result


def _webhook_url(value):
    try:
        parts = urlsplit(value)
        valid = (
            isinstance(value, str) and not re.search(r"[\x00-\x20\x7f]", value)
            and parts.scheme == "https" and parts.netloc == "discord.com"
            and not parts.query and not parts.fragment
            and WEBHOOK_PATH_PATTERN.fullmatch(parts.path)
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise DeliveryError("DISCORD_WEBHOOK_URL must be an HTTPS discord.com API webhook URL (no query/fragment).")
    return value.rstrip("/")


def _read_file(path, max_bytes, label):
    try:
        with Path(path).open("rb") as handle:
            contents = handle.read(max_bytes + 1)
    except (OSError, ValueError):
        raise DeliveryError(f"Cannot read {label} file.") from None
    if not contents or len(contents) > max_bytes:
        raise DeliveryError(f"{label} file is empty or exceeds its size limit.")
    return contents


def _retry_after(response):
    try:
        body = response.json()
        value = body.get("retry_after") if isinstance(body, dict) else None
        if value is None:
            value = response.headers.get("Retry-After")
        seconds = float(value)
        if math.isfinite(seconds) and 0 <= seconds <= 86400:
            return f" Wait at least {math.ceil(seconds)} seconds before considering a retry."
    except (TypeError, ValueError):
        pass
    return ""


def send_discord(summary, pdf_path, *, webhook_url=None, session=None):
    """Send one confirmed multipart message. Never blindly retry a POST.

    A timeout/5xx can occur after the message was accepted; inspect the channel
    before manual reruns. A 429 is reported with retry_after, not auto-resubmitted.
    """
    endpoint = _webhook_url(webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", ""))
    try:
        content = summary.strip()
        units = len(content.encode("utf-16-le")) // 2
    except (AttributeError, UnicodeEncodeError):
        raise DeliveryError("Summary must be valid Unicode text.") from None
    if not content or units > MAX_SUMMARY_UNITS:
        raise DeliveryError("Discord summary must contain 1 to 2000 UTF-16 code units.")
    pdf = _read_file(pdf_path, MAX_PDF_BYTES, "PDF")
    if not pdf.startswith(b"%PDF-"):
        raise DeliveryError("Attachment is not a PDF.")
    payload = {
        "content": content,
        "allowed_mentions": {"parse": [], "replied_user": False},
        "attachments": [{"id": 0, "filename": "newspaper.pdf"}],
    }
    owns_session = session is None
    if owns_session:
        session = requests.Session()
        session.trust_env = False
    try:
        try:
            response = session.post(
                endpoint, params={"wait": "true"},
                data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                files={"files[0]": ("newspaper.pdf", pdf, "application/pdf")},
                timeout=NETWORK_TIMEOUT, allow_redirects=False,
            )
        except requests.RequestException:
            raise DeliveryError("Discord delivery was not confirmed (network error; details redacted). Check the channel before retrying.") from None
        if response.status_code == 429:
            raise DeliveryError("Discord rate limit reached; no automatic resend." + _retry_after(response))
        if response.status_code != 200:
            raise DeliveryError(f"Discord delivery was not confirmed (HTTP {response.status_code}). Check the channel before retrying.")
        try:
            message = response.json()
        except ValueError:
            message = None
        if not isinstance(message, dict) or not re.fullmatch(r"[0-9]{1,25}", str(message.get("id", ""))):
            raise DeliveryError("Discord did not return a message confirmation. Check the channel before retrying.")
        return {"message_id": str(message["id"])}
    finally:
        if owns_session:
            session.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send a generated weekly summary and PDF to Discord once.")
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        raw_summary = _read_file(args.summary, MAX_SUMMARY_BYTES, "Summary")
        try:
            summary = raw_summary.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise DeliveryError("Summary file must be UTF-8.") from None
        send_discord(summary, args.pdf)
    except DeliveryError as error:
        print(f"Weekly Discord delivery failed: {error}", file=sys.stderr)
        return 1
    print("Weekly summary and PDF sent to Discord; message confirmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
