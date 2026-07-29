"""The two outbound escape hatches, spelled in exactly one place.

``src/core/security/outbound_http.py`` reads two environment variables to decide
whether the seam's default posture — no private/reserved addresses, no plaintext
http — may be relaxed for a test that needs a loopback origin. Three test
surfaces need to set them: the seam's own suite (``set_flags``), the
webhook-delivery envs that run a real local origin (``LocalOriginMixin``), and
the BDD env that grades a refusal (``RealResolverProductEnv``).

Three spellings of the same pair is three places to get one of them wrong — and
a test that means "both hatches closed" but sets only one grades the wrong gate
while still going green. So the names, and the ``"true"``/``"false"`` literals
the repo's ``== "true"`` convention reads, live here and nowhere else.

Both values are ALWAYS written, including the off case: a hatch left unset is a
hatch decided by whatever exported it into the shell (``run_all_tests_host.sh``
exports both as ``true``), which is how a refusal test gets silently disarmed.
"""

from __future__ import annotations

ALLOW_PRIVATE_ENV = "ADCP_OUTBOUND_ALLOW_PRIVATE"
ALLOW_INSECURE_ENV = "ADCP_OUTBOUND_ALLOW_INSECURE"


def egress_hatch_env(*, private: bool, insecure: bool) -> dict[str, str]:
    """Return the environment mapping that sets BOTH hatches explicitly.

    Args:
        private: Allow reserved/private-range destination addresses.
        insecure: Allow a plaintext ``http://`` scheme.

    Returns:
        A ``{name: "true"|"false"}`` mapping suitable for ``patch.dict(os.environ, ...)``
        or for feeding ``monkeypatch.setenv`` item by item.
    """
    return {
        ALLOW_PRIVATE_ENV: "true" if private else "false",
        ALLOW_INSECURE_ENV: "true" if insecure else "false",
    }
