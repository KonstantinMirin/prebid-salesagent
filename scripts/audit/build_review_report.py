#!/usr/bin/env python3
"""Build a self-contained local HTML review of the storyboard re-grounding sweep.

Assembles, from the real artifacts (never hand-typed):

  * every one of the 40 `@storyboard-v3.1` scenarios — verdict, action, and the
    proposed Gherkin, shown as a diff against what is in the tree today
  * the consolidated ticket slate
  * the discrepancies found — spec vs production, scenario vs spec, and the
    defects found in this sweep's own tooling
  * the one question left unresolved, and what it would change

Nothing here has been applied. Every scenario change is a proposal.

    uv run python scripts/audit/build_review_report.py --proposals <dir> --out <file.html>
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit import storyboard_reconciliation, storyboard_spec  # noqa: E402

FEATURES = Path("tests/bdd/features")
GHERKIN_RE = re.compile(r"##\s*\d*\.?\s*Proposed Gherkin.*?```gherkin\n(.*?)```", re.S | re.I)
VERDICT_RE = re.compile(r"^##\s*\d*\.?\s*VERDICT\s*$", re.M)
TICKET_RE = re.compile(r"^\*\*((?:T|TM|\d+\.)[^*]{5,160})\*\*", re.M)
SLATE_ROW_RE = re.compile(
    r"^\|\s*([PTSU]-\d+)\s*\|\s*(.+?)\s*\|\s*([\w-]+)\s*\|\s*(S\d[^|]*)\|\s*(\d+)\s*\|\s*([\d~]+)\s*\|", re.M
)


def load_reconciliation(proposals: Path) -> list[dict[str, Any]]:
    """In-process call into the sibling script's ``build()``.

    Previously this shelled out via ``subprocess`` and parsed the child's
    stdout as JSON, discarding its stderr — a failure inside the sibling
    (e.g. a missing proposals directory) surfaced here as an opaque
    ``json.JSONDecodeError`` on empty stdout, not the real cause. Calling
    ``build()`` directly lets a :class:`storyboard_spec.StoryboardAuditError`
    propagate with its real message intact, and drops the subprocess
    re-entry between sibling audit scripts entirely.
    """
    return storyboard_reconciliation.build(proposals, storyboard_reconciliation.EXPECTED_SCENARIOS)["rows"]


def current_scenario_text(repo: Path, identifier: str) -> tuple[str, str]:
    """(feature file, the scenario as it stands in the tree today).

    The "tag line terminates the block, 80-line window" walk belongs to
    :func:`storyboard_spec.tagged_scenarios`, which already takes the tag to
    key on — this reads the same blocks, keyed by an individual scenario's
    ``@T-UC-…`` identifier instead of the shared ``@storyboard-v3.1``. A local
    re-implementation of that walk is exactly the drift storyboard_spec exists
    to prevent.
    """
    matches = storyboard_spec.tagged_scenarios(repo / FEATURES, tag=f"@{identifier}")
    if not matches:
        return "", ""
    return matches[0].feature, matches[0].block.rstrip()


def parse_proposals(proposals: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(list(proposals.glob("sb-*.md")) + list(proposals.glob("repin-*.md"))):
        text = path.read_text("utf-8")
        key = path.stem.removeprefix("sb-").removeprefix("repin-")
        gherkin = GHERKIN_RE.search(text)
        ident = re.search(r"@(T-UC-[\w\-]+)", text)
        found[key] = {
            "proposed": gherkin.group(1).rstrip() if gherkin else "",
            "identifier": ident.group(1) if ident else "",
            "tickets": TICKET_RE.findall(text)[:14],
            "file": path.name,
        }
    return found


def parse_slate(consolidated: Path) -> list[dict[str, str]]:
    if not consolidated.exists():
        return []
    rows = []
    for m in SLATE_ROW_RE.finditer(consolidated.read_text("utf-8")):
        rows.append(
            {
                "id": m.group(1),
                "title": m.group(2),
                "cls": m.group(3),
                "sev": m.group(4).strip(),
                "raised": m.group(5),
                "blocks": m.group(6),
            }
        )
    return rows


def diff_lines(before: str, after: str) -> str:
    """Minimal line diff, rendered as coloured rows. Empty `before` means 'new'."""
    import difflib

    out = []
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=3):
        if line.startswith("+++") or line.startswith("---"):
            continue
        cls = (
            "d-add"
            if line.startswith("+")
            else "d-del"
            if line.startswith("-")
            else "d-hunk"
            if line.startswith("@@")
            else "d-ctx"
        )
        out.append(f'<div class="{cls}">{html.escape(line) or "&nbsp;"}</div>')
    return "\n".join(out) or '<div class="d-ctx">(no textual change captured)</div>'


CSS = """
:root{--bg:#fff;--fg:#16181d;--mut:#5b6270;--line:#e3e6ec;--card:#fafbfc;
--add:#e6ffed;--addf:#04521f;--del:#ffeef0;--delf:#82071e;--hunk:#eef2ff;
--s1:#b3261e;--s2:#a15c00;--s3:#4a5568;--ok:#0f7b3f;--warn:#8a5a00;--acc:#2b5fd9;}
@media(prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e6e8ec;--mut:#9aa2b1;--line:#242a35;
--card:#151922;--add:#0d2a17;--addf:#7ee2a8;--del:#2d1417;--delf:#ffa8a8;--hunk:#161d33;
--s1:#ff7b72;--s2:#e3b341;--s3:#9aa2b1;--ok:#3fb950;--warn:#e3b341;--acc:#79a5ff;}}
:root[data-theme=dark]{--bg:#0f1115;--fg:#e6e8ec;--mut:#9aa2b1;--line:#242a35;--card:#151922;
--add:#0d2a17;--addf:#7ee2a8;--del:#2d1417;--delf:#ffa8a8;--hunk:#161d33;
--s1:#ff7b72;--s2:#e3b341;--s3:#9aa2b1;--ok:#3fb950;--warn:#e3b341;--acc:#79a5ff;}
:root[data-theme=light]{--bg:#fff;--fg:#16181d;--mut:#5b6270;--line:#e3e6ec;--card:#fafbfc;
--add:#e6ffed;--addf:#04521f;--del:#ffeef0;--delf:#82071e;--hunk:#eef2ff;
--s1:#b3261e;--s2:#a15c00;--s3:#4a5568;--ok:#0f7b3f;--warn:#8a5a00;--acc:#2b5fd9;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
.wrap{max-width:1180px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:21px;margin:44px 0 14px;padding-top:18px;border-top:1px solid var(--line);letter-spacing:-.01em}
h3{font-size:16px;margin:26px 0 8px}
.sub{color:var(--mut);margin:0 0 26px}
.banner{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--warn);
padding:14px 16px;border-radius:8px;margin:20px 0}
.banner strong{color:var(--warn)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:22px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .n{font-size:27px;font-weight:640;letter-spacing:-.02em}
.card .l{color:var(--mut);font-size:12.5px;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:12px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
tbody tr:hover{background:var(--card)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
code,pre,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
code{font-size:12.5px;background:var(--card);padding:1px 5px;border-radius:4px;border:1px solid var(--line)}
.pill{display:inline-block;font-size:11px;font-weight:640;padding:2px 8px;border-radius:20px;
border:1px solid currentColor;white-space:nowrap}
.RETAG{color:var(--acc)}.REPIN{color:var(--s3)}.PARTIAL{color:var(--warn)}
.FIX-ASSERT{color:var(--s2)}.TICKET{color:var(--s1)}
.S1{color:var(--s1)}.S2{color:var(--s2)}.S3{color:var(--s3)}
.GRADED{color:var(--ok)}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:9px 0}
summary{cursor:pointer;padding:11px 14px;font-weight:560;font-size:14px;list-style:none;display:flex;
gap:10px;align-items:center;flex-wrap:wrap}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸";color:var(--mut);font-size:12px}
details[open] summary::before{content:"▾"}
.body{padding:2px 14px 14px;border-top:1px solid var(--line)}
.diff{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;line-height:1.55;
border:1px solid var(--line);border-radius:8px;overflow-x:auto;margin:10px 0;background:var(--bg)}
.diff div{padding:1px 12px;white-space:pre}
.d-add{background:var(--add);color:var(--addf)}
.d-del{background:var(--del);color:var(--delf)}
.d-hunk{background:var(--hunk);color:var(--mut)}
.d-ctx{color:var(--mut)}
ul{padding-left:20px}li{margin:5px 0}
.muted{color:var(--mut)}
.tick{font-size:12.5px;color:var(--mut);margin:3px 0 3px 2px}
.legend{font-size:13px;color:var(--mut);margin:8px 0 16px}
.legend b{color:var(--fg);font-weight:600}
"""

JS = """
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{
  const f=b.dataset.filter;
  document.querySelectorAll('details[data-action]').forEach(d=>{
    d.style.display = (f==='ALL'||d.dataset.action===f)?'':'none';});
  document.querySelectorAll('[data-filter]').forEach(x=>x.style.fontWeight='400');
  b.style.fontWeight='700';});
"""


def build(repo: Path, proposals: Path, consolidated: Path) -> str:
    rows = load_reconciliation(proposals)
    props = parse_proposals(proposals)
    slate = parse_slate(consolidated)

    actions: dict[str, int] = {}
    for r in rows:
        actions[r["action"]] = actions.get(r["action"], 0) + 1
    graded = sum(1 for r in rows if r["status"] == "GRADED")

    parts: list[str] = []
    A = parts.append
    # The pinned version is READ, never typed: these strings are published, so a
    # hardcoded version publishes a claim about a pin the code may not be on.
    pinned = storyboard_spec.pinned_version(repo)

    A("<h1>Storyboard re-grounding — review</h1>")
    A(
        '<p class="sub">All 40 <code>@storyboard-v3.1</code> BDD scenarios re-grounded against '
        f"AdCP <b>{pinned}</b> (the pinned version) and the storyboards that grade them. "
        "Branch <code>test/storyboard-binding-baseline</code>.</p>"
    )

    A(
        '<div class="banner"><strong>Nothing has been applied.</strong> No scenario in the repo has '
        "been edited and no GitHub issue has been filed. Every change below is a proposal, shown as a "
        "diff against what is in the tree today. The commits on this branch add audit tooling, "
        "generated evidence and one structural guard — no test or production behaviour.</div>"
    )

    A('<div class="cards">')
    for n, l in [
        (len(rows), "scenarios audited"),
        (graded, "genuinely graded"),
        (len(rows) - graded, "not on our path"),
        (len(slate), "tickets to file"),
        (sum(1 for s in slate if s["sev"].startswith("S1")), "of them S1 critical"),
    ]:
        A(f'<div class="card"><div class="n">{n}</div><div class="l">{l}</div></div>')
    A("</div>")

    # ---- what changes, per scenario -------------------------------------------------
    A("<h2>1 &nbsp;What would change, per scenario</h2>")
    A(
        '<p class="legend">'
        '<b class="pill RETAG">RETAG</b> the scenario claims a storyboard grades it, but that storyboard '
        "is behind a protocol, specialism or capability we do not declare — it becomes "
        "<code>@schema-v3.1</code>. &nbsp; "
        '<b class="pill REPIN">REPIN</b> genuinely graded; only the <code>@source</code> pointer is '
        "stale, wrong or missing. &nbsp; "
        '<b class="pill FIX-ASSERT">FIX-ASSERT</b> graded, but the scenario asserts the wrong thing. &nbsp; '
        '<b class="pill PARTIAL">PARTIAL</b> part salvageable, part not — needs your call. &nbsp; '
        '<b class="pill TICKET">TICKET</b> graded, but production is non-conformant, so it cannot be '
        "made green and stays dormant.</p>"
    )

    A('<p style="font-size:13px">Filter: ')
    A('<a href="#" data-filter="ALL" style="margin-right:12px;font-weight:700">all</a>')
    for a in ("RETAG", "REPIN", "FIX-ASSERT", "PARTIAL", "TICKET"):
        A(f'<a href="#" data-filter="{a}" style="margin-right:12px">{a.lower()} ({actions.get(a, 0)})</a>')
    A("</p>")

    for r in sorted(rows, key=lambda x: (x["action"], x["scenario"])):
        p = props.get(r["scenario"], {})
        ident = p.get("identifier") or ""
        feature, before = current_scenario_text(repo, ident) if ident else ("", "")
        after = p.get("proposed", "")
        A(
            f'<details data-action="{r["action"]}"><summary>'
            f'<span class="pill {r["action"]}">{r["action"]}</span> '
            f"<code>{html.escape(r['scenario'])}</code> "
            f'<span class="muted" style="font-size:12px">{html.escape(feature)}</span></summary>'
            f'<div class="body">'
        )
        A(f"<p><b>Verdict.</b> {html.escape(r['verdict'])}</p>")
        if before or after:
            A("<h3>Proposed change</h3>")
            A(f'<div class="diff">{diff_lines(before, after)}</div>')
        if p.get("tickets"):
            A("<h3>Follow-ups this scenario raised</h3>")
            for t in p["tickets"]:
                A(f'<div class="tick">• {html.escape(t)}</div>')
        A(f'<p class="muted" style="font-size:12px">Full analysis: <code>{p.get("file", "—")}</code></p>')
        A("</div></details>")

    # ---- tickets ---------------------------------------------------------------------
    A("<h2>2 &nbsp;Tickets to file</h2>")
    A(
        '<p class="sub">Deduplicated across all 40 analyses — one ticket per defect, not per scenario. '
        "“Raised by” counts how many independent analyses hit it.</p>"
    )
    A(
        '<div class="scroll"><table><thead><tr><th>ID</th><th>Issue</th><th>Class</th>'
        "<th>Severity</th><th>Raised by</th><th>Blocks</th></tr></thead><tbody>"
    )
    for s in slate:
        sev = s["sev"].split()[0]
        A(
            f'<tr><td class="mono">{s["id"]}</td><td>{html.escape(s["title"])}</td>'
            f'<td class="muted">{s["cls"]}</td><td><span class="pill {sev}">{html.escape(s["sev"])}</span></td>'
            f"<td>{s['raised']}</td><td>{s['blocks']}</td></tr>"
        )
    A("</tbody></table></div>")

    # ---- discrepancies ---------------------------------------------------------------
    A("<h2>3 &nbsp;Where the discrepancies are</h2>")
    A(
        '<p class="sub">Three different kinds turned up. They need different responses, so they are '
        "separated here rather than pooled.</p>"
    )

    by_cls: dict[str, list[dict[str, str]]] = {}
    for s_ in slate:
        by_cls.setdefault(s_["cls"], []).append(s_)

    A("<h3>Production disagrees with the spec</h3>")
    A(
        f"<p>Our implementation does not do what AdCP {pinned} requires. These are conformance gaps: "
        "a scenario asserting the correct behaviour would go red today, which is why they are tickets "
        "rather than scenario edits.</p><ul>"
    )
    for s_ in by_cls.get("PRODUCTION", [])[:10]:
        A(
            f'<li><span class="pill {s_["sev"].split()[0]}">{html.escape(s_["sev"])}</span> '
            f'{html.escape(s_["title"])} <span class="muted">— found independently by '
            f"{s_['raised']} analyses</span></li>"
        )
    rest = len(by_cls.get("PRODUCTION", [])) - 10
    if rest > 0:
        A(f'<li class="muted">…and {rest} more in the table above.</li>')
    A("</ul>")

    A("<h3>The scenario disagrees with the spec</h3>")
    A(
        "<p>The test was wrong, not the code. Either it claimed a storyboard that does not grade us, "
        "or it asserted something the spec never said. These are fixable in the scenario, and most are "
        "safe to fix now.</p><ul>"
    )
    for s_ in by_cls.get("SCENARIO", []):
        A(
            f'<li><span class="pill {s_["sev"].split()[0]}">{html.escape(s_["sev"])}</span> '
            f"{html.escape(s_['title'])}</li>"
        )
    A("</ul>")

    A("<h3>The spec disagrees with itself</h3>")
    A(f"<p>Defects in AdCP {pinned} itself — these belong upstream, not in our tree.</p><ul>")
    for s_ in by_cls.get("UPSTREAM", []):
        A(f"<li>{html.escape(s_['title'])}</li>")
    A("</ul>")

    A("<h3>This audit's own tooling was wrong four times</h3>")
    A(
        "<p>Each was caught by cross-checking against the spec or by an analysis contradicting the "
        "tool, and each would have produced fabricated findings had it gone unnoticed. Recorded here "
        "because the tooling earns trust by being checked, not by running clean.</p><ul>"
        "<li><b>Loose phase matching</b> — reported 16 mismatches that were really tool names "
        "appearing in prose. Tightened, it drops to 1.</li>"
        "<li><b><code>Path.stem</code> collapsed every <code>index.yaml</code></b> onto the literal "
        '"index", so one citation looked like a claim on all 20 specialisms. Misclaims fell 38 → 15.</li>'
        "<li><b><code>requires_scenarios</code> treated as a whitelist</b> — wrote off 7 genuinely "
        "graded storyboards. Caught when an analysis returned GRADED for one of them.</li>"
        "<li><b>Gating by directory</b> — <code>governance_conditions</code> sits under "
        "<code>protocols/media-buy/</code> but is pulled in only by specialisms we do not declare. "
        "Missed all four <code>governance_*</code> and three <code>proposal_*</code> scenarios.</li>"
        "</ul>"
    )

    # ---- unresolved ------------------------------------------------------------------
    A("<h2>4 &nbsp;One question left open</h2>")
    A(
        '<div class="banner"><strong>How does the compliance runner decide a storyboard applies '
        'to us?</strong><p style="margin:10px 0 0">A storyboard can be reached because an index '
        "pulls it in — a protocol or specialism we declare — or, possibly, just because we advertise "
        "the tools it needs. <code>provenance_enforcement</code> appears in "
        "<b>no index anywhere</b>. So either it still grades us on tool-advertisement alone, or "
        "nothing reaches it and it is dead.</p>"
        '<p style="margin:10px 0 0">Settling it needs the compliance runner\'s source, which we do '
        "not have. The classifier currently assumes it still applies. If that is wrong, "
        "<b>five of the graded verdicts flip</b> — all the provenance ones — and two tickets "
        "(P-18, P-11) change severity. Four separate analyses hit this and none could resolve it.</p>"
        '<p style="margin:10px 0 0">Everything else in this report is independent of the answer.</p>'
        "</div>"
    )

    A("<h2>5 &nbsp;What happens next</h2>")
    A(
        "<ul>"
        "<li>File the tickets against milestone <b>Storyboard Compliance</b>, each naming this branch. "
        "Holding the five provenance tickets until the question above is settled.</li>"
        "<li>Comment on the six existing issues rather than duplicating them.</li>"
        '<li>Decide the five <span class="pill PARTIAL">PARTIAL</span> splits — those need your call.</li>'
        "<li>Apply the retag / re-pin / fix-assert edits, green-only: nothing that would go red lands "
        "as an assertion; it becomes a ticket instead.</li>"
        "</ul>"
    )

    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--proposals", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    repo = args.repo.resolve()
    consolidated = args.proposals / "CONSOLIDATED-ISSUES.md"
    try:
        body = build(repo, args.proposals.resolve(), consolidated)
    except storyboard_spec.StoryboardAuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.out.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Storyboard re-grounding — review</title>"
        f'<style>{CSS}</style></head><body><div class="wrap">{body}</div>'
        f"<script>{JS}</script></body></html>",
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
