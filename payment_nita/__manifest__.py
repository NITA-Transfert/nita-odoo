{
    'name': 'NITA - Paiement en ligne',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Encaissez via NITA (Achat en ligne)',
    'author': 'NITA Transfert',
    'license': 'OPL-1',
    'depends': ['payment', 'website_sale'],
    'external_dependencies': {'python': ['nita_sdk']},
    'data': [
        'security/ir.model.access.csv',
        'views/payment_nita_templates.xml',
        'views/payment_provider_views.xml',
        'data/payment_provider_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_nita/static/src/js/payment_form.js',
        ],
    },
    'application': False,
    'installable': True,
}
