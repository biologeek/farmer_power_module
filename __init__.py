from . import models
from . import controllers


def _post_init_hook(env):
    """Charge le catalogue de départ de la langue d'installation (aucun si la langue n'a pas de jeu de données)."""
    dataset = env['garden.dataset']
    code = dataset._guess_dataset_code()
    if code:
        dataset._load_dataset(code)
