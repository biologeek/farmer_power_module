{
    'name': 'Farmer Power - Purchase bridge',
    'version': '19.0.1.0.0',
    'category': 'Agriculture',
    'summary': 'Create draft seed and plant requests for quotation from the Farmer Power crop plan.',
    # TODO before publication: publisher name (author).
    'author': 'TODO - publisher to be defined',
    'website': 'https://odoo.biologeek.info',
    'depends': ['farmer_power', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/garden_seed_order_wizard_views.xml',
    ],
    'auto_install': True,
    'license': 'LGPL-3',  # free module (no price)
}
