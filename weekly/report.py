"""Build a Japanese newspaper PDF and Discord summary without changing Bot state."""
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from .metrics import build_digest

JST = timezone(timedelta(hours=9))
INK = colors.HexColor("#172431")
MUTED = colors.HexColor("#657078")
ACCENT = colors.HexColor("#A34D31")
PAPER = colors.HexColor("#FCFAF4")
RULE = colors.HexColor("#C8C6BE")
GREEN = colors.HexColor("#267064")
W, H, M = 595.276, 841.89, 35


def number(value, decimals=0, suffix=""):
    try:
        n = float(value)
        if not math.isfinite(n):
            return "-"
        return f"{n:,.{decimals}f}{suffix}"
    except (ValueError, TypeError):
        return "-"


def percent(value):
    try:
        n = float(value)
        if not math.isfinite(n):
            return "-"
        return f"{n:+.2f}%"
    except (ValueError, TypeError):
        return "-"


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(JST).strftime("%m/%d %H:%M")
    except (AttributeError, ValueError):
        return "-"


def safe_text(value):
    # Treat external titles and review prose as text, not ReportLab markup.
    return escape(str(value or "")).replace("\n", "<br/>")


def plain_excerpt(value, limit=380):
    text = str(value or "").replace("\r", "")
    text = re.sub(r"\[([^\]]+)\]\(https?://[^\s)]+\)", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text).replace("**", "").replace("`", "")
    return text[:limit] + ("…（全文はリンク先）" if len(text) > limit else "")


def register_fonts():
    candidates = [
        (Path("C:/Windows/Fonts/yumin.ttf"), Path("C:/Windows/Fonts/meiryo.ttc")),
        (Path("/usr/share/fonts/opentype/ipaexfont-mincho/ipaexm.ttf"),
         Path("/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf")),
        (Path("/usr/share/fonts/truetype/ipaexfont/ipaexm.ttf"),
         Path("/usr/share/fonts/truetype/ipaexfont/ipaexg.ttf")),
    ]
    for serif, sans in candidates:
        if serif.is_file():
            pdfmetrics.registerFont(TTFont("JPSerif", str(serif)))
            pdfmetrics.registerFont(TTFont("JPSans", str(sans if sans.is_file() else serif)))
            return
    root = Path("/usr/share/fonts")
    fonts = list(root.rglob("ipaexm.ttf")) if root.exists() else []
    if fonts:
        pdfmetrics.registerFont(TTFont("JPSerif", str(fonts[0])))
        gothic = list(root.rglob("ipaexg.ttf"))
        pdfmetrics.registerFont(TTFont("JPSans", str(gothic[0] if gothic else fonts[0])))
        return
    raise RuntimeError("Japanese TTF fonts missing. Install fonts-ipaexfont before generating the PDF.")


def text(c, value, x, top, size=10, font="JPSans", color=INK):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, H - top - size, str(value))


def rule(c, top, x=M, width=W-2*M, color=RULE, weight=0.55):
    c.setStrokeColor(color)
    c.setLineWidth(weight)
    c.line(x, H-top, x+width, H-top)


def paragraph(c, value, x, top, width, size=9, height=150, color=INK, serif=False):
    """Draw bounded prose, visibly shortening overlong untrusted issue/PR bodies."""
    style = ParagraphStyle("body", fontName="JPSerif" if serif else "JPSans", fontSize=size,
                           leading=size*1.65, textColor=color, wordWrap="CJK")
    value = re.sub(r"\n{3,}", "\n\n", str(value or "").replace("\r", "")).strip()
    limit = len(value)
    while True:
        shown = value[:limit].rstrip() + ("…" if limit < len(value) else "")
        p = Paragraph(safe_text(shown), style)
        _, h = p.wrap(width, height)
        if h <= height:
            break
        if limit == 0:
            return 0
        limit = max(0, int(limit*0.8)-1)
    p.drawOn(c, x, H-top-h)
    return h


def page_base(c, digest, page, preview):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    text(c, "MARKET & CODE", M, 22, 8, color=ACCENT)
    text(c, "週刊ペーパートレード通信", 149, 22, 8, color=MUTED)
    date = str(digest["generated_at"])[:10].replace("-", ".")
    label = "見本号 / " if preview else ""
    text(c, f"{label}{date}", 414, 22, 8, color=MUTED)
    rule(c, 39, color=INK, weight=1)
    rule(c, 800, color=INK, weight=0.7)
    text(c, "実売買なし・監視銘柄の記録に基づく分析 / 投資成果を保証しません", M, 808, 7, color=MUTED)
    text(c, f"{page:02d} / 02", W-75, 808, 7, color=MUTED)


def stat(c, x, top, width, label, value, sub=""):
    rule(c, top, x, width, color=INK)
    text(c, label, x, top+9, 8, color=MUTED)
    text(c, value, x, top+25, 20, font="JPSerif")
    text(c, sub, x, top+55, 7, color=MUTED)


def chart(c, curve, x, top, width, height):
    valid = [(str(p.get("at", "")), p.get("total_value")) for p in curve]
    valid = [(t, float(v)) for t, v in valid if isinstance(v, (float, int)) and math.isfinite(v)]
    if len(valid) < 2:
        paragraph(c, "資産推移を描くための時系列データが不足しています。", x, top, width, height=height)
        return
    low, high = min(v for _, v in valid), max(v for _, v in valid)
    pad = max((high-low)*0.15, 100)
    low, high = low-pad, high+pad
    left, right = x+50, x+width-4
    upper, lower = H-top-8, H-top-height+22
    for fraction in (0, 0.5, 1):
        y = lower + (upper-lower)*fraction
        c.setStrokeColor(RULE)
        c.setLineWidth(0.35)
        c.line(left, y, right, y)
        text(c, f"{(low+(high-low)*fraction)/10000:.1f}万", x, H-y-4, 7, color=MUTED)
    times = [datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() for t, _ in valid]
    span = max(times[-1]-times[0], 1)
    points = [(left+(right-left)*(times[i]-times[0])/span,
               lower+(value-low)/(high-low)*(upper-lower)) for i, (_, value) in enumerate(valid)]
    p = c.beginPath()
    p.moveTo(*points[0])
    for point in points[1:]:
        p.lineTo(*point)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.8)
    c.drawPath(p)
    text(c, timestamp(valid[0][0]), left, top+height-12, 7, color=MUTED)
    text(c, timestamp(valid[-1][0]), right-60, top+height-12, 7, color=MUTED)


def review_status(github, now):
    reviews = github.get("reviews", [])
    today = now.astimezone(JST).strftime("%Y-%m-%d")
    current = next((r for r in reviews
                    if str(r.get("title", "")).startswith(f"[週次レビュー {today}]")
                    and r.get("author_association") in {"OWNER", "MEMBER", "COLLABORATOR"}), None)
    if current is None:
        return None, "当日レビュー未確認"
    return current, "当日レビュー記録あり"


def pr_status(pr):
    if pr.get("merged_at"):
        target = pr.get("base_branch")
        return f"{target}へマージ済み" if target else "マージ済み（反映先未確認）"
    return {"open": "提案中・未反映", "closed": "クローズ・未マージ"}.get(pr.get("state"), "状態未確認")


def create_pdf(path, digest, github, repository, preview=False):
    register_fonts()
    c = canvas.Canvas(str(path), pagesize=(W,H))
    c.setTitle("市場とコード | 週刊ペーパートレード通信")
    c.setAuthor("Discord Market Bot / Weekly Review")
    p, a = digest["portfolio"], digest["activity"]
    page_base(c, digest, 1, preview)
    text(c, "市場とコード", M, 51, 35, "JPSerif")
    text(c, "THE WEEKLY REVIEW", M, 96, 9, color=ACCENT)
    text(c, "監視する。検証する。変更を残す。", 311, 97, 10, "JPSerif")
    rule(c, 122, color=INK, weight=2)
    window = percent(p.get("window_pnl_pct"))
    headline = "一週間の運用を、数字で読む" if window != "-" else "週次の基準データを点検"
    text(c, headline, M, 135, 21, "JPSerif")
    subtitle = f"集計 {timestamp(digest.get('period_start'))} - {timestamp(digest.get('period_end'))} JST / 最終記録 {timestamp(digest.get('latest_at'))} JST"
    text(c, subtitle, M, 166, 8, color=MUTED)
    width = (W-2*M-24)/3
    stat(c, M, 189, width, "総資産 / 期末の記録", number(p.get("total_value"),0," 円"),
         "初期資金100万円のペーパートレード")
    stat(c, M+width+12, 189, width, "対象期間の損益率", window,
         f"基準記録 {timestamp(p.get('baseline_at'))} JST" if window != "-" else "履歴不足時は推計しない")
    ratio = p.get("cash_ratio")
    stat(c, M+2*(width+12), 189, width, "現金比率", number(ratio*100 if ratio is not None else None,1,"%"),
         f"現金 {number(p.get('cash'),0,' 円')}")
    text(c, "資産推移", M, 276, 11, "JPSerif")
    text(c, "記録時点ベース / 円", 440, 280, 7, color=MUTED)
    chart(c, digest.get("equity_curve", []), M, 299, W-2*M, 138)
    rule(c, 450)
    col = (W-2*M-25)/2
    text(c, "01 / 監視セクターの温度", M, 464, 12, "JPSerif")
    text(c, "最新記録の5営業日騰落率・単純平均", M, 487, 7.5, color=MUTED)
    for i, sector in enumerate(digest.get("sectors", [])[:6]):
        y=510+i*26
        label = f"{sector['name']} ({sector['coverage']}/{sector['total']})"
        text(c, label, M, y, 8)
        value=sector.get("change_5d_pct")
        text(c, percent(value), M+col-58, y, 9,
             color=GREEN if value is not None and value >= 0 else ACCENT)
        rule(c, y+20, M, col)
    right = M+col+25
    text(c, "02 / 売買とリスク", right, 464, 12, "JPSerif")
    notes = [
        f"買付 {a.get('buys',0)} 回 / うち段階買い増し {a.get('scale_ins',0)} 回。",
        f"売却 {number(a.get('sells'))} 回。対象期間の実現損益は {number(a.get('realized_pnl_jpy'),0,' 円')}。",
        f"累計損益 {number(p.get('pnl_jpy'),0,' 円')}（{percent(p.get('pnl_pct'))}）。",
        f"記録済み最高資産からの下落率 {percent(p.get('peak_drawdown_pct'))}。",
        "セクター値は監視銘柄だけの集計。指数や市場全体の騰落率ではありません。",
    ]
    paragraph(c, "\n".join(notes), right, 490, col, size=9, height=182, serif=True)
    warnings = digest.get("warnings", [])
    quality = " / ".join(warnings[:3]) if warnings else "期間基準と最終記録を確認。集計は保存済みレポートの範囲です。"
    rule(c, 687)
    text(c, "DATA NOTE", M, 698, 8, color=ACCENT)
    paragraph(c, quality, M, 716, W-2*M, size=8, height=65, color=MUTED)
    c.showPage()

    page_base(c, digest, 2, preview)
    text(c, "変更の記録と、次の検証", M, 56, 26, "JPSerif")
    text(c, "CODE DESK / 提案と反映を分けて記録", M, 97, 9, color=ACCENT)
    rule(c, 122, color=INK, weight=2)
    now = datetime.fromisoformat(digest["generated_at"])
    review, status = review_status(github, now)
    text(c, status, M, 137, 14, "JPSerif")
    prs = github.get("pull_requests", [])
    merged = sum(bool(item.get("merged_at")) for item in prs)
    opened = sum(item.get("state") == "open" for item in prs)
    text(c, f"直近7日の更新PR: {len(prs)} 件 / マージ済み {merged} / 提案中 {opened}", M, 163, 8, color=MUTED)
    if github.get("warnings"):
        paragraph(c, "取得上の注意: " + " / ".join(github["warnings"]), M, 304, W-2*M, size=6.5, height=17, color=ACCENT)
    if review:
        review_copy = plain_excerpt(review.get("body"), 410)
    else:
        review_copy = ("この発行日の自動レビュー記録はまだありません。分析が未実施、実行中、または接続・承認待ちの可能性があります。"
                       "以下はGitHubから取得した変更状況であり、週次レビューの完了や本番稼働を示すものではありません。")
    paragraph(c, review_copy, M, 186, W-2*M, size=9, height=112, serif=True)
    if review and not github.get("warnings"):
        url = review.get("html_url","")
        text(c, f"レビュー原文: {url}", M, 303, 7, color=ACCENT)
    rule(c, 326)
    text(c, "変更一覧", M, 340, 12, "JPSerif")
    y = 364
    if not prs:
        paragraph(c, "取得範囲内に更新PRはありません。修正を必要としない場合も、レビュー記録で理由を残します。",
                  M, y, W-2*M, height=72)
    for pr in prs[:3]:
        label = pr_status(pr)
        text(c, f"#{pr.get('number','-')}  {label}", M, y, 8, color=ACCENT)
        paragraph(c, str(pr.get("title",""))[:100], M, y+17, W-2*M, size=11, height=34, serif=True)
        excerpt=plain_excerpt(pr.get("body"),180)
        paragraph(c, excerpt, M, y+52, W-2*M, size=8, height=42, color=MUTED)
        text(c, str(pr.get("html_url","")), M, y+96, 6.8, color=ACCENT)
        rule(c, y+111)
        y+=122
    if len(prs) <= 1:
        box_top = 555
        text(c, "運用メモ", M, box_top, 12, "JPSerif")
        memo = ("毎週、必要性を検証してから最小限の修正を提案します。変更が不要な週も、その理由を残します。"
                "短期間の利益だけを根拠に売買条件を変更せず、再現テストと後方互換性を確認します。"
                "PRがマージされても、本番の実行成功は別に確認が必要です。")
        paragraph(c, memo, M, box_top+24, W-2*M, size=9, height=86, serif=True)
    footer_top = 746 if len(prs)>=3 else 690
    if len(prs)>3:
        text(c, f"ほか {len(prs)-3} 件。全件は同梱digest.jsonとGitHubで確認。", M, footer_top-16, 7, color=MUTED)
    sources = f"出典: github.com/{repository} / data/reports.json、Pull requests、週次レビューIssue"
    paragraph(c, sources+"\n売買ロジック・stateへの自動反映なし。外部ニュースはレビューIssueに出典がある場合のみ扱います。",
              M, footer_top, W-2*M, size=7, height=44, color=MUTED)
    c.save()


def build_summary(digest, github, repository):
    p, a = digest["portfolio"], digest["activity"]
    review, status = review_status(github, datetime.fromisoformat(digest["generated_at"]))
    cash_ratio = p.get("cash_ratio")
    lines = [
        "**市場とコード | 週刊ペーパートレード通信**",
        f"発行 {str(digest['generated_at'])[:10]} / 最終記録 {timestamp(digest.get('latest_at'))} JST",
        f"総資産 {number(p.get('total_value'),0,'円')} / 期間損益率 {percent(p.get('window_pnl_pct'))}",
        f"累計損益 {number(p.get('pnl_jpy'),0,'円')} / 現金比率 {number(cash_ratio*100 if cash_ratio is not None else None,1,'%')}",
        f"買付 {number(a.get('buys'))}回（段階買い増し {number(a.get('scale_ins'))}回）/ 売却 {number(a.get('sells'))}回",
        f"**レビュー状況: {status}**",
    ]
    for warning in github.get("warnings",[])[:2]:
        lines.append(f"GitHub取得注意: {str(warning)[:200]}")
    for pr in github.get("pull_requests",[])[:4]:
        status = pr_status(pr)
        lines.append(f"- {status}: #{pr.get('number')} {str(pr.get('title',''))[:90]}\n{pr.get('html_url','')}")
    if review:
        lines.append(f"レビュー詳細: {review.get('html_url','')}")
    for warning in digest.get("warnings",[])[:2]:
        lines.append(f"注意: {warning}")
    lines.append("新聞PDFを添付。実売買なし。提案中の変更は運用へ反映されていません。")
    return "\n".join(lines).encode("utf-16-le",errors="replace")[:3700].decode("utf-16-le",errors="ignore")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--repository",default="hongsan13/discord-market-bot")
    parser.add_argument("--as-of")
    parser.add_argument("--collect-github",action="store_true")
    parser.add_argument("--github-json",type=Path)
    parser.add_argument("--preview",action="store_true")
    args=parser.parse_args()
    if args.collect_github and args.github_json:
        parser.error("Use either --collect-github or --github-json")
    now=datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(JST)
    if now.tzinfo is None:
        parser.error("--as-of needs a timezone")
    raw=args.state.read_bytes()
    digest=build_digest(json.loads(raw),now)
    github={"pull_requests":[],"reviews":[],"warnings":["GitHub変更情報は未取得"]}
    if args.github_json:
        github=json.loads(args.github_json.read_text(encoding="utf-8"))
    elif args.collect_github:
        from .delivery import collect_github
        github=collect_github(args.repository,now)
    digest["source_sha256"]=hashlib.sha256(raw).hexdigest()
    digest["github"]=github
    args.output_dir.mkdir(parents=True,exist_ok=True)
    targets={name:args.output_dir/name for name in ("newspaper.pdf","summary.txt","digest.json")}
    if any(p.resolve()==args.state.resolve() for p in targets.values()):
        raise ValueError("Output would overwrite source state")
    create_pdf(targets["newspaper.pdf"],digest,github,args.repository,args.preview)
    targets["summary.txt"].write_text(build_summary(digest,github,args.repository),encoding="utf-8")
    targets["digest.json"].write_text(json.dumps(digest,ensure_ascii=False,indent=2),encoding="utf-8")
    if args.state.read_bytes()!=raw:
        raise RuntimeError("Source changed while generating report")
    print(f"Report generated: {len(digest.get('holdings',[]))} holdings; source left unchanged.")


if __name__=="__main__":
    main()
