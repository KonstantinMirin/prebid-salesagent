# Un-recorded beads state — write these back when the Dolt server is reachable

**Why this file exists:** the beads Dolt server (127.0.0.1:61525) became unreachable
mid-session with `dial tcp: can't assign requested address`, then `i/o timeout`. Cause is
the machine-wide ephemeral-port exhaustion documented on epic `salesagent-3v5a`
(all 16,383 ports in 49152-65535 occupied; ~64k TIME_WAIT sockets machine-wide, sustained
by 44 docker containers and ~19 concurrent peer agent sessions). Six retries over two
minutes did not recover. Nothing is lost — it is all written here.

## Atom transitions not yet recorded

| atom | intended state | reason |
|---|---|---|
| `salesagent-id0u.47` | **CLOSE** | L7 implemented; see below |
| `salesagent-id0u.48` | **CLAIM** | L7 diff-review, next in the chain |

Close reason for `.47`:
> L7 implemented: CompletedTaskStatusMixin + AlwaysIncludeFieldsMixin in `_base.py`,
> composed into 4 + 2 adopters, ApprovalStatus aliased to the library enum; all 101 tests
> in `test_adcp_contract.py` + `test_architecture_schema_inheritance.py` green.

## L7 implementation record (append to `salesagent-3v5a.7`)

### What landed — `src/core/schemas/_base.py`
- **`CompletedTaskStatusMixin`** (plain mixin, beside `NestedModelSerializerMixin`).
  Docstring states the spec fact, then records the **per-adopter obsolescence condition**
  as gate-strengthening (3) required: the sync pair is temporary and dies when adcp ships
  the field; the create/update pair is permanent because the parents already type the
  field and the mixin only supplies the default. Explicitly notes base order is style, not
  contract, and that `GetMediaBuysResponse` deliberately stays out.
- **`AlwaysIncludeFieldsMixin`** with `_ALWAYS_INCLUDE_NULL_FIELDS: ClassVar[frozenset[str]]`.
  Both gate-Q4 footguns are named in the docstring rather than inherited silently:
  (i) an explicit `exclude={...}` would be defeated by the `getattr` re-insert;
  (ii) under `mode="json"` the re-insert puts a raw Python value in.
- Adopters: `CreateMediaBuySuccess`, `UpdateMediaBuySuccess` (both first-in-bases; their
  local `status` declarations deleted, surrounding comments repointed at the mixin),
  `GetMediaBuysMediaBuy` (hand-written `confirmed_at` re-insert deleted; its `model_dump`
  now only re-serializes local package subclasses).
- `ApprovalStatus = LibraryApprovalStatus` replacing the hand-written 3-member StrEnum.

### `account.py` / `creative.py`
- `SyncAccountsResponse` and `SyncCreativesResponse` compose the mixin; their two
  near-paraphrase rationale blocks collapse to one pointer each, each stating its own
  obsolescence condition.
- `Account` adopts `AlwaysIncludeFieldsMixin`; its bespoke `_ALWAYS_INCLUDE` set + loop
  deleted (same three fields, identical `getattr` semantics preserved).

### One deviation from the design, and why

The design said to import the library enum as `LibraryCreativeApprovalStatus`. That made
`test_all_library_types_have_local_subclass` **fail**, and the failure was correct: the
guard reads `Library<X>` as "local class X must be or extend this", and
`src.core.schemas` already exports an unrelated `CreativeApprovalStatus`
(`creative.py:252`, a per-creative *result model*, imported under that bare name by
`media_buy_create.py:137`). The guard pointed at that model.

Resolved by aliasing to **our** name for the concept — `CreativeApprovalStatus as
LibraryApprovalStatus` — so the guard checks `ApprovalStatus`, which *is* the library
type, and passes. The import comment records both reasons (star-import shadowing and the
guard's name-based mapping). This is the same name-based collector weakness that owner
ruling **A7** directs L11 to fix properly.

### Verification
- `tests/unit/test_adcp_contract.py` — 99 passed (the 9 RED cases now green).
- `tests/unit/test_architecture_schema_inheritance.py` — 2 passed.
- Full `tests/unit` — 5642 passed, 9 skipped, 26 xfailed. Only failures are (a)
  `test_architecture_bdd_no_shadowed_steps.py::test_no_domain_exact_text_shadows_generic_parser`,
  the deliberately-RED L6 guard authored this session, and (b) the two
  `test_e2e_port_allocation.py` cases blocked by the ephemeral-port exhaustion.
- Runtime check of the composed classes: all four carry the mixin with default
  `"completed"`; `ApprovalStatus.__module__` is
  `adcp.types.generated_poc.enums.creative_approval_status`; `Account` declares
  `{advertiser, payment_terms, rate_card}` and `GetMediaBuysMediaBuy` declares
  `{confirmed_at}`.

### Not yet run for L7
Integration verification. `tests/integration` began erroring partway through with
`psycopg2.OperationalError: ... Can't assign requested address` — the ephemeral exhaustion
now blocks **outbound** connections, not just binds, so the DB became unreachable mid-run
(20 tests passed before it did).

---

## Second batch of un-recorded state (beads still down)

| atom | intended state |
|---|---|
| `salesagent-id0u.39` (L6 write-test) | **CLOSE** — guard authored, verified RED on the UC-005 collision |
| `salesagent-id0u.40` (L6 implement) | **CLOSE** — see below |
| `salesagent-id0u.53` (L8 write-test) | **CLOSE** — RED cases authored on `_stamp_a2a_protocol_fields(...)["message"]` |
| `salesagent-id0u.54` (L8 implement) | **CLOSE** — see below |
| `salesagent-id0u.73` (L11 solution-review) | gate ran; verdict not retrievable (beads down) |
| `salesagent-id0u.74` (L11 implement) | **PARTIAL** — DB/GitHub-free items done, see below |

### L6 — implemented, guard green with an EMPTY allowlist
- **F16**: deleted the exact-text `then_response_schema_valid` from
  `tests/bdd/steps/domain/uc005_format_id_roundtrip.py` (body was
  `assert isinstance(formats, list)`), leaving the generic full-validation parser as the
  sentence's single meaning. Replaced with a comment recording why.
- **F14**: `tests/bdd/steps/generic/then_schema.py:42` — the exact-text
  `"the response envelope carries status completed"` is now
  `parsers.parse("the response envelope carries status {expected_status}")`.
- **A6 ref fix**: `BR-UC-005-...feature:1071` now names
  `creative/list-creative-formats-response.json`. The bare basename resolved to TWO pinned
  documents. Category confirmed against this repo's own registry
  (`test_pydantic_schema_alignment.py:931`).
  A parallel qualification of `sync-accounts-response.json` was made and then REVERTED —
  that ref is not ambiguous, so the edit was out of lane.
- **F17b**: rewrote the inverted rationale in `tests/bdd/test_uc018_list_creatives.py`.
  It had presented inline re-registration of a shared sentence as a virtue ("keeping the
  blast radius to UC-018"); it now says the opposite and points at the guard.
- **F17c**: moved the three orphaned traceability comments (`# @bva brand`, `# POST-S5`,
  `# POST-S6`) back above the inserted `@T-UC-011-sync-schema-valid` scenario, onto
  `sync-create` whose own tags are `@post-s5 @post-s6`.
- **Guard result**: `parser_count=1168`, `line_count=12665`, `matched_line_count=5653`,
  **1 overlap at HEAD** (the UC-005 collision), **0 after the deletion**. Non-vacuity is
  asserted on all three counts, so a pytest bump cannot make it pass by scanning nothing.

**STILL OPEN in L6:** the A6 xfail-ledger routing for the UC-005 scenario. It needs the
GitHub issue number for the pixel_tracker catalog-vs-pin gap, and per **A8** that number
may only be chosen after an extensive open+closed search. GitHub is unreachable
(`dial tcp 140.82.121.5:443: can't assign requested address`). Adding a FIXME with an
unresolvable reference would violate the project rule, so this is deliberately not done.

### L8 — implemented
`GetMediaBuysResponse.__str__` added, mirroring the same-file sibling
`ListAuthorizedPropertiesResponse.__str__`: 0 -> "No media buys found.", 1 -> "Found 1
media buy.", N -> "Found N media buys.". Verified end-to-end:
`_stamp_a2a_protocol_fields(GetMediaBuysResponse(media_buys=[]))["message"]` is now
`'No media buys found.'` instead of the 316-char repr. The docstring records that MCP hits
the same method via `mcp_result(response)` -> `_mcp.py:27`.

### L11 — the DB/GitHub-free items
- **F22 errexit**: split the `&&`-list at `run_all_tests.sh:151`, with the A/B repro in the
  comment. `bash -n` clean.
- **F23 DRY**: extracted `_resolved_allof_arms` in `test_pydantic_schema_alignment.py`;
  `_allof_required_fields` and `_allof_properties` are now comprehensions over it.
  Last-arm-wins merge semantics preserved deliberately.
- **F26 / A7 collector fix — the substantive one.** `test_architecture_schema_inheritance.py`
  now collects redefinition targets by **MRO membership** (`_get_redefinition_targets`)
  instead of by alias-minus-`Library`, and grades with `assert_violations_match_allowlist`
  so the allowlist can only shrink. `ALIAS_ONLY_TYPES` hoisted to module scope;
  `_UNIVERSAL_BASES` excludes `AdCPBaseModel` so the fix does not flag every schema.
  All six previously-invisible redefinitions dispositioned:
  * `SyncAccountsResponse.accounts`, `SyncCreativesResponse.creatives` -> **allowlisted**
    (Pattern #4 narrowing to local subclasses that add fields the library type lacks).
  * `AdCPPackageUpdate.targeting_overlay` -> already allowlisted; now actually reachable.
  * `SyncAccountsResponse.dry_run`, `.context`, `.ext` -> **DELETED as stale**. `dry_run`
    was byte-identical to the parent; `context` widened to accept a raw dict although
    `SyncAccountsRequest.context` is itself a `ContextObject`; `ext` weakened the parent's
    `ExtensionObject` to a bare dict and no construction site passes it. The
    `SyncCreativesResponse` twin already inherits all three. Stale class docstring fixed too.
- **F27 docs de-count**: `docs/development/structural-guards.md` no longer quotes a count
  (it said 27; the set held 44).
- **Prose**: `media_buy_list.py` now names the real producers
  (`_stamp_confirmation_if_needed`, `_bump_parent_revision` — verified those symbols exist;
  an earlier draft cited a `confirm()` that does not);
  `models.py` lost the false "the two cannot drift" claim and now distinguishes
  present-and-null (get_media_buys) from absent (create's not-yet-committed arms);
  `tests/harness/media_buy_create_list.py` now cites `_run_mcp_client`, the dispatcher that
  actually runs, instead of the deprecated `_run_mcp_wrapper`;
  `uc019_query_media_buys.py` no longer implies it grades the whole storyboard step —
  checked against `git show v3.1.1:dist/compliance/3.1.1/domains/media-buy/index.yaml`,
  `check_buy_status` carries **six** validations and these Thens grade three; the three
  ungraded ones are named, with the reason (no correlation_id is sent).

**STILL OPEN in L11:** F29 (beads-ids -> GH numbers; needs `gh`), the ticket filing
(needs `gh` + A8 search), and F28's guard comment reconciliation.

### Two pre-existing mypy errors from earlier lanes, fixed
Neither was introduced this batch; both were left by L3/L5 and the branch must finish green.
- `_media_buy_status.py:143` — indexed `dict[PersistedMediaBuyStatus, str]` with a bare
  `str`. Now converts through `PersistedMediaBuyStatus(persisted)`.
- `media_buy_update.py` x3 — `_adcp_status_and_actions` requires a `MediaBuy` but received
  `MediaBuy | None`. `_revision_or_raise` renamed to `_buy_and_revision_or_raise` and now
  returns `(buy, revision)`, so the one place that proves the row exists also hands callers
  a non-optional row.

### Quality gate at this point
`ruff format --check` clean (1267 files) - `ruff check` clean - `mypy src/` **Success, 283
source files** - `pytest tests/unit` **5642 passed**, 9 skipped, 26 xfailed.
The only failures are the now-**four** `test_e2e_port_allocation.py` cases, all from the
ephemeral-port exhaustion (it has worsened during the session: two more cases that bind
ports now fail as well).
