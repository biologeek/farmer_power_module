from odoo import models, fields

class GardenCropCatalog(models.Model):
    _name = 'garden.crop.catalog'
    _description = 'Catalogue de cultures'

    name = fields.Char('Nom', required=True)
    supplier_id = fields.Many2one('res.partner', string='Fournisseur')
    variety = fields.Char('Variété')
    description = fields.Text('Description')
    mode_culture = fields.Many2one('garden.culture.mode', string='Mode de culture')
    distance = fields.Float(
        'Distance entre plants (cm)',
        related='mode_culture.distance',
        store=True,
        readonly=False,
    )
    nb_rangs = fields.Integer(
        'Nombre de rangs',
        related='mode_culture.nb_rangs',
        store=True,
        readonly=False,
    )
    duree_previsionnelle = fields.Integer('Durée prévisionnelle (jours)')
