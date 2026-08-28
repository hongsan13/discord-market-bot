"""Offline tests: no real webhook, token, GitHub requests, or Bot execution."""

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from weekly import delivery


NOW = datetime(2026, 8, 29, 1, 0, tzinfo=timezone.utc)
REPO = "hongsan13/discord-market-bot"
WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/test_token_not_a_real_secret"


def response(payload=None, status=200, *, next_page=False, headers=None):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    result.links = {"next": {"url": "https://untrusted.example/never-follow"}} if next_page else {}
    result.headers = headers or {}
    return result


def pr(number, **overrides):
    item = {
        "number": number, "title": f"Change {number}", "state": "open",
        "body": "Proposed changes; tests claimed in the text are not proof.",
        "updated_at": "2026-08-28T03:00:00Z", "merged_at": None,
        "author_association": "OWNER", "user": {"login": "hongsan13"},
    }
    item.update(overrides)
    return item


class GitHubCollectionTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"GITHUB_TOKEN": "test_only_token"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.session = Mock()

    def collect(self, *responses):
        self.session.get.side_effect = responses
        return delivery.collect_github(REPO, NOW, session=self.session)

    def test_open_closed_and_merged_are_distinct_and_checks_not_inferred(self):
        result = self.collect(
            response([
                pr(1),
                pr(2, state="closed"),
                pr(3, state="closed", merged_at="2026-08-27T09:00:00Z"),
            ]), response([]),
        )
        records = result["pull_requests"]
        self.assertEqual([r["status"] for r in records], ["open", "closed", "merged"])
        self.assertEqual([r["merged_at"] is None for r in records], [True, True, False])
        self.assertTrue(all(r["checks_status"].startswith("unknown") for r in records))
        self.assertEqual(records[0]["html_url"], f"https://github.com/{REPO}/pull/1")
        self.assertEqual(result["warnings"], [])
        for call in self.session.get.call_args_list:
            self.assertTrue(call.args[0].startswith(f"https://api.github.com/repos/{REPO}/"))
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer test_only_token")
            self.assertEqual(call.kwargs["timeout"], delivery.NETWORK_TIMEOUT)

    def test_issue_filter_excludes_prs_even_when_pull_request_object_is_empty(self):
        result = self.collect(response([]), response([
            pr(1, title="[週次レビュー 2026-08-29] 修正なし"),
            pr(2, title="[週次レビュー 2026-08-29] PR", pull_request={}),
            pr(3, title="Unrelated issue"),
            pr(4, title="prefix [週次レビュー 2026-08-29]"),
        ]))
        self.assertEqual([r["number"] for r in result["reviews"]], [1])
        self.assertEqual(result["reviews"][0]["html_url"], f"https://github.com/{REPO}/issues/1")
        self.assertEqual(self.session.get.call_args.kwargs["params"]["since"], "2026-08-22T01:00:00Z")

    def test_merge_target_is_preserved_without_assuming_default_branch(self):
        result = self.collect(response([
            pr(1, state="closed", merged_at="2026-08-27T09:00:00Z", base={"ref": "main"}),
            pr(2, state="closed", merged_at="2026-08-27T09:00:00Z", base={"ref": "experiment"}),
            pr(3), pr(4, base={"ref": 123}), pr(5, base="invalid"),
        ]), response([]))
        self.assertEqual(
            [record["base_branch"] for record in result["pull_requests"]],
            ["main", "experiment", None, None, None],
        )

    def test_newer_outsider_review_cannot_override_trusted_review(self):
        result = self.collect(response([]), response([
            pr(2, title="[週次レビュー 2026-08-29] impersonation",
               updated_at="2026-08-29T00:59:00Z", author_association="NONE",
               user={"login": "outsider"}, body="Untrusted claims of a successful review."),
            pr(1, title="[週次レビュー 2026-08-29] trusted review",
               updated_at="2026-08-29T00:00:00Z"),
        ]))
        self.assertEqual([record["number"] for record in result["reviews"]], [1])
        self.assertEqual(result["reviews"][0]["author_association"], "OWNER")
        self.assertEqual(result["reviews"][0]["author_login"], "hongsan13")
        self.assertIn("untrusted authors were omitted", " ".join(result["warnings"]))
        self.assertNotIn("impersonation", json.dumps(result))

    def test_reviews_require_trusted_association_not_just_contribution_or_login(self):
        associations = ("OWNER", "MEMBER", "COLLABORATOR", "CONTRIBUTOR", "FIRST_TIMER", "NONE", None, {})
        result = self.collect(response([]), response([
            pr(number, title="[週次レビュー 2026-08-29] review", author_association=association)
            for number, association in enumerate(associations, start=1)
        ]))
        self.assertEqual([record["number"] for record in result["reviews"]], [1, 2, 3])
        self.assertTrue(result["warnings"])

    def test_pr_attribution_is_preserved_without_excluding_external_proposals(self):
        result = self.collect(response([
            pr(1, author_association="CONTRIBUTOR", user={"login": "external-contributor"}),
            pr(2, author_association=None, user=None),
        ]), response([]))
        self.assertEqual(result["pull_requests"][0]["author_association"], "CONTRIBUTOR")
        self.assertEqual(result["pull_requests"][0]["author_login"], "external-contributor")
        self.assertIsNone(result["pull_requests"][1]["author_association"])
        self.assertIsNone(result["pull_requests"][1]["author_login"])

    def test_week_boundary_inclusive_and_old_records_stop_pagination(self):
        result = self.collect(response([
            pr(1, updated_at="2026-08-29T01:00:00Z"),
            pr(2, updated_at="2026-08-22T01:00:00Z"),
            pr(3, updated_at="2026-08-22T00:59:59Z"),
        ], next_page=True), response([]))
        self.assertEqual([r["number"] for r in result["pull_requests"]], [1, 2])
        self.assertEqual(self.session.get.call_count, 2)

    def test_bad_or_future_timestamps_are_not_reported_as_current(self):
        result = self.collect(response([
            pr(1, updated_at="2026-08-29T01:00:01Z"),
            pr(2, updated_at="2026-08-28T01:00:00"),
            pr(3, updated_at="invalid"), pr(4),
        ]), response([]))
        self.assertEqual([r["number"] for r in result["pull_requests"]], [4])
        self.assertTrue(result["warnings"])

    def test_pagination_uses_fixed_api_and_reports_cap(self):
        with patch.object(delivery, "GITHUB_PAGE_SIZE", 2), patch.object(delivery, "GITHUB_MAX_PAGES", 2):
            result = self.collect(
                response([pr(1), pr(2)], next_page=True),
                response([pr(3), pr(4)], next_page=True), response([]),
            )
        self.assertEqual(len(result["pull_requests"]), 4)
        self.assertTrue(result["truncated"])
        self.assertIn("capped at 2 pages", " ".join(result["warnings"]))
        calls = self.session.get.call_args_list
        self.assertEqual(calls[0].args[0], calls[1].args[0])
        self.assertEqual(calls[1].kwargs["params"]["page"], 2)
        self.assertNotIn("untrusted.example", str(calls))

    def test_duplicates_and_malformed_metadata_are_omitted(self):
        result = self.collect(response([pr(1), pr(1), pr(True), pr(-1), "not an object"]), response([]))
        self.assertEqual(len(result["pull_requests"]), 1)
        self.assertTrue(result["warnings"])

    def test_large_bodies_are_truncated_and_text_is_only_data(self):
        untrusted = "$(do-not-execute) <script>none</script> @everyone"
        result = self.collect(response([pr(1, body=untrusted), pr(2, body="a" * 6001)]), response([]))
        self.assertEqual(result["pull_requests"][0]["body"], untrusted)
        self.assertEqual(len(result["pull_requests"][1]["body"]), 6000)
        self.assertTrue(result["pull_requests"][1]["body_truncated"])
        self.assertTrue(result["truncated"])

    def test_api_failure_is_visible_but_does_not_leak_error_text(self):
        result = self.collect(
            requests.ConnectionError("https://api.github.com/?test_only_token"),
            response([pr(5, title="[週次レビュー 2026-08-29] 記録")]),
        )
        self.assertEqual(result["pull_requests"], [])
        self.assertEqual(len(result["reviews"]), 1)
        self.assertIn("incomplete", " ".join(result["warnings"]))
        self.assertNotIn("test_only_token", json.dumps(result))

    def test_forbidden_and_unexpected_json_shape_are_visible(self):
        result = self.collect(response(status=403), response({"unexpected": "shape"}))
        self.assertEqual(len(result["warnings"]), 2)
        self.assertIn("HTTP 403", result["warnings"][0])
        self.assertIn("unexpected response shape", result["warnings"][1])

    def test_no_token_means_not_collected_not_no_changes(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            result = delivery.collect_github(REPO, NOW, session=self.session)
        self.session.get.assert_not_called()
        self.assertIn("not run", " ".join(result["warnings"]))

    def test_repository_validation_prevents_endpoint_injection(self):
        for repository in ("https://evil.example/a", "owner/../evil", "owner/..", "owner/repo?x=1", "owner/repo\n", "../repo", ""):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                delivery.collect_github(repository, NOW, session=self.session)
        self.session.get.assert_not_called()

    def test_naive_collection_time_rejected(self):
        with self.assertRaises(ValueError):
            delivery.collect_github(REPO, NOW.replace(tzinfo=None), session=self.session)


class DiscordDeliveryTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": ""})
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.pdf = self.root / "newspaper.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nmock pdf for offline transport test\n%%EOF")
        self.session = Mock()
        self.session.post.return_value = response({"id": "123456789012345678"})

    def send(self, summary="週次レビュー: 提案PRは未反映です。", **kwargs):
        return delivery.send_discord(summary, self.pdf, webhook_url=WEBHOOK, session=self.session, **kwargs)

    def test_confirmed_multipart_post_disables_mentions_and_redirects(self):
        result = self.send("週次レビュー @everyone <@123456789>")
        self.assertEqual(result, {"message_id": "123456789012345678"})
        call = self.session.post.call_args
        self.assertEqual(call.args[0], WEBHOOK)
        self.assertEqual(call.kwargs["params"], {"wait": "true"})
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(call.kwargs["timeout"], delivery.NETWORK_TIMEOUT)
        payload = json.loads(call.kwargs["data"]["payload_json"])
        self.assertEqual(payload["allowed_mentions"]["parse"], [])
        self.assertFalse(payload["allowed_mentions"]["replied_user"])
        self.assertEqual(call.kwargs["files"]["files[0]"][0], "newspaper.pdf")
        self.assertEqual(call.kwargs["files"]["files[0]"][2], "application/pdf")

    def test_webhook_validation_rejects_other_hosts_auth_queries_and_fragments(self):
        for endpoint in (
            WEBHOOK.replace("https:", "http:"), WEBHOOK.replace("discord.com", "discord.com.evil.example"),
            WEBHOOK.replace("discord.com", "discordapp.com"), WEBHOOK.replace("discord.com", "user@discord.com"),
            WEBHOOK.replace("discord.com", "discord.com:443"), WEBHOOK + "?wait=false", WEBHOOK + "#secret",
            "\n" + WEBHOOK, WEBHOOK + "\t",
            "https://discord.com/api/webhooks/../invalid", "", "https://discord.com/channels/123",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(delivery.DeliveryError) as error:
                delivery.send_discord("summary", self.pdf, webhook_url=endpoint, session=self.session)
            self.assertNotIn("test_token_not_a_real_secret", str(error.exception))
        self.session.post.assert_not_called()

    def test_network_failure_redacted_and_never_retried(self):
        self.session.post.side_effect = requests.Timeout(WEBHOOK)
        with self.assertRaises(delivery.DeliveryError) as error:
            self.send()
        self.assertNotIn(WEBHOOK, str(error.exception))
        self.assertIn("Check the channel", str(error.exception))
        self.session.post.assert_called_once()

    def test_429_honors_retry_after_information_without_resending(self):
        self.session.post.return_value = response({"retry_after": 1.2}, status=429)
        with self.assertRaises(delivery.DeliveryError) as error:
            self.send()
        self.assertIn("at least 2 seconds", str(error.exception))
        self.assertIn("no automatic resend", str(error.exception))
        self.session.post.assert_called_once()

    def test_untrusted_retry_after_or_response_text_never_leaks(self):
        self.session.post.return_value = response({"retry_after": WEBHOOK, "message": WEBHOOK}, status=429)
        with self.assertRaises(delivery.DeliveryError) as error:
            self.send()
        self.assertNotIn(WEBHOOK, str(error.exception))

    def test_error_redirect_and_unconfirmed_success_are_not_retried(self):
        for status in (400, 404, 500, 302, 204):
            with self.subTest(status=status):
                self.session.reset_mock()
                self.session.post.return_value = response({"message": WEBHOOK}, status=status)
                with self.assertRaises(delivery.DeliveryError) as error:
                    self.send()
                self.assertNotIn(WEBHOOK, str(error.exception))
                self.session.post.assert_called_once()

    def test_missing_confirmation_id_is_not_success(self):
        for payload in ({}, {"id": "not-an-id"}, [], None):
            with self.subTest(payload=payload):
                self.session.post.return_value = response(payload)
                with self.assertRaises(delivery.DeliveryError):
                    self.send()

    def test_summary_boundaries_include_utf16_units(self):
        self.send("a" * 2000)
        self.send("😀" * 1000)
        self.session.reset_mock()
        for summary in ("a" * 2001, "😀" * 1001, " \n\t", "\ud800", None):
            with self.subTest(summary_type=type(summary).__name__), self.assertRaises(delivery.DeliveryError):
                self.send(summary)
        self.session.post.assert_not_called()

    def test_empty_oversized_and_nonpdf_attachments_rejected_before_network(self):
        for contents in (b"", b"not a pdf", b"%PDF-" + b"x" * 16):
            with self.subTest(contents=contents), patch.object(delivery, "MAX_PDF_BYTES", 16):
                self.pdf.write_bytes(contents)
                with self.assertRaises(delivery.DeliveryError):
                    self.send()
        self.session.post.assert_not_called()

    def test_missing_pdf_rejected_before_network(self):
        missing = self.root / "absent.pdf"
        with self.assertRaises(delivery.DeliveryError):
            delivery.send_discord("summary", missing, webhook_url=WEBHOOK, session=self.session)
        self.session.post.assert_not_called()

    def test_cli_handles_utf8_bom_and_uses_environment_not_url_argument(self):
        summary_path = self.root / "summary.txt"
        summary_path.write_text("週次レビュー", encoding="utf-8-sig")
        with patch.object(delivery, "send_discord") as send, patch("sys.stdout", new_callable=io.StringIO):
            result = delivery.main(["--summary", str(summary_path), "--pdf", str(self.pdf)])
        self.assertEqual(result, 0)
        send.assert_called_once_with("週次レビュー", self.pdf)

    def test_cli_missing_secret_fails_without_printing_paths_or_secrets(self):
        summary_path = self.root / "summary.txt"
        summary_path.write_text("週次レビュー", encoding="utf-8")
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": ""}), patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = delivery.main(["--summary", str(summary_path), "--pdf", str(self.pdf)])
        self.assertEqual(result, 1)
        self.assertIn("Weekly Discord delivery failed", stderr.getvalue())
        self.assertNotIn(str(self.root), stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
