import re

def request_id_for_order(reference):
    """requestId NITA = la référence (commande/facture), assainie et bornée 100.
    Déterministe : même référence -> même requestId."""
    clean = re.sub(r'[^A-Za-z0-9_-]+', '-', str(reference or '').strip())
    clean = clean.strip('-')
    if not clean:
        clean = 'odoo'
    return clean[:100]

def amount_xof(total):
    """Montant envoyé à NITA : le XOF n'a pas de décimales."""
    return int(round(float(total)))
