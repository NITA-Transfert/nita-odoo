try:
    import odoo  # noqa: F401
    _HAS_ODOO = True
except ImportError:
    _HAS_ODOO = False

if _HAS_ODOO:
    from . import models
    from . import controllers

    from odoo.addons.payment import setup_provider, reset_payment_provider

    def post_init_hook(env):
        """Enregistre NITA comme fournisseur de paiement côté comptabilité.

        Crée l'`account.payment.method` de code `nita` (comme le font Stripe,
        Flutterwave, etc.). Sans ça, le journal n'a aucune ligne de méthode de
        paiement NITA et la finalisation d'un paiement échoue avec
        « Please define a payment method line on your payment »."""
        setup_provider(env, 'nita')

    def uninstall_hook(env):
        reset_payment_provider(env, 'nita')
