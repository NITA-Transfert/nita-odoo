from payment_nita.lib.mapping import request_id_for_order, amount_xof

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
