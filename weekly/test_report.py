import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from weekly import report
from weekly.metrics import build_digest


NOW = datetime(2026, 8, 28, 15, tzinfo=report.JST)


def fixture():
    def snapshot(at, total):
        return {"generated_at": at, "strategy_version": "v6_fixture",
                "portfolio": {"total_value": total, "cash": 800_000,
                              "starting_capital": 1_000_000, "positions": [],
                              "realized_pnl_jpy": 1000},
                "decisions": [], "market_data": []}
    latest = snapshot(NOW.isoformat(), 1_100_000)
    return {"starting_capital": 1_000_000, "realized_trades": [],
            "reports": [snapshot("2026-08-21T15:00:00+09:00", 1_000_000), latest],
            "latest": latest}


class ReportTests(unittest.TestCase):
    def test_missing_values_are_not_zero(self):
        digest = build_digest({}, NOW)
        summary = report.build_summary(digest, {}, "owner/repo")
        self.assertIn("現金比率 -", summary)
        self.assertNotIn("現金比率 0.0%", summary)
        self.assertIn("売却 -回", summary)

    def test_merged_target_and_proposal_are_distinct(self):
        self.assertEqual(report.pr_status({"merged_at": "2026", "base_branch": "experiment"}),
                         "experimentへマージ済み")
        self.assertNotIn("main", report.pr_status({"merged_at": "2026"}))
        self.assertIn("未反映", report.pr_status({"state": "open"}))
        self.assertEqual(report.pr_status({"state": "unknown"}), "状態未確認")

    def test_old_review_is_not_todays_review(self):
        github = {"reviews": [{"title": "[週次レビュー 2026-08-21] reviewed", "body": "old",
                               "author_association": "OWNER"}]}
        review, status = report.review_status(github, NOW)
        self.assertIsNone(review)
        self.assertIn("未確認", status)
        github["reviews"].append({"title": "[週次レビュー 2026-08-28] reviewed", "body": "today",
                                  "author_association": "OWNER"})
        self.assertEqual(report.review_status(github, NOW)[0]["body"], "today")

    def test_outsider_cannot_impersonate_todays_review(self):
        github={"reviews":[{"title":"[週次レビュー 2026-08-28] fake","body":"untrusted",
                            "author_association":"NONE"},
                           {"title":"[週次レビュー 2026-08-28] actual","body":"trusted",
                            "author_association":"OWNER"}]}
        self.assertEqual(report.review_status(github,NOW)[0]["body"],"trusted")

    def test_short_multiline_text_cannot_overflow_its_box(self):
        report.register_fonts()
        with tempfile.TemporaryDirectory() as tmp:
            c=report.canvas.Canvas(str(Path(tmp)/"bounded.pdf"))
            for value in ("\n"*6+"Short body","\n"*20,"x\ny\nz\nx\ny\nz\na"):
                self.assertLessEqual(report.paragraph(c,value,35,50,200,size=8,height=42),42)
            self.assertEqual(report.paragraph(c,"text",35,50,200,size=8,height=0),0)
            c.save()

    def test_collection_warning_survives_other_data_warnings(self):
        digest=build_digest({}, NOW)
        digest["warnings"]=["data warning"]*5
        summary=report.build_summary(digest, {"warnings":["HTTP 403: collection incomplete"]}, "owner/repo")
        self.assertIn("HTTP 403", summary)
        self.assertIn("レビュー状況", summary)

    def test_utf16_summary_limit_and_untrusted_markup(self):
        digest=build_digest(fixture(),NOW)
        prs=[{"number":i,"state":"open","title":"😀"*100,
              "html_url":"https://github.com/owner/repo/pull/"+str(i)} for i in range(4)]
        summary=report.build_summary(digest,{"pull_requests":prs}, "owner/repo")
        self.assertLessEqual(len(summary.encode("utf-16-le"))//2,2000)
        self.assertEqual(report.safe_text("<img src='http://invalid'/>"), "&lt;img src='http://invalid'/&gt;")

    def test_full_render_cli_preserves_source_and_creates_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"state.json"
            original=json.dumps(fixture(),ensure_ascii=False).encode("utf-8")
            source.write_bytes(original)
            github=root/"github.json"
            github.write_text(json.dumps({"pull_requests":[
                {"number":i,"title":"変更の提案 "*25,"body":"<img src='https://invalid'/>\n説明"*120,
                 "state":"open","html_url":f"https://github.com/owner/repo/pull/{i}"}
                for i in range(1,5)],"reviews":[],"warnings":["GitHub collection incomplete"]}),encoding="utf-8")
            args=["weekly.report","--state",str(source),"--output-dir",str(root/"output"),
                  "--as-of",NOW.isoformat(),"--github-json",str(github),"--preview"]
            with patch.object(sys,"argv",args):
                report.main()
            self.assertEqual(source.read_bytes(),original)
            pdf=(root/"output/newspaper.pdf").read_bytes()
            self.assertTrue(pdf.startswith(b"%PDF-"))
            self.assertLess(len(pdf),8*1024*1024)
            digest=json.loads((root/"output/digest.json").read_text(encoding="utf-8"))
            self.assertEqual(digest["portfolio"]["window_pnl_jpy"],100_000)
            self.assertIn("提案中・未反映",(root/"output/summary.txt").read_text(encoding="utf-8"))

    def test_refuses_source_output_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"digest.json"
            original=json.dumps(fixture()).encode()
            source.write_bytes(original)
            args=["weekly.report","--state",str(source),"--output-dir",tmp,"--as-of",NOW.isoformat()]
            with patch.object(sys,"argv",args), self.assertRaisesRegex(ValueError,"overwrite"):
                report.main()
            self.assertEqual(source.read_bytes(),original)

    def test_summary_and_pdf_do_not_mutate_digest(self):
        digest=build_digest(fixture(),NOW)
        original=copy.deepcopy(digest)
        report.build_summary(digest,{},"owner/repo")
        with tempfile.TemporaryDirectory() as tmp:
            report.create_pdf(Path(tmp)/"report.pdf",digest,{},"owner/repo")
        self.assertEqual(digest,original)


if __name__=="__main__":
    unittest.main()
