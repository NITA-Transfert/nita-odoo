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

def build_achat_args(*, reference, total, currency, items, callback_url, phone, ip=''):
    """Construit les arguments de createAchat (attributs snake du modèle SDK).
    Géoloc omise (facultative pour l'achat en ligne). Lève ValueError si invalide."""
    if str(currency or '').upper() != 'XOF':
        raise ValueError('NITA: devise non supportée (XOF requis)')
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
        'adresse_ip': (str(ip or '').strip() or '0.0.0.0'),
    }
