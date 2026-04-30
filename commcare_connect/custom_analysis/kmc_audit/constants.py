"""
Static configuration for the KMC Audit Dashboard.

Holds the canonical KMC opportunity list with their LLO (Local Lead
Organization) tags. The LLO is a per-opportunity attribute — each
KMC opportunity belongs to exactly one LLO partner (NAMA, PIPN, GHI).

Source: opportunity list provided by Sidarth on 2026-05-01.
"""

LLO_NAMA = "NAMA"
LLO_PIPN = "PIPN"
LLO_GHI = "GHI"

LLO_CHOICES: tuple[str, ...] = (LLO_NAMA, LLO_PIPN, LLO_GHI)

# Each entry: opportunity_id -> {"name": str, "llo": str, "uuid": str}
KMC_OPPORTUNITIES: dict[int, dict[str, str]] = {
    523: {
        "name": "Nama Wellness- Kangaroo Mother Care (KMC)",
        "llo": LLO_NAMA,
        "uuid": "17f3b632-74f4-402b-a36a-60fe5e6509e5",
    },
    524: {
        "name": "Kangaroo Mother Care- Preterm Infants Parents Network (PIPN)",
        "llo": LLO_PIPN,
        "uuid": "f1030d12-6d4e-491e-a6f1-567523a27257",
    },
    675: {
        "name": "Kangaroo Mother Care- GHI",
        "llo": LLO_GHI,
        "uuid": "23111005-3166-43b8-bcfa-bb0fa49a96ca",
    },
    874: {
        "name": "KMC PIPN - New Opportunity",
        "llo": LLO_PIPN,
        "uuid": "7b196dee-152e-4f98-8267-4edf32c17976",
    },
    938: {
        "name": "KMC Nama - New Opportunity",
        "llo": LLO_NAMA,
        "uuid": "2626a261-1bfc-42ce-bb9b-531f8508e31a",
    },
}

KMC_OPPORTUNITY_IDS: tuple[int, ...] = tuple(KMC_OPPORTUNITIES.keys())


def llo_for_opportunity(opportunity_id: int | None) -> str | None:
    """Return the LLO tag for a KMC opportunity, or None if unknown."""
    if opportunity_id is None:
        return None
    entry = KMC_OPPORTUNITIES.get(int(opportunity_id))
    return entry["llo"] if entry else None


def opportunity_name(opportunity_id: int | None) -> str:
    """Return the human-readable opportunity name, or '' if unknown."""
    if opportunity_id is None:
        return ""
    entry = KMC_OPPORTUNITIES.get(int(opportunity_id))
    return entry["name"] if entry else ""
