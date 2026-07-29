"""The egress-hatch posture, settable on any env that grades a seam refusal.

``set_egress_hatches`` began life on ``RealResolverProductEnv`` for the
get_products property-list refusal. The ingest-time webhook refusal
(``create_media_buy`` with a ``push_notification_config.url`` the seam would
never dial) grades the same seam from ``MediaBuyCreateEnv``, and the BDD
guards forbid per-env ``hasattr`` branching in steps — so the method lives
here once and both envs mix it in, instead of each growing a copy that can
drift into setting only one hatch.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from tests.harness._realize import E2EUnsupportedSetup, realize_e2e
from tests.helpers.egress_hatches import egress_hatch_env


def _egress_hatches_on_the_live_stack(self: EgressHatchMixin, *, private: bool, insecure: bool) -> None:
    """Realize a hatch posture on the live e2e stack — whose posture is fixed, and open.

    ``docker-compose.e2e.yml`` exports ``ADCP_OUTBOUND_ALLOW_PRIVATE=true`` and
    ``ADCP_OUTBOUND_ALLOW_INSECURE=true`` on both the adcp-server (:81-82) and
    the runner (:227-228), and the process making the outbound request is not
    the process this test controls — so over e2e_rest the posture cannot be set
    from here. "Both hatches open" is therefore ALREADY realized and asking for
    it is a no-op; anything else has no surface at all and is declared
    unrealizable rather than silently graded against the stack's own posture.

    That asymmetry is deliberate and is what makes the two refusal causes the
    egress scenarios grade (a cloud-metadata address, an unresolvable host)
    meaningful over e2e_rest: both are refused with the hatches WIDE OPEN, so
    they are the only causes whose green mark over e2e_rest means the same
    thing as in-process.
    """
    if private and insecure:
        return
    raise E2EUnsupportedSetup(
        "docker-compose.e2e.yml opens both egress hatches for the test stack "
        "(adcp-server :81-82, runner :227-228), and the server's environment is "
        f"not settable from the test process: private={private}, insecure={insecure} "
        "cannot be realized over e2e_rest."
    )


class EgressHatchMixin:
    """Mixes ``set_egress_hatches`` into an env whose scenarios grade the seam.

    Host env must be an ``IntegrationEnv`` (relies on ``self._patchers`` for
    posture cleanup on exit).
    """

    _patchers: list

    @realize_e2e(_egress_hatches_on_the_live_stack)
    def set_egress_hatches(self, *, private: bool, insecure: bool) -> None:
        """Pin BOTH outbound escape hatches for the lifetime of this env.

        A refusal scenario that does not say which posture it runs under is
        graded by a different gate in each environment — the reserved-range gate
        under ``saci`` (hatches off), the metadata blocklist under
        ``run_all_tests_host.sh`` (:110-111 exports both on) — for one green
        mark. Saying it out loud makes the scenario name the gate it grades.

        The patcher joins ``self._patchers``, so ``IntegrationEnv.__exit__``
        stops it with everything else and no scenario leaks a posture into the
        next one.
        """
        patcher = patch.dict(os.environ, egress_hatch_env(private=private, insecure=insecure))
        patcher.start()
        self._patchers.append(patcher)
