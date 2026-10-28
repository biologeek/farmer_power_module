from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # `hourly_cost` n'existe que dans le module `hr_hourly_cost` (non requis) et est réservé aux
    # officiers RH : le coût horaire du travail maraîcher est donc porté par un champ propre,
    # visible du chef de culture et du gérant seulement.
    garden_hourly_cost = fields.Float(
        'Coût horaire (maraîchage)', digits='Product Price', groups='odoo_garden.group_garden_chef',
        help="Coût horaire chargé de l'employé pour valoriser le temps des opérations. "
             "À 0, le taux horaire par défaut des paramètres Maraîchage s'applique.",
    )
