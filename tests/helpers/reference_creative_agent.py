"""The reference creative agent's answers, read off the checked-in reference catalog.

A test deployment's registry serves its formats from that catalog
(``ReferenceFormatsRegistry``); a preview of a creative is the one creative-agent call it
still dials. These build the agent's answers from the same catalog, so a stand-in previews
a creative at the size its format defines.
"""

from __future__ import annotations

from typing import Any

from src.core.format_cache import load_reference_formats


def reference_format(format_id: str) -> Any:
    """The reference catalog's format *format_id*."""
    (fmt,) = [f for f in load_reference_formats() if f.format_id.id == format_id]
    return fmt


def reference_preview(format_id: str) -> dict[str, Any]:
    """The agent's ``preview_creative`` answer: one render at the format's primary size.

    sync_creatives takes a creative's dimensions from this render.
    """
    width, height = reference_format(format_id).get_primary_dimensions()
    return {
        "previews": [
            {
                "renders": [
                    {
                        "preview_url": "https://preview.example.com/render.html",
                        "dimensions": {"width": width, "height": height},
                    }
                ]
            }
        ]
    }
