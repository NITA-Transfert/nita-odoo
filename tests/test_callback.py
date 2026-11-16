import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from payment_nita.lib.callback import extract_code_achat as ex


def test_query_param():
    assert ex('ACH-123_x', b'') == 'ACH-123_x'
    assert ex('  ABC  ', b'') == 'ABC'


def test_body_json_when_no_query():
    assert ex(None, b'{"status":"1","transaction_id":" CODE1 "}') == 'CODE1'
    assert ex('', b'{"transaction_id":"CODE2"}') == 'CODE2'


def test_query_wins_over_body():
    assert ex('Q1', b'{"transaction_id":"B1"}') == 'Q1'


def test_invalid_query_does_not_fall_back_to_body():
    assert ex('bad code!', b'{"transaction_id":"B1"}') is None


def test_invalid_formats():
    assert ex('a' * 101, b'') is None
    assert ex('a' * 100, b'') == 'a' * 100
    assert ex('../etc', b'') is None
    assert ex('a b', b'') is None
    assert ex('   ', b'') is None
    assert ex(None, b'{"transaction_id":"x;y"}') is None


def test_bad_body():
    assert ex(None, b'not json') is None
    assert ex(None, bytes([0xff, 0xfe])) is None
    assert ex(None, b'[1,2]') is None
    assert ex(None, b'{"transaction_id":123}') is None
    assert ex(None, b'{}') is None
    assert ex(None, None) is None
    assert ex(None, b'{"transaction_id":"A"}' + b' ' * 70000) is None
