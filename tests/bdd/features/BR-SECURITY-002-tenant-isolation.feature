# Hand-authored feature — not compiled from adcp-req
# Grades what salesagent-02rgd centralised: one resolver decides which tenant and which
# principal a request runs as. Until this feature existed nothing graded that decision --
# every other scenario seeds ONE tenant, so an unscoped query returns the right rows by
# accident and a broken filter is invisible.

@security
Feature: A credential reaches exactly one tenant's data
  As a publisher whose inventory sits in a shared database beside other publishers',
  I want a buyer's credential to resolve to exactly one tenant and one principal,
  so that no buyer can read, or be served, another tenant's data.

  Background:
    Given two tenants each own a product the other does not

  # POSITIVE, and it is only half a test on its own. "A sees A's product" also passes
  # when A sees EVERY tenant's products, so the absence assertion below it is what
  # separates a scoped query from an unscoped one.
  @T-SECURITY-002-own-tenant-only
  Scenario Outline: A buyer sees its own tenant's products and no other tenant's
    When the buyer requests products with tenant "<tenant>" credentials
    Then the response contains tenant "<tenant>" products
    And the response contains no tenant "<other>" products

    Examples:
      | tenant | other |
      | A      | B     |
      | B      | A     |

  # NEGATIVE. A token is minted per (tenant, principal) and the lookup filters on both
  # columns, so a credential is meaningless outside the tenant it belongs to. The failure
  # this guards against is the request being served ANYWAY -- either as the addressed
  # tenant (contamination) or as the token's own tenant (the address silently ignored).
  #
  # No error CODE is pinned here, on purpose. get_products is auth="optional", so a rejected
  # credential is downgraded to anonymous before the tool runs and the refusal comes from the
  # tenant's own brand_manifest_policy -- which reports AUTH_MISSING to a buyer who did
  # present a credential. That confusion is real and filed separately; this scenario grades
  # the security property, which is that the request is not served.
  @T-SECURITY-002-credential-does-not-cross-tenants
  Scenario Outline: A credential minted for one tenant is refused by the other
    When the buyer presents tenant "<holder>" credentials addressed to tenant "<target>"
    Then the request is refused and no products are returned

    Examples:
      | holder | target |
      | A      | B      |
      | B      | A      |
