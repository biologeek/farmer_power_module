{
    'name': 'Farmer Power - Purchase bridge',
    'version': '19.0.2.0.0',
    'category': 'Agriculture',
    'summary': 'Create draft seed and plant requests for quotation from the Farmer Power crop plan.',
    # TODO before publication: publisher and website (see the README of farmer_power).
    'author': 'TODO - publisher to be defined',
    'website': 'https://example.com/TODO',
    'depends': ['farmer_power', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/garden_seed_order_wizard_views.xml',
    ],
    'auto_install': True,
    'license': 'OPL-1',
}
