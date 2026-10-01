import pytest
from payment_nita.lib.mapping import request_id_for_order, amount_xof, build_achat_args

def test_request_id_deterministic_and_sanitized():
    assert request_id_for_order('S00001') == 'S00001'
    assert request_id_for_order('S00001') == 'S00001'
    assert request_id_for_order('INV/2026 1') == 'INV-2026-1'
    assert request_id_for_order('  abc  ') == 'abc'

def test_request_id_bounds_and_fallback():
    assert len(request_id_for_order('9' * 200)) <= 100
    assert request_id_for_order('///') == 'odoo'

def test_amount_xof_is_integer_without_decimals():
    assert amount_xof(15000.0) == 15000
    assert amount_xof(15000.4) == 15000
    assert amount_xof('2500') == 2500

def _base(**kw):
    args = dict(reference='S00001', total=15000, currency='XOF',
                items=['T-shirt', 'Mug'], callback_url='https://shop/cb', phone='0022790000000', ip='41.1.2.3')
    args.update(kw); return args

def test_build_achat_args_ok():
    a = build_achat_args(**_base())
    assert a['request_id'] == 'S00001'
    assert a['montant_transaction'] == 15000
    assert a['phone_client'] == '0022790000000'
    assert a['url_callback'] == 'https://shop/cb'
    assert a['adresse_ip'] == '41.1.2.3'
    assert a['description_achat'] == ['T-shirt', 'Mug']
    assert a['motif_transaction']
    assert 'long_transaction' not in a and 'lat_transaction' not in a  # géoloc omise

def test_build_achat_args_rejects_non_xof():
    with pytest.raises(ValueError):
        build_achat_args(**_base(currency='EUR'))

def test_build_achat_args_requires_phone():
    with pytest.raises(ValueError):
        build_achat_args(**_base(phone='  '))

def test_build_achat_args_rejects_zero_amount():
    with pytest.raises(ValueError):
        build_achat_args(**_base(total=0))

def test_build_achat_args_ip_fallback_and_items_fallback():
    a = build_achat_args(**_base(ip='', items=[]))
    assert a['adresse_ip'] == '0.0.0.0'          # SDK exige adresse_ip non vide
    assert a['description_achat'] == ['Commande S00001']  # repli si pas d'articles
    assert 'S00001' in a['motif_transaction']
