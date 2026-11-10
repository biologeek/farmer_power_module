"""Catalogues de départ par langue d'installation : variétés (rattachées aux espèces et aux produits récoltés
génériques du module) et intrants courants.

Chaque langue a son fichier (``fr.py``, ``es.py``...) qui ne contient que ce qui dépend du pays : les noms de
variétés cultivées localement et les noms des intrants. Les données agronomiques (graines par gramme, taux de
germination, teneur en azote) sont communes et définies ici.

Valeurs INDICATIVES, rédigées de mémoire (aucune source de semencier), à faire relire par un agronome et par des
locuteurs avant publication. Les phytosanitaires sont volontairement absents (numéros d'AMM réglementaires).
"""

# Langues proposées : code du jeu de données -> libellé natif
LANGUAGES = {
    'fr': 'Français',
    'es': 'Español',
    'de': 'Deutsch',
    'nl': 'Nederlands',
    'it': 'Italiano',
    'pt_BR': 'Português (Brasil)',
}

# Espèce -> (graines par gramme, taux de germination %). 0 graine/g : multiplication végétative (tubercules,
# bulbes, caïeux, plants, griffes) ; le taux est alors laissé à 100.
SPECIES_SEEDS = {
    'tomato': (300, 90), 'pepper': (150, 85), 'chili': (150, 85), 'eggplant': (250, 85),
    'potato': (0, 100), 'lettuce': (900, 90), 'endive': (700, 85), 'artichoke': (25, 80),
    'carrot': (800, 80), 'celeriac': (2500, 75), 'celery': (2500, 75), 'parsnip': (200, 70),
    'fennel': (200, 80), 'parsley': (500, 75), 'coriander': (90, 80), 'leek': (330, 85),
    'onion': (250, 85), 'shallot': (0, 100), 'garlic': (0, 100), 'chives': (650, 80),
    'cabbage': (250, 90), 'cauliflower': (300, 90), 'broccoli': (300, 90), 'kale': (250, 90),
    'kohlrabi': (250, 90), 'brussels': (250, 90), 'chinese_cabbage': (250, 90), 'radish': (100, 90),
    'turnip': (330, 90), 'rocket': (600, 85), 'asian_greens': (400, 90), 'zucchini': (6, 90),
    'cucumber': (35, 90), 'squash': (5, 90), 'melon': (30, 90), 'watermelon': (12, 90),
    'bean': (2.5, 90), 'pea': (4, 90), 'broad_bean': (1, 90), 'beet': (50, 85),
    'spinach': (100, 80), 'chard': (50, 85), 'sweet_corn': (4, 90), 'lambs_lettuce': (500, 80),
    'basil': (600, 85), 'strawberry': (0, 100), 'rhubarb': (0, 100), 'asparagus': (0, 100),
}

# Intrants complémentaires (hors phytosanitaires) : clé -> (type d'intrant, unité, azote %, autorisé en bio).
# Le module livre déjà (données ``noupdate``, noms traduits) compost, fumier composté, chaux, corne broyée, granulés de
# volaille, vinasse et terreaux : ils ne sont pas répétés ici. Les types et l'azote alimentent le registre de
# fertilisation et l'export de certification bio (les engrais minéraux, non autorisés en bio, y sont signalés).
INPUTS = {
    'feather_meal': ('fertilizer', 'kg', 12.0, True),     # farine de plumes
    'blood_meal': ('fertilizer', 'kg', 12.0, True),       # sang desséché
    'bone_meal': ('fertilizer', 'kg', 4.0, True),         # poudre d'os
    'npk': ('fertilizer', 'kg', 15.0, False),             # engrais minéral NPK 15-15-15
    'ammonium_nitrate': ('fertilizer', 'kg', 33.5, False),
    'dolomite': ('amendment', 'kg', 0.0, True),           # dolomie (amendement calco-magnésien)
    'wood_ash': ('amendment', 'kg', 0.0, True),           # cendres de bois non traité
}


def get_dataset(code):
    """Module Python du jeu de données ``code`` (``fr``, ``es``...), ou ``None`` si inconnu."""
    if code not in LANGUAGES:
        return None
    import importlib  # noqa: PLC0415
    return importlib.import_module('%s.%s' % (__name__, code))


def code_for_lang(lang):
    """Code de jeu de données d'une langue Odoo (``fr_BE`` -> ``fr``, ``pt_BR`` -> ``pt_BR``), ou ``None``."""
    if not lang:
        return None
    if lang in LANGUAGES:
        return lang
    prefix = lang.split('_')[0]
    return prefix if prefix in LANGUAGES and prefix != 'pt_BR' else None
