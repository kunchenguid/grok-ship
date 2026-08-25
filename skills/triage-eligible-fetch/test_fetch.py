#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "fetch", Path(__file__).with_name("fetch.py")
)
fetch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["fetch"] = fetch
SPEC.loader.exec_module(fetch)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
OWNER = "repo-owner"
REPO = "acme/tools"
MARK = "Speaking as Firstmate"


def activity(when: datetime, kind: str, body: str | None = None, login: str | None = "other") -> fetch.Activity:
    return fetch.Activity(when=when, kind=kind, login=login, body=body)


def issue(**kwargs) -> fetch.Item:
    values = dict(
        number=1,
        title="bug",
        url="https://example.com/i/1",
        created_at=NOW - timedelta(days=2),
        author="contributor",
        body="something broke",
        kind="issue",
    )
    values.update(kwargs)
    return fetch.Item(**values)


def pr(**kwargs) -> fetch.Item:
    values = dict(
        number=10,
        title="fix bug",
        url="https://example.com/p/10",
        created_at=NOW - timedelta(days=2),
        author="contributor",
        body="Fixes #1",
        kind="pr",
    )
    values.update(kwargs)
    return fetch.Item(**values)


def classify(item: fetch.Item, **kwargs) -> fetch.Classified | None:
    params = dict(owner=OWNER, firstmate_mark=MARK, stale_days=14, now=NOW, repo=REPO)
    params.update(kwargs)
    return fetch.classify_item(item, **params)


class StampRegexTests(unittest.TestCase):
    def test_generic_and_prefixed_stamps_count(self) -> None:
        texts = [
            "<!-- triage: 2026-08-21T07:50:20Z outcome=waiting-author -->",
            "<!-- gh-axi-triage: 2026-08-20T11:00:00Z outcome=ready-for-pr -->",
            "<!-- treehouse-triage: 2026-08-19T19:50:00Z outcome=ci-not-green -->",
            "<!--  triage: 2026-08-18T00:00:00Z -->",
        ]
        stamps = fetch.latest_stamp(texts)
        self.assertIsNotNone(stamps)
        assert stamps is not None
        self.assertEqual(stamps[0], datetime(2026, 8, 21, 7, 50, 20, tzinfo=timezone.utc))
        self.assertEqual(stamps[1], "waiting-author")

    def test_colonless_treehouse_stamp_still_counts(self) -> None:
        stamps = fetch.find_stamps(
            "<!-- treehouse-triage 2026-08-19T19:50:00Z outcome=ci-not-green -->"
        )
        self.assertEqual(len(stamps), 1)
        self.assertEqual(stamps[0][1], "ci-not-green")

    def test_prefixed_stamps_are_found_individually(self) -> None:
        gh = fetch.find_stamps("<!-- gh-axi-triage: 2026-08-20T11:00:00Z outcome=ready-for-pr -->")
        th = fetch.find_stamps("<!-- treehouse-triage: 2026-08-19T19:50:00Z outcome=ci-not-green -->")
        self.assertEqual(gh[0][1], "ready-for-pr")
        self.assertEqual(th[0][1], "ci-not-green")


class SkipTests(unittest.TestCase):
    def test_skip_owner_except_last_resort_port(self) -> None:
        self.assertTrue(fetch.skip_owner(OWNER, OWNER, "ordinary body", "ordinary title"))
        self.assertFalse(
            fetch.skip_owner(
                OWNER,
                OWNER,
                "Last-resort port of #128\n\nThe original is still open.",
                "docs: catalog",
            )
        )
        self.assertFalse(fetch.skip_owner("someone-else", OWNER, "body", "title"))

    def test_owner_skip_is_case_insensitive(self) -> None:
        self.assertTrue(fetch.skip_owner("Repo-Owner", OWNER, "body", "title"))

    def test_skip_before_classify_drops_owner_and_automation(self) -> None:
        self.assertTrue(fetch.skip_before_classify(issue(author=OWNER), OWNER))
        self.assertTrue(
            fetch.skip_before_classify(pr(author="dependabot[bot]"), OWNER)
        )
        self.assertFalse(fetch.skip_before_classify(issue(), OWNER))
        self.assertFalse(
            fetch.skip_before_classify(
                pr(
                    author=OWNER,
                    body="Last-resort port of #44\n\nFixes #8",
                    title="port",
                ),
                OWNER,
            )
        )

    def test_automation_skips(self) -> None:
        self.assertTrue(fetch.is_automation("dependabot[bot]"))
        self.assertTrue(fetch.is_automation("github-actions[bot]"))
        self.assertTrue(fetch.is_automation("release-please[bot]"))
        self.assertTrue(fetch.is_automation("renovate[bot]"))
        self.assertTrue(fetch.is_automation("imgbot[bot]"))
        self.assertTrue(fetch.is_automation("app/my-helper"))
        self.assertTrue(fetch.is_automation("greptile-apps[bot]"))
        self.assertTrue(fetch.is_automation("Greptile"))
        self.assertFalse(fetch.is_automation("human-contributor"))
        self.assertFalse(fetch.is_automation(OWNER))

    def test_no_hardcoded_kun_strings(self) -> None:
        source = Path(__file__).with_name("fetch.py").read_text()
        self.assertNotIn("kunchenguid", source.lower())
        self.assertNotIn("kun's firstmate", source.lower())
        self.assertNotIn("kun’s firstmate", source.lower())
        pack_root = Path(__file__).resolve().parents[2]
        pack_files = [
            pack_root / "GROK_BOT_TRIAGE.md",
            pack_root / "TRIAGE.md",
            pack_root / "skills/triage-eligible-fetch/SKILL.md",
            pack_root / "skills/vision-md-triage-verdict/SKILL.md",
            pack_root / "skills/14-day-stale-pr-close/SKILL.md",
        ]
        for path in pack_files:
            text = path.read_text().lower()
            self.assertNotIn("kunchenguid", text, path)
            self.assertNotIn("kun's firstmate", text, path)
        close_skill = pack_root / "skills/14-day-stale-pr-close/SKILL.md"
        self.assertIn("gh pr close <n> --repo <OWNER/NAME> --comment", close_skill.read_text())


class ClockTests(unittest.TestCase):
    def test_unstamped_is_eligible(self) -> None:
        row = classify(issue())
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "unstamped")

    def test_firstmate_comment_does_not_reset_clock(self) -> None:
        stamp_at = NOW - timedelta(days=3)
        body = f"thanks\n<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            issue(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(
                        NOW - timedelta(hours=1),
                        "comment",
                        f"{MARK}: still waiting.",
                        OWNER,
                    ),
                ]
            )
        )
        self.assertIsNone(row)

    def test_quoted_disclosure_is_not_firstmate_chatter(self) -> None:
        self.assertTrue(fetch.is_firstmate_text(f"{MARK}: still waiting.", MARK))
        self.assertFalse(
            fetch.is_firstmate_text(
                f"Got it.\n\n> {MARK}: please push a fix\n\nPushed.",
                MARK,
            )
        )
        stamp_at = NOW - timedelta(days=1)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            issue(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(
                        NOW - timedelta(hours=1),
                        "comment",
                        f"Re: {MARK}: I pushed a fix.",
                        "contributor",
                    ),
                ]
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "live")

    def test_stale_restamp_after_stale_days(self) -> None:
        stamp_at = NOW - timedelta(days=14)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            issue(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(NOW - timedelta(hours=2), "comment", f"{MARK}: ping", OWNER),
                ]
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "stale-restamp")

    def test_later_non_firstmate_comment_makes_live(self) -> None:
        stamp_at = NOW - timedelta(days=1)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            issue(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(NOW - timedelta(hours=1), "comment", "pushed a fix", "contributor"),
                ]
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "live")

    def test_author_push_after_stamp_is_live(self) -> None:
        stamp_at = NOW - timedelta(days=1)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            pr(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(NOW - timedelta(hours=3), "commit", None, "contributor"),
                ]
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "live")

    def test_bot_comment_after_stamp_is_not_live(self) -> None:
        stamp_at = NOW - timedelta(days=3)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            issue(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(
                        NOW - timedelta(hours=1),
                        "comment",
                        "The PR appears safe to merge.",
                        "greptile-apps[bot]",
                    ),
                ]
            )
        )
        self.assertIsNone(row)

    def test_bot_review_after_stamp_is_not_live(self) -> None:
        stamp_at = NOW - timedelta(days=3)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            pr(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(
                        NOW - timedelta(hours=1),
                        "review",
                        "LGTM from CI.",
                        "github-actions[bot]",
                    ),
                ]
            )
        )
        self.assertIsNone(row)

    def test_owner_authored_issue_is_skipped(self) -> None:
        self.assertIsNone(classify(issue(author=OWNER)))

    def test_owner_last_resort_port_is_kept(self) -> None:
        row = classify(
            pr(
                author=OWNER,
                body="Last-resort port of #44\n\nFixes #8",
                title="port",
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "unstamped")

    def test_dependabot_is_skipped(self) -> None:
        self.assertIsNone(classify(pr(author="dependabot[bot]")))

    def test_inline_review_thread_reply_makes_live(self) -> None:
        stamp_at = NOW - timedelta(days=1)
        body = (
            f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
            "outcome=waiting-author -->"
        )
        item = pr(
            activities=[
                activity(stamp_at, "comment", body, OWNER),
            ]
        )
        payload = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "comments": {
                                    "nodes": [
                                        {
                                            "author": {"login": "reviewer"},
                                            "body": "please fix this line",
                                            "createdAt": (
                                                stamp_at - timedelta(hours=2)
                                            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        },
                                        {
                                            "author": {"login": "contributor"},
                                            "body": "fixed on the diff",
                                            "createdAt": (
                                                NOW - timedelta(hours=1)
                                            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        },
                                    ]
                                }
                            }
                        ],
                    }
                }
            }
        }
        from unittest.mock import patch

        with patch.object(fetch, "gh_graphql", return_value=payload) as gql:
            fetch.backfill_review_threads(item, "acme", "tools")
            self.assertEqual(gql.call_args.args[0], fetch.REVIEW_THREAD_PAGE_QUERY)
        self.assertEqual([a.kind for a in item.activities[1:]], ["comment", "comment"])
        self.assertEqual(item.activities[-1].login, "contributor")
        row = classify(item)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "live")

    def test_bot_inline_review_reply_is_not_live(self) -> None:
        stamp_at = NOW - timedelta(days=3)
        body = (
            f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
            "outcome=waiting-author -->"
        )
        item = pr(
            activities=[
                activity(stamp_at, "comment", body, OWNER),
            ]
        )
        payload = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "comments": {
                                    "nodes": [
                                        {
                                            "author": {"login": "greptile-apps[bot]"},
                                            "body": "style nit on this line",
                                            "createdAt": (
                                                NOW - timedelta(hours=1)
                                            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        }
                                    ]
                                }
                            }
                        ],
                    }
                }
            }
        }
        from unittest.mock import patch

        with patch.object(fetch, "gh_graphql", return_value=payload):
            fetch.backfill_review_threads(item, "acme", "tools")
        self.assertIsNone(classify(item))


class RankTests(unittest.TestCase):
    def test_issues_unstamped_newer_then_oldest_stale(self) -> None:
        older = classify(issue(number=1, created_at=NOW - timedelta(days=5), title="old"))
        newer = classify(issue(number=2, created_at=NOW - timedelta(days=1), title="new"))
        stamp_at = NOW - timedelta(days=20)
        stale = classify(
            issue(
                number=3,
                created_at=NOW - timedelta(days=30),
                title="stale",
                activities=[
                    activity(
                        stamp_at,
                        "comment",
                        f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->",
                        OWNER,
                    )
                ],
            )
        )
        ranked = fetch.rank_issues([older, newer, stale], cap=5)  # type: ignore[list-item]
        self.assertEqual([row.item.number for row in ranked], [2, 1, 3])

    def test_issue_cap(self) -> None:
        rows = [
            classify(issue(number=i, created_at=NOW - timedelta(days=10 - i)))
            for i in range(1, 8)
        ]
        ranked = fetch.rank_issues([row for row in rows if row], cap=5)
        self.assertEqual(len(ranked), 5)
        self.assertEqual([row.item.number for row in ranked], [7, 6, 5, 4, 3])

    def test_prs_ready_for_pr_closers_first(self) -> None:
        closer = classify(
            pr(
                number=11,
                created_at=NOW - timedelta(days=5),
                body="Closes #8",
                closing_issues=[
                    {
                        "number": 8,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        other = classify(
            pr(number=12, created_at=NOW - timedelta(days=1), body="tweaks")
        )
        stamp_at = NOW - timedelta(days=21)
        stale = classify(
            pr(
                number=13,
                created_at=NOW - timedelta(days=40),
                body="old",
                activities=[
                    activity(
                        stamp_at,
                        "comment",
                        f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->",
                        OWNER,
                    )
                ],
            )
        )
        ranked = fetch.rank_prs([other, stale, closer], cap=5)  # type: ignore[list-item]
        self.assertEqual([row.item.number for row in ranked], [11, 12, 13])
        self.assertEqual(ranked[0].closes_ready, [8])

    def test_related_to_is_not_a_closing_keyword(self) -> None:
        self.assertEqual(fetch.closing_issue_numbers("Related to #8"), [])
        self.assertEqual(fetch.closing_issue_numbers("Fixes #8"), [8])
        self.assertEqual(fetch.closing_issue_numbers("Closes #2\nResolves #3"), [2, 3])
        self.assertEqual(fetch.closing_issue_numbers("Closes: #8"), [8])
        self.assertEqual(fetch.closing_issue_numbers("Fixes: #9"), [9])
        self.assertEqual(fetch.closing_issue_numbers("Closing #8"), [8])
        self.assertEqual(fetch.closing_issue_numbers("Resolving #9"), [9])
        self.assertEqual(fetch.closing_issue_numbers("Fixes #1, #2"), [1, 2])
        self.assertEqual(fetch.closing_issue_numbers("Fixes #1 and #2"), [1, 2])
        self.assertEqual(fetch.closing_issue_numbers("Fixes #1, #2, and #3"), [1, 2, 3])
        self.assertEqual(
            fetch.closing_issue_numbers("Fixes acme/tools#8", repo=REPO), [8]
        )
        self.assertEqual(
            fetch.closing_issue_numbers(
                "Fixes https://github.com/acme/tools/issues/8", repo=REPO
            ),
            [8],
        )
        self.assertEqual(
            fetch.closing_issue_numbers("Fixes other/repo#8", repo=REPO), []
        )
        self.assertEqual(
            fetch.closing_issue_numbers(
                "Fixes https://github.com/other/repo/issues/8", repo=REPO
            ),
            [],
        )
        self.assertEqual(fetch.closing_issue_numbers("fix: handle the crash"), [])
        self.assertEqual(fetch.closing_issue_numbers("Closing this now."), [])

    def test_bare_fix_word_is_not_a_closer(self) -> None:
        row = classify(
            pr(
                body="Closing this now.",
                closing_issues=[
                    {
                        "number": 8,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [])
        conventional = classify(
            pr(
                body="fix: handle the crash",
                commit_messages=["fix: handle the crash"],
                closing_issues=[
                    {
                        "number": 8,
                        "state": "OPEN",
                        "nameWithOwner": REPO,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(conventional)
        assert conventional is not None
        self.assertEqual(conventional.closes_ready, [])
        self.assertNotEqual(
            fetch.serialize(conventional).get("reason"), "ready-for-pr-closer"
        )

    def test_keyword_with_ref_uses_github_linked_list(self) -> None:
        row = classify(
            pr(
                body="Fixes #1",
                closing_issues=[
                    {
                        "number": 1,
                        "nameWithOwner": REPO,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                    {
                        "number": 2,
                        "nameWithOwner": REPO,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [1, 2])

    def test_commit_message_closing_keyword_counts(self) -> None:
        row = classify(
            pr(
                body="no keywords in the body",
                commit_messages=["Fixes #9"],
                closing_issues=[
                    {
                        "number": 9,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [9])

    def test_fixes_list_keeps_every_ready_issue(self) -> None:
        row = classify(
            pr(
                body="Fixes #1, #2",
                closing_issues=[
                    {
                        "number": 1,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                    {
                        "number": 2,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [1, 2])

    def test_graphql_manual_link_without_keyword_is_not_a_closer(self) -> None:
        row = classify(
            pr(
                body="See #8",
                closing_issues=[
                    {
                        "number": 8,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [])

    def test_ready_for_pr_via_stamp_outcome(self) -> None:
        row = classify(
            pr(
                body="Resolves #9",
                closing_issues=[
                    {
                        "number": 9,
                        "labels": [],
                        "body": "",
                        "comment_bodies": [
                            "<!-- triage: 2026-08-19T23:40:00Z outcome=ready-for-pr -->"
                        ],
                    }
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [9])

    def test_closed_ready_for_pr_issue_is_not_a_closer(self) -> None:
        row = classify(
            pr(
                body="Fixes #8",
                closing_issues=[
                    {
                        "number": 8,
                        "state": "CLOSED",
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [])
        self.assertNotEqual(fetch.serialize(row).get("reason"), "ready-for-pr-closer")

    def test_mixed_open_and_closed_ready_issues(self) -> None:
        row = classify(
            pr(
                body="Fixes #1, #2",
                closing_issues=[
                    {
                        "number": 1,
                        "state": "closed",
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                    {
                        "number": 2,
                        "state": "OPEN",
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [2])

    def test_cross_repo_closing_ref_is_not_local(self) -> None:
        foreign_url = classify(
            pr(
                body="Fixes https://github.com/other/repo/issues/8",
                closing_issues=[
                    {
                        "number": 8,
                        "state": "OPEN",
                        "nameWithOwner": REPO,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(foreign_url)
        assert foreign_url is not None
        self.assertEqual(foreign_url.closes_ready, [])
        shorthand = classify(
            pr(
                body="Fixes other/repo#8",
                closing_issues=[
                    {
                        "number": 8,
                        "state": "OPEN",
                        "nameWithOwner": "other/repo",
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(shorthand)
        assert shorthand is not None
        self.assertEqual(shorthand.closes_ready, [])
        mixed = classify(
            pr(
                body="Fixes #1",
                closing_issues=[
                    {
                        "number": 1,
                        "state": "OPEN",
                        "nameWithOwner": REPO,
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                    {
                        "number": 1,
                        "state": "OPEN",
                        "nameWithOwner": "other/repo",
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    },
                ],
            )
        )
        self.assertIsNotNone(mixed)
        assert mixed is not None
        self.assertEqual(mixed.closes_ready, [1])
        same_repo = classify(
            pr(
                body="Fixes acme/tools#4",
                closing_issues=[
                    {
                        "number": 4,
                        "state": "OPEN",
                        "nameWithOwner": "Acme/Tools",
                        "labels": ["ready-for-pr"],
                        "body": "",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(same_repo)
        assert same_repo is not None
        self.assertEqual(same_repo.closes_ready, [4])

    def test_item_from_pr_keeps_linked_issue_repo(self) -> None:
        item = fetch.item_from_pr(
            {
                "number": 10,
                "title": "fix",
                "url": "https://github.com/acme/tools/pull/10",
                "createdAt": "2026-08-20T00:00:00Z",
                "body": "Fixes #8",
                "author": {"login": "contributor"},
                "comments": {"pageInfo": {}, "nodes": []},
                "reviews": {"nodes": []},
                "commits": {"nodes": []},
                "closingIssuesReferences": {
                    "nodes": [
                        {
                            "number": 8,
                            "title": "bug",
                            "state": "OPEN",
                            "body": "",
                            "repository": {"nameWithOwner": "other/repo"},
                            "labels": {"nodes": [{"name": "ready-for-pr"}]},
                            "comments": {"nodes": []},
                        }
                    ]
                },
            }
        )
        self.assertEqual(item.closing_issues[0]["nameWithOwner"], "other/repo")
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO), [])

    def test_ready_for_pr_stamp_in_issue_body(self) -> None:
        row = classify(
            pr(
                body="Closes: #4",
                closing_issues=[
                    {
                        "number": 4,
                        "labels": [],
                        "body": "<!-- triage: 2026-08-19T23:40:00Z outcome=ready-for-pr -->",
                        "comment_bodies": [],
                    }
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [4])

    def test_pr_cap(self) -> None:
        rows = [
            classify(pr(number=i, created_at=NOW - timedelta(days=10 - i), body="n"))
            for i in range(1, 8)
        ]
        ranked = fetch.rank_prs([row for row in rows if row], cap=5)
        self.assertEqual(len(ranked), 5)


class CliTests(unittest.TestCase):
    def test_repo_and_owner_required(self) -> None:
        parser = fetch.build_parser()
        from contextlib import redirect_stderr
        from io import StringIO

        with self.assertRaises(SystemExit):
            with redirect_stderr(StringIO()):
                parser.parse_args([])
        args = parser.parse_args(
            ["--repo", "acme/tools", "--owner", "acme", "--firstmate-mark", MARK]
        )
        self.assertEqual(args.stale_days, 14)
        self.assertEqual(args.issues, 5)
        self.assertEqual(args.prs, 5)
        help_text = parser.format_help()
        folded = " ".join(help_text.split())
        self.assertIn("personal GitHub login", folded)
        self.assertIn("not the org or repo-owner slug", folded)
        self.assertIn("OWNER/NAME", folded)
        firstmate = Path(__file__).resolve().parents[2] / "GROK_BOT_FIRSTMATE.md"
        charter = firstmate.read_text()
        self.assertIn("captain's personal GitHub login for `--owner`", charter)
        self.assertIn("`--repo` stays OWNER/NAME", charter)
        self.assertIn("Triage wakes stay in chat or cron, not factory.db", charter)
        self.assertIn("do not add kind=triage", charter)
        self.assertIn("do not file it as scout or ship", charter)
        self.assertIn("FM-", charter)
        schema = (Path(__file__).resolve().parents[2] / "skills/project-management/SKILL.md").read_text()
        self.assertIn("`tasks.kind` is `scout`, `ship`, or `decision`. Do not add `triage`.", schema)
        self.assertIn("Do not write a factory.db row for a standing wake or on-demand", schema)
        addendum = (Path(__file__).resolve().parents[2] / "GROK_BOT_TRIAGE.md").read_text()
        self.assertIn("ONLY when Firstmate sends a real factory scout or ship", addendum)
        self.assertIn("NEVER launch a cloud agent for issue fixes", addendum)
        self.assertIn("FM-", addendum)

    def test_parse_repo(self) -> None:
        self.assertEqual(fetch.parse_repo("acme/tools"), ("acme", "tools"))
        with self.assertRaises(Exception):
            fetch.parse_repo("tools")

    def test_comment_page_query_matches_first_page_order(self) -> None:
        self.assertIn(
            "orderBy: {field: UPDATED_AT, direction: ASC}",
            fetch.ISSUE_LIST_QUERY,
        )
        self.assertIn(
            "orderBy: {field: UPDATED_AT, direction: ASC}",
            fetch.COMMENT_PAGE_QUERY,
        )
        self.assertIn("before: $cursor, orderBy:", fetch.COMMENT_PAGE_QUERY)
        self.assertIn("number title state body", fetch.PR_LIST_QUERY)
        self.assertIn("repository { nameWithOwner }", fetch.PR_LIST_QUERY)
        self.assertIn("message", fetch.PR_LIST_QUERY)
        self.assertIn("reviewThreads(last: 40, before: $cursor)", fetch.REVIEW_THREAD_PAGE_QUERY)
        self.assertIn("comments(last: 30)", fetch.REVIEW_THREAD_PAGE_QUERY)

    def test_null_repository_exits_nonzero(self) -> None:
        from unittest.mock import patch

        with patch.object(
            fetch, "gh_graphql", return_value={"repository": None}
        ):
            with self.assertRaises(SystemExit) as ctx:
                fetch.paginate_nodes(
                    fetch.ISSUE_LIST_QUERY, "nope", "missing", "issues"
                )
        self.assertIn("not found", str(ctx.exception).lower())
        self.assertIn("nope/missing", str(ctx.exception))

    def test_main_skips_comment_backfill_for_owner_and_bots(self) -> None:
        from io import StringIO
        from unittest.mock import patch

        owner_issue = {
            "number": 1,
            "title": "captain work",
            "url": "https://example.com/i/1",
            "createdAt": "2026-08-20T00:00:00Z",
            "body": "mine",
            "author": {"login": OWNER},
            "labels": {"nodes": []},
            "comments": {
                "pageInfo": {"hasPreviousPage": True, "startCursor": "c1"},
                "nodes": [],
            },
        }
        contributor_issue = {
            "number": 2,
            "title": "bug",
            "url": "https://example.com/i/2",
            "createdAt": "2026-08-21T00:00:00Z",
            "body": "broke",
            "author": {"login": "contributor"},
            "labels": {"nodes": []},
            "comments": {
                "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                "nodes": [],
            },
        }
        bot_pr = {
            "number": 3,
            "title": "deps",
            "url": "https://example.com/p/3",
            "createdAt": "2026-08-22T00:00:00Z",
            "body": "chore",
            "author": {"login": "dependabot[bot]"},
            "comments": {
                "pageInfo": {"hasPreviousPage": True, "startCursor": "c3"},
                "nodes": [],
            },
            "reviews": {"nodes": []},
            "commits": {"nodes": []},
            "closingIssuesReferences": {"nodes": []},
        }
        last_resort = {
            "number": 4,
            "title": "port",
            "url": "https://example.com/p/4",
            "createdAt": "2026-08-23T00:00:00Z",
            "body": "Last-resort port of #44",
            "author": {"login": OWNER},
            "comments": {
                "pageInfo": {"hasPreviousPage": False, "startCursor": None},
                "nodes": [],
            },
            "reviews": {"nodes": []},
            "commits": {"nodes": []},
            "closingIssuesReferences": {"nodes": []},
        }

        def paginate(_query, _owner, _name, field):
            if field == "issues":
                return [owner_issue, contributor_issue]
            return [bot_pr, last_resort]

        backfilled: list[int] = []
        review_backfilled: list[int] = []

        def fake_comments(item, *_args):
            backfilled.append(item.number)

        def fake_reviews(item, *_args):
            review_backfilled.append(item.number)

        stdout = StringIO()
        with (
            patch.object(fetch, "paginate_nodes", side_effect=paginate),
            patch.object(fetch, "backfill_comments", side_effect=fake_comments),
            patch.object(fetch, "backfill_review_threads", side_effect=fake_reviews),
            patch.object(sys, "stdout", stdout),
        ):
            rc = fetch.main(
                [
                    "--repo",
                    "acme/tools",
                    "--owner",
                    OWNER,
                    "--firstmate-mark",
                    MARK,
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(backfilled, [2, 4])
        self.assertEqual(review_backfilled, [4])
        payload = json.loads(stdout.getvalue())
        self.assertEqual([row["number"] for row in payload["issues"]], [2])
        self.assertEqual([row["number"] for row in payload["prs"]], [4])

    def test_empty_repository_is_not_an_error(self) -> None:
        from unittest.mock import patch

        with patch.object(
            fetch,
            "gh_graphql",
            return_value={
                "repository": {
                    "issues": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            },
        ):
            self.assertEqual(
                fetch.paginate_nodes(
                    fetch.ISSUE_LIST_QUERY, "acme", "tools", "issues"
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
