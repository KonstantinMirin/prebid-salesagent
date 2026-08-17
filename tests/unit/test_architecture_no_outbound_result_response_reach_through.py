"""Structural guard: OutboundResult closes over content/text/headers, not httpx.Response.

salesagent-tbrk.5: ``OutboundResult`` was half-built -- the body bytes were
already held as ``_body`` but not surfaced, so the TID251 raw-egress import
ban was satisfied while four call sites still reached through
``OutboundResult.response`` to program directly against ``httpx.Response``
(triage F8/R5). The seam had to poke ``response._content`` (``_attach_body``,
a private-attribute write on a third-party object) purely to keep
``.text``/``.json()`` working on a streamed-then-closed body for that
reach-through -- a hack that only exists to serve the leak this guard closes.

This guard has three legs, all against the CURRENT tree (before the lane's
implement atom lands):

1. ``OutboundResult`` still declares a ``response`` field (RED) -- once the
   type closes over ``status_code``/``headers``/``content``/``attempts``/
   ``duration_seconds`` only, a caller cannot hold or reach through an httpx
   object at all, which is what makes leg 3 permanently true rather than
   true-until-the-next-caller.
2. ``_attach_body`` still exists on the seam module (RED) -- it deletes
   alongside ``.response``; nothing needs to poke a private httpx attribute
   once the body is surfaced directly on the closed type.
3. The four inventoried consumers still read ``.response`` off a seam result
   (RED, exactly four sites) -- ``src/adapters/broadstreet/client.py``,
   ``src/adapters/gam_reporting_service.py``, ``src/adapters/triton_digital.py``,
   ``src/core/creative_agent_registry.py``. Scoped to exactly these four files
   (not a repo-wide ``.response`` sweep): the attribute name ``response``
   alone is not seam-specific -- ``CreateMediaBuyResult.response`` in
   ``src/core/tools/media_buy_create.py`` and ``src/core/schemas/_base.py``,
   and ``httpx.HTTPStatusError.response`` in
   ``src/core/helpers/outbound_error_mapping.py:204-205``, are unrelated
   types that share the same attribute name and would false-positive a
   name-only, repo-wide scan. ``src/core/security/outbound_http.py`` itself
   (the type's own definition, reading ``self.response.status_code``) is
   excluded for the same reason -- it's the definition, not a consumer.

All three legs turn GREEN together once the lane's implement atom lands:
``OutboundResult`` moves to ``src/core/security/egress/response.py`` with no
``response`` field, ``_attach_body`` and the old field-holding class delete
from ``outbound_http.py``, and the four sites read ``.content``/``.text``/
``.headers``/``.json()`` directly off the closed result.
"""

from __future__ import annotations

import ast
import dataclasses

from src.core.security import outbound_http
from tests.unit._architecture_helpers import parse_module, repo_root

# The exact four-site inventory this lane names (salesagent-tbrk.5 design,
# "Verified starting state" + "4-site inventory confirmed complete"). Scoping
# the scan to exactly these files -- not a repo-wide ``.response`` sweep --
# is what keeps the detector from false-positiving on unrelated types that
# happen to share the attribute name (see module docstring, leg 3).
_CONSUMER_FILES = (
    "src/adapters/broadstreet/client.py",
    "src/adapters/gam_reporting_service.py",
    "src/adapters/triton_digital.py",
    "src/core/creative_agent_registry.py",
)


def find_response_attribute_reads(tree: ast.Module) -> list[int]:
    """Line numbers of any ``<expr>.response`` attribute read in *tree*.

    Shaped as a ``(tree) -> list[int]`` detector, matching the sibling
    architecture guards (e.g. ``test_architecture_no_destination_rewrite.py``),
    so the meta-tests below can feed it synthetic sources directly. Matches
    a bare ``x.response`` (creative_agent_registry.py's ``response =
    result.response``) equally to a chained ``x.response.content``
    (broadstreet's ``result.response.content``) -- both are Attribute nodes
    with ``attr == "response"``; the chain is just a parent node the walk
    also visits separately.
    """
    return sorted(node.lineno for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "response")


def _scan_consumer_files() -> dict[str, list[int]]:
    """Map each of the four inventoried consumer files to its ``.response`` read lines."""
    repo = repo_root()
    violations: dict[str, list[int]] = {}
    for rel_path in _CONSUMER_FILES:
        lines = find_response_attribute_reads(parse_module(repo / rel_path))
        if lines:
            violations[rel_path] = lines
    return violations


class TestOutboundResultHasNoResponseField:
    """``OutboundResult`` must not expose an httpx type as a public field.

    RED today: the field is exactly ``response: httpx.Response``
    (outbound_http.py:349, per the design's verified starting state). GREEN
    once the lane's implement atom closes the type over content/text/headers
    only. Imports through the facade (``src.core.security.outbound_http``),
    the same path every real consumer uses -- valid both before AND after
    the implement atom, since the facade re-exports ``OutboundResult`` from
    the new ``egress.response`` module unchanged (design: "every ``from
    src.core.security.outbound_http import OutboundResult`` site is
    untouched").
    """

    def test_no_response_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(outbound_http.OutboundResult)}
        assert "response" not in field_names, (
            f"OutboundResult still declares a 'response' field ({sorted(field_names)}) -- "
            "a caller holding this field can reach through to any httpx.Response attribute, "
            "which is the exact leak salesagent-tbrk.5 closes. The field must delete; status_code/"
            "headers/content/attempts/duration_seconds must be constructed directly, not derived "
            "from a held httpx.Response."
        )


class TestAttachBodyDeleted:
    """``_attach_body`` (the ``response._content = body`` private-attribute poke) must delete.

    RED today: it exists at outbound_http.py (~549-560) and is called from
    ``_result``. GREEN once the closed ``OutboundResult`` surfaces ``content``
    directly, so nothing needs the streamed-then-closed httpx response to be
    readable through its own ``.content``/``.text`` any more.
    """

    def test_attach_body_no_longer_exists(self) -> None:
        assert not hasattr(outbound_http, "_attach_body"), (
            "_attach_body still exists on src.core.security.outbound_http -- it existed only to "
            "poke httpx.Response._content so the reach-through's .text/.json() kept working on a "
            "streamed-then-closed body; once OutboundResult surfaces content/text/json() directly "
            "there is nothing left for it to do and it must delete."
        )


class TestNoResponseReachThroughInConsumers:
    """The four inventoried consumers must not read ``.response`` off a seam result.

    RED today: exactly four sites (one per file). GREEN once each site reads
    ``.content``/``.text``/``.headers``/``.json()`` directly off the closed
    ``OutboundResult`` instead of indirecting through a held ``httpx.Response``.
    """

    def test_no_response_reach_through(self) -> None:
        offenders = _scan_consumer_files()
        assert not offenders, (
            "OutboundResult.response reach-through found in consumer(s):\n\n"
            + "\n".join(f"  {path}: line(s) {lines}" for path, lines in sorted(offenders.items()))
            + "\n\nEach of these must read .content/.text/.headers/.json() directly off the "
            "OutboundResult it already holds -- not indirect through a held httpx.Response via "
            ".response. This is the exact reach-through salesagent-tbrk.5 closes (triage F8/R5)."
        )


class TestDetectorCorrectness:
    """The ``.response`` attribute-read detector's own fitness, on synthetic sources."""

    def test_catches_bare_attribute_read(self) -> None:
        """``response = result.response`` (creative_agent_registry.py's exact shape)."""
        tree = ast.parse("response = result.response\n")
        assert find_response_attribute_reads(tree) == [1]

    def test_catches_chained_attribute_read(self) -> None:
        """``result.response.content`` (broadstreet's exact shape) -- one hit per Attribute node."""
        tree = ast.parse("body = result.response.content\n")
        # Two Attribute nodes match attr=='response'... no: only the inner one has attr='response';
        # the outer node's attr is 'content'. Exactly one hit.
        assert find_response_attribute_reads(tree) == [1]

    def test_catches_conditional_expression_read(self) -> None:
        """``result.json() if result.response.content else None`` (broadstreet's literal line)."""
        tree = ast.parse("body = result.json() if result.response.content else None\n")
        assert find_response_attribute_reads(tree) == [1]

    def test_ignores_unrelated_attribute_names(self) -> None:
        """A `.content` or `.headers` read alone is not a `.response` reach-through."""
        tree = ast.parse("body = result.content\nheaders = result.headers\n")
        assert find_response_attribute_reads(tree) == []

    def test_current_consumer_files_match_the_inventory_exactly(self) -> None:
        """Non-vacuity, post-implementation: the four inventoried sites are gone, nothing new appeared.

        Before salesagent-tbrk.5 landed, this pinned the RED state exactly
        (broadstreet/client.py:136, gam_reporting_service.py:382,
        triton_digital.py:488, creative_agent_registry.py:488) so a future
        drift in line number or an unexpected fifth site would be visible
        here, not silently swallowed by the boolean pass/fail of the RED-gate
        test above. Now that the lane has landed, the honest pin is that the
        scan finds NOTHING across the four files -- proof the migration is
        exhaustive, not just that the boolean check above happens to pass.
        """
        offenders = _scan_consumer_files()
        assert offenders == {}, offenders

    def test_unrelated_response_attribute_sites_are_out_of_scope_by_file(self) -> None:
        """media_buy_create.py / schemas/_base.py / outbound_error_mapping.py are NOT scanned.

        These files use the same attribute name (``response``) on unrelated types
        (``CreateMediaBuyResult.response``, ``httpx.HTTPStatusError.response``) --
        proof that scoping this guard to the four consumer files (not a repo-wide
        ``.response`` sweep) is a deliberate precision choice, not an oversight.
        Each file DOES contain ``.response`` attribute reads (asserted below, so
        this isn't vacuous); they are simply outside ``_CONSUMER_FILES``.
        """
        repo = repo_root()
        unrelated_files = (
            "src/core/tools/media_buy_create.py",
            "src/core/schemas/_base.py",
            "src/core/helpers/outbound_error_mapping.py",
        )
        for rel_path in unrelated_files:
            assert rel_path not in _CONSUMER_FILES
            hits = find_response_attribute_reads(parse_module(repo / rel_path))
            assert hits, f"expected {rel_path} to contain unrelated .response reads (non-vacuity check)"

    def test_definition_file_itself_is_out_of_scope(self) -> None:
        """outbound_http.py is excluded from the consumer scan on principle, not because it happens to be clean.

        Before salesagent-tbrk.5 landed, this file legitimately contained a
        ``.response`` read of its own (``OutboundResult.status_code``'s
        ``self.response.status_code``) -- proof the exclusion from
        ``_CONSUMER_FILES`` was deliberate (it is the type's definition, not
        a consumer reaching through it), not an accidental miss. That
        property has since moved to ``egress/response.py`` with no
        ``response`` field at all, so the file is now clean on its own
        merits too -- the exclusion no longer needs a non-vacuity proof to
        stay honest, only the membership check below.
        """
        repo = repo_root()
        assert "src/core/security/outbound_http.py" not in _CONSUMER_FILES
        hits = find_response_attribute_reads(parse_module(repo / "src/core/security/outbound_http.py"))
        assert hits == [], f"outbound_http.py unexpectedly reads .response at line(s) {hits}"
