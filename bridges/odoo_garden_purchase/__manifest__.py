{
    'name': 'Farmer Power - Purchase bridge',
    'version': '19.0.1.0.0',
    'category': 'Agriculture',
    'summary': 'Create draft seed and plant requests for quotation from the Farmer Power crop plan.',
    # TODO before publication: publisher and website (see the README of odoo_garden).
    'author': 'TODO - publisher to be defined',
    'website': 'https://example.com/TODO',
    'depends': ['odoo_garden', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/garden_seed_order_wizard_views.xml',
    ],
    'auto_install': True,
    'license': 'OPL-1',
}
