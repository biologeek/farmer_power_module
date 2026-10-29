{
    'name': 'Odoo Garden - Purchase bridge',
    'version': '19.0.1.0.0',
    'category': 'Agriculture',
    'summary': 'Create draft seed and plant requests for quotation from the Odoo Garden crop plan.',
    'description': """
Odoo Garden - Purchase bridge
=============================

Installed automatically when both Odoo Garden and Purchase are installed.
Adds a "Create RFQs" wizard (menu Planning, and button on the season) that turns the seed needs
of a season into draft requests for quotation, one per supplier.
""",
    'author': 'TODO - publisher to be defined',
    'website': 'https://example.com/TODO',
    'depends': ['odoo_garden', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/garden_seed_order_wizard_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
