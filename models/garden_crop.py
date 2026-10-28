from odoo import models, fields, api

class GardenCrop(models.Model):
    _name = 'garden.crop'
    _description = 'Culture sur planche'

    catalog_id = fields.Many2one('garden.crop.catalog', string='Catalogue de culture', required=True)
    sowing_quantity = fields.Float('Nombre de plants semés')
    planted_quantity = fields.Float('Nombre de plants plantés')
    bed_id = fields.Many2one('garden.bed', string='Planche', required=True)
    notes = fields.Text('Notes')
    date_start = fields.Date('Date de début')
    date_end = fields.Date('Date de fin')
    quantity_harvested = fields.Float('Quantité récoltée (kg)')
    value_harvested = fields.Float('Valeur récoltée (€)')
    action_ids = fields.One2many('garden.action', 'crop_id', string='Actions')
    # autres champs pertinents

    @api.model
    def get_production_statistics_data(self, params=None):
        self.env.flush_all()
        self.env.cr.execute(
            """
            SELECT COALESCE(TO_CHAR(COALESCE(date_end, date_start), 'YYYY-MM'), 'Unknown') AS period,
                   COALESCE(SUM(quantity_harvested), 0) AS quantity,
                   COALESCE(SUM(value_harvested), 0) AS value
            FROM garden_crop
            GROUP BY period
            ORDER BY period
            """
        )
        month_rows = self.env.cr.fetchall()
        month_totals = [
            {
                'period': period or 'Unknown',
                'quantity': float(quantity or 0.0),
                'value': float(value or 0.0),
            }
            for period, quantity, value in month_rows
        ]

        self.env.cr.execute(
            """
            SELECT COALESCE(b.name, 'Sans planche') AS bed_name,
                   COALESCE(SUM(quantity_harvested), 0) AS quantity,
                   COALESCE(SUM(value_harvested), 0) AS value
            FROM garden_crop c
            LEFT JOIN garden_bed b ON c.bed_id = b.id
            GROUP BY b.name
            ORDER BY b.name
            """
        )
        bed_rows = self.env.cr.fetchall()
        bed_totals = [
            {
                'bed': bed_name,
                'quantity': float(quantity or 0.0),
                'value': float(value or 0.0),
            }
            for bed_name, quantity, value in bed_rows
        ]

        self.env.cr.execute(
            """
            SELECT COALESCE(cat.name, 'Sans culture') AS crop_name,
                   COALESCE(SUM(quantity_harvested), 0) AS quantity,
                   COALESCE(SUM(value_harvested), 0) AS value
            FROM garden_crop c
            LEFT JOIN garden_crop_catalog cat ON c.catalog_id = cat.id
            GROUP BY cat.name
            ORDER BY cat.name
            """
        )
        crop_rows = self.env.cr.fetchall()
        crop_totals = [
            {
                'crop': crop_name,
                'quantity': float(quantity or 0.0),
                'value': float(value or 0.0),
            }
            for crop_name, quantity, value in crop_rows
        ]

        return {
            'month_totals': month_totals,
            'bed_totals': bed_totals,
            'crop_totals': crop_totals,
        }
