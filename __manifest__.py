# -*- coding: utf-8 -*-
{
    'name': 'Odoo Garden',
    'version': '19.0.1.0.0',
    'category': 'Agriculture',
    'summary': 'Gestion du maraîchage : fermes, sites, jardins, planches, parcelles, cultures, actions, traçabilité, post-process, pertes, rétro-planning, statistiques.',
    'author': 'Votre Nom',
    'website': 'https://votresite.com',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/garden_farm_views.xml',
        'views/garden_site_views.xml',
        'views/garden_garden_views.xml',
        'views/garden_bed_views.xml',
        'views/garden_crop_views.xml',
        'views/garden_crop_catalog_views.xml',
        'views/garden_action_views.xml',
        'views/garden_postprocess_views.xml',
        'views/garden_loss_views.xml',
        'views/garden_statistics_views.xml',
        'views/garden_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'odoo_garden/static/src/js/garden_bed_occupancy.js',
            'odoo_garden/static/src/xml/garden_bed_occupancy.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
