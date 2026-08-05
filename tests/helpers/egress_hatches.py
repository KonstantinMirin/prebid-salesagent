"""The outbound escape hatch, spelled in exactly one place.

``src/core/security/outbound_http.py`` reads an environment variable to decide
whether the seam's default posture — no private/reserved destination addresses
— may be relaxed for a test that needs a loopback origin. Three test surfaces
need to set it: the seam's own suite (``set_flags``), the webhook-delivery envs
that run a real local origin (``LocalOriginMixin``), and the BDD env that
grades a refusal (``RealResolverProductEnv``).

Three spellings of the same value is three places to get it wrong — so the
name, and the ``"true"``/``"false"`` literal the repo's ``== "true"``
convention reads, live here and nowhere else.

The value is ALWAYS written, including the off case: a hatch left unset is a
hatch decided by whatever exported it into the shell, which is how a refusal
test gets silently disarmed.

``ADCP_OUTBOUND_ALLOW_INSECURE`` (salesagent-e6h0): production no longer reads
this at all — ``_require_tls``/``_require_https`` are unconditional. There is
therefore no ``insecure`` parameter here anymore; a caller cannot relax the
scheme gate through this helper because there is nothing left to relax.
``ALLOW_INSECURE_ENV`` is kept ONLY as a literal for tests proving the (now
inert) env var has no effect — see
``tests/integration/test_outbound_allow_insecure_gate_removal.py``.
"""

from __future__ import annotations

ALLOW_PRIVATE_ENV = "ADCP_OUTBOUND_ALLOW_PRIVATE"
ALLOW_INSECURE_ENV = "ADCP_OUTBOUND_ALLOW_INSECURE"


def egress_hatch_env(*, private: bool) -> dict[str, str]:
    """Return the environment mapping that sets the private-range hatch explicitly.

    Args:
        private: Allow reserved/private-range destination addresses.

    Returns:
        A ``{name: "true"|"false"}`` mapping suitable for ``patch.dict(os.environ, ...)``
        or for feeding ``monkeypatch.setenv`` item by item.
    """
    return {
        ALLOW_PRIVATE_ENV: "true" if private else "false",
    }
