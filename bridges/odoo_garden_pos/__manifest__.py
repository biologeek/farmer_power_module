{
    'name': 'Odoo Garden - Point of Sale bridge',
    'version': '19.0.1.0.0',
    'category': 'Agriculture',
    'summary': 'Include Point of Sale (market) sales in the revenue and profitability of Odoo Garden crops.',
    'description': """
Odoo Garden - Point of Sale bridge
==================================

Installed automatically when both Odoo Garden and Point of Sale are installed.
Paid or posted Point of Sale order lines are attributed to crops like customer invoices are:
pro rata of the monthly harvest of the product, or exactly by lot when the lot names entered on the
order line are crop lots. Refunds count negatively; an order already invoiced is never counted twice.
""",
    'author': 'TODO - publisher to be defined',
    'website': 'https://example.com/TODO',
    'depends': ['odoo_garden', 'point_of_sale'],
    'data': [],
    'auto_install': True,
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
