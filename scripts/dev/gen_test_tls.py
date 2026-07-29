#!/usr/bin/env python3
"""Generate the test stacks' private CA and server certificate (salesagent-tgzb).

WHY THIS EXISTS. ``_get_protocol_for_domain`` (``src/core/domain_config.py``)
publishes ``https`` only for a dotted, non-loopback host — deliberately, because
advertising https for a host with no certificate publishes a trust root nothing
can reach. Every test host was such a host, so the https branch of the trust
root could never be exercised end to end. This mints the material that lets a
test host EARN https by actually serving it: a private CA and one leaf covering
the dotted names the test stacks are reachable at.

THE CAVEAT, STATED HERE RATHER THAN DISCOVERED LATER. A private CA is not
"publicly trusted", which is the exact wording of ``_get_protocol_for_domain``'s
rationale. That rationale is about reachability BY A COUNTERPARTY; in the test
stack the counterparty is our own client, which trusts this CA explicitly. The
production predicate needs no change and must not be weakened.

LIFECYCLE
    * Output lands in ``.test-tls/`` at the repo root — gitignored, and already
      inside the ``.:/app`` bind mount both the server and the runner get, so no
      compose plumbing has to distribute it.
    * Validity is deliberately SHORT (30 days) and regeneration is automatic:
      missing, unparseable, expiring within 7 days, or no longer covering the
      names we serve all trigger a rewrite. "Exists" is not the same as "valid",
      and a certificate that expires mid-suite is a flaky-test generator.
    * ``not_before`` is backdated an hour to absorb container/host clock skew.
    * NOTHING DELETES IT. It is a build artifact: regenerating per run would
      race parallel stacks that are already serving the previous leaf.

Run it directly, or via ``scripts/dev/ensure-test-tls.sh`` (which finds an
interpreter that has ``cryptography``, a direct dependency of this project).
"""

from __future__ import annotations

import datetime as dt
import ipaddress
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

REPO_ROOT = Path(__file__).resolve().parents[2]
TLS_DIR = REPO_ROOT / ".test-tls"
CA_CERT = TLS_DIR / "ca.pem"
CA_KEY = TLS_DIR / "ca.key"
SERVER_CERT = TLS_DIR / "server.pem"
SERVER_KEY = TLS_DIR / "server.key"

VALIDITY = dt.timedelta(days=30)
RENEW_WITHIN = dt.timedelta(days=7)
CLOCK_SKEW = dt.timedelta(hours=1)

# ``*.adcp.test`` is the whole per-worker mechanism: the bdd_e2e TLS sidecars are
# named ``<compose-project>-tls-gwN.adcp.test`` and COMPOSE_PROJECT_NAME never
# contains a dot, so every worker of every concurrent stack is exactly one label
# under this wildcard. ``agent.localhost`` is the host-published name: RFC 6761
# reserves ``.localhost`` for loopback, so it resolves with no DNS and no
# /etc/hosts edit, and it has a dot — which is what makes the predicate answer
# https for it without being told to.
SAN_DNS_NAMES = (
    "adcp.test",
    "*.adcp.test",
    "localhost",
    "agent.localhost",
    "*.localhost",
)
SAN_IP_ADDRESSES = ("127.0.0.1", "::1")

_CA_SUBJECT = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AdCP test stack CA")])
_LEAF_SUBJECT = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "adcp.test")])


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _subject_alt_name() -> x509.SubjectAlternativeName:
    names: list[x509.GeneralName] = [x509.DNSName(name) for name in SAN_DNS_NAMES]
    names.extend(x509.IPAddress(ipaddress.ip_address(addr)) for addr in SAN_IP_ADDRESSES)
    return x509.SubjectAlternativeName(names)


def _sign(
    *,
    subject: x509.Name,
    issuer: x509.Name,
    public_key: ec.EllipticCurvePublicKey,
    signing_key: ec.EllipticCurvePrivateKey,
    extensions: list[tuple[x509.ExtensionType, bool]],
) -> x509.Certificate:
    """Build and sign one certificate. Shared by the CA and the leaf."""
    now = _now()
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - CLOCK_SKEW)
        .not_valid_after(now + VALIDITY)
    )
    for extension, critical in extensions:
        builder = builder.add_extension(extension, critical=critical)
    return builder.sign(signing_key, hashes.SHA256())


def _key_usage(**enabled: bool) -> x509.KeyUsage:
    flags: dict[str, Any] = dict.fromkeys(
        (
            "digital_signature",
            "content_commitment",
            "key_encipherment",
            "data_encipherment",
            "key_agreement",
            "key_cert_sign",
            "crl_sign",
            "encipher_only",
            "decipher_only",
        ),
        False,
    )
    flags.update(enabled)
    return x509.KeyUsage(**flags)


def _write(path: Path, data: bytes, *, private: bool) -> None:
    path.write_bytes(data)
    path.chmod(0o600 if private else 0o644)


def _pem_cert(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _pem_key(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _is_current() -> bool:
    """True when the material on disk can still be served and still matches.

    Three independent reasons to regenerate, all of which have to be checked or
    "the file exists" quietly stands in for "the file works": it is missing or
    unreadable, it expires soon, or the SAN set drifted from what the stacks are
    reachable at (a name added to ``SAN_DNS_NAMES`` must actually reach a leaf).
    """
    if not all(path.is_file() for path in (CA_CERT, CA_KEY, SERVER_CERT, SERVER_KEY)):
        return False
    try:
        ca = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
        leaf = x509.load_pem_x509_certificate(SERVER_CERT.read_bytes())
        served = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except Exception:  # noqa: BLE001 - any parse failure means "regenerate", never "trust it"
        return False
    if set(served.get_values_for_type(x509.DNSName)) != set(SAN_DNS_NAMES):
        return False
    return min(ca.not_valid_after_utc, leaf.not_valid_after_utc) > _now() + RENEW_WITHIN


def ensure_test_tls(*, force: bool = False) -> Path:
    """Make sure ``.test-tls/`` holds a usable CA + leaf; return the CA bundle path.

    Idempotent: a run that finds current material writes nothing, so concurrent
    stacks serving the existing leaf are never disturbed.
    """
    if not force and _is_current():
        return CA_CERT

    TLS_DIR.mkdir(parents=True, exist_ok=True)

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = _sign(
        subject=_CA_SUBJECT,
        issuer=_CA_SUBJECT,
        public_key=ca_key.public_key(),
        signing_key=ca_key,
        extensions=[
            (x509.BasicConstraints(ca=True, path_length=0), True),
            (_key_usage(key_cert_sign=True, crl_sign=True), True),
            (x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False),
        ],
    )

    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_cert = _sign(
        subject=_LEAF_SUBJECT,
        issuer=ca_cert.subject,
        public_key=leaf_key.public_key(),
        signing_key=ca_key,
        extensions=[
            (_subject_alt_name(), False),
            (x509.BasicConstraints(ca=False, path_length=None), True),
            (_key_usage(digital_signature=True, key_agreement=True), True),
            (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False),
            (x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), False),
            (x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False),
        ],
    )

    _write(CA_KEY, _pem_key(ca_key), private=True)
    _write(CA_CERT, _pem_cert(ca_cert), private=False)
    _write(SERVER_KEY, _pem_key(leaf_key), private=True)
    # Full chain: the leaf first, then the issuer. Clients that trust ca.pem do
    # not need it, but a chain costs nothing and makes the file usable by tools
    # that do walk it.
    _write(SERVER_CERT, _pem_cert(leaf_cert) + _pem_cert(ca_cert), private=False)
    return CA_CERT


def main() -> None:
    ca = ensure_test_tls()
    print(f"test TLS material ready: {ca} (serving {', '.join(SAN_DNS_NAMES)})")


if __name__ == "__main__":
    main()
