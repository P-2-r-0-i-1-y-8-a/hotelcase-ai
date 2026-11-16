import sqlite3
from pathlib import Path
import pandas as pd
import pytest
from hotelcase.sample_data import create_data
from hotelcase.reconciliation import reconcile
from hotelcase.storage import connect,sync_cases,get_statuses,get_audit,update_status
from hotelcase.agent import investigate
from hotelcase.evidence import build_packet

@pytest.fixture
def fixture_data(tmp_path):
    create_data(tmp_path)
    frames=[pd.read_csv(tmp_path/f,dtype=str,keep_default_na=False) for f in ('reservations.csv','payments.csv','settlements.csv')]
    cases,_=reconcile(*frames)
    db=connect(tmp_path/'test.db');sync_cases(db,cases)
    return cases,frames,db

def test_new_cases_are_audited(fixture_data):
    cases,frames,db=fixture_data
    assert len(get_statuses(db))==len(cases)
    assert any(a['action']=='CASE_CREATED' for a in get_audit(db))

def test_review_requires_actor_and_approval_note(fixture_data):
    cases,frames,db=fixture_data
    with pytest.raises(ValueError,match='Reviewer'):update_status(db,'HC-1001','CLOSED','','')
    with pytest.raises(ValueError,match='rationale'):update_status(db,'HC-1001','APPROVED_FOR_MANUAL_SUBMISSION','Manager','')
    update_status(db,'HC-1001','APPROVED_FOR_MANUAL_SUBMISSION','Manager','Verified supporting evidence')
    assert get_statuses(db)['HC-1001']['state']=='APPROVED_FOR_MANUAL_SUBMISSION'
    assert get_audit(db,'HC-1001')[0]['action']=='REVIEW_STATE_CHANGED'

def test_changed_financial_source_resets_approval(fixture_data):
    cases,frames,db=fixture_data
    update_status(db,'HC-1001','APPROVED_FOR_MANUAL_SUBMISSION','Manager','Confirmed evidence')
    payments=frames[1].copy()
    payments.loc[payments['payment_id']=='PAY-001','amount']='320.00'
    updated,_=reconcile(frames[0],payments,frames[2]);sync_cases(db,updated)
    assert get_statuses(db)['HC-1001']['state']=='OPEN'
    assert any(a['action']=='SOURCE_DATA_CHANGED' for a in get_audit(db,'HC-1001'))

@pytest.mark.skipif(__import__("importlib").util.find_spec("langgraph") is None, reason="langgraph not installed in build environment")
def test_langgraph_investigation_and_pdf(fixture_data):
    cases,frames,db=fixture_data
    c=next(c for c in cases if c.reservation_id=='HC-1001')
    out=investigate(c,frames[1],frames[2],use_ollama=False)
    assert out['route']=='review'
    assert out['payment_rows']
    assert 'settlement' in out['next_step'].lower()
    pdf=build_packet(c,out,get_audit(db,c.reservation_id))
    assert pdf.startswith(b'%PDF-')
    assert len(pdf)>1000

@pytest.mark.skipif(__import__("importlib").util.find_spec("langgraph") is None, reason="langgraph not installed in build environment")
def test_langgraph_clear_route(fixture_data):
    cases,frames,db=fixture_data
    c=next(c for c in cases if c.reservation_id=='HC-1003')
    out=investigate(c,frames[1],frames[2])
    assert out['route']=='clear'
    assert 'No payment recovery action' in out['recommendation']


def test_pdf_packet_without_graph(fixture_data):
    cases,frames,db=fixture_data
    c=next(c for c in cases if c.reservation_id=='HC-1001')
    record={'recommendation':c.reason,'next_step':'Check source records','checks':['Expected matches contract assumptions'],'payment_rows':[],'settlement_rows':[]}
    pdf=build_packet(c,record,get_audit(db,c.reservation_id))
    assert pdf.startswith(b'%PDF-')
    assert len(pdf)>1000
