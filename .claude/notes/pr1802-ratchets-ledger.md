# PR #1802 — Ratchets ledger, corrected against the tree

`salesagent-pldmk.14`'s K4. The ticket says the PR description's ratchets ledger
"is wrong on four numbers"; this is the corrected table, measured at the tree
rather than carried forward, plus the three live `# noqa: TID251` exemptions with
their reasons. Copy this into the PR description.

## Ratchets

Every number below was produced by re-running the repo's own hook, not by
reading a prior ledger. Both hooks report **unchanged**, which is the point: this
lane moved no ratchet.

| ratchet | value | source of truth |
|---|---|---|
| duplicate blocks — `src/` | 32 | `.pre-commit-hooks/check_code_duplication.py` |
| duplicate blocks — `tests/` | 72 | same |
| duplicate blocks — `scripts/` | 0 | same |
| C901 (complexity) | 178 | `.pre-commit-hooks/check_ruff_complexity_count.py` |
| PLR0912 (branches) | 131 | same |
| PLR0915 (statements) | 103 | same |
| `EXPECTED_UNSUPPORTED_DECLARATIONS` | 6 | `tests/unit/test_architecture_e2e_rest_escape_hatches.py` |
| live `# noqa: TID251` in `src/` | 3 | the three below; pinned by `SEAM_FILES` in `tests/unit/test_ruff_egress_bans.py` |

`EXPECTED_UNSUPPORTED_DECLARATIONS` is 6 and stays 6 in this PR. The path to 5
and then to 3 is recorded on `salesagent-pldmk.33` and `salesagent-pldmk.10`:
one entry retires with the egress-Given change, two more only once
`salesagent-pldmk.7` gives the verdict a wire projection, and the remaining
three are pre-existing and untouched here.

## The three sanctioned egress exemptions

The TID251 bans in `ruff-egress.toml` make raw egress imports an error across
`src/`. Exactly three sites are exempt, each self-documenting at the source and
each pinned by `SEAM_FILES` — a stale entry there fails the build, so this list
cannot drift from the code.

| site | import | why it is sanctioned |
|---|---|---|
| `src/core/security/outbound_http.py:158` | `httpx` | **the seam itself** — the one sanctioned `httpx` importer. Every other outbound call goes through `send`/`asend` here, which is the whole point of the ban (GH #1589). |
| `src/core/security/egress/policy.py:27` | `ipaddress` | **the egress package's own address classification** — the one sanctioned site. Address policy is decided here so no call site re-decides it (GH #1589). |
| `src/core/utils/mcp_client.py:36` | `StreamableHttpTransport` | **the MCP seam** — transport construction is factory-pinned immediately below the import, so the exemption covers construction rather than free use (GH #1589). |

`tests/unit/test_ruff_egress_bans.py` proves each ban actually fires and that
every exemption is live rather than prose — an exemption that stopped being
needed would fail, so the count of 3 is a measurement, not an assertion.
