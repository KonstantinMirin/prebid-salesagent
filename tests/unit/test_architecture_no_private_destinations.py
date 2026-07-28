"""Guard: the SSRF relaxation is a TEST argument and never reaches production.

``allow_private_destinations`` (and the SDK's underlying ``allow_private``) turns
off the pin that stops key discovery from being pointed at RFC1918, link-local
and cloud-metadata addresses. Tests need it — the local stack is
``http://localhost:<port>`` — and nothing in ``src/`` may pass it, because a
resolver that follows a counterparty-supplied URL into the private network is a
straight SSRF.

#1291 A3 (salesagent-z6nr.9), R-L: A3 has no production reader to gate, so the
acceptance is discharged mechanically here rather than with a runtime flag that
would itself be settable in production. When B1 (salesagent-z6nr.12) wires the
inbound verifier — where the resolver DOES run in production — this guard is what
makes an accidental production call site fail the build.
"""

from __future__ import annotations

import pytest

from tests.unit._architecture_helpers import (
    format_failure,
    iter_call_expressions,
    repo_root,
    safe_parse,
    src_python_files,
)

# Both spellings: ours (``adcp.signing.async_resolve_agent``) and the SDK's own
# lower-level fetchers (``adcp.signing.jwks`` / ``brand_jwks`` / the IP-pinned
# transport builders).
FORBIDDEN_KEYWORDS = {"allow_private_destinations", "allow_private"}

_KNOWN_BAD_SNIPPET = "resolve_agent(url, allow_private_destinations=True)\n"


def _find_private_destination_violations(repo) -> list[str]:
    violations: list[str] = []
    for path in src_python_files(repo):
        tree = safe_parse(path)
        if tree is None:
            continue
        for node in iter_call_expressions(tree):
            for keyword in node.keywords:
                if keyword.arg in FORBIDDEN_KEYWORDS:
                    location = path.relative_to(repo)
                    violations.append(f"{location}:{node.lineno}: passes {keyword.arg}=")
    return violations


@pytest.mark.arch_guard
def test_no_src_call_site_relaxes_private_destinations() -> None:
    violations = _find_private_destination_violations(repo_root())
    assert not violations, format_failure(
        summary="allow_private_destinations / allow_private must not be passed from src/",
        violations=violations,
        fix_hint=(
            "Key discovery in production must keep the SSRF pin. Relax it only inside a test, against a local stack."
        ),
        docs_link="docs/development/structural-guards.md",
    )


@pytest.mark.arch_guard
def test_private_destination_detector_catches_known_bad_snippet(tmp_path) -> None:
    bad_file = tmp_path / "src" / "probe.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(_KNOWN_BAD_SNIPPET, encoding="utf-8")

    assert _find_private_destination_violations(tmp_path), (
        "Detector must flag a src/ call site passing allow_private_destinations"
    )
