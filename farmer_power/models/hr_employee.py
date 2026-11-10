from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # `hourly_cost` n'existe que dans le module `hr_hourly_cost` (non requis) et est réservé aux
    # officiers RH : le coût horaire du travail maraîcher est donc porté par un champ propre,
    # visible du chef de culture et du gérant seulement.
    garden_hourly_cost = fields.Float(
        'Hourly Cost (Market Gardening)', digits='Product Price', groups='farmer_power.group_garden_chef',
        help='Fully loaded hourly cost of the employee to value the time of operations. At 0, the default '
             'hourly rate of the Market Gardening settings applies.',
    )
