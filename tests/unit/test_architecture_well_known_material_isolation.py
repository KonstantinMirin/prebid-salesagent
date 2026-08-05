"""Guard: only ONE handler in well_known.py ever resolves signing MATERIAL.

#1291 A5 follow-up, salesagent-z6nr.27. The architect review flagged that the
"narrowed seam" invariant (only the revocation-list handler decrypts a
private key; the other three secret-free bootstrap documents never do)
rested on convention, not enforcement — the shared ``DocumentBuilder`` type
hands every handler the whole ``TrustRootUoW``, so any handler COULD call
``resolve_signing_material``/``resolve_signing_provider`` without a type
error. This guard makes the invariant executable: an AST scan of
``src/routes/well_known.py`` for calls to either name, asserting they occur
in exactly one named function.

Widening from one call site to two (or moving the call into a shared helper
this module's handlers all invoke) is exactly the regression this guard
exists to catch: it would mean a currently-unauthenticated, secret-free
bootstrap route (brand.json/adagents.json/jwks.json) started resolving
private key material on every GET — a DoS-adjacent amplification surface on
routes whose module docstring justifies their lack of auth by carrying no
secret.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.unit._architecture_helpers import iter_call_expressions

REPO_ROOT = Path(__file__).resolve().parents[2]
WELL_KNOWN_MODULE = REPO_ROOT / "src" / "routes" / "well_known.py"

_MATERIAL_RESOLVERS = ("resolve_signing_material", "resolve_signing_provider")


def _functions_calling_material_resolvers(tree: ast.Module) -> set[str]:
    """Names of top-level functions whose body calls a material resolver."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(next(iter_call_expressions(node, name=resolver), None) is not None for resolver in _MATERIAL_RESOLVERS):
            found.add(node.name)
    return found


def test_exactly_one_handler_resolves_signing_material():
    tree = ast.parse(WELL_KNOWN_MODULE.read_text(encoding="utf-8"), filename=str(WELL_KNOWN_MODULE))
    resolvers = _functions_calling_material_resolvers(tree)
    assert resolvers == {"_governance_revocations_handler"}, (
        "exactly one well_known.py handler may resolve signing material "
        "(resolve_signing_material/resolve_signing_provider) -- the three secret-free "
        f"bootstrap documents must never touch private key material. Found: {sorted(resolvers)}"
    )


# ---------------------------------------------------------------------------
# Meta-tests: the detector can actually go red, and does not cry wolf on
# unrelated calls.
# ---------------------------------------------------------------------------

_TWO_HANDLERS_SOURCE = """
def handler_a(uow, tenant, now):
    material = resolve_signing_material(uow.signing_keys, tenant_id=tenant.tenant_id, now=now)
    return material

def handler_b(uow, tenant, now):
    return resolve_signing_provider(uow.signing_keys, tenant_id=tenant.tenant_id, now=now)
"""

_ONE_HANDLER_SOURCE = """
def handler_a(uow, tenant, now):
    return build_jwks(uow.signing_keys.publishable_at(now=now, grace_seconds=1))

def handler_b(uow, tenant, now):
    material = resolve_signing_material(uow.signing_keys, tenant_id=tenant.tenant_id, now=now)
    return material
"""


def test_detector_flags_more_than_one_resolving_handler():
    tree = ast.parse(_TWO_HANDLERS_SOURCE)
    assert _functions_calling_material_resolvers(tree) == {"handler_a", "handler_b"}


def test_detector_does_not_flag_unrelated_calls():
    tree = ast.parse(_ONE_HANDLER_SOURCE)
    assert _functions_calling_material_resolvers(tree) == {"handler_b"}
