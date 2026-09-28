"""Structural guard: where the Apx-Incoming-Host fold is declared, every proxying location does it.

``config/nginx/nginx-multi-tenant.conf`` declares ``map $http_apx_incoming_host
$tenant_host`` and is the premise the vendor-header deletion rests on. The app reads a
tenant from exactly two inputs -- ``Host`` against ``tenants.virtual_host``, and an
``x-adcp-tenant`` the client sent -- and that is only true while the proxy folds
``Apx-Incoming-Host`` into ``Host`` and drops the header on the way through. A location
that forwards it hands the app a third spelling of the first input, and two readers of one
fact disagree about which wins.

So each location proxying to the upstream must do BOTH:

* ``proxy_set_header Host $tenant_host;`` -- the folded host
* ``proxy_set_header Apx-Incoming-Host "";`` -- and nothing downstream of the fold

The file is exact today at 14 proxying locations. It got there through a defect worth
encoding: ``location = /`` carried a pre-existing ``Apx-Incoming-Host`` passthrough BELOW
the inserted strip, nginx applied the LAST directive, and so one location forwarded the
header while the file read as though all 14 dropped it. Presence of the strip is therefore
not the check -- the check is what the last directive for that header says.

WHICH FILES ARE GRADED IS DERIVED, not listed: a config is graded if it declares the fold.
That is the only place the vendor header means anything, so a second config adopting the
fold is covered the day it does, and the three that do not are not held to a rule they never
took on.

Two nginx semantics the parser implements rather than assumes, because a guard that models
the wrong nginx grades the wrong file:

* **Last wins within a level.** The defect above is the evidence.
* **Array directives are replaced, not merged, on inheritance.** A location declaring ANY
  ``proxy_set_header`` inherits NONE from its server; one declaring none inherits the whole
  set (nginx ``ngx_http_proxy_module``: inherited "if and only if there are no
  proxy_set_header directives defined on the current level"). So a deployment that hoists
  the pair to the server level passes, and one that hoists it and then adds an unrelated
  header to a location fails -- which is what nginx does.

Every detector below is proven against a synthetic regression. A detector that cannot go red
is not a guard (tests/unit/CLAUDE.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NGINX_DIR = _REPO_ROOT / "config" / "nginx"

#: The declaration that makes a config subject to this guard.
_FOLD_DECLARATION = re.compile(r"map\s+\$http_apx_incoming_host\s+\$tenant_host\s*\{")

#: header name (lowercased, since HTTP header names are case-insensitive) -> the value the
#: last directive for it must carry, and why.
_REQUIRED = {
    "host": ("$tenant_host", "so the folded host is what names the tenant"),
    "apx-incoming-host": ('""', "so the vendor header never reaches the app as a second spelling of Host"),
}


@dataclass
class _Block:
    """One brace-delimited nginx block: its opening text, its simple directives, its children."""

    header: str
    line: int
    directives: list[tuple[str, int]] = field(default_factory=list)
    children: list[_Block] = field(default_factory=list)


def _strip_comments(text: str) -> str:
    """Drop ``#`` to end of line, preserving the line count so reports name real lines."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def parse_nginx(text: str) -> _Block:
    """The block tree. Enough nginx to answer this question and deliberately no more.

    Raises on unbalanced braces rather than guessing: a config this cannot parse must fail
    loudly, because a parser that quietly finds no locations makes the guard vacuous.
    """
    root = _Block(header="", line=0)
    stack = [root]
    token = ""
    line = 1
    token_line = 1

    for raw in _strip_comments(text):
        char = " " if raw == "\n" else raw
        if raw == "\n":
            line += 1

        if char == "{":
            block = _Block(header=" ".join(token.split()), line=token_line)
            stack[-1].children.append(block)
            stack.append(block)
            token = ""
        elif char == "}":
            if len(stack) == 1:
                raise ValueError(f"unbalanced '}}' at line {line}")
            stack.pop()
            token = ""
        elif char == ";":
            stack[-1].directives.append((" ".join(token.split()), token_line))
            token = ""
        else:
            if not token.strip():
                token_line = line
            token += char

    if len(stack) != 1:
        raise ValueError(f"unbalanced '{{': {len(stack) - 1} block(s) left open")
    return root


def _proxy_set_headers(block: _Block) -> list[tuple[str, str, int]]:
    """``(name lowercased, value, line)`` for each ``proxy_set_header`` here, in file order."""
    found = []
    for directive, line in block.directives:
        parts = directive.split(None, 2)
        if len(parts) >= 2 and parts[0] == "proxy_set_header":
            found.append((parts[1].lower(), parts[2].strip() if len(parts) > 2 else "", line))
    return found


def _effective_proxy_set_headers(chain: list[_Block]) -> list[tuple[str, str, int]]:
    """The set nginx actually applies: the innermost level that declares any, or none."""
    for block in reversed(chain):
        declared = _proxy_set_headers(block)
        if declared:
            return declared
    return []


def proxying_location_chains(root: _Block) -> list[list[_Block]]:
    """Every ``location`` block that proxies, as the chain of blocks enclosing it.

    A ``location`` holding no ``proxy_pass`` sends nothing upstream -- the three
    ``location = /admin`` redirect blocks -- so it has no header to get wrong.
    """
    chains: list[list[_Block]] = []

    def walk(block: _Block, ancestry: list[_Block]) -> None:
        here = [*ancestry, block]
        if block.header.split(None, 1)[:1] == ["location"] and any(
            directive.startswith("proxy_pass ") for directive, _ in block.directives
        ):
            chains.append(here)
        for child in block.children:
            walk(child, here)

    for child in root.children:
        walk(child, [root])
    return chains


def find_locations_not_folding_tenant_host(path: Path) -> list[str]:
    """One message per (location, required header) pair the config gets wrong.

    Returns ``[]`` for a config that does not declare the fold: the vendor header means
    nothing there.
    """
    text = path.read_text()
    if not _FOLD_DECLARATION.search(text):
        return []

    problems: list[str] = []
    for chain in proxying_location_chains(parse_nginx(text)):
        location = chain[-1]
        applied = _effective_proxy_set_headers(chain)
        where = f"{path.name}:{location.line} `{location.header}`"

        for name, (expected, why) in _REQUIRED.items():
            directives = [(value, line) for header, value, line in applied if header == name]
            if not directives:
                problems.append(f"{where} proxies upstream but never sets {name} -- {why}")
                continue
            value, line = directives[-1]  # nginx applies the LAST directive at a level
            if value != expected:
                problems.append(
                    f"{where} ends up sending {name}: {value} (line {line}, the last of "
                    f"{len(directives)} directive(s) for it); expected {expected} -- {why}"
                )
    return problems


def _configs() -> list[Path]:
    return sorted(p for p in _NGINX_DIR.iterdir() if p.is_file())


# ---------------------------------------------------------------------------
# The invariant, on the real files
# ---------------------------------------------------------------------------


def test_every_proxying_location_folds_the_tenant_host() -> None:
    problems = [message for path in _configs() for message in find_locations_not_folding_tenant_host(path)]
    assert not problems, "nginx locations that break the Apx-Incoming-Host fold:\n" + "\n".join(problems)


def test_the_fold_is_declared_somewhere() -> None:
    """Otherwise the guard above grades nothing at all and passes for that reason."""
    declaring = [path.name for path in _configs() if _FOLD_DECLARATION.search(path.read_text())]
    assert declaring, f"no config under {_NGINX_DIR} declares the $tenant_host fold, so nothing is graded"


def test_the_parser_reaches_every_proxying_location() -> None:
    """The count the guard examined equals the ``proxy_pass`` directives in the file.

    The other half of the anti-vacuity check: a parser bug that dropped a server block would
    leave the guard green while saying nothing about the locations inside it.
    """
    for path in _configs():
        text = path.read_text()
        if not _FOLD_DECLARATION.search(text):
            continue
        examined = proxying_location_chains(parse_nginx(text))
        expected = _strip_comments(text).count("proxy_pass ")
        assert len(examined) == expected, (
            f"{path.name} has {expected} proxy_pass directive(s) but the guard examined "
            f"{len(examined)} location(s): {[chain[-1].header for chain in examined]}"
        )


# ---------------------------------------------------------------------------
# The detectors, proven against synthetic regressions
# ---------------------------------------------------------------------------

_FOLD = """
http {
    map $http_apx_incoming_host $tenant_host {
        ""      $host;
        default $http_apx_incoming_host;
    }
    upstream mcp_server { server localhost:8080; }
    server {
        listen 0.0.0.0:8000;
%s
    }
}
"""

_GOOD_LOCATION = """
        location /health {
            proxy_pass http://mcp_server/health;
            proxy_set_header Host $tenant_host;
            proxy_set_header Apx-Incoming-Host "";
        }
"""


def _write(tmp_path: Path, locations: str, *, name: str = "nginx-probe.conf") -> Path:
    path = tmp_path / name
    path.write_text(_FOLD % locations)
    return path


def test_the_config_as_written_passes_the_detector(tmp_path: Path) -> None:
    assert find_locations_not_folding_tenant_host(_write(tmp_path, _GOOD_LOCATION)) == []


def test_detector_catches_a_fifteenth_location_added_without_the_pair(tmp_path: Path) -> None:
    """The regression the guard exists for: a new location that proxies and folds nothing."""
    added = (
        _GOOD_LOCATION
        + """
        location /new-thing/ {
            proxy_pass http://mcp_server/new-thing/;
            proxy_set_header X-Real-IP $remote_addr;
        }
"""
    )
    problems = find_locations_not_folding_tenant_host(_write(tmp_path, added))

    assert len(problems) == 2, problems
    assert all("location /new-thing/" in message for message in problems)
    assert any("never sets host" in message for message in problems)
    assert any("never sets apx-incoming-host" in message for message in problems)


def test_detector_catches_a_passthrough_below_the_strip(tmp_path: Path) -> None:
    """The historical defect: the strip is present, and a later directive undoes it."""
    overridden = """
        location = / {
            proxy_pass http://mcp_server/;
            proxy_set_header Host $tenant_host;
            proxy_set_header Apx-Incoming-Host "";
            proxy_set_header Apx-Incoming-Host $http_apx_incoming_host;
        }
"""
    problems = find_locations_not_folding_tenant_host(_write(tmp_path, overridden))

    assert len(problems) == 1, problems
    assert "apx-incoming-host: $http_apx_incoming_host" in problems[0]
    assert "the last of 2 directive(s)" in problems[0]


def test_detector_catches_host_bypassing_the_fold(tmp_path: Path) -> None:
    """``$host`` is the unfolded header, so behind the vendor proxy it names this backend."""
    unfolded = """
        location / {
            proxy_pass http://mcp_server;
            proxy_set_header Host $host;
            proxy_set_header Apx-Incoming-Host "";
        }
"""
    problems = find_locations_not_folding_tenant_host(_write(tmp_path, unfolded))

    assert len(problems) == 1, problems
    assert "host: $host" in problems[0]


def test_detector_ignores_a_location_that_proxies_nothing(tmp_path: Path) -> None:
    redirect = (
        _GOOD_LOCATION
        + """
        location = /admin {
            return 301 $scheme://$host/admin/;
        }
"""
    )
    assert find_locations_not_folding_tenant_host(_write(tmp_path, redirect)) == []


def test_detector_ignores_a_config_that_never_declared_the_fold(tmp_path: Path) -> None:
    """The three configs with no vendor proxy in front of them are not held to its rule."""
    path = tmp_path / "nginx-no-fold.conf"
    path.write_text(
        """
http {
    upstream mcp_server { server localhost:8080; }
    server {
        location / {
            proxy_pass http://mcp_server;
            proxy_set_header Host $host;
        }
    }
}
"""
    )
    assert find_locations_not_folding_tenant_host(path) == []


def test_detector_honours_nginx_array_directive_inheritance(tmp_path: Path) -> None:
    """The pair hoisted to the server level covers a location declaring no header of its own.

    And stops covering one that declares any, because nginx replaces the inherited set
    wholesale rather than merging into it.
    """
    hoisted = """
        proxy_set_header Host $tenant_host;
        proxy_set_header Apx-Incoming-Host "";

        location /inherits/ {
            proxy_pass http://mcp_server/inherits/;
        }

        location /replaces/ {
            proxy_pass http://mcp_server/replaces/;
            proxy_set_header X-Real-IP $remote_addr;
        }
"""
    problems = find_locations_not_folding_tenant_host(_write(tmp_path, hoisted))

    assert all("location /replaces/" in message for message in problems), problems
    assert len(problems) == 2, problems


def test_parser_refuses_an_unbalanced_config(tmp_path: Path) -> None:
    """A config this cannot parse fails the run; it does not silently examine nothing."""
    path = tmp_path / "nginx-broken.conf"
    path.write_text(_FOLD % _GOOD_LOCATION + "}\n")

    with pytest.raises(ValueError, match="unbalanced"):
        find_locations_not_folding_tenant_host(path)
