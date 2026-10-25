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


def activity(when: datetime, kind: str, body: str | None = None, login: str | None = "other", typename: str | None = None) -> fetch.Activity:
    return fetch.Activity(when=when, kind=kind, login=login, body=body, typename=typename)


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


def closing_issue(number: int, **kwargs) -> dict:
    values: dict = {
        "number": number,
        "labels": ["ready-for-pr"],
        "body": "",
        "comment_bodies": [],
        "nameWithOwner": REPO,
        "state": "OPEN",
    }
    values.update(kwargs)
    return values


def pr_graphql(**kwargs) -> dict:
    values: dict = {
        "number": 10,
        "title": "fix",
        "url": "https://github.com/acme/tools/pull/10",
        "createdAt": "2026-08-20T00:00:00Z",
        "body": "Fixes #8",
        "author": {"login": "contributor"},
        "comments": {"pageInfo": {}, "nodes": []},
        "reviews": {"nodes": []},
        "commits": {"nodes": []},
        "closingIssuesReferences": {"nodes": []},
    }
    values.update(kwargs)
    return values


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
        self.assertFalse(fetch.is_automation("codecov"))
        self.assertFalse(fetch.is_automation("vercel"))
        self.assertTrue(fetch.is_automation("codecov", "Bot"))
        self.assertTrue(fetch.is_automation("vercel", "Bot"))
        self.assertFalse(fetch.is_automation("codecov", "User"))

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

    def test_graphql_bot_comment_after_stamp_is_not_live(self) -> None:
        stamp_at = NOW - timedelta(days=3)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            issue(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(
                        NOW - timedelta(hours=1),
                        "comment",
                        "Coverage after this change.",
                        "codecov",
                        "Bot",
                    ),
                ]
            )
        )
        self.assertIsNone(row)

    def test_graphql_bot_review_after_stamp_is_not_live(self) -> None:
        stamp_at = NOW - timedelta(days=3)
        body = f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} outcome=waiting-author -->"
        row = classify(
            pr(
                activities=[
                    activity(stamp_at, "comment", body, OWNER),
                    activity(
                        NOW - timedelta(hours=1),
                        "review",
                        "Ready to deploy.",
                        "vercel",
                        "Bot",
                    ),
                ]
            )
        )
        self.assertIsNone(row)

    def test_future_stamp_is_ignored(self) -> None:
        future = "<!-- triage: 2099-01-01T00:00:00Z outcome=waiting-author -->"
        self.assertEqual(fetch.find_stamps(future, now=NOW), [])
        row = classify(issue(body=future))
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "unstamped")
        stamp_at = NOW - timedelta(days=20)
        real = (
            f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
            "outcome=waiting-author -->"
        )
        stale = classify(issue(body=future + "\n" + real))
        self.assertIsNotNone(stale)
        assert stale is not None
        self.assertEqual(stale.bucket, "stale-restamp")
        self.assertEqual(stale.stamp_at, stamp_at)

    def test_older_author_review_makes_live(self) -> None:
        stamp_at = NOW - timedelta(days=1)
        stamp = (
            f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
            "outcome=waiting-author -->"
        )
        item = fetch.item_from_pr(
            pr_graphql(
                body="",
                comments={
                    "pageInfo": {},
                    "nodes": [
                        {
                            "author": {"login": OWNER},
                            "body": stamp,
                            "createdAt": stamp_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        }
                    ],
                },
                reviews={
                    "pageInfo": {"hasPreviousPage": True, "startCursor": "r1"},
                    "nodes": [
                        {
                            "author": {"login": "github-actions[bot]"},
                            "body": "LGTM from CI.",
                            "createdAt": (NOW - timedelta(minutes=5)).strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                        }
                    ],
                },
            )
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertIsNone(classify(item))
        older = {
            "repository": {
                "pullRequest": {
                    "reviews": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "author": {"login": "contributor"},
                                "body": "addressed the nits",
                                "createdAt": (NOW - timedelta(hours=1)).strftime(
                                    "%Y-%m-%dT%H:%M:%SZ"
                                ),
                            }
                        ],
                    }
                }
            }
        }
        from unittest.mock import patch

        with patch.object(fetch, "gh_graphql", return_value=older) as gql:
            fetch.backfill_reviews(item, "acme", "tools")
            self.assertEqual(gql.call_args.args[0], fetch.REVIEW_PAGE_QUERY)
        row = classify(item)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "live")

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

    def test_paginated_thread_comments_count_author_reply(self) -> None:
        stamp_at = NOW - timedelta(days=1)
        body = (
            f"<!-- triage: {stamp_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
            "outcome=waiting-author -->"
        )
        item = pr(activities=[activity(stamp_at, "comment", body, OWNER)])

        def gh(query: str, variables: dict) -> dict:
            if query == fetch.REVIEW_THREAD_PAGE_QUERY:
                return {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "pageInfo": {"hasPreviousPage": False},
                                "nodes": [
                                    {
                                        "id": "thread1",
                                        "comments": {
                                            "pageInfo": {
                                                "hasPreviousPage": True,
                                                "startCursor": "old",
                                            },
                                            "nodes": [
                                                {
                                                    "author": {
                                                        "login": "greptile-apps[bot]"
                                                    },
                                                    "body": "style nit",
                                                    "createdAt": (
                                                        NOW - timedelta(minutes=10)
                                                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                }
                                            ],
                                        },
                                    }
                                ],
                            }
                        }
                    }
                }
            self.assertEqual(query, fetch.REVIEW_THREAD_COMMENT_PAGE_QUERY)
            self.assertEqual(variables["id"], "thread1")
            return {
                "node": {
                    "comments": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "author": {"login": "contributor"},
                                "body": "fixed on the diff",
                                "createdAt": (NOW - timedelta(hours=1)).strftime(
                                    "%Y-%m-%dT%H:%M:%SZ"
                                ),
                            }
                        ],
                    }
                }
            }

        from unittest.mock import patch

        with patch.object(fetch, "gh_graphql", side_effect=gh):
            fetch.backfill_review_threads(item, "acme", "tools")
        logins = [act.login for act in item.activities[1:]]
        self.assertIn("contributor", logins)
        row = classify(item)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.bucket, "live")


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
                closing_issues=[closing_issue(8)],
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
                closing_issues=[closing_issue(8)],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [])
        conventional = classify(
            pr(
                body="fix: handle the crash",
                commit_messages=["fix: handle the crash"],
                closing_issues=[closing_issue(8)],
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
                closing_issues=[closing_issue(1), closing_issue(2)],
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
                closing_issues=[closing_issue(9)],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [9])

    def test_title_only_closing_keyword_counts(self) -> None:
        row = classify(
            pr(
                title="Fixes #8",
                body="no keywords in the body",
                closing_issues=[closing_issue(8)],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [8])
        ranked = fetch.rank_prs(
            [
                classify(pr(number=12, created_at=NOW - timedelta(days=1), body="tweaks")),
                row,
            ],
            cap=5,
        )
        self.assertEqual([item.item.number for item in ranked], [10, 12])
        self.assertEqual(ranked[0].closes_ready, [8])
        bare_title = classify(
            pr(
                title="fix: handle the crash",
                body="no keywords in the body",
                closing_issues=[closing_issue(8)],
            )
        )
        self.assertIsNotNone(bare_title)
        assert bare_title is not None
        self.assertEqual(bare_title.closes_ready, [])
        cross = classify(
            pr(
                title="Fixes other/repo#8",
                body="",
                closing_issues=[closing_issue(8, nameWithOwner="other/repo")],
            )
        )
        self.assertIsNotNone(cross)
        assert cross is not None
        self.assertEqual(cross.closes_ready, [])

    def test_omitted_github_closing_list_still_loads_parsed_issue(self) -> None:
        from unittest.mock import patch

        item = pr(
            title="Fixes #8",
            body="no keywords in the body",
            closing_issues=[],
        )
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO, now=NOW), [])
        payload = {
            "repository": {
                "issue": {
                    "number": 8,
                    "title": "bug",
                    "state": "OPEN",
                    "body": (
                        "<!-- triage: 2026-08-19T23:40:00Z "
                        "outcome=ready-for-pr -->"
                    ),
                    "repository": {"nameWithOwner": REPO},
                    "labels": {"nodes": []},
                    "comments": {"pageInfo": {}, "nodes": []},
                }
            }
        }
        with patch.object(fetch, "gh_graphql", return_value=payload) as gql:
            fetch.backfill_parsed_closing_issues(item, REPO, "acme", "tools")
            self.assertEqual(gql.call_args.args[0], fetch.ISSUE_LOOKUP_QUERY)
            self.assertEqual(
                gql.call_args.args[1],
                {"owner": "acme", "name": "tools", "number": 8},
            )
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO, now=NOW), [8])
        foreign_same_number = pr(
            title="Fixes #8",
            body="",
            closing_issues=[closing_issue(8, nameWithOwner="other/repo")],
        )
        with patch.object(fetch, "gh_graphql", return_value=payload) as gql:
            fetch.backfill_parsed_closing_issues(
                foreign_same_number, REPO, "acme", "tools"
            )
            gql.assert_called_once()
        self.assertEqual(
            fetch.ready_for_pr_closers(foreign_same_number, REPO, now=NOW), [8]
        )
        closing = pr(
            title="fix bug",
            body="Closing #9",
            closing_issues=[],
        )
        closing_payload = {
            "repository": {
                "issue": {
                    "number": 9,
                    "title": "bug",
                    "state": "OPEN",
                    "body": "",
                    "repository": {"nameWithOwner": REPO},
                    "labels": {"nodes": [{"name": "ready-for-pr"}]},
                    "comments": {"nodes": []},
                }
            }
        }
        with patch.object(fetch, "gh_graphql", return_value=closing_payload):
            fetch.backfill_parsed_closing_issues(closing, REPO, "acme", "tools")
        self.assertEqual(fetch.ready_for_pr_closers(closing, REPO, now=NOW), [9])

    def test_parsed_lookup_skips_numbers_already_in_same_repo_list(self) -> None:
        from unittest.mock import patch

        item = pr(
            title="Fixes #8",
            body="",
            closing_issues=[closing_issue(8)],
        )
        with patch.object(fetch, "gh_graphql") as gql:
            fetch.backfill_parsed_closing_issues(item, REPO, "acme", "tools")
            gql.assert_not_called()
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO, now=NOW), [8])

    def test_parsed_lookup_skips_null_or_closed_issue(self) -> None:
        from unittest.mock import patch

        missing = pr(title="Fixes #8", body="", closing_issues=[])
        with patch.object(
            fetch, "gh_graphql", return_value={"repository": {"issue": None}}
        ):
            fetch.backfill_parsed_closing_issues(missing, REPO, "acme", "tools")
        self.assertEqual(missing.closing_issues, [])
        self.assertEqual(fetch.ready_for_pr_closers(missing, REPO, now=NOW), [])
        closed = pr(title="Fixes #8", body="", closing_issues=[])
        with patch.object(
            fetch,
            "gh_graphql",
            return_value={
                "repository": {
                    "issue": {
                        "number": 8,
                        "title": "bug",
                        "state": "CLOSED",
                        "body": "",
                        "repository": {"nameWithOwner": REPO},
                        "labels": {"nodes": [{"name": "ready-for-pr"}]},
                        "comments": {"nodes": []},
                    }
                }
            },
        ):
            fetch.backfill_parsed_closing_issues(closed, REPO, "acme", "tools")
        self.assertEqual(closed.closing_issues[0]["state"], "CLOSED")
        self.assertEqual(fetch.ready_for_pr_closers(closed, REPO, now=NOW), [])

    def test_fixes_list_keeps_every_ready_issue(self) -> None:
        row = classify(
            pr(
                body="Fixes #1, #2",
                closing_issues=[closing_issue(1), closing_issue(2)],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [1, 2])

    def test_graphql_manual_link_without_keyword_is_not_a_closer(self) -> None:
        row = classify(
            pr(
                body="See #8",
                closing_issues=[closing_issue(8)],
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
                    closing_issue(
                        9,
                        labels=[],
                        comment_bodies=[
                            "<!-- triage: 2026-08-19T23:40:00Z outcome=ready-for-pr -->"
                        ],
                    )
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
                closing_issues=[closing_issue(8, state="CLOSED")],
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
                    closing_issue(1, state="closed"),
                    closing_issue(2),
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
                closing_issues=[closing_issue(8)],
            )
        )
        self.assertIsNotNone(foreign_url)
        assert foreign_url is not None
        self.assertEqual(foreign_url.closes_ready, [])
        shorthand = classify(
            pr(
                body="Fixes other/repo#8",
                closing_issues=[closing_issue(8, nameWithOwner="other/repo")],
            )
        )
        self.assertIsNotNone(shorthand)
        assert shorthand is not None
        self.assertEqual(shorthand.closes_ready, [])
        mixed = classify(
            pr(
                body="Fixes #1",
                closing_issues=[
                    closing_issue(1),
                    closing_issue(1, nameWithOwner="other/repo"),
                ],
            )
        )
        self.assertIsNotNone(mixed)
        assert mixed is not None
        self.assertEqual(mixed.closes_ready, [1])
        same_repo = classify(
            pr(
                body="Fixes acme/tools#4",
                closing_issues=[closing_issue(4, nameWithOwner="Acme/Tools")],
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

    def test_missing_name_with_owner_is_not_local(self) -> None:
        self.assertFalse(fetch.linked_issue_in_repo({"number": 8}, REPO))
        self.assertFalse(fetch.linked_issue_in_repo({"number": 8, "nameWithOwner": ""}, REPO))
        row = classify(
            pr(body="Fixes #8", closing_issues=[closing_issue(8, nameWithOwner="")])
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [])

    def test_null_repository_closing_issue_is_not_local(self) -> None:
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
                            "repository": None,
                            "labels": {"nodes": [{"name": "ready-for-pr"}]},
                            "comments": {"nodes": []},
                        }
                    ]
                },
            }
        )
        self.assertEqual(item.closing_issues[0]["nameWithOwner"], "")
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO), [])

    def test_backfill_closing_issues_walks_pages(self) -> None:
        from unittest.mock import patch

        item = fetch.item_from_pr(
            {
                "number": 10,
                "title": "fix",
                "url": "https://github.com/acme/tools/pull/10",
                "createdAt": "2026-08-20T00:00:00Z",
                "body": "Fixes #1",
                "author": {"login": "contributor"},
                "comments": {"pageInfo": {}, "nodes": []},
                "reviews": {"nodes": []},
                "commits": {"nodes": []},
                "closingIssuesReferences": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                    "nodes": [
                        {
                            "number": 1,
                            "title": "one",
                            "state": "OPEN",
                            "body": "",
                            "repository": {"nameWithOwner": REPO},
                            "labels": {"nodes": [{"name": "ready-for-pr"}]},
                            "comments": {"nodes": []},
                        }
                    ],
                },
            }
        )
        page2 = {
            "repository": {
                "pullRequest": {
                    "closingIssuesReferences": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [
                            {
                                "number": 2,
                                "title": "two",
                                "state": "OPEN",
                                "body": "",
                                "repository": {"nameWithOwner": REPO},
                                "labels": {"nodes": [{"name": "ready-for-pr"}]},
                                "comments": {"nodes": []},
                            }
                        ],
                    }
                }
            }
        }
        with patch.object(fetch, "gh_graphql", return_value=page2) as gql:
            fetch.backfill_closing_issues(item, "acme", "tools")
            self.assertEqual(gql.call_args.args[0], fetch.CLOSING_ISSUE_PAGE_QUERY)
        self.assertEqual([issue["number"] for issue in item.closing_issues], [1, 2])
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO), [1, 2])

    def test_older_commit_closing_ref_is_a_closer(self) -> None:
        from unittest.mock import patch

        item = fetch.item_from_pr(
            pr_graphql(
                body="no keywords in the body",
                commits={
                    "pageInfo": {"hasPreviousPage": True, "startCursor": "c1"},
                    "nodes": [
                        {
                            "commit": {
                                "message": "tweak ci",
                                "committedDate": "2026-08-24T00:00:00Z",
                                "authors": {
                                    "nodes": [{"user": {"login": "contributor"}}]
                                },
                            }
                        }
                    ],
                },
                closingIssuesReferences={
                    "nodes": [
                        {
                            "number": 9,
                            "title": "bug",
                            "state": "OPEN",
                            "body": "",
                            "repository": {"nameWithOwner": REPO},
                            "labels": {"nodes": [{"name": "ready-for-pr"}]},
                            "comments": {"nodes": []},
                        }
                    ]
                },
            )
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO), [])
        older = {
            "repository": {
                "pullRequest": {
                    "commits": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "commit": {
                                    "message": "Fixes #9",
                                    "committedDate": "2026-08-20T00:00:00Z",
                                    "authors": {
                                        "nodes": [{"user": {"login": "contributor"}}]
                                    },
                                }
                            }
                        ],
                    }
                }
            }
        }
        with patch.object(fetch, "gh_graphql", return_value=older) as gql:
            fetch.backfill_commits(item, "acme", "tools")
            self.assertEqual(gql.call_args.args[0], fetch.COMMIT_PAGE_QUERY)
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO), [9])

    def test_backfill_loads_when_list_query_omits_nested_connections(self) -> None:
        from unittest.mock import patch

        item = fetch.item_from_pr(
            {
                "number": 10,
                "title": "fix",
                "url": "https://github.com/acme/tools/pull/10",
                "createdAt": "2026-08-20T00:00:00Z",
                "body": "Fixes #9",
                "author": {"login": "contributor", "__typename": "User"},
                "comments": {"pageInfo": {}, "nodes": []},
            }
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertTrue(item.has_older_reviews)
        self.assertTrue(item.has_older_commits)
        self.assertTrue(item.has_more_closing)
        self.assertEqual(item.author_typename, "User")
        review_page = {
            "repository": {
                "pullRequest": {
                    "reviews": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "author": {"login": "codecov", "__typename": "Bot"},
                                "body": "coverage",
                                "createdAt": "2026-08-24T12:00:00Z",
                            }
                        ],
                    }
                }
            }
        }
        commit_page = {
            "repository": {
                "pullRequest": {
                    "commits": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "commit": {
                                    "message": "Fixes #9",
                                    "committedDate": "2026-08-20T00:00:00Z",
                                    "authors": {
                                        "nodes": [{"user": {"login": "contributor"}}]
                                    },
                                }
                            }
                        ],
                    }
                }
            }
        }
        closing_page = {
            "repository": {
                "pullRequest": {
                    "closingIssuesReferences": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [
                            {
                                "number": 9,
                                "title": "bug",
                                "state": "OPEN",
                                "body": "",
                                "repository": {"nameWithOwner": REPO},
                                "labels": {"nodes": [{"name": "ready-for-pr"}]},
                                "comments": {"nodes": []},
                            }
                        ],
                    }
                }
            }
        }
        with patch.object(fetch, "gh_graphql", return_value=review_page):
            fetch.backfill_reviews(item, "acme", "tools")
        self.assertEqual(item.activities[-1].login, "codecov")
        self.assertEqual(item.activities[-1].typename, "Bot")
        self.assertTrue(fetch.is_clock_noise(item.activities[-1], MARK))
        with patch.object(fetch, "gh_graphql", return_value=commit_page):
            fetch.backfill_commits(item, "acme", "tools")
        with patch.object(fetch, "gh_graphql", return_value=closing_page):
            fetch.backfill_closing_issues(item, "acme", "tools")
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO), [9])

    def test_future_ready_for_pr_stamp_does_not_boost_closer(self) -> None:
        future = "<!-- triage: 2099-01-01T00:00:00Z outcome=ready-for-pr -->"
        self.assertFalse(fetch.has_ready_for_pr([], [future], now=NOW))
        row = classify(
            pr(
                body="Fixes #4",
                closing_issues=[closing_issue(4, labels=[], body=future)],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [])

    def test_future_stamp_does_not_hide_ready_for_pr_closer(self) -> None:
        real = "<!-- triage: 2026-08-19T23:40:00Z outcome=ready-for-pr -->"
        future = "<!-- triage: 2099-01-01T00:00:00Z outcome=waiting-author -->"
        self.assertTrue(fetch.has_ready_for_pr([], [real, future], now=NOW))
        row = classify(
            pr(
                body="Fixes #4",
                closing_issues=[
                    closing_issue(4, labels=[], body=real + "\n" + future)
                ],
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.closes_ready, [4])

    def test_older_closing_issue_comment_stamp_is_a_closer(self) -> None:
        from unittest.mock import patch

        item = fetch.item_from_pr(
            pr_graphql(
                body="Fixes #9",
                closingIssuesReferences={
                    "nodes": [
                        {
                            "number": 9,
                            "title": "bug",
                            "state": "OPEN",
                            "body": "",
                            "repository": {"nameWithOwner": REPO},
                            "labels": {"nodes": []},
                            "comments": {
                                "pageInfo": {
                                    "hasPreviousPage": True,
                                    "startCursor": "c1",
                                },
                                "nodes": [
                                    {
                                        "body": "no stamp here",
                                        "createdAt": "2026-08-24T00:00:00Z",
                                    }
                                ],
                            },
                        }
                    ]
                },
            )
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO, now=NOW), [])
        older = {
            "repository": {
                "issueOrPullRequest": {
                    "comments": {
                        "pageInfo": {"hasPreviousPage": False},
                        "nodes": [
                            {
                                "author": {"login": "contributor"},
                                "body": (
                                    "<!-- triage: 2026-08-19T23:40:00Z "
                                    "outcome=ready-for-pr -->"
                                ),
                                "createdAt": "2026-08-19T23:40:00Z",
                            }
                        ],
                    }
                }
            }
        }
        with patch.object(fetch, "gh_graphql", return_value=older) as gql:
            fetch.backfill_closing_issue_comments(item, REPO)
            self.assertEqual(gql.call_args.args[0], fetch.COMMENT_PAGE_QUERY)
            self.assertEqual(
                gql.call_args.args[1],
                {
                    "owner": "acme",
                    "name": "tools",
                    "number": 9,
                    "cursor": "c1",
                },
            )
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO, now=NOW), [9])

    def test_ready_for_pr_stamp_in_issue_body(self) -> None:
        row = classify(
            pr(
                body="Closes: #4",
                closing_issues=[
                    closing_issue(
                        4,
                        labels=[],
                        body="<!-- triage: 2026-08-19T23:40:00Z outcome=ready-for-pr -->",
                    )
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
        self.assertIn("Cannot-tell / inconclusive / undecided blocks auto-merge", addendum)
        self.assertIn("Do not ignore some undecided rules", addendum)
        self.assertIn("restore | new-default | opt-in | cannot-tell", addendum)
        self.assertIn("Write this next to the VISION per-rule verdict", addendum)
        self.assertIn("not new-default", addendum)
        self.assertIn(
            "the new behavior stays off unless the user turns it on", addendum
        )
        self.assertIn(
            "Changing a default-on setting, or shipping a new default-on config, is new-default",
            addendum,
        )
        self.assertNotIn("behind a flag or config", addendum)
        triage = Path(__file__).resolve().parents[2] / "TRIAGE.md"
        triage_text = triage.read_text()
        self.assertIn("Cannot-tell blocks auto-merge", triage_text)
        self.assertIn("Do not ignore some undecided rules", triage_text)
        self.assertNotIn("undecided rule that matters", triage_text)
        self.assertIn("restore | new-default | opt-in | cannot-tell", triage_text)
        self.assertIn("not a replacement of Classes", triage_text)
        self.assertIn("not new-default", triage_text)
        self.assertIn(
            "the new behavior stays off unless the user turns it on", triage_text
        )
        self.assertIn(
            "Changing a default-on setting, or shipping a new default-on config, is new-default",
            triage_text,
        )
        self.assertNotIn("behind a flag or config", triage_text)
        vision = (
            Path(__file__).resolve().parents[2]
            / "skills/vision-md-triage-verdict/SKILL.md"
        ).read_text()
        self.assertIn("Cannot-tell blocks auto-merge", vision)
        self.assertIn("Do not ignore some undecided rules", vision)
        self.assertIn("do not auto-merge", vision)
        self.assertIn("restore | new-default | opt-in | cannot-tell", vision)
        self.assertIn("Write this next to the VISION per-rule verdict", vision)
        self.assertIn("Do not special-case a repository", vision)
        self.assertIn(
            "the new behavior stays off unless the user turns it on", vision
        )
        self.assertIn(
            "Changing a default-on setting, or shipping a new default-on config, is new-default",
            vision,
        )
        self.assertNotIn("behind a flag or config", vision)
        readme = Path(__file__).resolve().parents[2] / "README.md"
        readme_text = readme.read_text()
        self.assertIn("factory ships never merge without your word", readme_text)
        self.assertIn("wired triage crewmate may auto-merge", readme_text)
        self.assertIn("corrective or opt-in", readme_text)
        self.assertIn("no cannot-tell", readme_text)
        self.assertIn("not default-behavior", readme_text)
        self.assertIn("not security", readme_text)
        self.assertIn("not new-default", readme_text)
        self.assertIn("May auto-merge only when all of these hold", triage_text)
        self.assertIn(
            "Factory ships never merge without the captain's explicit word",
            charter,
        )
        self.assertIn("wired triage crewmate may auto-merge", charter)
        self.assertIn("no cannot-tell", charter)
        self.assertIn("not new-default", charter)
        ship = (Path(__file__).resolve().parents[2] / "GROK_SHIP.md").read_text()
        self.assertIn("Factory ships never merge without the captain's word", ship)
        self.assertIn("wired triage crewmate may auto-merge", ship)
        self.assertIn("no cannot-tell", ship)
        self.assertIn("not new-default", ship)

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
        self.assertNotIn("reviews(", fetch.PR_LIST_QUERY)
        self.assertNotIn("commits(", fetch.PR_LIST_QUERY)
        self.assertNotIn("closingIssuesReferences", fetch.PR_LIST_QUERY)
        self.assertIn("author { login __typename }", fetch.PR_LIST_QUERY)
        self.assertIn("author { login __typename }", fetch.ISSUE_LIST_QUERY)
        self.assertIn("author { login __typename }", fetch.REVIEW_PAGE_QUERY)
        self.assertIn("author { login __typename }", fetch.COMMENT_PAGE_QUERY)
        self.assertIn("number title state body", fetch.CLOSING_ISSUE_PAGE_QUERY)
        self.assertIn("repository { nameWithOwner }", fetch.CLOSING_ISSUE_PAGE_QUERY)
        self.assertIn(
            "closingIssuesReferences(first: 50, after: $cursor, excludeUserLinked: true)",
            fetch.CLOSING_ISSUE_PAGE_QUERY,
        )
        self.assertIn("excludeUserLinked: true", fetch.CLOSING_ISSUE_PAGE_QUERY)
        self.assertIn(
            "comments(last: 50, orderBy: {field: UPDATED_AT, direction: ASC})",
            fetch.CLOSING_ISSUE_PAGE_QUERY,
        )
        self.assertIn("hasPreviousPage startCursor", fetch.CLOSING_ISSUE_PAGE_QUERY)
        self.assertIn("issue(number: $number)", fetch.ISSUE_LOOKUP_QUERY)
        self.assertIn("number title state body", fetch.ISSUE_LOOKUP_QUERY)
        self.assertIn("repository { nameWithOwner }", fetch.ISSUE_LOOKUP_QUERY)
        self.assertIn("message", fetch.COMMIT_PAGE_QUERY)
        self.assertIn("reviews(last: 100, before: $cursor)", fetch.REVIEW_PAGE_QUERY)
        self.assertIn("commits(last: 100, before: $cursor)", fetch.COMMIT_PAGE_QUERY)
        self.assertIn("reviewThreads(last: 40, before: $cursor)", fetch.REVIEW_THREAD_PAGE_QUERY)
        self.assertIn("comments(last: 100)", fetch.REVIEW_THREAD_PAGE_QUERY)
        self.assertIn("hasPreviousPage startCursor", fetch.REVIEW_THREAD_PAGE_QUERY)
        self.assertIn(
            "comments(last: 100, before: $cursor)",
            fetch.REVIEW_THREAD_COMMENT_PAGE_QUERY,
        )

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

    def test_graphql_partial_data_with_errors_is_usable(self) -> None:
        import subprocess
        from unittest.mock import patch

        payload = {
            "data": {
                "repository": {
                    "issues": {
                        "nodes": [
                            None,
                            {
                                "number": 2,
                                "title": "bug",
                                "url": "https://example.com/i/2",
                                "createdAt": "2026-08-21T00:00:00Z",
                                "body": "broke",
                                "author": {"login": "contributor"},
                                "labels": {"nodes": []},
                                "comments": {"pageInfo": {}, "nodes": []},
                            },
                        ],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            },
            "errors": [
                {
                    "type": "NOT_FOUND",
                    "path": ["repository", "issues", "nodes", 0],
                    "message": "Could not resolve to an Issue with the number of 1.",
                }
            ],
        }
        err = subprocess.CalledProcessError(
            1,
            ["gh", "api", "graphql"],
            output=json.dumps(payload),
            stderr="gh: GraphQL: Not Found (repository.issues.nodes.0)",
        )
        with patch.object(fetch.subprocess, "run", side_effect=err):
            nodes = fetch.paginate_nodes(
                fetch.ISSUE_LIST_QUERY, "acme", "tools", "issues"
            )
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["number"], 2)

    def test_graphql_errors_with_null_target_repo_still_fail(self) -> None:
        import subprocess
        from unittest.mock import patch

        payload = {
            "data": {"repository": None},
            "errors": [
                {
                    "type": "NOT_FOUND",
                    "path": ["repository"],
                    "message": "Could not resolve to a Repository",
                }
            ],
        }
        err = subprocess.CalledProcessError(
            1,
            ["gh", "api", "graphql"],
            output=json.dumps(payload),
            stderr="gh: GraphQL: Could not resolve to a Repository (repository)",
        )
        with patch.object(fetch.subprocess, "run", side_effect=err):
            with self.assertRaises(SystemExit) as ctx:
                fetch.paginate_nodes(
                    fetch.ISSUE_LIST_QUERY, "nope", "missing", "issues"
                )
        self.assertIn("not found", str(ctx.exception).lower())
        self.assertIn("nope/missing", str(ctx.exception))

    def test_graphql_errors_without_data_still_fail(self) -> None:
        import subprocess
        from unittest.mock import patch

        err = subprocess.CalledProcessError(
            1,
            ["gh", "api", "graphql"],
            output="",
            stderr="HTTP 401: Bad credentials",
        )
        with patch.object(fetch.subprocess, "run", side_effect=err):
            with self.assertRaises(SystemExit) as ctx:
                fetch.gh_graphql("query { viewer { login } }", {})
        self.assertIn("gh graphql failed", str(ctx.exception))
        self.assertIn("401", str(ctx.exception))

    def test_inaccessible_closing_issue_does_not_abort_wake(self) -> None:
        import subprocess
        from unittest.mock import patch

        item = fetch.item_from_pr(
            pr_graphql(
                body="Fixes #1",
                closingIssuesReferences={
                    "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                    "nodes": [],
                },
            )
        )
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "closingIssuesReferences": {
                            "pageInfo": {"hasNextPage": False},
                            "nodes": [
                                None,
                                {
                                    "number": 1,
                                    "title": "one",
                                    "state": "OPEN",
                                    "body": "",
                                    "repository": {"nameWithOwner": REPO},
                                    "labels": {"nodes": [{"name": "ready-for-pr"}]},
                                    "comments": {"nodes": []},
                                },
                            ],
                        }
                    }
                }
            },
            "errors": [
                {
                    "type": "NOT_FOUND",
                    "path": [
                        "repository",
                        "pullRequest",
                        "closingIssuesReferences",
                        "nodes",
                        0,
                    ],
                    "message": "Could not resolve to an Issue with the number of 99.",
                }
            ],
        }
        err = subprocess.CalledProcessError(
            1,
            ["gh", "api", "graphql"],
            output=json.dumps(payload),
            stderr="gh: GraphQL: Not Found (repository.pullRequest.closingIssuesReferences.nodes.0)",
        )
        with patch.object(fetch.subprocess, "run", side_effect=err):
            fetch.backfill_closing_issues(item, "acme", "tools")
        self.assertEqual([issue["number"] for issue in item.closing_issues], [1])
        self.assertEqual(fetch.ready_for_pr_closers(item, REPO, now=NOW), [1])

    def test_skips_closing_issue_comment_backfill_for_foreign_repo(self) -> None:
        from unittest.mock import patch

        item = fetch.item_from_pr(
            pr_graphql(
                body="Fixes #9",
                closingIssuesReferences={
                    "nodes": [
                        {
                            "number": 9,
                            "title": "bug",
                            "state": "OPEN",
                            "body": "",
                            "repository": {"nameWithOwner": "other/repo"},
                            "labels": {"nodes": []},
                            "comments": {
                                "pageInfo": {
                                    "hasPreviousPage": True,
                                    "startCursor": "c1",
                                },
                                "nodes": [{"body": "no stamp here"}],
                            },
                        }
                    ]
                },
            )
        )
        self.assertIsNotNone(item)
        assert item is not None
        with patch.object(fetch, "gh_graphql") as gql:
            fetch.backfill_closing_issue_comments(item, REPO)
            gql.assert_not_called()
        self.assertEqual(item.closing_issues[0]["comment_bodies"], ["no stamp here"])
        self.assertFalse(item.closing_issues[0]["has_older_comments"])

    def test_null_graphql_nodes_are_skipped(self) -> None:
        from unittest.mock import patch

        self.assertIsNone(fetch.item_from_issue(None))
        self.assertIsNone(fetch.item_from_pr(None))
        parsed = fetch._parse_closing_issues(
            [
                None,
                {
                    "number": 8,
                    "title": "bug",
                    "state": "OPEN",
                    "body": "",
                    "repository": {"nameWithOwner": REPO},
                    "labels": {"nodes": [None, {"name": "ready-for-pr"}]},
                    "comments": {"nodes": [None, {"body": "hi"}]},
                },
                None,
            ]
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["number"], 8)
        self.assertEqual(parsed[0]["labels"], ["ready-for-pr"])
        item = fetch.item_from_pr(
            pr_graphql(
                closingIssuesReferences={
                    "nodes": [
                        None,
                        {
                            "number": 8,
                            "title": "bug",
                            "state": "OPEN",
                            "body": "",
                            "repository": {"nameWithOwner": REPO},
                            "labels": {"nodes": [{"name": "ready-for-pr"}]},
                            "comments": {"nodes": []},
                        },
                        None,
                    ]
                }
            )
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual([issue["number"] for issue in item.closing_issues], [8])
        with patch.object(
            fetch,
            "gh_graphql",
            return_value={
                "repository": {
                    "issues": {
                        "nodes": [
                            None,
                            {
                                "number": 2,
                                "title": "bug",
                                "url": "https://example.com/i/2",
                                "createdAt": "2026-08-21T00:00:00Z",
                                "body": "broke",
                                "author": {"login": "contributor"},
                                "labels": {"nodes": []},
                                "comments": {"pageInfo": {}, "nodes": []},
                            },
                            None,
                        ],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            },
        ):
            nodes = fetch.paginate_nodes(
                fetch.ISSUE_LIST_QUERY, "acme", "tools", "issues"
            )
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["number"], 2)

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
        closing_backfilled: list[int] = []
        closing_comment_backfilled: list[int] = []
        parsed_closing_backfilled: list[int] = []
        pr_review_backfilled: list[int] = []
        commit_backfilled: list[int] = []

        def fake_comments(item, *_args):
            backfilled.append(item.number)

        def fake_threads(item, *_args):
            review_backfilled.append(item.number)

        def fake_closing(item, *_args):
            closing_backfilled.append(item.number)

        def fake_closing_comments(item, *_args):
            closing_comment_backfilled.append(item.number)

        def fake_parsed_closing(item, *_args):
            parsed_closing_backfilled.append(item.number)

        def fake_pr_reviews(item, *_args):
            pr_review_backfilled.append(item.number)

        def fake_commits(item, *_args):
            commit_backfilled.append(item.number)

        stdout = StringIO()
        with (
            patch.object(fetch, "paginate_nodes", side_effect=paginate),
            patch.object(fetch, "backfill_comments", side_effect=fake_comments),
            patch.object(fetch, "backfill_review_threads", side_effect=fake_threads),
            patch.object(fetch, "backfill_closing_issues", side_effect=fake_closing),
            patch.object(
                fetch,
                "backfill_parsed_closing_issues",
                side_effect=fake_parsed_closing,
            ),
            patch.object(
                fetch,
                "backfill_closing_issue_comments",
                side_effect=fake_closing_comments,
            ),
            patch.object(fetch, "backfill_reviews", side_effect=fake_pr_reviews),
            patch.object(fetch, "backfill_commits", side_effect=fake_commits),
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
        self.assertEqual(closing_backfilled, [4])
        self.assertEqual(parsed_closing_backfilled, [4])
        self.assertEqual(closing_comment_backfilled, [4])
        self.assertEqual(pr_review_backfilled, [4])
        self.assertEqual(commit_backfilled, [4])
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

    def test_paginate_nodes_stops_when_end_cursor_is_missing(self) -> None:
        from unittest.mock import patch

        page = {
            "repository": {
                "issues": {
                    "nodes": [
                        {
                            "number": 2,
                            "title": "bug",
                            "url": "https://example.com/i/2",
                            "createdAt": "2026-08-21T00:00:00Z",
                            "body": "broke",
                            "author": {"login": "contributor"},
                            "labels": {"nodes": []},
                            "comments": {"pageInfo": {}, "nodes": []},
                        }
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": None},
                }
            }
        }
        with patch.object(fetch, "gh_graphql", return_value=page) as gql:
            nodes = fetch.paginate_nodes(
                fetch.ISSUE_LIST_QUERY, "acme", "tools", "issues"
            )
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["number"], 2)
        self.assertEqual(gql.call_count, 1)


if __name__ == "__main__":
    unittest.main()
