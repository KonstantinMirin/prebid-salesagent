"""Guard: a format reference is never identified by comparing ``.format_id`` directly.

Disease (#1388): ``FormatId`` exists twice — the library type the AdCP schemas
declare, and ``src.core.schemas._base.FormatId``, a subclass that adds ``__str__``
and dimension helpers but not a single field. Pydantic v2 equality is
class-sensitive, so two references naming the very same format compare UNEQUAL
across those two classes; and pydantic does not re-validate a model instance that
already satisfies an annotation, so whichever class a caller happened to build
survives all the way down into ``CreativeAsset.format_id``.

What that cost: the A2A boundary pre-typed format_id into the subclass while MCP
and REST left it library-typed, so ``fmt.format_id == creative_format`` against a
registry listing matched NOTHING on A2A alone. The generative branch was never
entered, and a creative that should have been built (or rejected for a missing
API key) was silently written as a plain static asset. No error, no log, one
transport wrong.

A bare string is the same trap from the other side: a declared ``format_id: str``
compared against a model can never match, so the lookup degrades to "unknown
format" for every input.

**What is banned:** using a ``.format_id`` ATTRIBUTE as an operand of ``==``,
``!=``, ``in`` or ``not in`` anywhere in ``src/``. Format identity goes through
``src.core.format_resolver.find_format`` / ``format_identity``, which key on
``(agent_url, id, width, height, duration_ms)`` and are total over the three
shapes a reference actually arrives in (model, dict, bare string).

**Not banned:** comparing a component — ``fmt.format_id.id == wanted_id`` reads a
plain ``str`` off the reference, which is precisely what the shared helper does
internally and cannot carry a class mismatch. Nor is a comparison whose operand is
the helper's own result, since that is already a normalized tuple.

**Allowlist:** two pre-existing sites, both carrying ``# FIXME(#1388)`` at the
source. It may only ever shrink.
"""

import ast

from tests.unit._architecture_helpers import (
    REPO_ROOT,
    assert_detector_catches_ast_snippets,
    parse_module,
    src_python_files,
)

#: Files still comparing a format reference directly. Both are tracked by #1388;
#: neither is reachable from the creative-sync path this guard was written for.
#: ALLOWLISTS ONLY SHRINK — fix a site, delete its line.
ALLOWLIST = frozenset(
    {
        # get_format() compares a declared `format_id: str` against a FormatId
        # model, so its no-agent_url branch never matches anything.
        "src/core/format_resolver.py",
        # `creative.format_id in <set of config strings>` — a model against
        # strings, so no creative is ever auto-approvable.
        "src/adapters/mock_creative_engine.py",
    }
)


def find_format_id_identity_comparisons(tree: ast.Module) -> list[int]:
    """Line numbers where a ``.format_id`` attribute is an operand of an identity test.

    Every operand of the comparison is checked, not just the left one: the defect
    is symmetric, and ``wanted == fmt.format_id`` fails exactly as silently as
    ``fmt.format_id == wanted``.
    """
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)) for op in node.ops):
            continue
        for operand in [node.left, *node.comparators]:
            if isinstance(operand, ast.Attribute) and operand.attr == "format_id":
                lines.append(node.lineno)
                break
    return sorted(lines)


def test_format_identity_goes_through_the_shared_helper():
    violations: list[str] = []
    for path in src_python_files(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWLIST:
            continue
        for lineno in find_format_id_identity_comparisons(parse_module(path)):
            violations.append(f"{rel}:{lineno}")
    assert not violations, (
        "A format reference is being identified by comparing .format_id directly. "
        "FormatId exists as both the library type and a local subclass, and pydantic v2 "
        "equality is class-sensitive — so this comparison silently matches NOTHING "
        "whenever the two sides were built by different code paths (#1388). Use "
        "src.core.format_resolver.find_format (or format_identity):\n  " + "\n  ".join(violations)
    )


def test_the_allowlist_has_not_gone_stale():
    """An allowlisted file that no longer offends must leave the allowlist."""
    still_offending = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in src_python_files(REPO_ROOT)
        if path.relative_to(REPO_ROOT).as_posix() in ALLOWLIST
        and find_format_id_identity_comparisons(parse_module(path))
    }
    assert still_offending == set(ALLOWLIST), (
        "These files are allowlisted but no longer compare .format_id directly — "
        f"delete them from ALLOWLIST: {sorted(set(ALLOWLIST) - still_offending)}"
    )


def test_guard_catches_known_bad_shapes():
    """Positive meta-tests: every way the class-sensitive comparison reappears."""
    assert_detector_catches_ast_snippets(
        find_format_id_identity_comparisons,
        snippets={
            # The defect verbatim: the loop the shared helper replaced.
            "equality_loop_over_a_registry_listing": (
                "def f(all_formats, creative_format):\n"
                "    for fmt in all_formats:\n"
                "        if fmt.format_id == creative_format:\n"
                "            return fmt\n"
                "    return None\n"
            ),
            # Same defect written the other way round — operand order is irrelevant.
            "reversed_operand_order": ("def f(fmt, wanted):\n    return wanted == fmt.format_id\n"),
            # Membership is equality N times over, and hides the same mismatch.
            "membership_in_a_collection": ("def f(creative, approved):\n    return creative.format_id in approved\n"),
            # A negative test is just as silently wrong.
            "inequality": ("def f(fmt, wanted):\n    return fmt.format_id != wanted\n"),
            # A comprehension is the loop above with different syntax; a guard that
            # only looked at `if` statements would wave this straight through.
            "comprehension_filter": (
                "def f(all_formats, wanted):\n    return [f for f in all_formats if f.format_id == wanted]\n"
            ),
            # Chained through a longer receiver — the attribute is still the operand.
            "nested_receiver": ("def f(response, wanted):\n    return response.creative.format_id == wanted\n"),
        },
    )


def test_guard_ignores_the_fixed_shape():
    """Negative meta-test: the shared helper must not flag itself."""
    fixed = (
        "from src.core.format_resolver import find_format, format_identity\n"
        "\n"
        "def f(all_formats, creative_format):\n"
        "    return find_format(all_formats, creative_format)\n"
        "\n"
        "def g(fmt, wanted):\n"
        "    return format_identity(fmt.format_id) == format_identity(wanted)\n"
    )
    assert find_format_id_identity_comparisons(ast.parse(fixed)) == []


def test_guard_ignores_component_comparisons():
    """Negative meta-test: comparing a component reads a plain value, not a model.

    ``fmt.format_id.id`` is a ``str`` and ``fmt.format_id.width`` an ``int`` —
    neither can carry a class mismatch, and the shared helper compares exactly
    these internally. Flagging them would leave no legal way to express identity
    at all.
    """
    components = (
        "def f(fmt, wanted_id):\n"
        "    if fmt.format_id.id == wanted_id:\n"
        "        return True\n"
        "    return fmt.format_id.width != 300\n"
    )
    assert find_format_id_identity_comparisons(ast.parse(components)) == []


def test_guard_ignores_non_identity_operators():
    """Negative meta-test: ordering and identity-by-reference are not this disease.

    ``is None`` asks whether a reference exists, which is the presence check every
    caller legitimately makes before resolving anything.
    """
    presence = "def f(creative):\n    return creative.format_id is not None\n"
    assert find_format_id_identity_comparisons(ast.parse(presence)) == []
