#!/usr/bin/env python3
"""Eligible-fetch for a triage crewmate. Flags only; no config file.

Lists open issues and PRs that are due for triage. Items authored by
`--owner` (the captain's personal GitHub login) are skipped except
last-resort ports. Firstmate-mark comments and automation comments/reviews
do not reset the stamp clock. Author comments and new commits still do.
Existing `<!-- triage:`, `<!-- gh-axi-triage:`, and
`<!-- treehouse-triage:` stamps still count.
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
_ISSUE_REF_TOKEN = (
    r"(?:https://github\.com/[^/\s]+/[^/\s]+/issues/"
    r"|(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#)\d+"
)
CLOSING_LIST_RE = re.compile(
    r"(?i)\b(?:fix(?:es|ed|ing)?|clos(?:e|es|ed|ing)|resolv(?:e|es|ed|ing)):?\s*"
    rf"(?P<list>{_ISSUE_REF_TOKEN}"
    rf"(?:(?:\s*,?\s+and\s+|\s*[,;&/]\s*|\s+){_ISSUE_REF_TOKEN})*)"
)
ISSUE_REF_RE = re.compile(
    r"(?:https://github\.com/(?P<url_owner>[^/\s]+)/(?P<url_name>[^/\s]+)/issues/"
    r"|(?:(?P<ref_owner>[A-Za-z0-9_.-]+)/(?P<ref_name>[A-Za-z0-9_.-]+))?#)"
    r"(?P<number>\d+)",
    re.IGNORECASE,
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
        author { login __typename }
        labels(first: 20) { nodes { name } }
        comments(last: 50, orderBy: {field: UPDATED_AT, direction: ASC}) {
          pageInfo { hasPreviousPage startCursor }
          nodes { author { login __typename } body createdAt }
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
        author { login __typename }
        comments(last: 50, orderBy: {field: UPDATED_AT, direction: ASC}) {
          pageInfo { hasPreviousPage startCursor }
          nodes { author { login __typename } body createdAt }
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
          nodes { author { login __typename } body createdAt }
        }
      }
      ... on PullRequest {
        comments(last: 50, before: $cursor, orderBy: {field: UPDATED_AT, direction: ASC}) {
          pageInfo { hasPreviousPage startCursor }
          nodes { author { login __typename } body createdAt }
        }
      }
    }
  }
}
"""

REVIEW_THREAD_PAGE_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(last: 40, before: $cursor) {
        pageInfo { hasPreviousPage startCursor }
        nodes {
          id
          comments(last: 100) {
            pageInfo { hasPreviousPage startCursor }
            nodes { author { login __typename } body createdAt }
          }
        }
      }
    }
  }
}
"""

REVIEW_THREAD_COMMENT_PAGE_QUERY = """
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      comments(last: 100, before: $cursor) {
        pageInfo { hasPreviousPage startCursor }
        nodes { author { login __typename } body createdAt }
      }
    }
  }
}
"""

CLOSING_ISSUE_PAGE_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 50, after: $cursor, excludeUserLinked: true) {
        pageInfo { hasNextPage endCursor }
        nodes {
          number title state body
          repository { nameWithOwner }
          labels(first: 20) { nodes { name } }
          comments(last: 50, orderBy: {field: UPDATED_AT, direction: ASC}) {
            pageInfo { hasPreviousPage startCursor }
            nodes { body createdAt }
          }
        }
      }
    }
  }
}
"""

ISSUE_LOOKUP_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      number title state body
      repository { nameWithOwner }
      labels(first: 20) { nodes { name } }
      comments(last: 50, orderBy: {field: UPDATED_AT, direction: ASC}) {
        pageInfo { hasPreviousPage startCursor }
        nodes { body createdAt }
      }
    }
  }
}
"""

REVIEW_PAGE_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(last: 100, before: $cursor) {
        pageInfo { hasPreviousPage startCursor }
        nodes { author { login __typename } body createdAt }
      }
    }
  }
}
"""

COMMIT_PAGE_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      commits(last: 100, before: $cursor) {
        pageInfo { hasPreviousPage startCursor }
        nodes {
          commit {
            message
            committedDate
            authors(first: 5) { nodes { user { login } } }
          }
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


def is_automation(login: str | None, typename: str | None = None) -> bool:
    if (typename or "").lower() == "bot":
        return True
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


def skip_before_classify(item: Item, owner: str) -> bool:
    """True when classify_item would drop this item before reading comments."""
    if is_automation(item.author, item.author_typename):
        return True
    return skip_owner(item.author, owner, item.body, item.title)


def issue_is_open(issue: dict[str, Any]) -> bool:
    return (issue.get("state") or "OPEN").upper() == "OPEN"


def linked_issue_in_repo(issue: dict[str, Any], repo: str) -> bool:
    name = (issue.get("nameWithOwner") or "").strip()
    return bool(name) and name.lower() == repo.lower()


def _ref_is_local(match: re.Match[str], repo: str | None) -> bool:
    owner = match.group("url_owner") or match.group("ref_owner")
    name = match.group("url_name") or match.group("ref_name")
    if not owner or not name:
        return True
    if not repo:
        return False
    return f"{owner}/{name}".lower() == repo.lower()


def find_stamps(
    text: str | None, *, now: datetime | None = None
) -> list[tuple[datetime, str | None]]:
    stamps: list[tuple[datetime, str | None]] = []
    if not text:
        return stamps
    for match in STAMP_RE.finditer(text):
        try:
            when = parse_iso(match.group(1))
        except ValueError:
            continue
        if now is not None and when > now:
            continue
        window = text[match.end() : match.end() + 240]
        outcome_match = OUTCOME_RE.search(window)
        outcome = outcome_match.group(1) if outcome_match else None
        stamps.append((when, outcome))
    return stamps


def latest_stamp(
    texts: Iterable[str | None], *, now: datetime | None = None
) -> tuple[datetime, str | None] | None:
    found: list[tuple[datetime, str | None]] = []
    for text in texts:
        found.extend(find_stamps(text, now=now))
    if not found:
        return None
    return max(found, key=lambda item: item[0])


def has_ready_for_pr(
    labels: Iterable[str],
    texts: Iterable[str | None],
    *,
    now: datetime | None = None,
) -> bool:
    if any(label.lower() == "ready-for-pr" for label in labels):
        return True
    stamp = latest_stamp(texts, now=now)
    return bool(stamp and stamp[1] and stamp[1].lower() == "ready-for-pr")


def closing_issue_numbers(*texts: str | None, repo: str | None = None) -> list[int]:
    numbers: list[int] = []
    seen: set[int] = set()
    blob = "\n".join(text for text in texts if text)
    for match in CLOSING_LIST_RE.finditer(blob):
        for ref in ISSUE_REF_RE.finditer(match.group("list")):
            if not _ref_is_local(ref, repo):
                continue
            number = int(ref.group("number"))
            if number not in seen:
                seen.add(number)
                numbers.append(number)
    return numbers


def is_firstmate_text(text: str | None, firstmate_mark: str) -> bool:
    if not text or not firstmate_mark:
        return False
    return text.lstrip().lower().startswith(firstmate_mark.lower())


def is_clock_noise(activity: Activity, firstmate_mark: str) -> bool:
    """Firstmate-mark and automation comments/reviews do not reset the clock."""
    if activity.kind not in {"comment", "review"}:
        return False
    if is_automation(activity.login, activity.typename):
        return True
    return is_firstmate_text(activity.body, firstmate_mark)


def ready_for_pr_closers(
    item: Item, repo: str, *, now: datetime | None = None
) -> list[int]:
    """PRs that close a ready-for-pr issue via Fixes/Closes/Resolves (and Closing/Resolving)."""
    texts = (item.title, item.body, *item.commit_messages)
    parsed = closing_issue_numbers(*texts, repo=repo)
    candidates: list[int] = []
    seen: set[int] = set()

    def add(number: int) -> None:
        if number not in seen:
            seen.add(number)
            candidates.append(number)

    for number in parsed:
        add(number)
    # After a closing keyword with an issue ref in title, body, or commits,
    # use GitHub's same-repo linked issue list too. Bare fix/close/resolve
    # is not enough. Title-only Fixes/Closes/Resolves #N is a sort hint,
    # not proof the PR closes that issue.
    if parsed:
        for issue in item.closing_issues:
            number = issue.get("number")
            if (
                number is not None
                and issue_is_open(issue)
                and linked_issue_in_repo(issue, repo)
            ):
                add(int(number))
    if not candidates:
        return []
    by_number: dict[int, dict[str, Any]] = {}
    for issue in item.closing_issues:
        number = issue.get("number")
        if (
            number is None
            or not issue_is_open(issue)
            or not linked_issue_in_repo(issue, repo)
        ):
            continue
        by_number[int(number)] = issue
    ready: list[int] = []
    for number in candidates:
        issue = by_number.get(number)
        if issue is None:
            continue
        issue_texts = [issue.get("body"), *(issue.get("comment_bodies") or [])]
        if has_ready_for_pr(issue.get("labels") or [], issue_texts, now=now):
            ready.append(number)
    return ready


@dataclass(frozen=True)
class Activity:
    when: datetime
    kind: str
    login: str | None
    body: str | None = None
    typename: str | None = None


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
    closing_cursor: str | None = None
    has_more_closing: bool = False
    review_cursor: str | None = None
    has_older_reviews: bool = False
    commit_cursor: str | None = None
    has_older_commits: bool = False
    author_typename: str | None = None


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
    repo: str,
) -> Classified | None:
    if is_automation(item.author, item.author_typename):
        return None
    if skip_owner(item.author, owner, item.body, item.title):
        return None

    stamp = latest_stamp(
        [item.body, *(activity.body for activity in item.activities)],
        now=now,
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
        closes_ready = ready_for_pr_closers(item, repo, now=now)

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


def _load_json_object(raw: str | bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _graphql_data(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


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
        # `gh api graphql` exits 1 when the payload includes errors, even if
        # data is present (live: data + NOT_FOUND). Skip-null handling needs
        # that data; only fail here when stdout has no usable data.
        data = _graphql_data(_load_json_object(exc.stdout))
        if data is not None:
            return data
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        raise SystemExit(f"gh graphql failed: {err}") from exc
    payload = _load_json_object(completed.stdout) or {}
    data = _graphql_data(payload)
    if data is not None:
        return data
    if payload.get("errors"):
        raise SystemExit(f"gh graphql errors: {payload['errors']}")
    raise SystemExit("gh graphql failed: missing data")


def _actor_login(node: dict[str, Any] | None) -> str | None:
    if not node:
        return None
    return node.get("login")


def _actor_typename(node: dict[str, Any] | None) -> str | None:
    if not node:
        return None
    return node.get("__typename")


def _parse_comments(nodes: Iterable[dict[str, Any] | None]) -> list[Activity]:
    activities: list[Activity] = []
    for node in nodes:
        if not node:
            continue
        try:
            when = parse_iso(node["createdAt"])
        except (KeyError, TypeError, ValueError):
            continue
        author = node.get("author")
        activities.append(
            Activity(
                when=when,
                kind="comment",
                login=_actor_login(author),
                body=node.get("body") or "",
                typename=_actor_typename(author),
            )
        )
    return activities


def _label_names(node: dict[str, Any]) -> list[str]:
    return [
        label.get("name") or ""
        for label in (node.get("labels") or {}).get("nodes") or []
        if label
    ]


def _parse_reviews(nodes: Iterable[dict[str, Any] | None]) -> list[Activity]:
    activities: list[Activity] = []
    for review in nodes:
        if not review:
            continue
        try:
            when = parse_iso(review["createdAt"])
        except (KeyError, TypeError, ValueError):
            continue
        author = review.get("author")
        activities.append(
            Activity(
                when=when,
                kind="review",
                login=_actor_login(author),
                body=review.get("body") or "",
                typename=_actor_typename(author),
            )
        )
    return activities


def _parse_commits(
    nodes: Iterable[dict[str, Any] | None],
) -> tuple[list[Activity], list[str]]:
    activities: list[Activity] = []
    messages: list[str] = []
    for commit_node in nodes:
        if not commit_node:
            continue
        commit = commit_node.get("commit") or {}
        message = commit.get("message") or ""
        if message:
            messages.append(message)
        try:
            when = parse_iso(commit["committedDate"])
        except (KeyError, TypeError, ValueError):
            continue
        authors = (commit.get("authors") or {}).get("nodes") or []
        login = None
        for author in authors:
            if not author:
                continue
            user = author.get("user") or {}
            if user.get("login"):
                login = user["login"]
                break
        activities.append(Activity(when=when, kind="commit", login=login, body=None))
    return activities, messages


def item_from_issue(node: dict[str, Any] | None) -> Item | None:
    if not node:
        return None
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
        labels=_label_names(node),
        activities=_parse_comments(comments.get("nodes") or []),
        comment_cursor=page.get("startCursor"),
        has_older_comments=bool(page.get("hasPreviousPage")),
        author_typename=_actor_typename(node.get("author")),
    )


def _parse_closing_issues(nodes: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    closing: list[dict[str, Any]] = []
    for issue in nodes:
        if not issue:
            continue
        comments = issue.get("comments") or {}
        page = comments.get("pageInfo") or {}
        comment_bodies = [
            comment.get("body") or ""
            for comment in comments.get("nodes") or []
            if comment
        ]
        closing.append(
            {
                "number": issue.get("number"),
                "title": issue.get("title") or "",
                "state": issue.get("state"),
                "body": issue.get("body") or "",
                "labels": _label_names(issue),
                "comment_bodies": comment_bodies,
                "nameWithOwner": ((issue.get("repository") or {}).get("nameWithOwner") or ""),
                "comment_cursor": page.get("startCursor"),
                "has_older_comments": bool(page.get("hasPreviousPage")),
            }
        )
    return closing


def item_from_pr(node: dict[str, Any] | None) -> Item | None:
    if not node:
        return None
    comments = node.get("comments") or {}
    page = comments.get("pageInfo") or {}
    activities = _parse_comments(comments.get("nodes") or [])
    if "reviews" in node:
        reviews = node.get("reviews") or {}
        review_page = reviews.get("pageInfo") or {}
        activities.extend(_parse_reviews(reviews.get("nodes") or []))
        review_cursor = review_page.get("startCursor")
        has_older_reviews = bool(review_page.get("hasPreviousPage"))
    else:
        review_cursor = None
        has_older_reviews = True
    if "commits" in node:
        commits = node.get("commits") or {}
        commit_page = commits.get("pageInfo") or {}
        commit_activities, commit_messages = _parse_commits(commits.get("nodes") or [])
        activities.extend(commit_activities)
        commit_cursor = commit_page.get("startCursor")
        has_older_commits = bool(commit_page.get("hasPreviousPage"))
    else:
        commit_messages = []
        commit_cursor = None
        has_older_commits = True
    if "closingIssuesReferences" in node:
        closing_conn = node.get("closingIssuesReferences") or {}
        closing_page = closing_conn.get("pageInfo") or {}
        closing_issues = _parse_closing_issues(closing_conn.get("nodes") or [])
        closing_cursor = closing_page.get("endCursor")
        has_more_closing = bool(closing_page.get("hasNextPage"))
    else:
        closing_issues = []
        closing_cursor = None
        has_more_closing = True
    return Item(
        number=int(node["number"]),
        title=node.get("title") or "",
        url=node.get("url") or "",
        created_at=parse_iso(node["createdAt"]),
        author=_actor_login(node.get("author")),
        body=node.get("body") or "",
        kind="pr",
        activities=activities,
        closing_issues=closing_issues,
        commit_messages=commit_messages,
        comment_cursor=page.get("startCursor"),
        has_older_comments=bool(page.get("hasPreviousPage")),
        closing_cursor=closing_cursor,
        has_more_closing=has_more_closing,
        review_cursor=review_cursor,
        has_older_reviews=has_older_reviews,
        commit_cursor=commit_cursor,
        has_older_commits=has_older_commits,
        author_typename=_actor_typename(node.get("author")),
    )


def backfill_reviews(item: Item, repo_owner: str, repo_name: str) -> None:
    """Walk review summaries, including the first page when the list query omitted them."""
    if item.kind != "pr":
        return
    cursor = item.review_cursor
    while item.has_older_reviews:
        data = gh_graphql(
            REVIEW_PAGE_QUERY,
            {
                "owner": repo_owner,
                "name": repo_name,
                "number": item.number,
                "cursor": cursor,
            },
        )
        pull = ((data.get("repository") or {}).get("pullRequest")) or {}
        reviews = pull.get("reviews") or {}
        item.activities.extend(_parse_reviews(reviews.get("nodes") or []))
        page = reviews.get("pageInfo") or {}
        item.has_older_reviews = bool(page.get("hasPreviousPage"))
        cursor = page.get("startCursor")
        item.review_cursor = cursor
        if not item.has_older_reviews or not cursor:
            break


def backfill_commits(item: Item, repo_owner: str, repo_name: str) -> None:
    """Walk commits, including the first page when the list query omitted them."""
    if item.kind != "pr":
        return
    cursor = item.commit_cursor
    while item.has_older_commits:
        data = gh_graphql(
            COMMIT_PAGE_QUERY,
            {
                "owner": repo_owner,
                "name": repo_name,
                "number": item.number,
                "cursor": cursor,
            },
        )
        pull = ((data.get("repository") or {}).get("pullRequest")) or {}
        commits = pull.get("commits") or {}
        activities, messages = _parse_commits(commits.get("nodes") or [])
        item.activities.extend(activities)
        item.commit_messages.extend(messages)
        page = commits.get("pageInfo") or {}
        item.has_older_commits = bool(page.get("hasPreviousPage"))
        cursor = page.get("startCursor")
        item.commit_cursor = cursor
        if not item.has_older_commits or not cursor:
            break


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


def backfill_closing_issues(item: Item, repo_owner: str, repo_name: str) -> None:
    """Walk remaining keyword-closing refs (excludeUserLinked already applied)."""
    if item.kind != "pr":
        return
    cursor = item.closing_cursor
    while item.has_more_closing:
        data = gh_graphql(
            CLOSING_ISSUE_PAGE_QUERY,
            {
                "owner": repo_owner,
                "name": repo_name,
                "number": item.number,
                "cursor": cursor,
            },
        )
        pull = ((data.get("repository") or {}).get("pullRequest")) or {}
        conn = pull.get("closingIssuesReferences") or {}
        item.closing_issues.extend(_parse_closing_issues(conn.get("nodes") or []))
        page = conn.get("pageInfo") or {}
        item.has_more_closing = bool(page.get("hasNextPage"))
        cursor = page.get("endCursor")
        item.closing_cursor = cursor
        if not item.has_more_closing or not cursor:
            break


def backfill_parsed_closing_issues(
    item: Item, repo: str, repo_owner: str, repo_name: str
) -> None:
    """Load same-repo issues named by title/body/commits that GitHub omitted.

    GitHub does not fill closingIssuesReferences from a PR title, from
    Closing/Resolving, or when the PR is not against the default branch.
    """
    if item.kind != "pr":
        return
    parsed = closing_issue_numbers(
        item.title, item.body, *item.commit_messages, repo=repo
    )
    have = {
        int(issue["number"])
        for issue in item.closing_issues
        if issue.get("number") is not None and linked_issue_in_repo(issue, repo)
    }
    for number in parsed:
        if number in have:
            continue
        data = gh_graphql(
            ISSUE_LOOKUP_QUERY,
            {"owner": repo_owner, "name": repo_name, "number": int(number)},
        )
        node = (data.get("repository") or {}).get("issue")
        loaded = _parse_closing_issues([node] if node else [])
        if not loaded:
            continue
        item.closing_issues.extend(loaded)
        have.add(int(number))


def backfill_closing_issue_comments(item: Item, repo: str) -> None:
    """Walk older comments on same-repo linked issues. Foreign repos cannot boost ranking."""
    if item.kind != "pr":
        return
    for issue in item.closing_issues:
        if not linked_issue_in_repo(issue, repo):
            issue["has_older_comments"] = False
            continue
        cursor = issue.get("comment_cursor")
        while issue.get("has_older_comments") and cursor:
            nwo = issue.get("nameWithOwner") or ""
            parts = nwo.split("/")
            number = issue.get("number")
            if len(parts) != 2 or not parts[0] or not parts[1] or number is None:
                issue["has_older_comments"] = False
                break
            data = gh_graphql(
                COMMENT_PAGE_QUERY,
                {
                    "owner": parts[0],
                    "name": parts[1],
                    "number": int(number),
                    "cursor": cursor,
                },
            )
            container = (data.get("repository") or {}).get("issueOrPullRequest") or {}
            comments = container.get("comments") or {}
            issue.setdefault("comment_bodies", []).extend(
                comment.get("body") or ""
                for comment in comments.get("nodes") or []
                if comment
            )
            page = comments.get("pageInfo") or {}
            issue["has_older_comments"] = bool(page.get("hasPreviousPage"))
            cursor = page.get("startCursor")
            issue["comment_cursor"] = cursor


def _backfill_thread_comments(item: Item, thread: dict[str, Any]) -> None:
    comments = thread.get("comments") or {}
    item.activities.extend(_parse_comments(comments.get("nodes") or []))
    page = comments.get("pageInfo") or {}
    cursor = page.get("startCursor")
    thread_id = thread.get("id")
    while page.get("hasPreviousPage") and cursor and thread_id:
        data = gh_graphql(
            REVIEW_THREAD_COMMENT_PAGE_QUERY,
            {"id": thread_id, "cursor": cursor},
        )
        node = data.get("node") or {}
        comments = node.get("comments") or {}
        item.activities.extend(_parse_comments(comments.get("nodes") or []))
        page = comments.get("pageInfo") or {}
        cursor = page.get("startCursor")


def backfill_review_threads(item: Item, repo_owner: str, repo_name: str) -> None:
    """Inline review-thread replies, including author answers on the diff."""
    if item.kind != "pr":
        return
    cursor = None
    while True:
        data = gh_graphql(
            REVIEW_THREAD_PAGE_QUERY,
            {
                "owner": repo_owner,
                "name": repo_name,
                "number": item.number,
                "cursor": cursor,
            },
        )
        pull = ((data.get("repository") or {}).get("pullRequest")) or {}
        conn = pull.get("reviewThreads") or {}
        for thread in conn.get("nodes") or []:
            if thread:
                _backfill_thread_comments(item, thread)
        page = conn.get("pageInfo") or {}
        if not page.get("hasPreviousPage"):
            break
        cursor = page.get("startCursor")
        if not cursor:
            break


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
        nodes.extend(node for node in (conn.get("nodes") or []) if node)
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            break
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

    issues = [
        item
        for item in (item_from_issue(node) for node in issue_nodes)
        if item is not None and not skip_before_classify(item, args.owner)
    ]
    prs = [
        item
        for item in (item_from_pr(node) for node in pr_nodes)
        if item is not None and not skip_before_classify(item, args.owner)
    ]
    for item in issues + prs:
        backfill_comments(item, repo_owner, repo_name)
    for item in prs:
        backfill_closing_issues(item, repo_owner, repo_name)
        backfill_commits(item, repo_owner, repo_name)
        backfill_parsed_closing_issues(item, args.repo, repo_owner, repo_name)
        backfill_closing_issue_comments(item, args.repo)
        backfill_reviews(item, repo_owner, repo_name)
        backfill_review_threads(item, repo_owner, repo_name)

    classified_issues = [
        row
        for row in (
            classify_item(
                item,
                owner=args.owner,
                firstmate_mark=args.firstmate_mark,
                stale_days=args.stale_days,
                now=now,
                repo=args.repo,
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
                repo=args.repo,
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
