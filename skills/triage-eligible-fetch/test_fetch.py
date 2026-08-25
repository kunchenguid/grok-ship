#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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
    params = dict(owner=OWNER, firstmate_mark=MARK, stale_days=14, now=NOW)
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

    def test_automation_skips(self) -> None:
        self.assertTrue(fetch.is_automation("dependabot[bot]"))
        self.assertTrue(fetch.is_automation("github-actions[bot]"))
        self.assertTrue(fetch.is_automation("release-please[bot]"))
        self.assertTrue(fetch.is_automation("renovate[bot]"))
        self.assertTrue(fetch.is_automation("imgbot[bot]"))
        self.assertTrue(fetch.is_automation("app/my-helper"))
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

    def test_parse_repo(self) -> None:
        self.assertEqual(fetch.parse_repo("acme/tools"), ("acme", "tools"))
        with self.assertRaises(Exception):
            fetch.parse_repo("tools")


if __name__ == "__main__":
    unittest.main()
