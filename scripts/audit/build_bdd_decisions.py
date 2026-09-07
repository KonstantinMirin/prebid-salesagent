#!/usr/bin/env python3
"""Render the BDD findings as DECISIONS, grouped by defect class.

The companion page (``build_bdd_findings_report.py``) renders every agent report
whole. That is the evidence, and it is unreviewable as a work queue: it answers
"what did the agents find" when the question is "what do I have to decide".

This page inverts it. One row per decision, grouped by the defect class it
belongs to, each with the measured count, the verbatim evidence, and the specific
question whose answer unblocks the work. Nothing here is a summary of an agent
report — the counts are measured directly from the tree at render time, so the
page cannot drift from the code the way a hand-written finding list does.

    python3 scripts/audit/build_bdd_decisions.py <out.html>
"""

from __future__ import annotations

import ast
import collections
import glob
import html
import pathlib
import re
import sys

STEPS = "tests/bdd/steps/**/*.py"
FEATURES = "tests/bdd/features/*.feature"


def step_functions():
    """Every decorated step definition, with its AST node and location."""
    for path in sorted(glob.glob(STEPS, recursive=True)):
        text = pathlib.Path(path).read_text()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            kinds = {
                (d.func.id if isinstance(d.func, ast.Name) else getattr(d.func, "attr", ""))
                for d in node.decorator_list
                if isinstance(d, ast.Call)
            }
            kinds &= {"given", "when", "then"}
            if kinds:
                yield path, node, kinds, lines


def called_names(node: ast.AST) -> set[str]:
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            out.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    return out


def snippet(lines: list[str], lineno: int, span: int = 7) -> str:
    start = max(0, lineno - 1)
    return "\n".join(lines[start : start + span])


DISPATCH = ("call_via", "dispatch_request", "call_raw", "_call")


def collect():
    """Every finding, keyed by defect class. Measured, not recalled."""
    found = collections.defaultdict(list)
    for path, node, kinds, lines in step_functions():
        name = pathlib.Path(path).name
        loc = f"{name}:{node.lineno}"
        calls = called_names(node)
        dumped = ast.dump(node)
        has_assert = any(isinstance(s, ast.Assert) for s in ast.walk(node))
        has_raise = any(isinstance(s, ast.Raise) for s in ast.walk(node))
        delegates = any(
            c.startswith(("assert_", "require_", "expect_", "verify_", "check_")) or c.endswith("_compliant")
            for c in calls
        )

        if "then" in kinds and not (has_assert or has_raise or delegates):
            found["then-grades-nothing"].append((loc, snippet(lines, node.lineno)))

        if "then" in kinds and any(d in calls for d in DISPATCH):
            found["then-dispatches"].append((loc, snippet(lines, node.lineno)))

        if "given" in kinds and any(d in calls for d in DISPATCH):
            found["given-dispatches"].append((loc, snippet(lines, node.lineno)))

        if "then" in kinds:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and any(
                    isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "ctx"
                    for t in sub.targets
                ):
                    found["then-writes-ctx"].append((loc, snippet(lines, node.lineno)))
                    break

        if {"patch", "MagicMock", "Mock", "monkeypatch"} & calls:
            found["step-patches-mock"].append((loc, snippet(lines, node.lineno)))

        if "mock" in dumped and "env" in dumped and re.search(r"env\.mock", ast.unparse(node)):
            found["step-reaches-env-mock"].append((loc, snippet(lines, node.lineno)))

        raw = sum(
            1
            for s in ast.walk(node)
            if isinstance(s, ast.Subscript) and isinstance(s.value, ast.Name) and s.value.id == "ctx"
        )
        if raw >= 8:
            found["raw-ctx-heavy"].append((f"{loc} — {raw} subscripts", snippet(lines, node.lineno)))

        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert) and isinstance(sub.test, (ast.Name, ast.Attribute)):
                found["bare-truthiness"].append((loc, snippet(lines, node.lineno)))
                break
    return found


def shadowed():
    """Sentences bound in more than one module, with the bodies that compete."""
    reg = collections.defaultdict(list)
    for path, node, _kinds, _ in step_functions():
        body = [x for x in node.body if not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant))]
        key = ast.dump(ast.Module(body=body, type_ignores=[]), annotate_fields=False)
        for d in node.decorator_list:
            if not isinstance(d, ast.Call):
                continue
            fn = d.func.id if isinstance(d.func, ast.Name) else getattr(d.func, "attr", "")
            if fn not in ("given", "when", "then"):
                continue
            a = d.args[0] if d.args else None
            s = (
                a.value
                if isinstance(a, ast.Constant)
                else (
                    a.args[0].value
                    if isinstance(a, ast.Call) and a.args and isinstance(a.args[0], ast.Constant)
                    else None
                )
            )
            if s:
                reg[(fn, s)].append((pathlib.Path(path).name, node.name, key))
    return {k: v for k, v in reg.items() if len({m for m, _, _ in v}) > 1}


DECISIONS = [
    (
        "then-grades-nothing",
        "A Then that grades nothing",
        "No assert, no raise, and no call to an asserting helper. The scenario says an obligation holds; the step checks nothing. These pass unconditionally and always will.",
        "Delete the step and the sentence, or write the assertion it implies? Each needs the scenario read to know which.",
    ),
    (
        "shadowed",
        "One sentence, two competing bodies",
        "The same sentence is registered in two modules with DIFFERENT normalized bodies. Which one runs depends on plugin registration order, and pytest-bdd does not warn. Same class as the duplicate-scenario-name trap.",
        "For each: is one body correct and the other dead, or do they mean different things and need two sentences? Three of seven reviewed had the first opinion objected to.",
    ),
    (
        "then-dispatches",
        "A Then that performs the action it grades",
        "The assertion step calls the dispatch seam. A Then that acts is a When wearing the wrong keyword, and it makes the scenario's own Given/When/Then structure a lie about what happened in which order.",
        "Move the dispatch to a When, or is the second call deliberate (a re-read, an idempotency probe)?",
    ),
    (
        "given-dispatches",
        "A Given that performs the action",
        "Setup that dispatches through the tool seam. The scenario then has two actions and the When is not the one under test.",
        "Is the dispatch setup (seed via the API because no factory exists) or is it the action? If setup, it wants a factory; if the action, it wants to be the When.",
    ),
    (
        "then-writes-ctx",
        "A Then that mutates state",
        "An assertion step writing back into ctx. Later steps then depend on assertion order, so removing or reordering an assertion changes behaviour rather than just coverage.",
        "What later step consumes the write? If none, delete the write. If one, the value belongs in the When's result, not in an assertion.",
    ),
    (
        "step-patches-mock",
        "A step that patches a mock",
        "Patching inside a step definition. The scenario then grades the patch rather than production, and the patch is invisible in the feature file — a reader cannot tell the system was replaced.",
        "Can the state be produced for real (a factory, a seeded row)? If genuinely not, should the scenario say so out loud rather than hide it in a step?",
    ),
    (
        "step-reaches-env-mock",
        "A step reaching into env.mock[...]",
        "Direct access to the mock registry, bypassing the realization seam. These are the sites that cannot work on e2e, and they are not declared unsupported anywhere — so they are invisible until the transport changes.",
        "Route through the seam, or declare unsupported? Silently working on one transport is the outcome to avoid.",
    ),
    (
        "raw-ctx-heavy",
        "Raw ctx access, 8+ subscripts in one step",
        "A step reading and writing many ctx keys directly instead of going through the guarded helpers. Every raw read is a place a key can be absent, misspelled, or written by a different sentence than the one the author had in mind.",
        "Which of these keys are a real contract between steps, and which are incidental? The contract ones want a named accessor.",
    ),
    (
        "bare-truthiness",
        "assert on bare truthiness",
        "`assert x` with no comparison. Passes for any non-empty value, so it grades presence rather than correctness — and a wrong value of the right shape sails through.",
        "What is the actual expected value? A truthy check on a response field is nearly always a missed equality assertion.",
    ),
]

CSS = """
:root{--bg:#fff;--fg:#191919;--mut:#6a6a6a;--line:#e3e3e3;--code:#f7f7f5;--red:#b3261e;--amb:#8a6100;--ok:#0a6b3d}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151515;--fg:#e8e8e8;--mut:#9a9a9a;--line:#2d2d2d;--code:#1d1d1d;--red:#ff8a80;--amb:#ffcc66;--ok:#7fd1a5}}
:root[data-theme=dark]{--bg:#151515;--fg:#e8e8e8;--mut:#9a9a9a;--line:#2d2d2d;--code:#1d1d1d;--red:#ff8a80;--amb:#ffcc66;--ok:#7fd1a5}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);margin:0;font:15px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:34px 22px 100px}
h1{font-size:25px;margin:0 0 6px}
.lede{color:var(--mut);margin:0 0 26px;max-width:70ch}
.sum{width:100%;border-collapse:collapse;margin:0 0 34px;font-size:14px}
.sum th,.sum td{border:1px solid var(--line);padding:7px 10px;text-align:left}
.sum th{background:var(--code)}
.sum td.n{text-align:right;font:13px ui-monospace,Menlo,monospace;width:5.5em}
.sum a{color:inherit;text-decoration:none;border-bottom:1px solid var(--line)}
.d{border:1px solid var(--line);border-radius:7px;margin:22px 0;overflow:hidden}
.d>h2{margin:0;padding:13px 17px;font-size:17px;background:var(--code);border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.cnt{font:13px ui-monospace,Menlo,monospace;color:var(--mut);white-space:nowrap}
.d .in{padding:14px 17px}
.why{margin:0 0 10px}
.ask{border-left:3px solid var(--amb);background:var(--code);padding:9px 13px;margin:12px 0 4px;border-radius:0 4px 4px 0}
.ask strong{color:var(--amb)}
details.ev{margin-top:12px}
details.ev>summary{cursor:pointer;color:var(--mut);font-size:13.5px}
pre{background:var(--code);border:1px solid var(--line);border-radius:4px;padding:10px 12px;overflow-x:auto;font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;margin:6px 0 14px}
.loc{font:12.5px ui-monospace,Menlo,monospace;color:var(--mut);display:block;margin-top:10px}
code{background:var(--code);padding:1px 5px;border-radius:3px;font:13px ui-monospace,Menlo,monospace}
.more{color:var(--mut);font-size:13px;margin:4px 0 0}
"""


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = pathlib.Path(sys.argv[1])
    found = collect()
    sh = shadowed()
    found["shadowed"] = [
        (
            f"@{kw} {s}",
            "\n".join(f"{m}::{fn}" for m, fn, _ in v)
            + f"\n\n# {len({b for _, _, b in v})} distinct bodies compete for this sentence",
        )
        for (kw, s), v in sorted(sh.items())
    ]

    rows = "".join(
        f'<tr><td><a href="#{k}">{html.escape(t)}</a></td><td class="n">{len(found.get(k, []))}</td></tr>'
        for k, t, _, _ in DECISIONS
    )

    blocks = []
    for key, title, why, ask in DECISIONS:
        items = found.get(key, [])
        ev = "".join(
            f'<span class="loc">{html.escape(loc)}</span><pre>{html.escape(code)}</pre>' for loc, code in items[:6]
        )
        more = f'<p class="more">+{len(items) - 6} more of this class in the tree.</p>' if len(items) > 6 else ""
        blocks.append(
            f'<section class="d" id="{key}"><h2><span>{html.escape(title)}</span>'
            f'<span class="cnt">{len(items)} site{"" if len(items) == 1 else "s"}</span></h2><div class="in">'
            f'<p class="why">{html.escape(why)}</p>'
            f'<div class="ask"><strong>Decide:</strong> {html.escape(ask)}</div>'
            f'<details class="ev"><summary>Evidence — first {min(6, len(items))} of {len(items)}, verbatim</summary>{ev}{more}</details>'
            f"</div></section>"
        )

    total = sum(len(found.get(k, [])) for k, _, _, _ in DECISIONS)
    out.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>BDD decisions</title><style>{CSS}</style></head><body><div class='wrap'>"
        f"<h1>BDD harness — what needs deciding</h1>"
        f"<p class='lede'>{total} sites across {len(DECISIONS)} defect classes, measured from the tree at render time "
        f"rather than copied from a report, so this page cannot drift from the code. Each class states why it is a "
        f"defect and the one question whose answer unblocks the work. The agent reports behind these live in "
        f"<code>bdd-cluster-findings.html</code>.</p>"
        f"<table class='sum'><thead><tr><th>Defect class</th><th class='n'>Sites</th></tr></thead><tbody>{rows}</tbody></table>"
        f"{''.join(blocks)}</div></body></html>",
        encoding="utf-8",
    )
    print(f"wrote {out}  ({total} sites, {out.stat().st_size // 1024} KB)")
    for k, t, _, _ in DECISIONS:
        print(f"  {len(found.get(k, [])):5}  {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
