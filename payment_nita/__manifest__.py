{
    'name': 'NITA - Paiement en ligne',
    'version': '17.0.1.1.0',
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
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',  # Depends on `payment_method_nita`.
        'data/nita_cron.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_nita/static/src/js/payment_form.js',
        ],
    },
    'application': False,
    'installable': True,
    # Enregistre NITA comme account.payment.method à l'installation (comme
    # Stripe/Flutterwave) — sinon le journal n'a pas de ligne NITA et la
    # finalisation comptable d'un paiement échoue.
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
}
