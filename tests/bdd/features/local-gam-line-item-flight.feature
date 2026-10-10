# Hand-authored feature — not compiled from adcp-req.
#
# LOCALLY-ADDED (survives BR-*.feature regeneration).
#
# Seller-side adapter behavior, not protocol behavior: the instants a buyer names
# on create_media_buy are the instants the GAM line item flies. The pinned
# request (adcp==6.6.0 -> _schemas/3.1) defines them as
#   start_time: core/start-timing.json — "asap" or an ISO 8601 date-time
#   end_time:   media-buy/create-media-buy-request.json .properties.end_time —
#               ISO 8601 date-time
# so each names an absolute instant (the request schema refuses a value without
# an offset). GAM reads a DateTime's date/hour/minute/second in the zone its
# timeZoneId names; the line item has to carry the network's wall clock AND the
# network's zone, or it flies hours off the instant asked for.
#
# In-process transports only: the live e2e_rest server's tenants run the Mock
# adapter (E2EUnsupportedSetup from MediaBuyCreateEnv.sell_through_gam).
Feature: A GAM line item flies at the instants the buyer asked for (local)

  # Routed to MediaBuyCreateEnv by the T-UC-002-ext- tag prefix
  # (tests/bdd/conftest.py, the "uc002-ext" row).

  @T-UC-002-ext-gam-flight @extension @local-gam-flight
  Scenario Outline: The buyer's flight reaches GAM as the network's wall clock
    Given a valid create_media_buy request
    And the account exists and is active
    And the tenant sells through Google Ad Manager on a network in time zone "America/Los_Angeles"
    And start_time is <start>
    And end_time is <end>
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And GAM receives a line item starting <gam_start> and ending <gam_end> in time zone "America/Los_Angeles"

    # Winter (PST, UTC-8), summer (PDT, UTC-7), and an instant given with a
    # non-UTC offset: the same instant as the first row.
    Examples:
      | start                     | end                       | gam_start           | gam_end             |
      | 2027-01-15T15:00:00Z      | 2027-02-15T08:00:00Z      | 2027-01-15T07:00:00 | 2027-02-15T00:00:00 |
      | 2027-07-15T15:00:00Z      | 2027-08-15T07:00:00Z      | 2027-07-15T08:00:00 | 2027-08-15T00:00:00 |
      | 2027-01-15T10:00:00-05:00 | 2027-02-15T03:00:00-05:00 | 2027-01-15T07:00:00 | 2027-02-15T00:00:00 |

  @T-UC-002-ext-gam-flight-asap @extension @local-gam-flight
  Scenario: An "asap" start reaches GAM as a line item that starts immediately
    # GAM requires a line item's startDateTime to be in the future, and "asap"
    # resolves to the moment of the request, which has passed by the time the
    # line item is sent. IMMEDIATELY has GAM start it at the moment it is created.
    Given a valid create_media_buy request
    And the account exists and is active
    And the tenant sells through Google Ad Manager on a network in time zone "America/Los_Angeles"
    And start_time is asap
    And end_time is 2027-02-15T08:00:00Z
    When the Buyer Agent sends the create_media_buy request
    Then the response should succeed
    And GAM receives a line item starting immediately and ending 2027-02-15T00:00:00 in time zone "America/Los_Angeles"
