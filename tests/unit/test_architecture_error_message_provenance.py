"""Guard: a buyer-facing error message never carries text we did not author.

The sibling guard ``tests/unit/test_guards_no_raw_exception_message.py`` covers
prkv.8's half: the BARE ``AdCPError(str(exc))`` fallback and the A2A JSON-RPC
error constructors, in three named transport-boundary files. This guard covers
the half prkv.8's fix cannot reach — a TYPED ``AdCPError`` subclass, anywhere in
``src/`` — because those bypass the normalising chokepoint entirely.

THE DISEASE (salesagent-prkv.17, the follow-up to prkv.8). A typed ``AdCPError``
subclass is constructed at the raise site with an f-string that interpolates a
NON-FIRST-PARTY value — the caught third-party exception's ``str(exc)``, an SDK
exception's free-text ``.message``, or a free-text field read off an external
agent's response payload. ``normalize_to_adcp_error()`` returns an already-typed
``AdCPError`` UNCHANGED (``src/core/exceptions.py``: ``if isinstance(exc,
AdCPError): return exc``), so for a typed error there is no downstream
sanitisation point: THE RAISE SITE IS THE WIRE. Wrapping the text in a typed
error does not launder it — it merely skips the only place that would have.

Grounded in the pinned spec, AdCP 3.1.1 (``adcp==6.6.0``),
``dist/docs/3.1.1/building/operating/transport-errors.mdx`` § Security
Considerations / Seller Requirements: "Error responses flow through LLM context.
Every field is client-facing. Implementations MUST NOT include: internal service
names, hostnames, or IP addresses; database error text …; stack traces or file
paths; upstream API responses from internal services; credentials, tokens, or
session identifiers." The conformance storyboard grades the error CODE, not the
message CONTENT, so this obligation rests on that normative prose — which is
precisely why it needs a structural guard rather than a storyboard step.

WHY A BOUNDARY SCRUB IS RULED OUT, and therefore why the check has to be
static. ``dist/compliance/3.1.1/universal/error-compliance.yaml`` POSITIVELY
grades message CONTENT in ``version_negotiation/unsupported_major_version`` and
its release-precision sibling ("message referencing the buyer's requested
version and the seller's supported set"). Messages are NOT uniformly untrusted:
a downstream sanitizer that rewrote every message to a class name would regress
a graded step. The trust decision has to be taken AT CONSTRUCTION TIME, per
raise site — which leaves nothing at runtime to enforce it, and leaves this
guard as the only thing standing between the fix and instance 38.

THE SANCTIONED FORM is the ``internal_detail=`` slot prkv.17 added to
``AdCPError.__init__``: a keyword-only, NEVER-serialized diagnostic payload,
logged once by ``normalize_to_adcp_error()``. So the safe path is also the
SHORTER path — ``internal_detail=exc`` costs fewer characters than the f-string
it replaces — and this guard's job is to make the unsafe one loud.

WHAT IS GRADED: the WIRE-BOUND arguments only — the message (positional 0, or
``message=``), ``details=`` and ``suggestion=``. ``internal_detail=`` is
deliberately NOT graded: it is the destination. Grading it would flag every
migrated site and invert the guard.

THREE TAINT CLAUSES, all three mandatory. The prkv.17 disease scan measured that
a detector phrased only as "an ``except … as <n>`` binding interpolated into the
message" — the shape the original ticket described — reaches 6 of the 11 sites
the fix had to migrate. It misses the external-payload read entirely and it
green-lights the SDK ``.message`` reads, which are 5 more:

  * clause W1 — a name bound by ``except … as <n>``, or derived from one inside
    the handler. The classic shape; 13 of today's 16 baseline rows, and 6 of the
    11 sites prkv.17 migrated.
  * clause W2 — an exception-typed PARAMETER of the enclosing helper. No
    ``except`` is in sight at the raise site: the exception arrived as an
    argument. The remaining 3 baseline rows — ``normalize_to_adcp_error``'s own
    two arms and the a2a SSRF adapter — plus the four
    ``raise_mapped_adcp_error`` arms prkv.17 migrated, which are also the only
    place the ATTR-FREETEXT rule below is load-bearing.
  * clause W3 — a free-text field read off an EXTERNAL response object
    (``result.error``, ``getattr(result, "message")``), with no exception
    involved at all. ``creative_agent_registry`` had exactly this and both the
    ticket's grep and the first structural pass missed it, because it is not an
    exception and not in a handler. Grades ZERO VIOLATIONS today — the fix
    migrated the only instance — so it is a PINNED KNOWN-ZERO, declared here
    rather than presented as coverage; ``TestGuardIsNotVacuous`` proves the
    clause still reaches the real function it was written for.

READ GRADING is the second half of the predicate, and the half that decides
whether the guard is usable at all. An attribute read is NOT automatically safe
and a derived local is NOT automatically unsafe:

  * RAW        — the tainted name read bare, ``str(exc)``, ``f"{exc}"``.
  * FREETEXT   — an attribute read onto a free-text field (``.message``,
                 ``.detail``, ``.text``, ``.reason``, ``.error``). Structurally
                 an attribute, semantically identical to ``str(exc)``: the adcp
                 SDK builds ``ADCPConnectionError.message`` as
                 ``f"Failed to connect: {last_error}"`` over a raw httpx error
                 (``adcp/protocols/mcp.py``, ``a2a.py``), so ``exc.message``
                 launders exactly the text this guard is about. Without this
                 rule the four ``raise_mapped_adcp_error`` arms pass clean.
  * STRUCTURED — an attribute read onto a bounded, non-text field
                 (``exc.response.status_code``, ``e.missing_tasks``). Not the
                 disease; four in-tree sites depend on this exemption.
  * SAFE       — ``type(exc).__name__``. prkv.8's fix at
                 ``exceptions.py::normalize_to_adcp_error`` IS this shape: a
                 class name carries no instance text. Exempting it by rule
                 rather than by allowlist keeps the reference implementation
                 out of the debt list, where it would read as a defect.

A local inherits the WORST grade among the tainted reads that built it, so
``task_list = "\\n".join(t["name"] for t in e.missing_tasks)`` stays STRUCTURED
through two levels of derivation while ``error_msg = f"… Error: {e}"`` is RAW
through the same two.

WHAT THIS GUARD DOES NOT GRADE AT ALL: IDENTIFIER DISCLOSURE. The spec clause
this guard cites bans two different things, and the guard implements only one of
them. "Upstream API responses from internal services" is a PROVENANCE question —
whose text is this? — and that is the predicate above. "Internal service names,
hostnames, or IP addresses" is an IDENTIFIER question — is this value one the
buyer sent, or one the seller configured? — and no taint clause can answer it,
because a seller-configured hostname is a FIRST-PARTY local. prkv.17 handled
that half with a human rule ("keep an identifier the buyer supplied; drop one
the seller configured and the buyer never sent"), applied by reading, not by
detection.

The consequence is concrete and measured, not theoretical:
``creative_agent_registry._fetch_formats_raw_mcp`` builds ``mcp_url`` from the
seller-configured ``agent.agent_url`` (and ``_connection_agent_url`` may swap in
a deployment-internal host entirely). Re-adding ``f"Connection failed:
{mcp_url}"`` to the site prkv.17 migrated does NOT redden this guard, while
re-adding ``{exc}`` does — both verified by mutation. Three sibling raises in
that same function still carry ``{mcp_url}`` today for the same reason.
``test_does_not_grade_identifier_disclosure_and_that_is_declared`` pins this so
the gap is a stated one; closing it needs a second, differently-shaped guard
(one that knows which locals derive from tenant configuration), not a wider
taint set here.

WHAT IS DELIBERATELY NOT RESOLVED — see ``KNOWN_UNCOVERED``. The construction
must be a direct ``ClassName(...)`` call. Indirect dispatch through a variable
holding the class is NOT resolved, and that is not hypothetical: the prkv.17 fix
itself rewrote ``raise_mapped_adcp_error`` into a mapping table that ends in
``raise error_class(message, internal_detail=exc)``. That site is CORRECT today
(first-party message, raw text in the slot) and this guard cannot see it. Stated
here so the limit is a known one rather than a silent one.

THE ALLOWLIST holds every site the detector finds in ``src/`` today, in two
kinds, and the distinction is recorded per entry:

  * OPEN DEFECT — reaches the wire, violates the cited clause, deferred to a
    tracked follow-up ticket rather than fixed in prkv.17's blast radius.
  * SPEC-COMPLIANT — examined and correct: the interpolated text is the buyer's
    OWN input echoed back, or our own validator's prose about it, which the spec
    expects on the wire. The detector cannot decide provenance statically, so
    these are carried here with the reason instead.

SHRINK-ONLY either way: ``assert_violations_match_allowlist`` reports a stale
entry as loudly as a new violation.

No entry cites a ``FIXME(#…)`` GitHub issue because none exists for the deferred
clusters yet; per CLAUDE.md a local tracker id must never be written as a
``FIXME(...)`` citation, so the deferral is recorded in prose on each entry
instead of as a fake citation.

Per-site opt-out (reason REQUIRED):

    # structural-guard: error-message-provenance - <why this text is buyer-safe>
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

import pytest

from tests.unit._architecture_helpers import (
    REPO_ROOT,
    assert_violations_match_allowlist,
    collect_visitor_violations,
    import_map,
    parse_sources,
    read_source_roots,
    structural_guard_marker_re,
)

#: Directories this guard governs. Pinned by a meta-test so it cannot silently narrow.
SCAN_ROOTS = ("src",)

#: Constructor arguments that reach the buyer. ``internal_detail`` is the
#: sanctioned NON-WIRE destination and is pointedly absent; so is ``context``
#: (correlation ids the spec requires) and the structured identity kwargs.
#: Pinned by a meta-test — quietly dropping ``details`` would blind the guard to
#: a whole carrier.
WIRE_BOUND_KEYWORDS = frozenset({"message", "details", "suggestion"})

#: The non-wire slot. Named so the exemption is explicit rather than implied by
#: absence from the set above.
NON_WIRE_KEYWORD = "internal_detail"

#: Attribute names that carry text authored by the third party.
FREETEXT_ATTRS = frozenset(
    {
        "message",
        "msg",
        "detail",
        "text",
        "reason",
        "error",
        "error_message",
        "body",
        "content",
        "stderr",
        "stdout",
        "args",
    }
)

#: Response-ish objects (clause W3) and the payload fields read off them.
RESPONSE_OBJECTS = frozenset(
    {
        "result",
        "results",
        "response",
        "resp",
        "res",
        "reply",
        "payload",
        "sdk_result",
        "agent_result",
        "fetch_result",
        "http_response",
        "raw",
        "data",
    }
)
PAYLOAD_ATTRS = FREETEXT_ATTRS - {"args"}

#: Parameter names that mean "an exception arrived as an argument" (clause W2),
#: used alongside the annotation test below.
_EXC_PARAM_NAMES = frozenset({"e", "ex", "exc", "err", "error", "exception", "_e"})
_EXC_ANNOTATION_TOKENS = ("Exception", "Error", "BaseException")

#: Read grades. Only RAW and FREETEXT are violations; see the module docstring.
RAW, FREETEXT, STRUCTURED, SAFE = "RAW", "ATTR-FREETEXT", "ATTR-STRUCTURED", "SAFE"
_SEVERITY = {SAFE: 0, STRUCTURED: 1, FREETEXT: 2, RAW: 3}
UNSAFE_GRADES = frozenset({RAW, FREETEXT})

#: Construction shapes that DO put third-party text on the wire and that this
#: guard does NOT catch. Declared so the limit is stated, not silent.
KNOWN_UNCOVERED = (
    "error_class(f'{exc}')",  # class chosen at runtime — raise_mapped_adcp_error's shape
    "ERROR_TYPES['adapter'](f'{exc}')",  # class pulled from a registry
    "make_error(f'{exc}')",  # a first-party factory that constructs internally
    # Free text pulled back OUT of a structured container. ``exc.errors()`` is a
    # list of dicts — graded STRUCTURED, correctly — but ``[0]["msg"]`` reaches
    # a free-text field inside it. Live at exceptions.py::normalize_to_adcp_error,
    # where the text is pydantic's prose about the buyer's OWN request body and
    # the spec expects it on the wire; a different container could carry
    # third-party text through the same shape.
    "AdCPValidationError(exc.errors()[0]['msg'])",
    # A first-party helper's RETURN value that itself launders third-party text.
    # All three clauses are INTRAPROCEDURAL, so ``check_url_ssrf()`` returning
    # ``f"Invalid URL: {e}"`` from its own catch-all arm reads as first-party
    # here. prkv.17 migrated that site (property_list_resolver) on the strength
    # of a human read, NOT because this detector saw it. Absence from an
    # intraprocedural scan is never evidence of provenance.
    "AdCPAdapterError(f'rejected: {check_url_ssrf(u)[1]}')",
)

#: (path, enclosing function, error class, tainted expression). Line numbers are
#: deliberately absent so an edit elsewhere in the file does not churn the list.
#: The trade-off is measured, not assumed: two raises in the SAME function with
#: the same error class and the same tainted expression collapse to one entry —
#: which is exactly what the two ``raise_mapped_adcp_error`` arms did on the
#: pre-fix tree (11 migrated sites, 10 distinct keys). Both still redden the
#: guard; the allowlist just cannot hold one without the other.
#: SHRINK-ONLY. Measured against the tree, not hand-written.
ALLOWLIST: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        # ── OPEN DEFECT (11) ─────────────────────────────────────────────
        # These are the eleven rows prkv.17's disease scan dispositioned DEFER:
        # each reaches the buyer wire and violates the cited clause, and each was
        # left out of prkv.17's blast radius on purpose. The guard's job here is
        # to hold the line at eleven.
        #
        # Cluster salesagent-dvx2y — a broad `except Exception` on a buyer tool
        # path interpolates str(e): googleads/zeep SOAP faults, GAM creative-upload
        # rejections, adapter transport text. Fix is prkv.17's: a stable
        # first-party sentence plus internal_detail=e.
        ("src/adapters/google_ad_manager.py", "create_media_buy", "AdCPLineItemError", "error_msg"),
        (
            "src/core/helpers/creative_helpers.py",
            "process_and_upload_package_creatives",
            "AdCPAdapterError",
            "error_msg",
        ),
        ("src/core/tools/creative_formats.py", "_list_creative_formats_impl", "AdCPServiceUnavailableError", "e"),
        ("src/core/tools/media_buy_create.py", "_validate_and_convert_format_ids", "AdCPAdapterError", "e"),
        ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", "AdCPAdapterError", "str(upload_error)"),
        ("src/core/tools/media_buy_create.py", "_create_media_buy_impl", "AdCPAdapterError", "str(e)"),
        ("src/core/tools/products.py", "_get_products_impl", "AdCPAdapterError", "error_msg"),
        ("src/core/tools/properties.py", "_list_authorized_properties_impl", "AdCPAdapterError", "str(e)"),
        # Cluster salesagent-udff5 — normalize_to_adcp_error's own ValueError and
        # PermissionError arms assert that anything of that TYPE is our own safe
        # validation prose. Third-party libraries raise both, and OS
        # PermissionError text carries server paths and uid/gid. Changing it is a
        # protocol-behaviour change and carries its own spec-grounding gate, so it
        # is not folded into prkv.17.
        ("src/core/exceptions.py", "normalize_to_adcp_error", "AdCPValidationError", "str(exc)"),
        ("src/core/exceptions.py", "normalize_to_adcp_error", "AdCPAuthorizationError", "str(exc)"),
        # Ticket salesagent-j6dp8 (P3) — pydantic's text here enumerates our
        # INTERNAL declaration schema plus the operator's stored tenant config, and
        # the site is reachable from the buyer-facing capabilities tool. The
        # provenance is first-party; the disclosure is not.
        ("src/core/schemas/capability_declarations.py", "from_tenant", "AdCPConfigurationError", "exc"),
        # ── SPEC-COMPLIANT (5) ───────────────────────────────────────────
        # Examined and correct: the interpolated text is the buyer's OWN input
        # echoed back, or our own validator's prose about it. transport-errors.mdx
        # forbids text the buyer never sent and cannot act on; these are the
        # opposite, and the storyboard's correctable-error steps expect them. The
        # detector cannot decide provenance statically, so the judgement is
        # recorded here per site rather than as a per-site marker — this guard
        # landed alongside prkv.17's fix and does not edit unrelated production
        # files to make itself green.
        #
        # Our own SSRF validator rejecting a webhook URL the buyer supplied.
        # QUALIFIED, and deliberately recorded as such: the prkv.17 sweep traced
        # the only caller that REACHES this branch (the repository SSRF gate's
        # `except ValueError`, not the AdCPValidationError caller the original
        # disposition described) back to check_url_ssrf, whose catch-all arm
        # returns f"Invalid URL: {e}" and whose range check names the blocked
        # network. That is the same laundering shape that promoted
        # property_list_resolver's validator site to a fix. It sits here rather
        # than being fixed because this guard landed with prkv.17 and does not
        # widen that ticket's blast radius; the SSRF-oracle follow-up owns it.
        ("src/a2a_server/adcp_a2a_server.py", "_invalid_params_from_ssrf_error", "AdCPValidationError", "str(exc)"),
        # ValueError from parsing the buyer's own format_id, status_filter and
        # get_products payloads — the message echoes the value they sent.
        ("src/core/tools/media_buy_create.py", "_validate_and_convert_format_ids", "AdCPValidationError", "e"),
        ("src/core/tools/media_buy_list.py", "_resolve_status_filter", "AdCPValidationError", "e"),
        ("src/core/tools/products.py", "get_products", "AdCPValidationError", "e"),
        # Our own formatter over a pydantic error about buyer input.
        (
            "src/core/validation_helpers.py",
            "adcp_validation_boundary",
            "AdCPValidationError",
            "format_validation_error(e, context=context)",
        ),
    }
)


_MARKER = structural_guard_marker_re("error-message-provenance")


# ---------------------------------------------------------------------------
# The error-class set, resolved from the live hierarchy
# ---------------------------------------------------------------------------


def adcp_error_class_names() -> frozenset[str]:
    """Every ``AdCPError`` subclass name, walked from the live base class.

    Read from the hierarchy rather than hardcoded so the guard self-updates when
    a subclass is added — the failure mode a fixed list has is that the newest
    error type, the one most likely to be built wrong, is the one it cannot see.
    """
    from src.core.exceptions import AdCPError

    names = {AdCPError.__name__}
    pending = [AdCPError]
    while pending:
        for sub in pending.pop().__subclasses__():
            if sub.__name__ not in names:
                names.add(sub.__name__)
                pending.append(sub)
    return frozenset(names)


#: The SDK error MODEL — ``adcp.types.Error`` — is the non-exception shape of the
#: same disease: it is appended to a response's ``errors[]``, which the storyboard
#: treats as an equal-status error carrier alongside the envelope. It is resolved
#: per module through the import map, because this repo imports it under an alias.
SDK_ERROR_ORIGIN = ("adcp.types", "Error")


def target_class_names(relpath: str, tree: ast.Module, base_names: frozenset[str]) -> frozenset[str]:
    """Names that construct a buyer-facing error IN THIS module."""
    names = set(base_names)
    for local, origin in import_map(relpath, tree).items():
        if origin == SDK_ERROR_ORIGIN:
            names.add(local)
    return frozenset(names)


# ---------------------------------------------------------------------------
# Read grading
# ---------------------------------------------------------------------------


def _parent_map(node: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(node):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _is_type_name_read(name_node: ast.Name, parents: dict[int, ast.AST]) -> bool:
    """``type(exc).__name__`` — prkv.8's sanctioned shape."""
    call = parents.get(id(name_node))
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "type"):
        return False
    attribute = parents.get(id(call))
    return isinstance(attribute, ast.Attribute) and attribute.attr == "__name__"


def grade_read(name_node: ast.Name, parents: dict[int, ast.AST]) -> str:
    """How a single occurrence of a tainted name is read."""
    if _is_type_name_read(name_node, parents):
        return SAFE
    parent = parents.get(id(name_node))
    if not isinstance(parent, ast.Attribute):
        return RAW
    chain: list[str] = []
    cursor: ast.AST | None = parent
    while isinstance(cursor, ast.Attribute):
        chain.append(cursor.attr)
        cursor = parents.get(id(cursor))
    return FREETEXT if set(chain) & FREETEXT_ATTRS else STRUCTURED


def grade_expression(expr: ast.expr, tainted: dict[str, str]) -> str:
    """The worst grade among *expr*'s reads of tainted names — SAFE if none."""
    parents = _parent_map(expr)
    worst = SAFE
    for node in ast.walk(expr):
        if not (isinstance(node, ast.Name) and node.id in tainted):
            continue
        # A read can only be as trustworthy as the name it reads: a STRUCTURED
        # read off a name that is itself RAW-tainted is still RAW.
        read = grade_read(node, parents)
        grade = read if _SEVERITY[read] <= _SEVERITY[tainted[node.id]] else tainted[node.id]
        if _SEVERITY[grade] > _SEVERITY[worst]:
            worst = grade
    return worst


# ---------------------------------------------------------------------------
# Taint sources
# ---------------------------------------------------------------------------


def _direct_payload_read(value: ast.expr) -> bool:
    """Clause W3: a DIRECT read of a free-text field off a response-ish object.

    Deliberately shallow — a fixed object-name set and direct reads only — so a
    first-party local that happens to be called ``errors`` or ``message`` is not
    swept in.
    """
    if isinstance(value, ast.Attribute):
        return value.attr in PAYLOAD_ATTRS and isinstance(value.value, ast.Name) and value.value.id in RESPONSE_OBJECTS
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "getattr":
        return (
            len(value.args) >= 2
            and isinstance(value.args[0], ast.Name)
            and value.args[0].id in RESPONSE_OBJECTS
            and isinstance(value.args[1], ast.Constant)
            and value.args[1].value in PAYLOAD_ATTRS
        )
    if isinstance(value, ast.BoolOp):  # ``result.error or result.message or "…"``
        return any(_direct_payload_read(v) for v in value.values)
    return False


def exception_parameters(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    """Clause W2: parameters through which an exception arrives."""
    names: set[str] = set()
    for arg in list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs):
        annotation = ast.unparse(arg.annotation) if arg.annotation else ""
        if arg.arg in _EXC_PARAM_NAMES or any(token in annotation for token in _EXC_ANNOTATION_TOKENS):
            names.add(arg.arg)
    return frozenset(names)


def _propagate(scope: ast.AST, tainted: dict[str, str]) -> dict[str, str]:
    """Carry taint through assignments, worst-grade-wins, until it settles.

    Iterated to a fixed point rather than swept once in source order: a single
    pass makes the result depend on statement ORDER, which is how a two-step
    derivation (``task_list`` then ``error_msg``) silently drops its grade.
    """
    tainted = dict(tainted)
    changed = True
    while changed:
        changed = False
        for stmt in ast.walk(scope):
            if not isinstance(stmt, ast.Assign):
                continue
            grade = grade_expression(stmt.value, tainted)
            if grade == SAFE:
                continue
            for target in stmt.targets:
                for node in ast.walk(target):
                    if not isinstance(node, ast.Name):
                        continue
                    if _SEVERITY[grade] > _SEVERITY[tainted.get(node.id, SAFE)]:
                        tainted[node.id] = grade
                        changed = True
    return tainted


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

Violation = tuple[str, str, str, str]


@dataclass(frozen=True)
class _Finding:
    relpath: str
    function: str
    error_class: str
    expression: str
    grade: str
    lineno: int

    def key(self) -> Violation:
        return (self.relpath, self.function, self.error_class, self.expression)


class _ProvenanceVisitor(ast.NodeVisitor):
    """Error constructions whose wire-bound arguments read non-first-party text."""

    def __init__(self, relpath: str, targets: frozenset[str], lines: list[str]) -> None:
        self._relpath = relpath
        self._targets = targets
        self._lines = lines
        self.violations: list[_Finding] = []
        self._function = "<module>"
        self._tainted: dict[str, str] = {}

    # -- scopes ------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        previous = (self._function, self._tainted)
        self._function = node.name if previous[0] == "<module>" else f"{previous[0]}::{node.name}"
        # Clause W2 + clause W3 seed the function scope; a nested def INHERITS
        # the enclosing taint, because it closes over those names — otherwise
        # "move the raise into a closure" is a one-line evasion.
        seeded = dict(previous[1])
        seeded.update(dict.fromkeys(exception_parameters(node), RAW))
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign) and _direct_payload_read(stmt.value):
                for target in stmt.targets:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name):
                            seeded[name.id] = FREETEXT
        self._tainted = _propagate(node, seeded)
        self.generic_visit(node)
        self._function, self._tainted = previous

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        previous = self._tainted
        if node.name:
            # Clause W1. The binding is RAW: read bare it IS str(exc).
            self._tainted = _propagate(node, {**previous, node.name: RAW})
        self.generic_visit(node)
        self._tainted = previous

    # -- the construction --------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self._check(node)
        self.generic_visit(node)

    def _check(self, node: ast.Call) -> None:
        if not (isinstance(node.func, ast.Name) and node.func.id in self._targets):
            return
        if self._is_marked(node.lineno):
            return
        for expr in self._wire_bound_args(node):
            grade = grade_expression(expr, self._tainted)
            if grade in UNSAFE_GRADES:
                self.violations.append(
                    _Finding(
                        relpath=self._relpath,
                        function=self._function,
                        error_class=node.func.id,
                        expression=self._render(expr),
                        grade=grade,
                        lineno=node.lineno,
                    )
                )
                return

    def _wire_bound_args(self, node: ast.Call) -> list[ast.expr]:
        """The message plus the other serialized free-text kwargs.

        Positional 0 is the message for every ``AdCPError`` subclass and for the
        SDK model it is passed by keyword, so both spellings are covered.
        """
        args: list[ast.expr] = list(node.args[:1])
        args += [kw.value for kw in node.keywords if kw.arg in WIRE_BOUND_KEYWORDS]
        return args

    def _render(self, expr: ast.expr) -> str:
        """The tainted sub-expression, not the whole f-string.

        Keying on the rendered f-string would make the allowlist churn on every
        wording change; keying on the tainted READ keeps an entry stable until
        the provenance itself changes, which is the thing being allowlisted.
        """
        parents = _parent_map(expr)
        best: tuple[int, str] | None = None
        for node in ast.walk(expr):
            if not (isinstance(node, ast.Name) and node.id in self._tainted):
                continue
            read = grade_read(node, parents)
            if read == SAFE:
                continue
            owner: ast.AST = node
            while isinstance(parents.get(id(owner)), ast.Attribute | ast.Call):
                owner = parents[id(owner)]
            severity = _SEVERITY[min((read, self._tainted[node.id]), key=lambda g: _SEVERITY[g])]
            candidate = (severity, ast.unparse(owner))
            if best is None or candidate[0] > best[0]:
                best = candidate
        return best[1] if best else ast.unparse(expr)

    def _is_marked(self, lineno: int) -> bool:
        """A reason-carrying opt-out on the site's own line or the two above it.

        Two lines of slack because these raises are routinely wrapped by the
        formatter, putting the comment further from the call's own ``lineno``.
        """
        for candidate in (lineno - 1, lineno - 2, lineno - 3):
            if 0 <= candidate < len(self._lines) and _MARKER.search(self._lines[candidate]):
                return True
        return False


def find_findings(sources: dict[str, str]) -> list[_Finding]:
    trees, lines = parse_sources(sources)
    base = adcp_error_class_names()
    return collect_visitor_violations(
        trees,
        lambda relpath: _ProvenanceVisitor(
            relpath,
            target_class_names(relpath, trees[relpath], base),
            lines.get(relpath, []),
        ),
    )


def find_violations(sources: dict[str, str]) -> list[Violation]:
    return [finding.key() for finding in find_findings(sources)]


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_no_error_message_carries_third_party_text():
    """Both directions in one assertion: new violations AND entries the allowlist
    outlived."""
    assert_violations_match_allowlist(
        set(find_violations(read_source_roots(SCAN_ROOTS))),
        ALLOWLIST,
        fix_hint=(
            "normalize_to_adcp_error() returns a typed AdCPError UNCHANGED, so for a typed error "
            "the raise site IS the wire — there is no downstream point that can sanitise this "
            "message. AdCP 3.1.1 transport-errors.mdx § Security Considerations: 'Every field is "
            "client-facing … MUST NOT include internal service names, hostnames, or IP addresses "
            "… upstream API responses from internal services.'\n"
            "  keep the cause, off the wire:  raise AdCPAdapterError('<stable sentence>', "
            "internal_detail=exc) from exc\n"
            "     (normalize_to_adcp_error logs internal_detail server-side; it is never "
            "serialized)\n"
            "  drop seller-configured identifiers too — a hostname the buyer never sent is banned "
            "by the same clause, exception or not.\n"
            "If the text really is the buyer's own input echoed back, mark it: "
            "# structural-guard: error-message-provenance - <why>"
        ),
    )


def test_scan_scope_is_pinned():
    """A guard that quietly narrows its own scope reports clean for the wrong reason."""
    assert SCAN_ROOTS == ("src",)
    for root in SCAN_ROOTS:
        assert (REPO_ROOT / root).is_dir(), f"{root} does not exist — the scan would silently cover nothing"


def test_wire_bound_argument_set_is_pinned():
    """Dropping a carrier from this set is the cheapest way to blind the guard.

    ``details`` is serialized into the envelope exactly like ``message``; a guard
    that graded only the message would let the same text through one keyword over.
    """
    assert WIRE_BOUND_KEYWORDS == frozenset({"message", "details", "suggestion"})
    assert NON_WIRE_KEYWORD not in WIRE_BOUND_KEYWORDS


def test_the_non_wire_slot_still_exists_and_is_never_serialized():
    """The guard's whole premise is that there IS a sanctioned destination.

    If ``internal_detail`` were removed — or worse, started being serialized —
    the guard would still pass while the fix it protects had been undone.
    """
    import inspect

    from src.core.exceptions import AdCPAdapterError, AdCPError

    assert NON_WIRE_KEYWORD in inspect.signature(AdCPError.__init__).parameters, (
        "AdCPError.__init__ no longer accepts internal_detail — every raise site this guard "
        "pushes people toward has lost its destination."
    )
    error = AdCPAdapterError("first-party sentence", internal_detail=RuntimeError("proxy.internal:3128"))
    assert error.internal_detail is not None
    serialized = str(error.to_dict())
    assert "proxy.internal:3128" not in serialized, (
        f"internal_detail is being serialized into the wire payload: {serialized}"
    )


def test_the_error_hierarchy_resolves_to_more_than_the_base_class():
    """The class set is read from the live hierarchy; a broken walk would make
    the guard match ``AdCPError(...)`` only and grade almost nothing."""
    names = adcp_error_class_names()
    assert "AdCPError" in names
    assert {"AdCPAdapterError", "AdCPValidationError", "AdCPServiceUnavailableError"} <= names
    assert len(names) > 20, f"only {len(names)} AdCPError subclasses resolved — the walk is broken"


def test_every_allowlist_entry_names_a_real_file():
    """A path typo would silently retire an entry AND hide the violation behind it."""
    for path, _, _, _ in sorted(ALLOWLIST):
        assert (REPO_ROOT / path).is_file(), f"allowlisted path {path} does not exist"


class TestDetectorMetaTests:
    """The detector must catch what it claims, and not what it does not."""

    def _violations(self, source: str, path: str = "src/pkg/mod.py") -> list[Violation]:
        return find_violations({path: source})

    # ── clause W1: an ``except … as <n>`` binding ─────────────────────────

    def test_flags_str_of_a_caught_exception_in_the_message(self):
        """The shape prkv.17 migrated at kevel.py and triton_digital.py."""
        src = "def go():\n    try:\n        call()\n    except RequestException as e:\n        raise AdCPAdapterError(str(e)) from e\n"
        assert self._violations(src) == [("src/pkg/mod.py", "go", "AdCPAdapterError", "str(e)")]

    def test_flags_an_interpolated_exception_alongside_first_party_text(self):
        """``f"Connection failed: {mcp_url} — {exc}"`` — creative_agent_registry's
        site. A leading first-party sentence does not launder the tail."""
        src = (
            "def go(mcp_url):\n"
            "    try:\n"
            "        call()\n"
            "    except httpx.RequestError as exc:\n"
            '        raise AdCPServiceUnavailableError(f"Connection failed: {mcp_url} — {exc}") from exc\n'
        )
        assert self._violations(src) == [("src/pkg/mod.py", "go", "AdCPServiceUnavailableError", "exc")]

    def test_flags_a_local_derived_from_the_caught_exception(self):
        """``error_msg = f"…: {e}"`` then ``raise X(error_msg)`` — the shape at
        google_ad_manager.py and products.py, and the reason taint has to
        propagate through assignment at all."""
        src = (
            "def go():\n"
            "    try:\n"
            "        call()\n"
            "    except Exception as e:\n"
            '        error_msg = f"Failed to convert. Error: {e}"\n'
            "        raise AdCPAdapterError(error_msg) from e\n"
        )
        assert self._violations(src) == [("src/pkg/mod.py", "go", "AdCPAdapterError", "error_msg")]

    def test_flags_third_party_text_routed_through_details(self):
        """``details=`` is serialized into the envelope exactly like ``message``."""
        src = (
            "def go():\n"
            "    try:\n"
            "        call()\n"
            "    except Exception as e:\n"
            '        raise AdCPAdapterError("Upstream rejected the request", details={"cause": str(e)}) from e\n'
        )
        assert self._violations(src) == [("src/pkg/mod.py", "go", "AdCPAdapterError", "str(e)")]

    def test_flags_the_raise_when_it_is_moved_into_a_nested_closure(self):
        """A nested def closes over the handler's binding, so resetting taint on
        entering one would make "wrap it in a def" a one-line evasion."""
        src = (
            "def go():\n"
            "    try:\n"
            "        call()\n"
            "    except Exception as e:\n"
            "        def _fail():\n"
            "            raise AdCPAdapterError(str(e))\n"
            "        _fail()\n"
        )
        assert self._violations(src) == [("src/pkg/mod.py", "go::_fail", "AdCPAdapterError", "str(e)")]

    # ── clause W2: an exception-typed parameter ───────────────────────────

    def test_flags_an_exception_typed_parameter_of_a_helper(self):
        """No ``except`` at the raise site: the exception arrived as an argument.
        This is ``normalize_to_adcp_error``'s own shape."""
        src = 'def to_adcp(exc: Exception):\n    raise AdCPValidationError(f"Invalid: {exc}")\n'
        assert self._violations(src) == [("src/pkg/mod.py", "to_adcp", "AdCPValidationError", "exc")]

    def test_flags_an_exception_parameter_recognised_by_annotation_alone(self):
        """``raise_mapped_adcp_error(exc: ADCPError, …)`` names its parameter
        conventionally, but a differently-named one must not slip through."""
        src = 'def remap(sdk_failure: ADCPError, label: str):\n    raise AdCPAdapterError(f"{label}: {sdk_failure}")\n'
        assert self._violations(src) == [("src/pkg/mod.py", "remap", "AdCPAdapterError", "sdk_failure")]

    # ── the ATTR-FREETEXT rule ────────────────────────────────────────────

    def test_flags_a_free_text_attribute_read(self):
        """``exc.message`` is an ATTRIBUTE and is exactly as unsafe as ``str(exc)``:
        the adcp SDK builds it as f"Failed to connect: {raw_httpx_error}". Without
        this rule all four raise_mapped_adcp_error arms passed clean."""
        src = 'def remap(exc: ADCPError):\n    raise AdCPServiceUnavailableError(f"Connection failed: {exc.message}") from exc\n'
        assert self._violations(src) == [("src/pkg/mod.py", "remap", "AdCPServiceUnavailableError", "exc.message")]

    def test_flags_a_free_text_attribute_deep_in_a_chain(self):
        """``exc.response.text`` — the free-text element is not the last one, and
        it is not the first either."""
        src = 'def go():\n    try:\n        call()\n    except Exception as exc:\n        raise AdCPAdapterError(f"{exc.response.text}") from exc\n'
        assert self._violations(src) == [("src/pkg/mod.py", "go", "AdCPAdapterError", "exc.response.text")]

    # ── clause W3: an external response payload ───────────────────────────

    def test_flags_a_free_text_field_read_off_an_external_response(self):
        """creative_agent_registry's shape: no exception anywhere, the external
        agent's own error payload interpolated straight into the message. Both
        the ticket's grep and the first structural pass missed this."""
        src = (
            "async def fetch(agent):\n"
            "    result = await agent.call()\n"
            '    error_msg = getattr(result, "error", None) or getattr(result, "message", None)\n'
            '    raise AdCPAdapterError(f"Creative agent format fetch failed: {error_msg}")\n'
        )
        assert self._violations(src) == [("src/pkg/mod.py", "fetch", "AdCPAdapterError", "error_msg")]

    def test_flags_a_payload_read_through_plain_attribute_access(self):
        src = (
            "async def fetch(agent):\n"
            "    response = await agent.call()\n"
            "    detail = response.detail\n"
            '    raise AdCPAdapterError(f"Upstream said: {detail}")\n'
        )
        assert self._violations(src) == [("src/pkg/mod.py", "fetch", "AdCPAdapterError", "detail")]

    # ── the SDK error MODEL, resolved through its alias ───────────────────

    def test_flags_the_sdk_error_model_appended_to_a_success_payload(self):
        """``adcp.types.Error`` in ``errors[]`` is an equal-status error carrier
        per the storyboard, and this repo imports it under an alias — so the
        target set has to be resolved through the import map, not by name."""
        src = (
            "from adcp.types import Error as AdCPResponseError\n"
            "\n"
            "def collect(agent, errors):\n"
            "    try:\n"
            "        agent.fetch()\n"
            "    except Exception as e:\n"
            '        errors.append(AdCPResponseError(code="AGENT_UNREACHABLE", message=f"unreachable: {e}"))\n'
        )
        assert self._violations(src) == [("src/pkg/mod.py", "collect", "AdCPResponseError", "e")]

    def test_does_not_flag_the_sdk_model_when_it_is_not_the_sdk_model(self):
        """A local class that merely shares the alias name is not the carrier."""
        src = (
            "from src.pkg.other import Error as AdCPResponseError\n"
            "\n"
            "def collect(errors):\n"
            "    try:\n"
            "        call()\n"
            "    except Exception as e:\n"
            '        errors.append(AdCPResponseError(message=f"unreachable: {e}"))\n'
        )
        assert self._violations(src) == []

    # ── negatives: the sanctioned forms ───────────────────────────────────

    def test_does_not_flag_the_internal_detail_slot(self):
        """The prkv.17 fix itself — the whole point of the guard is that THIS
        passes while the f-string it replaced does not."""
        src = (
            "def go():\n"
            "    try:\n"
            "        call()\n"
            "    except RequestException as e:\n"
            '        raise AdCPAdapterError("Ad server rejected the media buy update", internal_detail=e) from e\n'
        )
        assert self._violations(src) == []

    def test_does_not_flag_from_exc_chaining_without_interpolation(self):
        """``from exc`` preserves the cause for the traceback and puts nothing on
        the wire. It is the correct thing to do and must never be discouraged."""
        src = 'def go():\n    try:\n        call()\n    except Exception as exc:\n        raise AdCPServiceUnavailableError("Creative agent HTTP error after 3 retries") from exc\n'
        assert self._violations(src) == []

    def test_does_not_flag_a_bounded_structured_attribute(self):
        """``exc.response.status_code`` is an HTTP status — bounded, and the buyer
        needs it. Four in-tree sites depend on this exemption holding."""
        src = (
            "def go(mcp_url):\n"
            "    try:\n"
            "        call()\n"
            "    except httpx.HTTPStatusError as exc:\n"
            '        raise AdCPServiceUnavailableError(f"Creative agent unavailable (HTTP {exc.response.status_code})") from exc\n'
        )
        assert self._violations(src) == []

    def test_does_not_flag_a_local_derived_only_from_a_structured_attribute(self):
        """Two levels of derivation off ``e.missing_tasks`` — media_buy_create's
        setup-incomplete message. A grade that resets on assignment would flag it."""
        src = (
            "def go():\n"
            "    try:\n"
            "        call()\n"
            "    except SetupIncompleteError as e:\n"
            '        task_list = "\\n".join(t["name"] for t in e.missing_tasks)\n'
            '        error_msg = f"Setup incomplete:\\n{task_list}"\n'
            '        raise AdCPValidationError(error_msg, recovery="terminal")\n'
        )
        assert self._violations(src) == []

    def test_does_not_flag_the_class_name_shape(self):
        """prkv.8's fix, live at exceptions.py::normalize_to_adcp_error. A class
        name carries no instance text — exempting it by RULE keeps the reference
        implementation out of the debt list, where it would read as a defect."""
        src = "def to_adcp(exc: Exception):\n    raise AdCPError(type(exc).__name__)\n"
        assert self._violations(src) == []

    def test_does_not_flag_a_wholly_first_party_message(self):
        src = 'def go(requested, supported):\n    raise AdCPValidationError(f"Requested AdCP {requested}; this seller supports {supported}")\n'
        assert self._violations(src) == []

    def test_does_not_flag_a_first_party_local_named_like_a_payload_field(self):
        """Clause W3's object-name set is deliberately narrow: our own local
        called ``message`` or ``errors`` must not be swept in."""
        src = 'def go(req):\n    message = build_seller_sentence(req)\n    raise AdCPValidationError(f"{message}")\n'
        assert self._violations(src) == []

    def test_respects_a_reason_carrying_marker(self):
        src = (
            "def go():\n"
            "    try:\n"
            "        call()\n"
            "    except ValueError as e:\n"
            "        # structural-guard: error-message-provenance - echoes the buyer's own filter value\n"
            '        raise AdCPValidationError(f"Invalid status_filter value: {e}")\n'
        )
        assert self._violations(src) == []

    def test_a_bare_marker_without_a_reason_does_not_silence_the_site(self):
        src = (
            "def go():\n"
            "    try:\n"
            "        call()\n"
            "    except ValueError as e:\n"
            "        # structural-guard: error-message-provenance\n"
            '        raise AdCPValidationError(f"Invalid status_filter value: {e}")\n'
        )
        assert self._violations(src) == [("src/pkg/mod.py", "go", "AdCPValidationError", "e")]

    def test_does_not_grade_identifier_disclosure_and_that_is_declared(self):
        """The OTHER half of the cited spec clause, pinned as out of scope.

        A seller-configured hostname on a buyer-facing message violates
        transport-errors.mdx § Security Considerations just as squarely as
        third-party text does — but it is a FIRST-PARTY local, so no provenance
        clause can see it. Asserting the miss here keeps it a declared limit
        instead of a silent one, and makes the day someone closes it visible.
        """
        src = (
            "def go(mcp_url):\n"
            "    try:\n"
            "        call()\n"
            "    except httpx.RequestError as exc:\n"
            '        raise AdCPServiceUnavailableError(f"Connection failed: {mcp_url}", internal_detail=exc) from exc\n'
        )
        assert self._violations(src) == [], (
            "Identifier disclosure is now graded — move it out of the declared limits in the "
            "module docstring and into the coverage claim."
        )
        # The control: the provenance half of the SAME site is still caught.
        unsafe = src.replace('f"Connection failed: {mcp_url}", internal_detail=exc', 'f"Connection failed: {exc}"')
        assert self._violations(unsafe) == [("src/pkg/mod.py", "go", "AdCPServiceUnavailableError", "exc")]

    @pytest.mark.parametrize("form", KNOWN_UNCOVERED)
    def test_known_uncovered_construction_forms_are_declared_not_caught(self, form: str):
        """Pins the detector's edge honestly.

        These DO build a buyer-facing error from third-party text and this guard
        does NOT resolve them. The assertion exists so the gap is a stated
        limitation rather than a silent one — widen the target resolution when
        one of them shows up in production.
        """
        src = f"def go():\n    try:\n        call()\n    except Exception as exc:\n        raise {form}\n"
        assert self._violations(src) == [], (
            f"{form} is now resolved — move it out of KNOWN_UNCOVERED and into the coverage claim"
        )


class TestGuardIsNotVacuous:
    """Measurements against the REAL tree, not synthetic snippets."""

    def test_the_guard_actually_grades_the_production_tree(self):
        """A detector that reaches nothing real is the failure mode this guard was
        written to avoid. The allowlist is the measured evidence that it does not:
        every entry is a site the detector found in ``src/``."""
        found = set(find_violations(read_source_roots(SCAN_ROOTS)))
        assert found, (
            "The detector found ZERO sites in src/. Either every third-party-text message has "
            "been fixed — in which case empty the ALLOWLIST and delete this test's premise — or "
            "resolution broke and the guard is now vacuous."
        )

    def test_clause_w2_reaches_the_real_normalize_boundary(self):
        """Clause W2's live anchor. ``normalize_to_adcp_error`` takes its exception
        as a PARAMETER — no ``except`` is in sight — so a W1-only detector grades
        the shared MCP/A2A/REST chokepoint at zero."""
        findings = find_findings(read_source_roots(SCAN_ROOTS))
        w2 = [f for f in findings if f.relpath == "src/core/exceptions.py"]
        assert w2, (
            "Clause W2 no longer reaches normalize_to_adcp_error. Either exceptions.py was "
            "restructured or exception_parameters() broke — in which case every helper-parameter "
            "site in the tree is now ungraded."
        )

    def test_clause_w3_still_reaches_the_function_it_was_written_for(self):
        """The PINNED KNOWN-ZERO. Clause W3 grades zero VIOLATIONS today because
        prkv.17 migrated its only instance — but the clause must still see the
        payload read that produced it, or the zero is blindness, not a fix.

        ``CreativeAgentRegistry._fetch_formats_from_agent`` assigns the external
        agent's own error payload to a local and then builds an error from it;
        the message is now a first-party sentence with the payload in
        ``internal_detail``. This asserts the taint still ARRIVES.
        """
        source = (REPO_ROOT / "src/core/creative_agent_registry.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        payload_locals: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and _direct_payload_read(node.value):
                for target in node.targets:
                    payload_locals |= {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
        assert payload_locals, (
            "Clause W3 finds no external-payload read in creative_agent_registry.py. Either the "
            "module was restructured or _direct_payload_read() broke — in which case W3's "
            "known-zero is blindness rather than a measurement."
        )

    def test_clause_w3_grades_zero_violations_and_that_is_the_fix(self):
        """The other half of the known-zero: it is zero because the site was
        migrated, and if a payload read ever lands back on the wire the main
        guard reddens and this test explains why the zero stopped holding."""
        findings = find_findings(read_source_roots(SCAN_ROOTS))
        registry = [f for f in findings if f.relpath == "src/core/creative_agent_registry.py"]
        assert registry == [], f"An external-payload message is back on the wire: {registry}"

    def test_the_files_prkv17_migrated_grade_clean(self):
        """The fix's own regression pin, stated by name.

        Measured against the pre-fix tree, this detector flagged all eleven sites
        prkv.17 migrated (ten distinct keys — the two ``ADCPTimeoutError`` /
        ``ADCPConnectionError`` arms of ``raise_mapped_adcp_error`` shared a key).
        It flags none of them now. ``assert_violations_match_allowlist`` would
        catch a revert as a new violation, but only this test says WHICH files
        the fix was about, so the failure names the change that broke it.
        """
        migrated = {
            "src/adapters/kevel.py",
            "src/adapters/triton_digital.py",
            "src/core/creative_agent_registry.py",
            "src/core/helpers/adapter_helpers.py",
            "src/core/property_list_resolver.py",
            "src/core/tools/signals.py",
        }
        sources = read_source_roots(SCAN_ROOTS)
        for relpath in sorted(migrated):
            assert relpath in sources, f"{relpath} is gone — this pin now grades nothing"
        regressed = [f for f in find_findings(sources) if f.relpath in migrated]
        assert regressed == [], (
            "A file prkv.17 migrated is putting third-party text back on the buyer wire: "
            + ", ".join(f"{f.relpath}:{f.lineno} ({f.grade})" for f in regressed)
        )

    def test_an_except_binding_only_detector_would_miss_a_third_of_the_baseline(self):
        """The measurement that justifies clauses W2 and W3 existing at all.

        The ticket described the disease as "a message interpolating a name bound
        by ``except … as <name>``". Re-measured live: that phrasing grades
        strictly fewer sites in ``src/`` than this guard does — the difference is
        the exception-typed parameters at ``exceptions.py`` and
        ``adcp_a2a_server.py``, which no handler encloses. If the two ever
        converge, the extra clauses stopped paying for themselves and the
        docstring's justification needs revisiting.
        """
        sources = read_source_roots(SCAN_ROOTS)
        trees, _ = parse_sources(sources)
        findings = find_findings(sources)
        full = {f.key() for f in findings}
        handler_only = {f.key() for f in findings if _is_inside_except_handler(trees[f.relpath], f.lineno)}
        assert handler_only < full, (
            "An except-handler-only detector now grades the same set as this guard. Clauses W2 "
            "and W3 are no longer earning their complexity — or they broke."
        )


def _is_inside_except_handler(tree: ast.Module, lineno: int) -> bool:
    """Would a W1-only detector — one that looks only inside ``except … as n`` — see this line?"""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ExceptHandler) and node.name):
            continue
        end = max((getattr(stmt, "end_lineno", None) or stmt.lineno) for stmt in node.body)
        if node.lineno <= lineno <= end:
            return True
    return False
