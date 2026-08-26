"""Guard: a format reference is never identified by comparing ``.format_id`` directly.

Disease (#2093): ``FormatId`` exists twice — the library type the AdCP schemas
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

**Allowlist:** empty. The two sites this guard shipped with were fixed under the
follow-up rather than tolerated, so nothing in ``src/`` is exempt.
"""

import ast

from tests.unit._architecture_helpers import (
    REPO_ROOT,
    assert_detector_catches_ast_snippets,
    parse_module,
    src_python_files,
)

#: EMPTY, and it stays that way. Both original entries were fixed rather than tolerated:
#: get_format's no-agent_url branch now resolves through find_format_by_id, and the mock
#: creative engine tests membership on the id. ALLOWLISTS ONLY SHRINK — an addition here
#: is a decision to ship the defect this guard exists to prevent.
ALLOWLIST: frozenset[str] = frozenset()


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


#: The one module allowed to define what "the same agent_url" means. Everything else
#: calls ``canonical_agent_url`` / ``format_id_identity`` from it.
CANONICALIZER_MODULE = "src/core/schemas/_base.py"


def find_hand_rolled_agent_url_normalization(tree: ast.Module) -> list[int]:
    """Line numbers where an ``agent_url`` is normalized by hand FOR COMPARISON.

    The pinned schema makes this a MUST, not a preference: "Callers comparing two
    format-id values MUST canonicalize agent_url per the AdCP URL canonicalization
    rules before treating two formats as the same" (core/format-id.json, agent_url).
    ``canonical_agent_url`` delegates to the SDK's ``canonicalize_target_uri``, which
    lowercases scheme/host, drops default ports, normalizes percent-encoding and strips
    userinfo and fragment. ``str(x.agent_url).rstrip("/")`` does none of that and looks
    close enough to pass review -- which is how a second identity rule came to be
    written while the first sat twenty lines away.

    Two things the rule has to get right, both learned the hard way:

    - The receiver counts by ATTRIBUTE or by NAME. An attribute-only rule waved through
      ``agent_url = fmt.agent_url`` / ``str(agent_url).rstrip("/")`` while its sibling
      two lines up was migrated, leaving two key sets that are COMPARED to each other
      normalized by different rules. Half a migration on a compared pair is worse than
      none.
    - Only normalization used for COMPARISON is a violation. Trimming a slash before
      concatenating an endpoint (``agent_url.rstrip("/") + "/lists/" + id``) decides no
      identity, and flagging it would only teach authors to silence the guard. So the
      normalized value must reach a comparison, a tuple (the shape every format key in
      this codebase takes), or a membership test.
    """
    normalizers = {"rstrip", "strip", "lower", "replace", "removesuffix", "casefold"}

    def reads_agent_url(node: ast.AST) -> bool:
        return any(
            (isinstance(sub, ast.Attribute) and sub.attr == "agent_url")
            or (isinstance(sub, ast.Name) and "agent_url" in sub.id)
            for sub in ast.walk(node)
        )

    def is_normalizing_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in normalizers
            and reads_agent_url(node.func.value)
        )

    # Names that hold a hand-normalized agent_url -> EVERY line that built one. A dict
    # of name->single-line silently collapses two sites that reuse a variable name, which
    # is the exact shape this guard exists to catch: the two halves of a compared key
    # pair, both called `normalized_url`, one migrated and one not.
    tainted: dict[str, list[int]] = {}
    inline: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and is_normalizing_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    tainted.setdefault(target.id, []).append(node.lineno)
        elif isinstance(node, (ast.Tuple, ast.Compare)):
            inline.extend(sub.lineno for sub in ast.walk(node) if is_normalizing_call(sub))
        elif isinstance(node, ast.IfExp) and is_normalizing_call(node.body):
            # `x.rstrip("/") if x else None` — the conditional form both real sites used.
            parent_assign = None
            for outer in ast.walk(tree):
                if isinstance(outer, ast.Assign) and outer.value is node:
                    parent_assign = outer
                    break
            if parent_assign is not None:
                for target in parent_assign.targets:
                    if isinstance(target, ast.Name):
                        tainted.setdefault(target.id, []).append(parent_assign.lineno)

    used_for_comparison = {
        sub.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Tuple, ast.Compare))
        for sub in ast.walk(node)
        if isinstance(sub, ast.Name) and sub.id in tainted
    }
    flagged = {lineno for name in used_for_comparison for lineno in tainted[name]}
    return sorted(flagged | set(inline))


def test_agent_url_is_canonicalized_only_in_one_place():
    violations: list[str] = []
    for path in src_python_files(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == CANONICALIZER_MODULE:
            continue
        for lineno in find_hand_rolled_agent_url_normalization(parse_module(path)):
            violations.append(f"{rel}:{lineno}")
    assert not violations, (
        "agent_url normalized by hand. The pinned schema REQUIRES the AdCP canonical "
        "form before two format references may be treated as the same, and a trim is "
        "not it — it leaves scheme/host case, default ports, percent-encoding, "
        "userinfo and fragments to split references the spec says are one. Use "
        "src.core.schemas.canonical_agent_url (or format_id_identity):\n  " + "\n  ".join(violations)
    )


def test_the_canonicalization_guard_catches_the_shape_that_shipped():
    """Positive meta-tests: hand-normalized agent_url actually used to decide identity."""
    assert_detector_catches_ast_snippets(
        find_hand_rolled_agent_url_normalization,
        snippets={
            # The duplicate identity function, verbatim.
            "rstrip_inside_an_identity_tuple": (
                "def f(format_id):\n    return (str(format_id.agent_url).rstrip('/'), format_id.id)\n"
            ),
            # A key set built by hand — the shape media_buy_create used on both sides.
            "local_name_bound_from_the_attribute": (
                "def f(formats):\n"
                "    keys = set()\n"
                "    for fmt in formats:\n"
                "        agent_url = fmt.agent_url\n"
                "        normalized = str(agent_url).rstrip('/') if agent_url else None\n"
                "        keys.add((normalized, fmt.id))\n"
                "    return keys\n"
            ),
            # Same, under a prefixed local name — an `agent_url`-exact rule would miss it.
            "local_name_with_a_prefix": (
                "def f(fmt, other):\n"
                "    product_agent_url = fmt.agent_url\n"
                "    normalized = str(product_agent_url).rstrip('/')\n"
                "    return (normalized, fmt.id) == other\n"
            ),
            # Case-folding is the same rule written differently, and equally partial.
            "lower_inside_a_key_tuple": (
                "def f(fmt, keys):\n    return (fmt.format_id.agent_url.lower(), fmt.format_id.id) in keys\n"
            ),
            # Direct comparison, no tuple.
            "removesuffix_in_a_comparison": (
                "def f(agent, other):\n    return str(agent.agent_url).removesuffix('/mcp') == other\n"
            ),
        },
    )


def test_the_canonicalization_guard_ignores_the_canonical_call():
    """Negative meta-test: going through the shared canonicalizer is the fixed shape."""
    fixed = (
        "from src.core.schemas import canonical_agent_url, format_id_identity\n"
        "\n"
        "def f(format_id):\n"
        "    return format_id_identity(format_id)\n"
        "\n"
        "def g(agent):\n"
        "    return canonical_agent_url(agent.agent_url)\n"
        "\n"
        "def h(fmt):\n"
        "    agent_url = fmt.agent_url\n"
        "    return canonical_agent_url(agent_url) if agent_url else None\n"
    )
    assert find_hand_rolled_agent_url_normalization(ast.parse(fixed)) == []


def test_the_canonicalization_guard_ignores_urls_that_are_not_agent_urls():
    """Negative meta-test: trimming some other URL is not this disease.

    The guard stays pointed at format-reference identity. A display string, or an
    endpoint built from an already-resolved URL, normalizes nothing about identity --
    and flagging those would push authors to silence the guard rather than use the
    helper.
    """
    unrelated = "def f(url, fid):\n    clean_url = str(url).rstrip('/')\n    return f'{clean_url}/{fid}'\n"
    assert find_hand_rolled_agent_url_normalization(ast.parse(unrelated)) == []


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
        "whenever the two sides were built by different code paths (#2093). Use "
        "src.core.format_resolver.find_format (or format_identity):\n  " + "\n  ".join(violations)
    )


def test_the_allowlist_has_not_gone_stale():
    """An allowlisted file that no longer offends must leave the allowlist.

    Vacuous while ALLOWLIST is empty, and kept exactly for that reason: the moment
    somebody adds an entry, this is what forces its removal once the site is fixed,
    instead of letting a permanent exemption accumulate.
    """
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
