import re
import unicodedata

from odoo import api, fields, models
from odoo.exceptions import UserError

from .. import datasets

UOM_XMLIDS = {'kg': 'uom.product_uom_kgm', 'unit': 'uom.product_uom_unit'}


def _slug(text):
    text = text.replace('œ', 'oe').replace('Œ', 'oe').replace('æ', 'ae').replace('ß', 'ss')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


class GardenDataset(models.AbstractModel):
    _name = 'garden.dataset'
    _description = 'Starter Catalog by Language'
    # Catalogue de départ propre à chaque langue (``datasets/<code>.py``) : variétés locales rattachées aux
    # espèces et aux produits récoltés génériques du module, et intrants courants (hors phytosanitaires).
    # Chaque enregistrement reçoit un identifiant externe ``dataset_<langue>_...`` : recharger un jeu de
    # données ne duplique rien et ne touche pas aux enregistrements déjà modifiés par l'utilisateur.

    @api.model
    def _guess_dataset_code(self):
        """Jeu de données de la langue d'installation : langue de l'administrateur, à défaut de la société."""
        candidates = [self.env.context.get('lang')]
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        candidates += [admin.lang if admin else None, self.env.company.partner_id.lang]
        for lang in candidates:
            code = datasets.code_for_lang(lang)
            if code:
                return code
        return None

    @api.model
    def _load_dataset(self, code):
        """Charge le jeu de données ``code`` ; retourne ``{'varieties': n, 'inputs': n}`` (enregistrements créés)."""
        data = datasets.get_dataset(code)
        if data is None:
            raise UserError(self.env._('No starter catalog exists for this language.'))
        self = self.sudo()
        return {
            'varieties': self._load_varieties(code, data.VARIETIES),
            'inputs': self._load_inputs(code, data.INPUT_NAMES),
        }

    @api.model
    def _exists_xmlid(self, xmlid):
        return bool(self.env['ir.model.data']._xmlid_to_res_id('odoo_garden.' + xmlid, raise_if_not_found=False))

    @api.model
    def _register_xmlids(self, records_by_xmlid):
        self.env['ir.model.data']._update_xmlids([
            {'xml_id': 'odoo_garden.' + xmlid, 'record': record, 'noupdate': True}
            for xmlid, record in records_by_xmlid.items()
        ])

    @api.model
    def _load_varieties(self, code, varieties):
        vals_list, xmlids = [], []
        for species_key, names in varieties.items():
            species = self.env.ref('odoo_garden.species_' + species_key, raise_if_not_found=False)
            template = self.env.ref('odoo_garden.product_harvest_' + species_key, raise_if_not_found=False)
            if not species:
                continue
            seeds_per_gram, germination = datasets.SPECIES_SEEDS[species_key]
            for name in names:
                xmlid = 'dataset_%s_variety_%s_%s' % (code, species_key, _slug(name))
                if self._exists_xmlid(xmlid):
                    continue
                vals_list.append({
                    'name': name, 'species_id': species.id, 'seeds_per_gram': seeds_per_gram,
                    'germination_rate': germination,
                    'harvest_product_id': template.product_variant_id.id if template else False,
                })
                xmlids.append(xmlid)
        # une variété du même nom et de la même espèce créée à la main : on ne la duplique pas
        existing = {(v.name, v.species_id.id) for v in self.env['garden.variety'].with_context(active_test=False).search([])}
        keep = [i for i, vals in enumerate(vals_list) if (vals['name'], vals['species_id']) not in existing]
        records = self.env['garden.variety'].create([vals_list[i] for i in keep])
        self._register_xmlids({xmlids[i]: record for i, record in zip(keep, records)})
        return len(records)

    @api.model
    def _load_inputs(self, code, names):
        vals_list, xmlids = [], []
        for key, (input_type, uom_key, nitrogen, organic) in datasets.INPUTS.items():
            xmlid = 'dataset_%s_input_%s' % (code, key)
            if self._exists_xmlid(xmlid):
                continue
            uom = self.env.ref(UOM_XMLIDS[uom_key])
            vals_list.append({
                'name': names[key], 'type': 'consu', 'is_storable': True, 'uom_id': uom.id,
                'garden_input_type': input_type, 'nitrogen_content': nitrogen, 'is_organic_allowed': organic,
                'list_price': 0.0, 'sale_ok': False, 'purchase_ok': True,
            })
            xmlids.append(xmlid)
        records = self.env['product.template'].create(vals_list)
        self._register_xmlids(dict(zip(xmlids, records)))
        return len(records)


class GardenDatasetWizard(models.TransientModel):
    _name = 'garden.dataset.wizard'
    _description = 'Load a Starter Catalog'

    lang_code = fields.Selection(
        [(code, label) for code, label in datasets.LANGUAGES.items()], string='Catalog Language', required=True,
        default=lambda self: self.env['garden.dataset']._guess_dataset_code() or 'fr',
        help='Varieties commonly grown in the country and common inputs, named in that language.',
    )

    def action_load(self):
        self.ensure_one()
        counts = self.env['garden.dataset']._load_dataset(self.lang_code)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Starter catalog loaded'),
                'message': self.env._(
                    '%(varieties)s varieties and %(inputs)s inputs created (existing ones are left untouched).',
                    varieties=counts['varieties'], inputs=counts['inputs'],
                ),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
