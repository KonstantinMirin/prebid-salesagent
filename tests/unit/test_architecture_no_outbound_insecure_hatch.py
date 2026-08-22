"""Structural guard: ADCP_OUTBOUND_ALLOW_INSECURE never comes back.

salesagent-e6h0 deleted the scheme escape hatch entirely — both production
read sites (``src/core/security/outbound_http.py``'s ``_require_tls``,
``src/core/webhook_validator.py``'s ``_require_https``) now require https
unconditionally, and every test/infra site that used to set the flag either
migrated to a real TLS-fronted origin (salesagent-40qh's primitive) or had its
assertion rewritten. A future change re-adding the env var to production code
or to the compose/host-script/tox.ini config would silently reintroduce the
plaintext-http escape hatch this ticket closed — this guard catches that at
``make quality`` time.

``.github/workflows/ci.yml``'s "creative" integration matrix group was the
last holdout (salesagent-amht.1): it now consumes
``scripts/creative-agent-stack.sh``'s own https TLS front (salesagent-40qh)
via ``steps.creative_agent.outputs.url`` instead of a plaintext
``localhost:9999`` URL, so the flag has no remaining legitimate use anywhere
in the repo.
"""

from __future__ import annotations

from pathlib import Path

from tests.unit._architecture_helpers import assert_scanned_paths_exist

_REPO_ROOT = Path(__file__).resolve().parents[2]

_FLAG = "ADCP_OUTBOUND_ALLOW_INSECURE"

# Files that must NEVER reference the flag again — the two production read
# sites, plus every infra file that used to declare it.
_MUST_NOT_CONTAIN = (
    "src/core/security/outbound_http.py",
    "src/core/webhook_validator.py",
    "docker-compose.e2e.yml",
    "tox.ini",
    "run_all_tests_host.sh",
    ".github/workflows/ci.yml",
)


def test_every_file_this_guard_scans_still_exists() -> None:
    """The scan set is a subject too, and it fails the same silent way.

    These are file PATHS, not symbols. Rename any of them and this guard keeps
    passing -- it reads nothing, so it finds nothing, which is exactly what
    compliance looks like. Measured before this was added: mutating the tuple to
    garbage changed no result anywhere.
    """
    assert_scanned_paths_exist(
        _MUST_NOT_CONTAIN,
        why=(
            "This guard asserts the insecure-egress flag never returns to these files. A path it "
            "cannot read is a file it cannot check, and the flag could come back there unnoticed."
        ),
    )


def find_flag_reintroductions(repo_root: Path, must_not_contain: tuple[str, ...]) -> list[str]:
    """Return the relpaths (of ``must_not_contain``) that DECLARE the flag again.

    Comment lines (stripped content starting with ``#``) are skipped — this
    guard bans reintroducing the actual escape hatch (a YAML key, a shell
    export, a Python read), not historical prose explaining that it was
    deleted (several files, deliberately, still say so).
    """
    hits = []
    for relpath in must_not_contain:
        path = repo_root / relpath
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if line.strip().startswith("#"):
                continue
            if _FLAG in line:
                hits.append(relpath)
                break
    return hits


def test_flag_does_not_reappear_in_production_or_infra_files() -> None:
    """None of the pinned production/infra files reference the deleted flag."""
    hits = find_flag_reintroductions(_REPO_ROOT, _MUST_NOT_CONTAIN)
    assert hits == [], (
        f"ADCP_OUTBOUND_ALLOW_INSECURE reappeared in {hits} — salesagent-e6h0 deleted this "
        "escape hatch; re-adding it anywhere in these files silently reopens a plaintext-http "
        "bypass. If a file genuinely needs it again, that is a scope decision, not a silent revert."
    )


def test_detector_catches_a_reintroduced_flag() -> None:
    """The live detector reports a file that has the flag reintroduced, synthetically."""
    synthetic_dir_marker = "src/core/security/outbound_http.py"
    # Build a fake root with one file containing the flag, to prove the
    # detector fires without touching the real tree.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / synthetic_dir_marker
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'if _env_flag("{_FLAG}"):\n    return\n')
        hits = find_flag_reintroductions(tmp_path, (synthetic_dir_marker,))
    assert hits == [synthetic_dir_marker]


def test_detector_ignores_a_file_that_never_had_the_flag() -> None:
    """The live detector does not false-positive on an unrelated file."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        marker = "docker-compose.e2e.yml"
        (tmp_path / marker).write_text("ADCP_OUTBOUND_ALLOW_PRIVATE: 'true'\n")
        hits = find_flag_reintroductions(tmp_path, (marker,))
    assert hits == []
