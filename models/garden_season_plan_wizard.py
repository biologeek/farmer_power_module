from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class GardenSeasonPlanWizard(models.TransientModel):
    """Crée en série des cultures d'une saison sur une liste de planches, éventuellement échelonnées."""
    _name = 'garden.season.plan.wizard'
    _description = 'Assistant de planification en série'

    season_id = fields.Many2one('garden.season', string='Saison', required=True, help="Saison qui recevra les cultures créées.")
    template_id = fields.Many2one(
        'garden.crop.template', string='Itinéraire technique', required=True,
        help="Itinéraire appliqué à toutes les cultures créées.",
    )
    bed_ids = fields.Many2many(
        'garden.bed', string='Planches', required=True,
        help="Une culture est créée sur chacune de ces planches.",
    )
    target = fields.Selection(
        [('harvest', 'Début de récolte visé'), ('sowing', 'Date de semis')],
        string='Date visée', required=True, default='harvest',
        help="Indique si la date saisie est celle du début de récolte (rétro-planning) ou celle du semis.",
    )
    target_date = fields.Date('Date', required=True, help="Date visée pour la première planche.")
    stagger_days = fields.Integer(
        'Décalage entre planches (jours)', default=0,
        help="Nombre de jours ajouté à la date visée à chaque planche successive, pour échelonner "
             "les cultures (0 = toutes les planches à la même date).",
    )
    bed_share = fields.Float('Part de la planche (%)', default=100.0, help="Part de chaque planche occupée par la culture.")
    preview = fields.Text('Aperçu', compute='_compute_preview', help="Dates calculées pour chaque planche avant création.")

    def _get_dates_per_bed(self):
        """Liste de (planche, dates prévues) ; la planche n°i est décalée de i × ``stagger_days``."""
        self.ensure_one()
        result = []
        for index, bed in enumerate(self.bed_ids):
            target = self.target_date + timedelta(days=index * self.stagger_days)
            if self.target == 'sowing':
                dates = self.template_id._plan_dates(sowing_date=target)
            else:
                dates = self.template_id._plan_dates(harvest_start=target)
            result.append((bed, dates))
        return result

    @api.depends('template_id', 'bed_ids', 'target', 'target_date', 'stagger_days')
    def _compute_preview(self):
        for wizard in self:
            if not (wizard.template_id and wizard.bed_ids and wizard.target_date):
                wizard.preview = False
                continue
            lines = [
                "%s : semis %s, récolte %s → %s" % (
                    bed.display_name, dates['planned_sowing_date'], dates['planned_harvest_start'],
                    dates['planned_harvest_end'],
                )
                for bed, dates in wizard._get_dates_per_bed()
            ]
            wizard.preview = "\n".join(lines)

    def action_create_crops(self):
        self.ensure_one()
        if not self.bed_ids:
            raise UserError(self.env._("Sélectionnez au moins une planche."))
        vals_list = [
            {
                'season_id': self.season_id.id,
                'template_id': self.template_id.id,
                'bed_id': bed.id,
                'bed_share': self.bed_share,
                **dates,
            }
            for bed, dates in self._get_dates_per_bed()
        ]
        crops = self.env['garden.crop'].create(vals_list)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Cultures créées"),
            'res_model': 'garden.crop',
            'view_mode': 'list,form',
            'domain': [('id', 'in', crops.ids)],
        }
