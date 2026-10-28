from odoo import models, fields, api


class GardenAction(models.Model):
    _name = 'garden.action'
    _description = 'Action sur planche'

    type_id = fields.Many2one('garden.action.type', string='Type', required=True)
    date = fields.Date('Date')
    duration = fields.Integer('Durée (minutes)')
    crop_id = fields.Many2one('garden.crop', string='Culture', required=True)
    bed_id = fields.Many2one(
        'garden.bed',
        string='Planche',
        related='crop_id.bed_id',
        store=True,
        readonly=False,
    )
    description = fields.Text('Description')

    @api.model
    def get_statistics_data(self, params=None):
        """Return aggregated data for statistics charts.

        Returns a dict with two keys:
        - 'pie': list of {label, value} for total duration per action type
        - 'stacked': {categories: [variety names], series: [{name: type, data: [values per category]}]}
        """
        self.env.flush_all()
        self.env.cr.execute(
            """
            SELECT at.name AS type_name, COALESCE(SUM(a.duration),0) AS total
            FROM garden_action a
            LEFT JOIN garden_action_type at ON a.type_id = at.id
            GROUP BY at.name
            ORDER BY at.name
            """
        )
        pie_rows = self.env.cr.fetchall()
        pie = []
        for type_name, total in pie_rows:
            pie.append({
                'label': type_name or 'Sans type',
                'value': float(total or 0.0),
            })

        # stacked: duration per (variety, action type)
        self.env.cr.execute(
            """
            SELECT COALESCE(cat.name, '') AS variety, COALESCE(at.name, '') AS type_name, COALESCE(SUM(a.duration),0) AS total
            FROM garden_action a
            LEFT JOIN garden_action_type at ON a.type_id = at.id
            LEFT JOIN garden_crop c ON a.crop_id = c.id
            LEFT JOIN garden_crop_template cat ON c.template_id = cat.id
            GROUP BY at.name, cat.name
            ORDER BY at.name
           """
        )
        rows = self.env.cr.fetchall()

        # build ordered categories and series map
        categories = []
        series_map = {}
        for variety, type_name, total in rows:
            v = variety or 'Sans variété'
            t = type_name or 'Sans type'
            if v not in categories:
                categories.append(v)
            series_map.setdefault(t, {})[v] = float(total or 0.0)

        series = []
        for tname, data_map in series_map.items():
            data = [data_map.get(cat, 0.0) for cat in categories]
            series.append({'name': tname, 'data': data})

        return {'pie': pie, 'stacked': {'categories': categories, 'series': series}}
