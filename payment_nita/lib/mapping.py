import re

def request_id_for_order(reference):
    """requestId NITA = la référence (commande/facture), assainie et bornée 100.
    Déterministe : même référence -> même requestId."""
    clean = re.sub(r'[^A-Za-z0-9_-]+', '-', str(reference or '').strip())
    clean = clean.strip('-')
    if not clean:
        clean = 'odoo'
    return clean[:100]

# Francs CFA encaissés par NITA : XOF (Niger) et XAF (Tchad). L'API ne reçoit pas la devise :
# elle est celle de l'organisation NITA visée par l'URL de base.
SUPPORTED_CURRENCIES = ('XOF', 'XAF')

def amount_xof(total):
    """Montant envoyé à NITA : le franc CFA (XOF, XAF) n'a pas de décimales."""
    return int(round(float(total)))

def build_achat_args(*, reference, total, currency, items, callback_url, phone, ip='', return_url=''):
    """Construit les arguments de createAchat (attributs snake du modèle SDK).
    Géoloc omise (facultative pour l'achat en ligne). Lève ValueError si invalide."""
    if str(currency or '').upper() not in SUPPORTED_CURRENCIES:
        raise ValueError('NITA: devise non supportée (XOF ou XAF requis)')
    phone = str(phone or '').strip()
    if not phone:
        raise ValueError('NITA: numéro MyNITA (phoneClient) requis')
    amount = amount_xof(total)
    if amount <= 0:
        raise ValueError('NITA: montant invalide')
    libelles = [str(i) for i in (items or []) if str(i).strip()]
    if not libelles:
        libelles = ['Commande ' + str(reference)]
    return {
        'request_id': request_id_for_order(reference),
        'montant_transaction': amount,
        'phone_client': phone,
        'description_achat': libelles,
        'motif_transaction': 'Commande ' + str(reference),
        'url_callback': str(callback_url or ''),
        'url_retour': str(return_url or ''),
        'adresse_ip': (str(ip or '').strip() or '0.0.0.0'),
    }
