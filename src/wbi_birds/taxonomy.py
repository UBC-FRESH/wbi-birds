"""eBird taxonomy snapshot for the WBI species suite (E-P4.2).

Curated subset of the eBird taxonomy v2026 (fetched via the eBird API on
2026-10-11; full snapshot held in the manuscript repo planning docs).
"""

SOURCE = "eBird taxonomy (API fetch, 2026-10-11)"

TAXONOMY_SNAPSHOT: dict[str, dict[str, str]] = {
    "rebnut": {"common": "Red-breasted Nuthatch", "scientific": "Sitta canadensis"},
    "borchi2": {"common": "Boreal Chickadee", "scientific": "Poecile hudsonicus"},
    "gockin": {"common": "Golden-crowned Kinglet", "scientific": "Regulus satrapa"},
    "brncre": {"common": "Brown Creeper", "scientific": "Certhia americana"},
    "yerwar": {"common": "Yellow-rumped Warbler", "scientific": "Setophaga coronata"},
    "swathr": {"common": "Swainson's Thrush", "scientific": "Catharus ustulatus"},
    "whtspa": {"common": "White-throated Sparrow", "scientific": "Zonotrichia albicollis"},
    "tenwar": {"common": "Tennessee Warbler", "scientific": "Leiothlypis peregrina"},
    "yebsap": {"common": "Yellow-bellied Sapsucker", "scientific": "Sphyrapicus varius"},
}
