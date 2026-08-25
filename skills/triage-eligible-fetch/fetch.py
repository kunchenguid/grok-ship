#!/usr/bin/env python3
"""Eligible-fetch for a triage crewmate. Flags only; no config file.

Lists open issues and PRs that are due for triage. Items authored by
`--owner` (the captain's personal GitHub login) are skipped except
last-resort ports. Firstmate-mark comments and automation comments/reviews
do not reset the stamp clock. Existing `<!-- triage:`, `<!-- gh-axi-triage:`,
and `<!-- treehouse-triage:` stamps still count.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

STAMP_RE = re.compile(
    r"<!--\s*(?:[\w.-]+-)?triage:?\s*"
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))",
    re.IGNORECASE,
)
OUTCOME_RE = re.compile(r"outcome=([A-Za-z0-9_.-]+)", re.IGNORECASE)
LAST_RESORT_RE = re.compile(r"Last-resort port of #(\d+)", re.IGNORECASE)
CLOSING_KEYWORD_RE = re.compile(
    r"(?i)\b(?:fix(?:es|ed|ing)?|clos(?:e|es|ed|ing)|resolv(?:e|es|ed|ing))\b"
)
CLOSING_LIST_RE = re.compile(
    r"(?i)\b(?:fix(?:es|ed|ing)?|clos(?:e|es|ed|ing)|resolv(?:e|es|ed|ing)):?\s*"
    r"(?P<list>(?:https://github\.com/[^/\s]+/[^/\s]+/issues/|#)\d+"
    r"(?:(?:\s*,?\s+and\s+|\s*[,;&/]\s*|\s+)"
    r"(?:https://github\.com/[^/\s]+/[^/\s]+/issues/|#)\d+)*)"
)
ISSUE_REF_RE = re.compile(
    r"(?:https://github\.com/[^/\s]+/[^/\s]+/issues/|#)(\d+)"
)
AUTOMATION_MARKERS = (
    "dependabot",
    "github-actions",
    "release-please",
    "renovate",
    "[bot]",
    "app/",
    "greptile",
)

ISSUE_LIST_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 50, states: OPEN, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url createdAt updatedAt body
        author { login }
        labels(first: 20) { nodes { name } }
        comments(last: 50, orderBy: {field: UPDATED_AT, direction: ASC}) {
          pageInfo { hasPreviousPage startCursor }
          nodes { author { login } body createdAt }
        }
      }
    }
  }
}
"""

PR_LIST_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 40, states: OPEN, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url createdAt updatedAt body
        author { login }
        comments(last: 50, orderBy: {field: UPDATED_AT, direction: ASC}) {
          pageInfo { hasPreviousPage startCursor }
          nodes { author { login } body createdAt }
        }
        reviews(last: 30) {
          nodes { author { login } body createdAt }
        }
        commits(last: 20) {
          nodes {
            commit {
              message
              committedDate
              authors(first: 5) { nodes { user { login } } }
            }
          }
        }
        closingIssuesReferences(first: 10) {
          nodes {
            number title state body
            labels(first: 20) { nodes { name } }
            comments(last: 20) {
              nodes { body createdAt }
            }
          }
        }
      }
    }
  }
}
"""

COMMENT_PAGE_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issueOrPullRequest(number: $number) {
      ... on Issue {
        comments(last: 50, before: $cursor, orderBy: {field: UPDATED_AT, direction: ASC}) {
          pageInfo { hasPreviousPage startCursor }
          nodes { author { login } body createdAt }
        }
      }
      ... on PullRequest {
        comments(last: 50, before: $cursor, orderBy: {field: UPDATED_AT, direction: ASC}) {
          pageInfo { hasPreviousPage startCursor }
          nodes { author { login } body createdAt }
        }
      }
    }
  }
}
"""


def parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_automation(login: str | None) -> bool:
    if not login:
        return False
    low = login.lower()
    return any(marker in low for marker in AUTOMATION_MARKERS)


def is_last_resort_port(text: str | None) -> bool:
    return bool(LAST_RESORT_RE.search(text or ""))


def skip_owner(login: str | None, owner: str, body: str | None, title: str | None) -> bool:
    if not login or login.lower() != owner.lower():
        return False
    blob = f"{title or ''}\n{body or ''}"
    return not is_last_resort_port(blob)


def find_stamps(text: str | None) -> list[tuple[datetime, str | None]]:
    stamps: list[tuple[datetime, str | None]] = []
    if not text:
        return stamps
    for match in STAMP_RE.finditer(text):
        try:
            when = parse_iso(match.group(1))
        except ValueError:
            continue
        window = text[match.end() : match.end() + 240]
        outcome_match = OUTCOME_RE.search(window)
        outcome = outcome_match.group(1) if outcome_match else None
        stamps.append((when, outcome))
    return stamps


def latest_stamp(texts: Iterable[str | None]) -> tuple[datetime, str | None] | None:
    found: list[tuple[datetime, str | None]] = []
    for text in texts:
        found.extend(find_stamps(text))
    if not found:
        return None
    return max(found, key=lambda item: item[0])


def has_ready_for_pr(labels: Iterable[str], texts: Iterable[str | None]) -> bool:
    if any(label.lower() == "ready-for-pr" for label in labels):
        return True
    stamp = latest_stamp(texts)
    return bool(stamp and stamp[1] and stamp[1].lower() == "ready-for-pr")


def closing_issue_numbers(*texts: str | None) -> list[int]:
    numbers: list[int] = []
    seen: set[int] = set()
    blob = "\n".join(text for text in texts if text)
    for match in CLOSING_LIST_RE.finditer(blob):
        for ref in ISSUE_REF_RE.finditer(match.group("list")):
            number = int(ref.group(1))
            if number not in seen:
                seen.add(number)
                numbers.append(number)
    return numbers


def has_closing_keyword(*texts: str | None) -> bool:
    blob = "\n".join(text for text in texts if text)
    return bool(CLOSING_KEYWORD_RE.search(blob))


def is_firstmate_text(text: str | None, firstmate_mark: str) -> bool:
    if not text or not firstmate_mark:
        return False
    return text.lstrip().lower().startswith(firstmate_mark.lower())


def is_clock_noise(activity: Activity, firstmate_mark: str) -> bool:
    """Bot comments/reviews (and bot commits) and firstmate-mark comments do not reset the clock."""
    if is_automation(activity.login):
        return True
    if activity.kind in {"comment", "review"} and is_firstmate_text(
        activity.body, firstmate_mark
    ):
        return True
    return False


def ready_for_pr_closers(item: Item) -> list[int]:
    """PRs that close a ready-for-pr issue via Fixes/Closes/Resolves (and Closing/Resolving)."""
    texts = (item.body, *item.commit_messages)
    parsed = closing_issue_numbers(*texts)
    candidates: list[int] = []
    seen: set[int] = set()

    def add(number: int) -> None:
        if number not in seen:
            seen.add(number)
            candidates.append(number)

    for number in parsed:
        add(number)
    # After a closing keyword, use GitHub's linked issue list too (commit
    # messages and multi-issue lists the body parser might still miss).
    if has_closing_keyword(*texts):
        for issue in item.closing_issues:
            number = issue.get("number")
            if number is not None:
                add(int(number))
    if not candidates:
        return []
    by_number: dict[int, dict[str, Any]] = {}
    for issue in item.closing_issues:
        number = issue.get("number")
        if number is None:
            continue
        by_number[int(number)] = issue
    ready: list[int] = []
    for number in candidates:
        issue = by_number.get(number)
        if issue is None:
            continue
        issue_texts = [issue.get("body"), *(issue.get("comment_bodies") or [])]
        if has_ready_for_pr(issue.get("labels") or [], issue_texts):
            ready.append(number)
    return ready


@dataclass(frozen=True)
class Activity:
    when: datetime
    kind: str
    login: str | None
    body: str | None = None


@dataclass
class Item:
    number: int
    title: str
    url: str
    created_at: datetime
    author: str | None
    body: str
    kind: str
    labels: list[str] = field(default_factory=list)
    activities: list[Activity] = field(default_factory=list)
    closing_issues: list[dict[str, Any]] = field(default_factory=list)
    commit_messages: list[str] = field(default_factory=list)
    comment_cursor: str | None = None
    has_older_comments: bool = False


@dataclass(frozen=True)
class Classified:
    item: Item
    bucket: str
    stamp_at: datetime | None
    outcome: str | None
    closes_ready: list[int]


def classify_item(
    item: Item,
    *,
    owner: str,
    firstmate_mark: str,
    stale_days: int,
    now: datetime,
) -> Classified | None:
    if is_automation(item.author):
        return None
    if skip_owner(item.author, owner, item.body, item.title):
        return None

    stamp = latest_stamp(
        [item.body, *(activity.body for activity in item.activities)]
    )
    later_real = False
    if stamp is not None:
        for activity in item.activities:
            if activity.when <= stamp[0]:
                continue
            if is_clock_noise(activity, firstmate_mark):
                continue
            later_real = True
            break

    closes_ready: list[int] = []
    if item.kind == "pr":
        closes_ready = ready_for_pr_closers(item)

    if stamp is None:
        return Classified(item, "unstamped", None, None, closes_ready)
    if later_real:
        return Classified(item, "live", stamp[0], stamp[1], closes_ready)

    age = now - stamp[0]
    if age >= timedelta(days=stale_days):
        return Classified(item, "stale-restamp", stamp[0], stamp[1], closes_ready)
    return None


def rank_issues(classified: list[Classified], cap: int) -> list[Classified]:
    live = [row for row in classified if row.bucket in {"unstamped", "live"}]
    stale = [row for row in classified if row.bucket == "stale-restamp"]
    live.sort(key=lambda row: row.item.created_at, reverse=True)
    stale.sort(key=lambda row: row.stamp_at or row.item.created_at)
    return (live + stale)[:cap]


def rank_prs(classified: list[Classified], cap: int) -> list[Classified]:
    closers = [row for row in classified if row.closes_ready]
    closer_numbers = {row.item.number for row in closers}
    other_live = [
        row
        for row in classified
        if row.item.number not in closer_numbers and row.bucket in {"unstamped", "live"}
    ]
    stale = [
        row
        for row in classified
        if row.item.number not in closer_numbers and row.bucket == "stale-restamp"
    ]
    closers.sort(key=lambda row: row.item.created_at, reverse=True)
    other_live.sort(key=lambda row: row.item.created_at, reverse=True)
    stale.sort(key=lambda row: row.stamp_at or row.item.created_at)
    return (closers + other_live + stale)[:cap]


def gh_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        if isinstance(value, int):
            cmd.extend(["-F", f"{key}={value}"])
        else:
            cmd.extend(["-f", f"{key}={value}"])
    try:
        completed = subprocess.run(
            cmd, check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise SystemExit("gh is required") from exc
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        raise SystemExit(f"gh graphql failed: {err}") from exc
    payload = json.loads(completed.stdout)
    if payload.get("errors"):
        raise SystemExit(f"gh graphql errors: {payload['errors']}")
    return payload["data"]


def _actor_login(node: dict[str, Any] | None) -> str | None:
    if not node:
        return None
    return node.get("login")


def _parse_comments(nodes: Iterable[dict[str, Any]]) -> list[Activity]:
    activities: list[Activity] = []
    for node in nodes:
        try:
            when = parse_iso(node["createdAt"])
        except (KeyError, TypeError, ValueError):
            continue
        activities.append(
            Activity(
                when=when,
                kind="comment",
                login=_actor_login(node.get("author")),
                body=node.get("body") or "",
            )
        )
    return activities


def item_from_issue(node: dict[str, Any]) -> Item:
    comments = node.get("comments") or {}
    page = comments.get("pageInfo") or {}
    return Item(
        number=int(node["number"]),
        title=node.get("title") or "",
        url=node.get("url") or "",
        created_at=parse_iso(node["createdAt"]),
        author=_actor_login(node.get("author")),
        body=node.get("body") or "",
        kind="issue",
        labels=[label.get("name") or "" for label in (node.get("labels") or {}).get("nodes") or []],
        activities=_parse_comments(comments.get("nodes") or []),
        comment_cursor=page.get("startCursor"),
        has_older_comments=bool(page.get("hasPreviousPage")),
    )


def item_from_pr(node: dict[str, Any]) -> Item:
    comments = node.get("comments") or {}
    page = comments.get("pageInfo") or {}
    activities = _parse_comments(comments.get("nodes") or [])
    commit_messages: list[str] = []
    for review in (node.get("reviews") or {}).get("nodes") or []:
        try:
            when = parse_iso(review["createdAt"])
        except (KeyError, TypeError, ValueError):
            continue
        activities.append(
            Activity(
                when=when,
                kind="review",
                login=_actor_login(review.get("author")),
                body=review.get("body") or "",
            )
        )
    for commit_node in (node.get("commits") or {}).get("nodes") or []:
        commit = (commit_node or {}).get("commit") or {}
        message = commit.get("message") or ""
        if message:
            commit_messages.append(message)
        try:
            when = parse_iso(commit["committedDate"])
        except (KeyError, TypeError, ValueError):
            continue
        authors = (commit.get("authors") or {}).get("nodes") or []
        login = None
        for author in authors:
            user = (author or {}).get("user") or {}
            if user.get("login"):
                login = user["login"]
                break
        activities.append(
            Activity(when=when, kind="commit", login=login, body=None)
        )
    closing = []
    for issue in (node.get("closingIssuesReferences") or {}).get("nodes") or []:
        comment_bodies = [
            comment.get("body") or ""
            for comment in (issue.get("comments") or {}).get("nodes") or []
        ]
        closing.append(
            {
                "number": issue.get("number"),
                "title": issue.get("title") or "",
                "state": issue.get("state"),
                "body": issue.get("body") or "",
                "labels": [
                    label.get("name") or ""
                    for label in (issue.get("labels") or {}).get("nodes") or []
                ],
                "comment_bodies": comment_bodies,
            }
        )
    return Item(
        number=int(node["number"]),
        title=node.get("title") or "",
        url=node.get("url") or "",
        created_at=parse_iso(node["createdAt"]),
        author=_actor_login(node.get("author")),
        body=node.get("body") or "",
        kind="pr",
        activities=activities,
        closing_issues=closing,
        commit_messages=commit_messages,
        comment_cursor=page.get("startCursor"),
        has_older_comments=bool(page.get("hasPreviousPage")),
    )


def backfill_comments(item: Item, repo_owner: str, repo_name: str) -> None:
    """Walk older UPDATED_AT comment pages. Do not stop because the newest page already has a stamp."""
    cursor = item.comment_cursor
    while item.has_older_comments and cursor:
        data = gh_graphql(
            COMMENT_PAGE_QUERY,
            {
                "owner": repo_owner,
                "name": repo_name,
                "number": item.number,
                "cursor": cursor,
            },
        )
        container = (data.get("repository") or {}).get("issueOrPullRequest") or {}
        comments = container.get("comments") or {}
        older = _parse_comments(comments.get("nodes") or [])
        item.activities.extend(older)
        page = comments.get("pageInfo") or {}
        item.has_older_comments = bool(page.get("hasPreviousPage"))
        cursor = page.get("startCursor")
        item.comment_cursor = cursor


def paginate_nodes(
    query: str, repo_owner: str, repo_name: str, field: str
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    cursor = None
    while True:
        data = gh_graphql(
            query, {"owner": repo_owner, "name": repo_name, "cursor": cursor}
        )
        repo = data.get("repository")
        if repo is None:
            raise SystemExit(
                f"repository not found or inaccessible: {repo_owner}/{repo_name}"
            )
        conn = repo.get(field) or {}
        nodes.extend(conn.get("nodes") or [])
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
    return nodes


def serialize(row: Classified) -> dict[str, Any]:
    payload = {
        "number": row.item.number,
        "title": row.item.title,
        "url": row.item.url,
        "author": row.item.author,
        "bucket": row.bucket,
        "created_at": row.item.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if row.stamp_at is not None:
        payload["stamp_at"] = row.stamp_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    if row.outcome:
        payload["outcome"] = row.outcome
    if row.closes_ready:
        payload["closes_ready_for_pr"] = row.closes_ready
        payload["reason"] = "ready-for-pr-closer"
    elif row.bucket == "stale-restamp":
        payload["reason"] = "stale-restamp"
    elif row.bucket == "live":
        payload["reason"] = "later-activity"
    else:
        payload["reason"] = "unstamped"
    return payload


def parse_repo(value: str) -> tuple[str, str]:
    parts = value.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError("--repo must be OWNER/NAME")
    return parts[0], parts[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List open issues and PRs eligible for triage."
    )
    parser.add_argument(
        "--repo", required=True, help="OWNER/NAME of the GitHub repository"
    )
    parser.add_argument(
        "--owner",
        required=True,
        help="Captain's personal GitHub login to skip (not the org or repo-owner slug); last-resort ports are kept",
    )
    parser.add_argument(
        "--firstmate-mark",
        required=True,
        help="Text that must start a firstmate comment so those comments do not reset the clock",
    )
    parser.add_argument("--stale-days", type=int, default=14)
    parser.add_argument("--issues", type=int, default=5, help="Issue cap (default 5)")
    parser.add_argument("--prs", type=int, default=5, help="PR cap (default 5)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_owner, repo_name = parse_repo(args.repo)
    now = datetime.now(timezone.utc)

    issue_nodes = paginate_nodes(ISSUE_LIST_QUERY, repo_owner, repo_name, "issues")
    pr_nodes = paginate_nodes(PR_LIST_QUERY, repo_owner, repo_name, "pullRequests")

    issues = [item_from_issue(node) for node in issue_nodes]
    prs = [item_from_pr(node) for node in pr_nodes]
    for item in issues + prs:
        backfill_comments(item, repo_owner, repo_name)

    classified_issues = [
        row
        for row in (
            classify_item(
                item,
                owner=args.owner,
                firstmate_mark=args.firstmate_mark,
                stale_days=args.stale_days,
                now=now,
            )
            for item in issues
        )
        if row is not None
    ]
    classified_prs = [
        row
        for row in (
            classify_item(
                item,
                owner=args.owner,
                firstmate_mark=args.firstmate_mark,
                stale_days=args.stale_days,
                now=now,
            )
            for item in prs
        )
        if row is not None
    ]

    picked_issues = rank_issues(classified_issues, args.issues)
    picked_prs = rank_prs(classified_prs, args.prs)
    json.dump(
        {
            "repo": args.repo,
            "issues": [serialize(row) for row in picked_issues],
            "prs": [serialize(row) for row in picked_prs],
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
