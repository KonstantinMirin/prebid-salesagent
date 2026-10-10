# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# SUBJECT. A package's geo overlay reaches the line item the Google Ad Manager
# adapter creates, as GAM location ids, and a geo code the adapter cannot map to
# a GAM location is refused before anything is booked. The adapter used to load
# its geo mapping from a path that does not exist, continue with empty mappings,
# and book every geo-targeted package untargeted while the response echoed the
# overlay back to the buyer.
#
# PINNED AUTHORITY (adcp==6.6.0 -> _schemas/3.1, AdCP 3.1.1 — docs/adcp-spec-version.md).
#   core/targeting.json: geo_countries / geo_regions / geo_metros "Restrict
#   delivery to specific ..." — an overlay is a restriction, so booking without
#   it delivers outside what the buyer bought.
#   docs/protocol/get_adcp_capabilities.mdx § targeting (v3.1.1): a seller that
#   cannot serve a requested geo field "MUST return a validation error for
#   unsupported fields rather than silently ignoring them".
#   docs/building/by-layer/L3/error-handling.mdx § Server-narrowed public
#   elements (v3.1.1): a value the public schema accepts but the seller rejects
#   on its own state is refused with POLICY_VIOLATION or UNSUPPORTED_FEATURE,
#   not VALIDATION_ERROR. enums/error-code.json: UNSUPPORTED_FEATURE, recovery
#   correctable ("check get_adcp_capabilities and remove unsupported fields").
#   docs/reference/migration/geo-targeting.mdx (v3.1.1): "Inclusion fields are
#   combined with AND logic — delivery must match all specified constraints." GAM
#   ORs every targeted location, so the adapter books the finest inclusion list cut
#   to the listed countries, and refuses regions with metros (a state-by-DMA
#   intersection GAM cannot express).
#   STORYBOARD: ungraded — no dist/compliance/3.1.1 scenario sends a geo overlay.
#
# GAM IDS. The ids below are GAM Geo_Target ids: countries and regions checked by
# name against Google's geotargets table (the same id space), DMAs as 200000 + the
# Nielsen code.
#
# TRANSPORTS. In-process transports only: the real GAM adapter runs against an
# in-process stand-in for GAM's SOAP API (tests/helpers/gam_client), and the live
# e2e_rest server's tenants run the Mock adapter (E2EUnsupportedSetup from
# MediaBuyCreateEnv.sell_through_gam).
Feature: The GAM adapter books a package's geo overlay into its line item (local)

  # Routed to MediaBuyCreateEnv by the T-UC-002-ext- tag prefix
  # (tests/bdd/conftest.py, the "uc002-ext" row).

  Background:
    Given a valid create_media_buy request
    And the account exists and is active
    And the tenant sells through Google Ad Manager on a network in time zone "America/New_York"

  @T-UC-002-ext-gam-geo-mapped @extension @local-gam-geo
  Scenario Outline: The overlay's geo inclusions reach the line item as GAM locations - <case>
    Given the package targeting_overlay for the create is <overlay>
    When the Buyer Agent sends the create_media_buy request
    Then the result should be success
    And the line item sent to Google Ad Manager carries geoTargeting <geo_targeting>

    Examples:
      | case                                | overlay                                                                                      | geo_targeting                                                                   |
      | region (ISO 3166-2)                 | {"geo_regions": ["US-NY"]}                                                                   | {"targetedLocations": [{"id": "21167"}]}                                        |
      | metro (Nielsen DMA)                 | {"geo_metros": [{"system": "nielsen_dma", "values": ["501"]}]}                               | {"targetedLocations": [{"id": "200501"}]}                                       |
      | country                             | {"geo_countries": ["US"]}                                                                    | {"targetedLocations": [{"id": "2840"}]}                                         |
      | excluded region                     | {"geo_countries": ["US"], "geo_regions_exclude": ["US-CA"]}                                  | {"targetedLocations": [{"id": "2840"}], "excludedLocations": [{"id": "21137"}]} |
      | country AND region is the region    | {"geo_countries": ["US"], "geo_regions": ["US-NY"]}                                          | {"targetedLocations": [{"id": "21167"}]}                                        |
      | country AND metro is the metro      | {"geo_countries": ["US"], "geo_metros": [{"system": "nielsen_dma", "values": ["501"]}]}      | {"targetedLocations": [{"id": "200501"}]}                                       |
      | region outside the countries drops  | {"geo_countries": ["US"], "geo_regions": ["US-TX", "CA-ON"]}                                 | {"targetedLocations": [{"id": "21176"}]}                                        |

  @T-UC-002-ext-gam-geo-unmapped @extension @local-gam-geo
  Scenario Outline: A geo code with no GAM location is refused before anything is booked - <case>
    Given the package targeting_overlay for the create is <overlay>
    When the Buyer Agent sends the create_media_buy request
    Then the refusal is UNSUPPORTED_FEATURE naming capability "<capability>" and rejected value <rejected>
    And no order was created in Google Ad Manager

    Examples:
      | case            | overlay                                                        | capability          | rejected |
      | region          | {"geo_regions": ["FR-IDF"]}                                    | geo_regions         | "FR-IDF" |
      | metro           | {"geo_metros": [{"system": "nielsen_dma", "values": ["999"]}]} | geo_metros          | "999"    |
      | country         | {"geo_countries": ["IS"]}                                      | geo_countries       | "IS"     |
      | excluded region | {"geo_countries": ["US"], "geo_regions_exclude": ["FR-IDF"]}   | geo_regions_exclude | "FR-IDF" |

  @T-UC-002-ext-gam-geo-region-and-metro @extension @local-gam-geo
  Scenario: Regions with metros are refused, because GAM cannot intersect a state with a DMA
    Given the package targeting_overlay for the create is {"geo_regions": ["US-NY"], "geo_metros": [{"system": "nielsen_dma", "values": ["501"]}]}
    When the Buyer Agent sends the create_media_buy request
    Then the refusal is UNSUPPORTED_FEATURE naming capability "geo_regions_with_geo_metros" and rejected value ["US-NY", "501"]
    And no order was created in Google Ad Manager

  @T-UC-002-ext-gam-geo-disjoint @extension @local-gam-geo
  Scenario Outline: A finer inclusion wholly outside the listed countries leaves nowhere to deliver - <case>
    Given the package targeting_overlay for the create is <overlay>
    When the Buyer Agent sends the create_media_buy request
    Then the refusal is INVALID_REQUEST on targeting_overlay with geo_disjoint <geo_disjoint>
    And no order was created in Google Ad Manager

    Examples:
      | case   | overlay                                                                                 | geo_disjoint                                                                  |
      | region | {"geo_countries": ["CA"], "geo_regions": ["US-NY"]}                                     | [{"include": "geo_regions", "within": "geo_countries", "values": ["US-NY"]}] |
      | metro  | {"geo_countries": ["CA"], "geo_metros": [{"system": "nielsen_dma", "values": ["501"]}]} | [{"include": "geo_metros", "within": "geo_countries", "values": ["501"]}]    |
