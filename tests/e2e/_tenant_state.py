"""Shared helpers for mutating the ci-test tenant's adapter config in e2e tests.

The adapter_config row is SHARED tenant state across the whole e2e session.
Any test that switches to manual approval (``manual=True``) MUST restore
``manual=False`` in a finally block: leaving manual approval on leaks into
every later e2e test (pytest-randomly ordering), turning their creates into
spec-3.1.1 submitted envelopes with no media_buy_id.
"""

import psycopg2


def set_mock_approval(live_server: dict, *, manual: bool) -> None:
    """Set ci-test's mock adapter approval mode (SHARED tenant state)."""
    try:
        conn = psycopg2.connect(live_server["postgres"])
        cursor = conn.cursor()

        cursor.execute("SELECT tenant_id FROM tenants WHERE subdomain = 'ci-test'")
        tenant_row = cursor.fetchone()
        if tenant_row:
            tenant_id = tenant_row[0]
            cursor.execute(
                """
                INSERT INTO adapter_config (tenant_id, adapter_type, mock_manual_approval_required)
                VALUES (%s, 'mock', %s)
                ON CONFLICT (tenant_id)
                DO UPDATE SET mock_manual_approval_required = EXCLUDED.mock_manual_approval_required,
                              adapter_type = 'mock'
                """,
                (tenant_id, manual),
            )
            conn.commit()
            mode = "manual approval required" if manual else "auto-approval enabled"
            print(f"Updated adapter config for tenant {tenant_id}: {mode}")
        else:
            print("Warning: ci-test tenant not found for adapter config update")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Failed to update adapter config: {e}")
