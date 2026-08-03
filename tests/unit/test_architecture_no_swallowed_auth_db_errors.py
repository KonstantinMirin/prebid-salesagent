"""Structural guard: fixed auth/tenant-lookup functions must not re-swallow DB errors.

salesagent-xg5w.2: get_principal_from_token() and 10 sibling functions caught a
broad `except Exception` around a DB/IO call in an auth-critical function and
returned/fell-through to a generic deny sentinel -- a genuine DB outage was
therefore indistinguishable from "token invalid" / "not an admin" / etc.

This guard pins each fixed function's source to NOT contain a bare
`except Exception` (or `except BaseException`) handler around its DB/IO call,
preventing the exact regression. It intentionally does not attempt to catch
the disease elsewhere in the codebase (that needs the multi-lens semantic scan
this ticket ran, not a cheap syntactic check) -- see the disposition table on
salesagent-xg5w.2 for the full sweep and the DEFER rows' follow-up tickets
(salesagent-xg5w.7, salesagent-xg5w.8, epic salesagent-ctmz).
"""

import ast
import importlib

# (module_path, function_name) pairs fixed by salesagent-xg5w.2.
_FIXED_FUNCTIONS = [
    ("src.core.auth_utils", "get_principal_from_token"),
    ("src.admin.utils.helpers", "is_super_admin"),
    ("src.admin.utils.helpers", "is_tenant_admin"),
    ("src.admin.utils.helpers", "get_tenant_config_from_db"),
    ("src.core.config_loader", "get_default_tenant"),
    ("src.core.config_loader", "get_tenant_by_subdomain"),
    ("src.core.config_loader", "get_tenant_by_id"),
    ("src.core.config_loader", "get_tenant_by_virtual_host"),
    ("src.admin.auth_utils", "extract_user_info"),
]


def _handler_is_broad(node: ast.ExceptHandler) -> bool:
    if node.type is None:
        return True  # bare except:
    names = [ast.unparse(e) for e in node.type.elts] if isinstance(node.type, ast.Tuple) else [ast.unparse(node.type)]
    return bool({"Exception", "BaseException"} & set(names))


def _function_has_broad_except(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_handler_is_broad(node) for node in ast.walk(fn) if isinstance(node, ast.ExceptHandler))


def _find_function(module_path: str, func_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    file_path = importlib.import_module(module_path).__file__
    with open(file_path) as f:
        tree = ast.parse(f.read(), filename=file_path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    raise AssertionError(f"{func_name} not found in {module_path} ({file_path})")


def test_fixed_functions_do_not_swallow_broadly():
    """None of the 9 module-level fixed functions may reintroduce a broad except."""
    violations = []
    for module_path, func_name in _FIXED_FUNCTIONS:
        fn = _find_function(module_path, func_name)
        if _function_has_broad_except(fn):
            violations.append(f"  {module_path}.{func_name} -- broad except Exception/BaseException reintroduced")

    assert not violations, (
        "Auth/tenant-lookup functions fixed for salesagent-xg5w.2 now catch DB errors broadly again "
        "-- a real infra error will be silently reported as a denied/not-found decision:\n" + "\n".join(violations)
    )


def test_guard_catches_a_reintroduced_broad_except():
    """Meta-test (negative): the AST check must actually flag a broad except."""
    source = "def f():\n    try:\n        risky()\n    except Exception as e:\n        return None\n"
    fn = ast.parse(source).body[0]
    assert _function_has_broad_except(fn)


def test_guard_passes_clean_source():
    """Meta-test (positive): a function with no broad except (or a typed one) passes."""
    clean = ast.parse("def f():\n    try:\n        risky()\n    except ValueError:\n        return None\n").body[0]
    no_except = ast.parse("def f():\n    return risky()\n").body[0]
    assert not _function_has_broad_except(clean)
    assert not _function_has_broad_except(no_except)
