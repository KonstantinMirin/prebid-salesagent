"""Structural guard: every A2A skill handler selects its request bag off the TOOL.

THE RULE. A skill handler turns the buyer's parameter bag into a request through
``select_request_fields_for(tool, bag)`` — "the DTO's fields INTERSECT the builder's
parameters", read from the one lookup MCP and REST also read. A handler that selects any
other way decides for itself what a buyer may send on A2A, and that decision is invisible:
the transports go on advertising different field sets and nothing fails.

WHAT IT COST, measured on the tree before this guard existed. Twelve of thirteen handlers
selected off the tool. The thirteenth, ``list_authorized_properties``, built its DTO
directly and passed ``accepted=None`` — the unnarrowed form, which selects against the DTO
alone and skips the intersection entirely. So A2A accepted ``ext``:

    REST   rejected it outright  (derived body has no ``ext``; extra="forbid"
                                  -> extra_forbidden)
    MCP    never advertised it   (announced = DTO fields INTERSECT the wrapper signature)
    A2A    ACCEPTED it onto the request, where ``_list_authorized_properties_impl``
           never reads it

One request, three answers, chosen by which transport the buyer picked. That is the exact
class of divergence the one-binding work exists to make impossible, and it survived
because this single site opted out.

WHY A GUARD AND NOT JUST THE FIX. The opt-out was not an oversight — it was ARGUED, in a
comment reading "there is no signature to intersect with, so the DTO alone decides", which
was simply wrong (``build_list_authorized_properties_request`` had always existed and MCP
and REST had always gone through it). A wrong premise stated confidently at one call site
is not something the next reader re-derives. The builder's own docstring, meanwhile,
asserted that "no transport accepts ``ext``" — true of MCP and REST, false of A2A, and
nothing graded the difference. Two pieces of prose disagreeing about one fact is what a
structural rule replaces.

THE COMPLEMENT OF ``test_architecture_transport_field_parity.py``, NOT A PATCH OF IT. That
guard asks whether a transport LAGS -- whether A2A carries every field the other two do --
and it lists ``select_request_fields`` among its "wholesale" markers, correctly: a handler
consuming the bag against the DTO alone cannot possibly lag, because it takes everything.
The failure here is the opposite direction. A2A carried MORE than the others, and "more"
is invisible to a lag check by construction. Two rules, two directions; neither subsumes
the other, and the divergence lived in the gap.

MEMBERSHIP IS READ FROM THE DISPATCH TABLE, not from a name pattern. The skill-name ->
handler dict inside ``_handle_explicit_skill`` is what actually routes a buyer's request,
so it is the authoritative statement of which methods are skill handlers. Keying off the
``_handle_*_skill`` NAME instead would sweep in ``_handle_explicit_skill`` — the dispatcher
itself, which selects nothing because it routes — and would then need a name exception for
it. Reading the table needs none, and a skill added to the table is covered the day it is
added rather than the day someone remembers to list it here.

Ships with ZERO violations and no allowlist. Against the tree before the fix it reports
exactly one: ``list_authorized_properties``.

KNOWN LIMIT: this grades that the handler CALLS the shared selector, not that it forwards
the result unaltered. A handler could select correctly and then mutate the bag. That is
visible in review and has not happened; the shape this guard exists for — a handler
inventing its own selection — is the one that did.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
A2A_SERVER = REPO_ROOT / "src" / "a2a_server" / "adcp_a2a_server.py"

#: The one sanctioned way a skill handler turns a parameter bag into request fields.
SELECTOR = "select_request_fields_for"

#: A dict literal is the dispatch table when it maps >= this many string skill names to
#: attribute references. The floor exists so an incidental small str->attr dict elsewhere
#: in the module cannot be mistaken for it; the real table routes thirteen.
_MIN_TABLE_ROWS = 5


def dispatch_table(tree: ast.AST) -> dict[str, str]:
    """``handler method name -> skill name``, read off the routing dict itself."""
    routed: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict) or not node.keys:
            continue
        if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in node.keys):
            continue
        if not all(isinstance(v, ast.Attribute) for v in node.values):
            continue
        if len(node.values) < _MIN_TABLE_ROWS:
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            assert isinstance(key, ast.Constant) and isinstance(value, ast.Attribute)
            routed[value.attr] = key.value
    return routed


def _called_names(node: ast.AST) -> set[str]:
    return {
        (call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", None))
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    }


def handlers_not_selecting_off_the_tool(tree: ast.AST) -> list[tuple[str, str, int]]:
    """``(skill, handler, lineno)`` for every routed handler that does not call SELECTOR."""
    routed = dispatch_table(tree)
    offenders: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or node.name not in routed:
            continue
        if SELECTOR not in _called_names(node):
            offenders.append((routed[node.name], node.name, node.lineno))
    return sorted(offenders)


def _a2a_tree() -> ast.AST:
    return ast.parse(A2A_SERVER.read_text(), filename=str(A2A_SERVER))


def test_every_routed_skill_handler_selects_off_the_tool():
    tree = _a2a_tree()
    routed = dispatch_table(tree)
    assert len(routed) >= _MIN_TABLE_ROWS, (
        f"the skill dispatch table did not parse -- only {len(routed)} rows found. This "
        f"guard derives which methods are skill handlers from that table, so a table it "
        f"cannot read makes it pass vacuously."
    )

    violations = [
        f"{skill!r} -> {handler} (line {lineno})"
        for skill, handler, lineno in handlers_not_selecting_off_the_tool(tree)
    ]
    assert not violations, (
        f"An A2A skill handler does not select its request bag through {SELECTOR}(tool, bag). "
        f"That helper reads the DTO and the builder off the TOOL -- the same lookup MCP's "
        f"announcement and the REST body derive from -- so a handler that selects any other "
        f"way makes A2A accept a different field set than the other two transports, "
        f"silently. Call {SELECTOR}(<the tool function>, parameters) and pass the result to "
        f"the tool's build_*_request. Violations:\n  " + "\n  ".join(violations)
    )


def test_the_guard_reads_the_real_dispatch_table():
    """The table it grades against is the live one, with the skills actually routed."""
    routed = dispatch_table(_a2a_tree())

    assert routed["_handle_list_authorized_properties_skill"] == "list_authorized_properties"
    assert routed["_handle_get_products_skill"] == "get_products"
    # The DISPATCHER routes; it is not routed, so it carries no obligation here.
    assert "_handle_explicit_skill" not in routed


# ── Meta-tests: the detector itself ─────────────────────────────────────────
#
# The rule ships green, so its pass says nothing until the detector is shown to fire.

_TABLE = (
    "handlers = {\n"
    "    'alpha': self._handle_alpha_skill,\n"
    "    'beta': self._handle_beta_skill,\n"
    "    'gamma': self._handle_gamma_skill,\n"
    "    'delta': self._handle_delta_skill,\n"
    "    'epsilon': self._handle_epsilon_skill,\n"
    "}\n"
)


def _detect(handler_body: str) -> list[tuple[str, str, int]]:
    return handlers_not_selecting_off_the_tool(ast.parse(_TABLE + handler_body))


class TestGuardDetector:
    def test_fires_on_the_unnarrowed_selector(self):
        """The literal shape this guard was written for: accepted=None."""
        assert _detect(
            "async def _handle_alpha_skill(self, parameters, identity):\n"
            "    return AlphaRequest.model_validate(select_request_fields(AlphaRequest, parameters, None))\n"
        )

    def test_fires_on_a_hand_listed_bag(self):
        assert _detect(
            "async def _handle_alpha_skill(self, parameters, identity):\n"
            "    return build_alpha_request(x=parameters.get('x'))\n"
        )

    def test_silent_when_selecting_off_the_tool(self):
        assert not _detect(
            "async def _handle_alpha_skill(self, parameters, identity):\n"
            "    return build_alpha_request(**select_request_fields_for(alpha, parameters))\n"
        )

    def test_ignores_a_method_the_table_does_not_route(self):
        assert not _detect(
            "async def _handle_unrouted_skill(self, parameters, identity):\n    return AlphaRequest(x=1)\n"
        )

    def test_names_the_skill_not_just_the_method(self):
        """The message has to say which SKILL diverged; that is the buyer-facing name."""
        ((skill, handler, _),) = _detect(
            "async def _handle_beta_skill(self, parameters, identity):\n    return BetaRequest(x=1)\n"
        )

        assert skill == "beta"
        assert handler == "_handle_beta_skill"


class TestDispatchTableParsing:
    def test_reads_a_table(self):
        assert dispatch_table(ast.parse(_TABLE)) == {
            "_handle_alpha_skill": "alpha",
            "_handle_beta_skill": "beta",
            "_handle_gamma_skill": "gamma",
            "_handle_delta_skill": "delta",
            "_handle_epsilon_skill": "epsilon",
        }

    def test_ignores_a_dict_that_is_too_small_to_be_the_table(self):
        assert dispatch_table(ast.parse("x = {'a': self._handle_a_skill}")) == {}

    def test_ignores_a_dict_of_non_attribute_values(self):
        assert dispatch_table(ast.parse("x = {'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5}")) == {}
