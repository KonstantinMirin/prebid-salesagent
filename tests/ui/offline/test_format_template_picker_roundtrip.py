"""Round-trip integrity of the GAM edit-product format picker.

Two symptoms of one root cause in ``static/js/format-template-picker.js``:
agent_url rebinding, and format multiplication on save. Both originate in the
single line added by GH #1168 (commit 9e395c5dc)::

    const templateId = FORMAT_TEMPLATES[id] ? id : expandedToTemplate[id];

which resolves a stored format to a template by ``id`` alone, discarding both
the agent that published it and which of the template's expanded ids was
actually stored. ``getSelectedFormats()`` then reconstitutes from the template,
re-inventing both facts from defaults. Found while reviewing GH #1600.

WHY A BROWSER TEST: the defect lives entirely in client-side JavaScript. The
picker builds the ``FormatId`` objects the product form submits, so it runs
BEFORE anything server-side sees the data -- the Python canonicalizer
(``format_id_identity``) cannot reach it. A Python test that re-implemented the
matching rules would assert against its own copy of the logic and could never
fail for a change to the real file, so these drive the actual shipped asset in a
real browser.

``tests/manual/test_format_template_roundtrip.js`` (added by #1168) is not a
substitute: no runner executes it, and it asserts only on ``id`` -- never on
``agent_url``, and never over a product storing a strict subset of a template's
expansion -- so it cannot observe either defect.

No server is required: the picker's constructor performs the whole round-trip
(``_parseInitialFormats`` -> ``_updateHiddenInput``), so a blank document
supplying the container div and hidden input is sufficient.
"""

import json
import pathlib

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.ui

_REL_PICKER_JS = pathlib.Path("static") / "js" / "format-template-picker.js"


def _locate_picker_js() -> pathlib.Path:
    """Find the shipped picker by walking up from this file to the repo root.

    Anchored on the asset itself rather than a fixed ``parents[N]`` so moving
    this test between directories cannot silently repoint it at a missing path.
    """
    for parent in pathlib.Path(__file__).resolve().parents:
        candidate = parent / _REL_PICKER_JS
        if candidate.is_file():
            return candidate
    raise AssertionError(f"could not locate {_REL_PICKER_JS} above {__file__}")


PICKER_JS = _locate_picker_js()

# Minimal DOM: the two elements FormatTemplatePicker's constructor looks up.
_BLANK_PAGE = '<!doctype html><html><body><div id="c"></div><input type="hidden" id="h"></body></html>'

# The JS constant the picker emits when it has no agent_url to preserve (:101).
# NOTE the missing trailing slash -- it does not match what the server sends.
_ADCP_DEFAULT_AGENT_JS_CONST = "https://creative.adcontextprotocol.org"

# What the EDIT PAGE ACTUALLY RECEIVES for a default-agent format. The bootstrap
# is built by src/admin/blueprints/products.py:1956 as
# ``fmt.model_dump(mode="json", ...)``, so agent_url is serialized through
# Pydantic ``AnyUrl``, which appends a trailing slash:
#     str(AnyUrl("https://creative.adcontextprotocol.org"))
#         == "https://creative.adcontextprotocol.org/"
# Tests here must use THIS form, not the JS constant. A fix that compares
# ``agentUrl === DEFAULT_CREATIVE_AGENT_URL`` looks correct against the constant
# and routes every real default-agent format into customFormats -- regressing
# GH #1168 (template cards unselected after save) while a slash-less test stays
# green. See TestFormatPickerMatchesTheAgentUrlProductionSends below.
_ADCP_DEFAULT_AGENT = "https://creative.adcontextprotocol.org/"

_THIRD_PARTY_AGENT = "https://formats.thirdparty.example"

# Drives one full load->save round-trip and returns what the form would submit.
_ROUND_TRIP = """
([initialFormats]) => {
    const picker = new FormatTemplatePicker({
        containerId: 'c',
        hiddenInputId: 'h',
        tenantId: 'default',
        initialFormats: initialFormats,
    });
    return {
        emitted: JSON.stringify(picker.getSelectedFormats()),
        hidden: document.getElementById('h').value,
        // Internals, so a test can distinguish "matched a built-in template"
        // from "fell through to customFormats" -- the two paths are not
        // separable from the emitted list alone.
        selectedTemplates: JSON.stringify([...picker.selectedTemplates.keys()]),
        customFormats: JSON.stringify(picker.customFormats),
    };
}
"""


def _key(fmt: dict) -> tuple:
    """Order-independent identity of an emitted format.

    Includes ``duration_ms``: the picker stores durations in the same per-template
    Set as sizes, so a comparison that ignored it would let a video duration be
    dropped or swapped without failing.
    """
    return (
        fmt.get("agent_url"),
        fmt.get("id"),
        fmt.get("width"),
        fmt.get("height"),
        fmt.get("duration_ms"),
    )


def _round_trip(page: Page, initial_formats: list[dict]) -> list[dict]:
    """Load ``initial_formats`` into a fresh picker and return what it would submit.

    The hidden input is the wire: it is the field the product form posts. It is
    asserted to agree with ``getSelectedFormats()`` so neither path can drift
    into passing while the other regresses.
    """
    return _drive(page, initial_formats)["emitted"]


def _drive(page: Page, initial_formats: list[dict]) -> dict:
    """Run the round-trip and return the submitted formats PLUS picker internals.

    Returns ``emitted`` (what the form would post), ``selectedTemplates`` (which
    built-in template cards were matched) and ``customFormats`` (what fell
    through to the preserving branch).
    """
    js_errors: list[str] = []
    page.on("pageerror", lambda err: js_errors.append(str(err)))
    page.set_content(_BLANK_PAGE)
    page.add_script_tag(path=str(PICKER_JS))

    result = page.evaluate(_ROUND_TRIP, [initial_formats])

    assert js_errors == [], f"picker raised JS errors during round-trip: {js_errors}"
    emitted = json.loads(result["emitted"])
    assert json.loads(result["hidden"]) == emitted, (
        "hidden input disagrees with getSelectedFormats() -- the submitted value is "
        f"{result['hidden']!r} but the picker reports {result['emitted']!r}"
    )
    return {
        "emitted": emitted,
        "selectedTemplates": json.loads(result["selectedTemplates"]),
        "customFormats": json.loads(result["customFormats"]),
    }


_DRIVE_WITH_EDITS = """
([initialFormats, edits]) => {
    const picker = new FormatTemplatePicker({
        containerId: 'c', hiddenInputId: 'h', tenantId: 'default',
        initialFormats: initialFormats,
    });
    for (const [method, args] of edits) {
        picker[method](...args);
    }
    return JSON.stringify(picker.getSelectedFormats());
}
"""


def _round_trip_with_edits(page: Page, initial_formats: list[dict], edits: list[list]) -> list[dict]:
    """Load a picker, apply real UI actions, and return what the form would submit."""
    page.set_content(_BLANK_PAGE)
    page.add_script_tag(path=str(PICKER_JS))
    return json.loads(page.evaluate(_DRIVE_WITH_EDITS, [initial_formats, edits]))


@pytest.mark.ui
class TestFormatPickerMatchesTheAgentUrlProductionSends:
    """A default-agent format must be RECOGNISED as a built-in template.

    Every other test here asserts preservation, and preservation alone cannot
    catch the most likely way to get this wrong. ``customFormats`` also preserves
    agent_url and also does not multiply, so a comparison that fails to match the
    default agent quietly routes everything down that branch and every
    preservation assertion still passes -- while the Display/Video cards render
    unselected on the edit page, which is exactly the GH #1168 regression.

    These assert on the picker's internal routing, not on the emitted list,
    because that is the only place the two paths differ.
    """

    def test_default_agent_with_trailing_slash_matches_a_template(self, page: Page):
        """The server sends agent_url WITH a trailing slash; matching must survive it.

        ``products.py`` serializes via Pydantic ``AnyUrl``, which appends "/", so
        the edit page never receives the slash-less form the JS constant holds.
        A bare ``agentUrl === DEFAULT_CREATIVE_AGENT_URL`` matches nothing real.
        """
        stored = [{"agent_url": _ADCP_DEFAULT_AGENT, "id": "display_image", "width": 300, "height": 250}]

        result = _drive(page, stored)

        assert result["selectedTemplates"] == ["display"], (
            "a default-agent format served with a trailing slash was not matched as a "
            f"built-in template; selectedTemplates={result['selectedTemplates']!r}, "
            f"customFormats={result['customFormats']!r}. The Display card would render "
            f"unselected on the edit page (GH #1168)."
        )
        assert result["customFormats"] == [], (
            f"default-agent format was misrouted to customFormats: {result['customFormats']!r}"
        )

    def test_default_agent_with_transport_suffix_matches_a_template(self, page: Page):
        """/mcp and /a2a are endpoints of the same agent, per canonical_agent_url."""
        stored = [{"agent_url": "https://creative.adcontextprotocol.org/mcp", "id": "video_standard"}]

        result = _drive(page, stored)

        assert result["selectedTemplates"] == ["video"], (
            "a default-agent format carrying a /mcp transport suffix was treated as a "
            f"different agent; selectedTemplates={result['selectedTemplates']!r}, "
            f"customFormats={result['customFormats']!r}"
        )

    def test_third_party_agent_is_not_matched_as_a_template(self, page: Page):
        """Negative control: a genuinely foreign agent must NOT match a template.

        Without this, the two assertions above could be satisfied by a comparison
        that matches everything -- which is today's bug.
        """
        stored = [{"agent_url": _THIRD_PARTY_AGENT, "id": "display_image", "width": 300, "height": 250}]

        result = _drive(page, stored)

        assert result["selectedTemplates"] == [], (
            f"a third-party format was absorbed into a built-in template: "
            f"selectedTemplates={result['selectedTemplates']!r}"
        )
        assert [f["agent_url"] for f in result["customFormats"]] == [_THIRD_PARTY_AGENT], (
            f"third-party format did not reach customFormats intact: {result['customFormats']!r}"
        )


@pytest.mark.ui
class TestFormatPickerTemplateSelectionStillExpands:
    """Selecting a template must still emit its whole expansion (guards GH #1168).

    The load path has to preserve a stored subset, but the CREATE path must not:
    an admin who ticks the Display card is choosing the template, not one of its
    formats, and must get all of display_image/display_html/display_js. A fix that
    preserves subsets by never expanding would silently regress #1168, and nothing
    pinned that behaviour before these tests.
    """

    def test_fresh_template_selection_emits_the_full_expansion(self, page: Page):
        """No stored formats at all: ticking Display + a size emits all three ids."""
        emitted = _round_trip_with_edits(page, [], [["toggleSize", ["display", 300, 250]]])

        assert {f["id"] for f in emitted} == {"display_image", "display_html", "display_js"}, (
            f"fresh template selection did not expand: {emitted!r}"
        )
        assert all(f.get("width") == 300 and f.get("height") == 250 for f in emitted), (
            f"selected size was not applied to the expansion: {emitted!r}"
        )

    def test_editing_a_loaded_template_regenerates_it(self, page: Page):
        """Once the admin edits a loaded template, it regenerates rather than replaying.

        The stored-subset preservation is only correct while the template is
        untouched. Adding a size is an explicit edit, so the template reverts to
        template semantics -- otherwise the admin's change could not take effect.
        """
        stored = [{"agent_url": _ADCP_DEFAULT_AGENT, "id": "display_image", "width": 300, "height": 250}]

        emitted = _round_trip_with_edits(page, stored, [["toggleSize", ["display", 728, 90]]])

        ids = {f["id"] for f in emitted}
        sizes = {(f.get("width"), f.get("height")) for f in emitted}
        assert ids == {"display_image", "display_html", "display_js"}, (
            f"edited template did not regenerate to the full expansion: {emitted!r}"
        )
        assert (728, 90) in sizes, f"the admin's new size is missing: {emitted!r}"
        assert (300, 250) in sizes, f"the pre-existing size was dropped: {emitted!r}"


@pytest.mark.ui
class TestFormatPickerPreservesAgentUrl:
    """A stored format's agent_url must survive an edit-and-save with no format changes."""

    def test_third_party_agent_url_survives_when_id_collides_with_a_template(self, page: Page):
        """A third-party format whose id collides with a built-in template keeps its agent.

        ``video_standard`` is one of the ids the built-in ``video`` template
        expands to, so a foreign agent publishing that id is matched as the
        local template and its identity is discarded. AdCP format identity is
        the (agent_url, id) PAIR -- rebinding the url silently repoints the
        product at a different agent's creative format.
        """
        emitted = _round_trip(page, [{"agent_url": _THIRD_PARTY_AGENT, "id": "video_standard"}])

        agents = {fmt.get("agent_url") for fmt in emitted}
        assert agents == {_THIRD_PARTY_AGENT}, (
            f"agent_url was not preserved: expected every emitted format to keep "
            f"{_THIRD_PARTY_AGENT!r}, got {agents!r}. A save with no user edits "
            f"silently rebinds this product to the AdCP default agent."
        )

    def test_third_party_agent_url_survives_on_a_top_level_template_id(self, page: Page):
        """Same defect via the other match path: a direct FORMAT_TEMPLATES key."""
        emitted = _round_trip(page, [{"agent_url": _THIRD_PARTY_AGENT, "id": "video"}])

        agents = {fmt.get("agent_url") for fmt in emitted}
        assert agents == {_THIRD_PARTY_AGENT}, (
            f"agent_url was not preserved on the top-level-key match path: got {agents!r}"
        )

    def test_non_colliding_third_party_format_is_untouched(self, page: Page):
        """Positive control: the preserving branch works, so the tests above discriminate.

        A third-party id that matches no template routes to ``customFormats``,
        which already carries agent_url through correctly. Without this control
        the assertions above would also pass if the picker simply dropped every
        format, so this pins that the defect is specific to the template-match
        path and must stay fixed when that path is repaired.
        """
        stored = {"agent_url": _THIRD_PARTY_AGENT, "id": "acme_billboard_970x250"}

        emitted = _round_trip(page, [stored])

        assert emitted == [stored], f"non-colliding third-party format was altered: {emitted!r}"


@pytest.mark.ui
class TestFormatPickerDoesNotFabricateFormats:
    """Saving with no user edits must not add formats the product never referenced."""

    def test_expanded_template_id_does_not_multiply(self, page: Page):
        """One stored ``display_image`` must not become three formats on save.

        Independent of agent identity -- this reproduces on the AdCP default
        agent with no collision. The picker collapses the stored id into its
        parent template and then re-expands that template to ALL of its child
        ids, so the product silently acquires ``display_html`` and
        ``display_js``, changing what inventory it will actually serve.
        """
        stored = {"agent_url": _ADCP_DEFAULT_AGENT, "id": "display_image", "width": 300, "height": 250}

        emitted = _round_trip(page, [stored])

        assert emitted == [stored], (
            f"round-trip fabricated formats: stored 1 format {stored!r} but the form "
            f"would submit {len(emitted)}: {emitted!r}"
        )

    def test_stored_format_set_is_preserved_exactly(self, page: Page):
        """The full set a product references round-trips unchanged, order aside."""
        stored = [
            {"agent_url": _ADCP_DEFAULT_AGENT, "id": "video_standard"},
            {"agent_url": _ADCP_DEFAULT_AGENT, "id": "display_image", "width": 300, "height": 250},
        ]

        emitted = _round_trip(page, stored)

        assert sorted(map(_key, emitted)) == sorted(map(_key, stored)), (
            f"stored format set was not preserved: submitted {emitted!r}, stored {stored!r}"
        )

    def test_two_sizes_within_one_template_do_not_cross_multiply(self, page: Page):
        """Distinct ids at distinct sizes under ONE template must not cross-product.

        The picker's state for a template is ``templateId -> Set`` of "WxH"
        strings, so which id carried which size is lost the moment two formats
        from the same template are stored. Emit then pairs EVERY expanded id with
        EVERY retained size: two stored formats come back as six.

        This is the case that makes "remember the ids and the params per
        template" an insufficient fix -- retaining two independent sets still
        multiplies them. Preserving the stored set requires keeping the
        (id, params) association, or re-emitting untouched templates verbatim.
        """
        stored = [
            {"agent_url": _ADCP_DEFAULT_AGENT, "id": "display_image", "width": 300, "height": 250},
            {"agent_url": _ADCP_DEFAULT_AGENT, "id": "display_html", "width": 728, "height": 90},
        ]

        emitted = _round_trip(page, stored)

        assert sorted(map(_key, emitted)) == sorted(map(_key, stored)), (
            f"round-trip cross-multiplied ids by sizes: stored {len(stored)} formats "
            f"{stored!r}, would submit {len(emitted)}: {emitted!r}"
        )
