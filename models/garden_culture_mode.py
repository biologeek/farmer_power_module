from odoo import models, fields

class GardenCultureMode(models.Model):
    _name = 'garden.culture.mode'
    _description = 'Mode de culture (serre, distance, rangs)'

    name = fields.Char('Nom du mode', required=True)
    type = fields.Selection([
        ('plein_air', 'Plein air'),
        ('sous_serre', 'Sous serre')
    ], string='Type de culture', required=True)
    distance = fields.Float('Distance entre plants (cm)')
    nb_rangs = fields.Integer('Nombre de rangs')
