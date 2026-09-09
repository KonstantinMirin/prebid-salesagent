#!/usr/bin/env python3
"""Trace and compare the auth path each transport takes, and write an HTML report.

WHY THIS EXISTS. The claim under test is architectural: that MCP, A2A and REST reach ONE
decision about a credential, and differ only in how they render the refusal. That claim is
easy to assert and easy to get wrong -- an earlier version of this code read
``ToolSpec.auth`` in two places and no test noticed. A trace of the actual calls is
evidence; a comment is not.

WHAT IT DOES. Runs six requests through the REAL ASGI app -- three transports, each with an
auth-required and an auth-optional tool, all unauthenticated -- capturing every call into
``src/`` with ``sys.setprofile``. Then writes an HTML report aligning the six paths so the
convergence point (or its absence) is visible, plus wall-clock per frame.

No new dependency: ``sys.setprofile`` is stdlib. It is a PROFILE hook rather than a trace
hook, so it fires per call/return rather than per line -- enough to see the shape of a path
without the ~50x slowdown of line tracing.

    uv run python scripts/profile_auth_paths.py [--out PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = str(REPO_ROOT / "src")

#: Mount prefix of the generated REST routes; ``ToolSpec.rest.path`` is relative to it.
REST_PREFIX = "/api/v1"

# Run directly (``python scripts/...``) rather than via ``-m``, so the repo root is not on
# the path yet. Prepended at import time deliberately: this is a script, not a module
# anything imports, and the alternative is making the caller remember PYTHONPATH.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class Frame:
    """One call into ``src/`` — what ran, where, how deep, and how long."""

    depth: int
    qualname: str
    location: str
    started: float
    elapsed_ms: float = 0.0


@dataclass
class Trace:
    """One scenario's captured path plus the answer the buyer actually received."""

    transport: str
    tool: str
    auth: str
    credential: str
    status: int | None = None
    challenge: str | None = None
    code: str | None = None
    body: str = ""
    frames: list[Frame] = field(default_factory=list)

    @property
    def case(self) -> str:
        """The question this scenario asks, independent of which transport asks it."""
        return f"{self.credential} credential, auth={self.auth}"

    @property
    def label(self) -> str:
        return f"{self.transport} · {self.tool} ({self.case})"


class SrcTracer:
    """Capture calls whose code object lives under ``src/``.

    Everything else -- framework internals, stdlib, the test client -- is dropped. The
    point is the shape of OUR path, and unfiltered output is thousands of frames of
    starlette and pydantic that hide it.
    """

    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self._stack: list[Frame] = []

    def __enter__(self) -> SrcTracer:
        # BOTH hooks. TestClient runs the ASGI app on a worker thread via anyio's portal,
        # and sys.setprofile only arms the CALLING thread -- which is why the first run of
        # this script captured zero frames while the requests plainly worked.
        # threading.setprofile arms threads created AFTER it is set.
        threading.setprofile(self._hook)
        sys.setprofile(self._hook)
        return self

    def __exit__(self, *exc: object) -> None:
        sys.setprofile(None)
        threading.setprofile(None)
        now = time.perf_counter()
        for frame in self._stack:  # anything still open when the request ended
            frame.elapsed_ms = (now - frame.started) * 1000

    def _hook(self, frame: object, event: str, _arg: object) -> None:
        code = getattr(frame, "f_code", None)
        if code is None or not code.co_filename.startswith(SRC):
            return
        if event == "call":
            rel = os.path.relpath(code.co_filename, REPO_ROOT)
            captured = Frame(
                depth=len(self._stack),
                qualname=code.co_qualname,
                location=f"{rel}:{code.co_firstlineno}",
                started=time.perf_counter(),
            )
            self._stack.append(captured)
            self.frames.append(captured)
        elif event == "return" and self._stack:
            done = self._stack.pop()
            done.elapsed_ms = (time.perf_counter() - done.started) * 1000


# Frames that matter to the auth question. The full trace is thousands of calls; these are
# the ones whose presence, order and SHARING across transports is the actual claim.
LANDMARKS = (
    "UnifiedAuthMiddleware.__call__",
    "AuthChallengeResponder",
    "credential_present",
    "adcp_error_code_in",
    "challenge_for_code",
    "resolve_identity",
    "resolve_identity_from_context",
    "_resolve_a2a_identity",
    "_require_auth_dep",
    "_resolve_auth_dep",
    "MCPAuthMiddleware.on_call_tool",
    "invoke_tool",
    "invoke",
    "_impl",
    "_envelope_response",
    "_restore_a2a_wire_integers",
)


def is_landmark(qualname: str) -> bool:
    return any(mark in qualname for mark in LANDMARKS)


async def run_scenarios() -> list[Trace]:
    """Drive six unauthenticated requests through the real app, tracing each.

    In-thread, via httpx's ASGI transport, with the app's lifespan entered by hand. Not
    TestClient: it runs the app on an anyio portal THREAD, and a profile hook armed on the
    caller never sees it -- the first version of this script captured zero frames for five
    of six scenarios for exactly that reason, while the requests themselves worked fine.
    One thread means ``sys.setprofile`` sees everything.
    """
    os.environ.setdefault("ADCP_RUN_BACKGROUND_SCHEDULERS", "false")
    import logging

    logging.disable(logging.CRITICAL)

    import httpx

    from src.app import app
    from src.core.auth_middleware import adcp_error_code_in
    from src.core.tools.registry import TOOLS

    required = next(n for n, s in TOOLS.items() if s.auth == "required" and s.rest)
    optional = next(n for n, s in TOOLS.items() if s.auth == "optional" and s.rest)
    mcp_headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    # a2a-sdk 1.0 validates this header BEFORE dispatching a skill: without it the request
    # is refused -32009 ("A2A version '0.3' is not supported") and never reaches auth at
    # all -- which is exactly how this profile first read A2A as answering 200 to an
    # unauthenticated auth-required call.
    a2a_headers = {"Content-Type": "application/json", "A2A-Version": "1.0"}

    def a2a_body(skill: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"data": {"skill": skill, "parameters": {}}}],
                }
            },
        }

    # Two credential states, because ONE of them is not enough to see the seam. With no
    # credential at all the three transports agree perfectly, and a report built on that
    # alone reads as "converged". The disagreement only appears when a credential IS
    # presented and does not resolve -- an auth="optional" tool answers AUTH_INVALID on MCP
    # and A2A and 200 on REST.
    credentials = {
        "no": {},
        "invalid": {"x-adcp-auth": "profile-probe-not-a-real-token"},
    }

    traces: list[Trace] = []
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://profile") as client:
            for tool, auth in ((required, "required"), (optional, "optional")):
                binding = TOOLS[tool].rest
                rest_path = REST_PREFIX + binding.path.replace("{media_buy_id}", "x")
                for credential, cred_headers in credentials.items():
                    calls = {
                        "MCP": lambda t=tool, h=cred_headers: client.post(
                            "/mcp/",
                            json={
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "tools/call",
                                "params": {"name": t, "arguments": {}},
                            },
                            headers={**mcp_headers, **h},
                        ),
                        "A2A": lambda t=tool, h=cred_headers: client.post(
                            "/a2a", json=a2a_body(t), headers={**a2a_headers, **h}
                        ),
                        "REST": lambda p=rest_path, v=binding.verb, h=cred_headers: client.request(
                            v, p, json={}, headers=h
                        ),
                    }
                    for name, call in calls.items():
                        trace = Trace(transport=name, tool=tool, auth=auth, credential=credential)
                        with SrcTracer() as tracer:
                            response = await call()
                        trace.frames = tracer.frames
                        trace.status = response.status_code
                        trace.challenge = response.headers.get("www-authenticate")
                        trace.body = response.text[:2000]
                        try:
                            trace.code = adcp_error_code_in(response.json())
                        except Exception:  # noqa: BLE001 - a non-JSON body simply has no code
                            trace.code = None
                        traces.append(trace)
    return traces


def render(traces: list[Trace]) -> str:
    """Build the report: the verdict first, then the evidence it rests on."""

    def path_of(trace: Trace) -> list[Frame]:
        return [f for f in trace.frames if is_landmark(f.qualname)]

    by_case: dict[str, list[Trace]] = {}
    for trace in traces:
        by_case.setdefault(trace.case, []).append(trace)

    # The verdict. Three transports asked the SAME question must give the same answer: same
    # status, same challenge, same code. Anything else is a divergence, and it is the report's
    # job to say so rather than leave it for a reader to spot in a table.
    verdicts: list[tuple[str, bool, dict[str, str]]] = []
    for case, group in by_case.items():
        answers = {t.transport: f"{t.status} · {t.challenge or '—'} · {t.code or '—'}" for t in group}
        verdicts.append((case, len(set(answers.values())) == 1, answers))

    # The claim: every transport reaches resolve_identity, and nothing else decides.
    deciders = {"resolve_identity", "resolve_identity_from_context"}
    rows = []
    for trace in traces:
        names = [f.qualname for f in trace.frames]
        reached = sorted({n.split(".")[-1] for n in names} & deciders)
        rows.append((trace, reached, len(trace.frames), path_of(trace)))

    parts: list[str] = []
    parts.append(
        """<title>Auth path by transport</title>
<style>
 :root{--bg:#fff;--fg:#16181d;--muted:#5b6472;--line:#e3e6ea;--accent:#0b5cad;--ok:#0a7d33;--warn:#a4551a;--code:#f6f7f9}
 :root:not([data-theme=light]) @media (prefers-color-scheme:dark){}
 @media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14161a;--fg:#e7e9ec;--muted:#98a2b3;--line:#2a2f37;--accent:#6aa9e9;--ok:#5fce86;--warn:#e0a56b;--code:#1c1f25}}
 :root[data-theme=dark]{--bg:#14161a;--fg:#e7e9ec;--muted:#98a2b3;--line:#2a2f37;--accent:#6aa9e9;--ok:#5fce86;--warn:#e0a56b;--code:#1c1f25}
 body{background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;padding:2.2rem 1.4rem 5rem}
 main{max-width:1180px;margin:0 auto}
 h1{font-size:1.7rem;margin:0 0 .3rem} h2{font-size:1.15rem;margin:2.4rem 0 .7rem;padding-bottom:.3rem;border-bottom:1px solid var(--line)}
 .sub{color:var(--muted);margin:0 0 1.6rem}
 table{border-collapse:collapse;width:100%;font-size:13.5px;margin:.6rem 0 1.2rem}
 th,td{text-align:left;padding:.42rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}
 th{color:var(--muted);font-weight:600;white-space:nowrap}
 code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
 .ok{color:var(--ok);font-weight:600}.warn{color:var(--warn);font-weight:600}
 .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:1rem}
 .col{border:1px solid var(--line);border-radius:8px;overflow:hidden}
 .col h3{margin:0;padding:.55rem .75rem;background:var(--code);font-size:13px;border-bottom:1px solid var(--line)}
 ol{margin:0;padding:.5rem .5rem .6rem 2.2rem} li{margin:.12rem 0;font-family:ui-monospace,Menlo,monospace;font-size:12px}
 li.shared{color:var(--fg)} li.only{color:var(--warn)}
 .scroll{overflow-x:auto}
 .note{background:var(--code);border-left:3px solid var(--accent);padding:.6rem .85rem;border-radius:0 6px 6px 0;margin:.8rem 0;color:var(--muted);font-size:13.5px}
</style>
<main>
<h1>Auth path by transport</h1>
<p class="sub">Twelve requests through the real ASGI app — three transports, two tools
(auth-required and auth-optional), two credential states (absent and invalid) — traced with
<code>sys.setprofile</code>. Every call into <code>src/</code> was captured; the paths below are
filtered to the frames that decide or render an auth outcome.</p>"""
    )

    agreed = sum(1 for _, same, _ in verdicts if same)
    parts.append(f"<h2>Verdict — {agreed} of {len(verdicts)} cases agree across transports</h2>")
    parts.append('<div class="scroll"><table>')
    parts.append("<tr><th>case</th><th>agree?</th><th>MCP</th><th>A2A</th><th>REST</th></tr>")
    for case, same, answers in verdicts:
        mark = '<span class="ok">yes</span>' if same else '<span class="warn">NO</span>'
        cells = "".join(
            f'<td class="mono{"" if same else " warn"}">{html.escape(answers.get(t, "—"))}</td>'
            for t in ("MCP", "A2A", "REST")
        )
        parts.append(f"<tr><td>{html.escape(case)}</td><td>{mark}</td>{cells}</tr>")
    parts.append("</table></div>")
    parts.append(
        '<div class="note">Each cell is <code>status · WWW-Authenticate · AdCP code</code>. '
        "The three transports are asked the same question in each row, so a row that does not "
        "agree is a divergence in behaviour, not in rendering.</div>"
    )

    parts.append('<h2>What each transport answered</h2><div class="scroll"><table>')
    parts.append(
        "<tr><th>transport</th><th>tool</th><th>auth</th><th>credential</th><th>status</th>"
        "<th>WWW-Authenticate</th><th>code</th><th>decided by</th><th>src frames</th></tr>"
    )
    for trace, reached, total, _ in rows:
        decided = ", ".join(reached) or "—"
        cls = "ok" if reached else "warn"
        parts.append(
            f"<tr><td><b>{html.escape(trace.transport)}</b></td><td class=mono>{html.escape(trace.tool)}</td>"
            f"<td>{trace.auth}</td><td>{trace.credential}</td>"
            f"<td class={'ok' if trace.status in (401, 200) else 'warn'}>{trace.status}</td>"
            f"<td class=mono>{html.escape(trace.challenge or '—')}</td>"
            f"<td class=mono>{html.escape(trace.code or '—')}</td>"
            f"<td class='mono {cls}'>{html.escape(decided)}</td><td>{total}</td></tr>"
        )
    parts.append("</table></div>")

    for auth, group in sorted(by_case.items()):
        paths = {t.transport: [f.qualname for f in path_of(t)] for t in group}
        shared = set.intersection(*(set(v) for v in paths.values())) if paths else set()
        parts.append(f"<h2>Path comparison — {html.escape(auth)}</h2>")
        parts.append(
            f'<div class="note">Frames in <b>every</b> transport are shown plain; frames unique to one are '
            f"highlighted. Shared frames: <b>{len(shared)}</b>.</div>"
        )
        parts.append('<div class="cols">')
        for trace in group:
            parts.append(f'<div class="col"><h3>{html.escape(trace.label)} → {trace.status}</h3><ol>')
            for frame in path_of(trace):
                cls = "shared" if frame.qualname in shared else "only"
                parts.append(
                    f'<li class="{cls}">{"&nbsp;" * frame.depth}{html.escape(frame.qualname)}'
                    f' <span style="color:var(--muted)">{frame.elapsed_ms:.2f}ms</span></li>'
                )
            parts.append("</ol></div>")
        parts.append("</div>")

    parts.append("<h2>Slowest src frames per scenario</h2><div class=scroll><table>")
    parts.append("<tr><th>scenario</th><th>frame</th><th>location</th><th>ms</th></tr>")
    for trace in traces:
        for frame in sorted(trace.frames, key=lambda f: -f.elapsed_ms)[:5]:
            parts.append(
                f"<tr><td>{html.escape(trace.label)}</td><td class=mono>{html.escape(frame.qualname)}</td>"
                f"<td class=mono>{html.escape(frame.location)}</td><td>{frame.elapsed_ms:.2f}</td></tr>"
            )
    parts.append("</table></div></main>")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/development/auth-transport-paths.html")
    parser.add_argument("--json", default="", help="also write the raw trace as JSON")
    args = parser.parse_args()

    traces = asyncio.run(run_scenarios())
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    # Trailing newline: the report is committed, and end-of-file-fixer rewrites a file
    # without one, so every regeneration would otherwise dirty the tree at commit time.
    out.write_text(render(traces) + "\n", encoding="utf-8")

    if args.json:
        raw = [
            {
                "transport": t.transport,
                "tool": t.tool,
                "auth": t.auth,
                "credential": t.credential,
                "status": t.status,
                "body": t.body,
                "challenge": t.challenge,
                "code": t.code,
                "frames": [
                    {"d": f.depth, "q": f.qualname, "at": f.location, "ms": round(f.elapsed_ms, 3)} for f in t.frames
                ],
            }
            for t in traces
        ]
        (REPO_ROOT / args.json).write_text(json.dumps(raw, indent=2), encoding="utf-8")

    for t in traces:
        print(
            f"  {t.transport:5} {t.credential:8} {t.auth:9} {t.tool:22} -> "
            f"{t.status} {t.challenge or '-':28} {t.code or '-':16} {len(t.frames)} frames"
        )

    # Fail loudly on a divergence. A report nobody opens is a report nobody acts on, and the
    # whole point of this script is that the three transports must answer alike.
    by_case: dict[str, set[str]] = {}
    for t in traces:
        by_case.setdefault(t.case, set()).add(f"{t.status}·{t.challenge}·{t.code}")
    diverged = [case for case, answers in by_case.items() if len(answers) > 1]
    print(f"\nreport: {out}")
    if diverged:
        print(f"DIVERGENCE in {len(diverged)} of {len(by_case)} cases: {', '.join(diverged)}")
    return 1 if diverged else 0


if __name__ == "__main__":
    raise SystemExit(main())
