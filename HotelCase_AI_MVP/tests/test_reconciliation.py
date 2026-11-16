from pathlib import Path
import pandas as pd
import pytest
from hotelcase.sample_data import create_data
from hotelcase.reconciliation import reconcile,DataValidationError,cents

@pytest.fixture
def frames(tmp_path):
    create_data(tmp_path)
    return [pd.read_csv(tmp_path/f,dtype=str,keep_default_na=False) for f in ('reservations.csv','payments.csv','settlements.csv')]

def case(cases,rid):return next(c for c in cases if c.reservation_id==rid)

def test_exact_match(frames):
    cs,_=reconcile(*frames)
    assert case(cs,'HC-1003').category=='RECONCILED'
    assert case(cs,'HC-1003').discrepancy_cents==0

def test_partial_hotel_payment(frames):
    cs,_=reconcile(*frames)
    c=case(cs,'HC-1001')
    assert (c.expected_cents,c.received_cents,c.discrepancy_cents)==(32000,22000,10000)
    assert c.category=='SHORTFALL'

def test_ota_commission_and_refund(frames):
    cs,_=reconcile(*frames)
    c=case(cs,'HC-1005')
    assert (c.expected_cents,c.received_cents,c.category)==(29000,29000,'RECONCILED')

def test_pending_not_a_shortfall(frames):
    cs,_=reconcile(*frames)
    assert case(cs,'HC-1004').category=='PENDING_VERIFICATION'
    assert case(cs,'HC-1008').category=='PENDING_VERIFICATION'

def test_overcollection(frames):
    cs,_=reconcile(*frames)
    assert case(cs,'HC-1006').category=='OVER_COLLECTION_REVIEW'
    assert case(cs,'HC-1006').discrepancy_cents==-2000

def test_cancelled_and_no_show_require_policy_review(frames):
    cs,_=reconcile(*frames)
    assert case(cs,'HC-1007').category=='POLICY_REVIEW'
    assert case(cs,'HC-1011').category=='POLICY_REVIEW'

def test_duplicate_ids_excluded_not_double_counted(frames):
    cs,warnings=reconcile(*frames)
    c=case(cs,'HC-1013')
    assert c.category=='DATA_QUALITY_REVIEW'
    assert c.received_cents==0
    assert any('repeated IDs' in w for w in warnings)

def test_missing_column_rejected(frames):
    frames[0]=frames[0].drop(columns=['gross_amount'])
    with pytest.raises(DataValidationError,match='gross_amount'):reconcile(*frames)

def test_duplicate_reservation_rejected(frames):
    frames[0]=pd.concat([frames[0],frames[0].iloc[:1]],ignore_index=True)
    with pytest.raises(DataValidationError,match='Duplicate reservation_id'):reconcile(*frames)

def test_mixed_currency_rejected(frames):
    frames[1].loc[0,'currency']='EUR'
    with pytest.raises(DataValidationError,match='mixed-currency'):reconcile(*frames)

def test_decimal_rounding():
    assert cents('0.105')==11
    assert cents('1.005')==101
    with pytest.raises(DataValidationError):cents('oops')
