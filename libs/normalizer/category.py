import re

# Mapping de catégories brutes marchands → chemin canonique
# Format : regex → "Catégorie/Sous-catégorie"
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btv\b|t[eé]l[eé]viseur|t[eé]l[eé]vision", re.I), "Électronique/TV & Audio/Téléviseurs"),
    (re.compile(r"\bsmartphone\b|t[eé]l[eé]phone\s+portable", re.I), "Électronique/Téléphones/Smartphones"),
    (re.compile(r"\blaptop\b|ordinateur\s+portable", re.I), "Informatique/Ordinateurs portables"),
    (re.compile(r"\bpc\s+de\s+bureau\b|ordinateur\s+de\s+bureau", re.I), "Informatique/PC de bureau"),
    (re.compile(r"\btablette\b|tablet", re.I), "Électronique/Tablettes"),
    (re.compile(r"\bappareil\s+photo\b|camera\b|camescope", re.I), "Électronique/Photo & Vidéo"),
    (re.compile(r"\bcasque\b|[eé]couteur|headphone|headset", re.I), "Électronique/TV & Audio/Casques"),
    (re.compile(r"\bimprimante\b|printer", re.I), "Informatique/Imprimantes"),
    (re.compile(r"\bfrigorifique\b|refrigerator|frigo", re.I), "Électroménager/Réfrigération"),
    (re.compile(r"\blave.linge\b|washing\s+machine", re.I), "Électroménager/Lavage"),
]


def normalize_category(raw: str | None) -> str | None:
    """Mappe une chaîne de catégorie brute vers le chemin canonique."""
    if not raw:
        return None
    for pattern, canonical in _RULES:
        if pattern.search(raw):
            return canonical
    return None
