try:
    import odoo  # noqa: F401
    _HAS_ODOO = True
except ImportError:
    _HAS_ODOO = False

if _HAS_ODOO:
    from . import models
    # from . import controllers   # décommenté par la Tâche 8
