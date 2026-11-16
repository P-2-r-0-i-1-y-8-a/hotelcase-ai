"""Real LangGraph state machine with auditable investigation tools.

Uses deterministic financial calculations and clearly bounded source evidence.
An optional Ollama explanation is informational only: it cannot modify amounts,
recommendation category, evidence, approval state or audit history.
"""
from __future__ import annotations
from typing import TypedDict
import json,urllib.request
import pandas as pd
from .reconciliation import Case, money

class InvestigationState(TypedDict, total=False):
    case: dict
    payment_rows: list[dict]
    settlement_rows: list[dict]
    evidence: list[str]
    checks: list[str]
    recommendation: str
    next_step: str
    explanation: str
    route: str

def investigate(case:Case, payments:pd.DataFrame, settlements:pd.DataFrame, use_ollama=False, ollama_model='llama3.2:3b') -> dict:
    try:
        from langgraph.graph import StateGraph,START,END
    except ImportError as exc:
        raise RuntimeError('LangGraph is not installed. Run pip install -r requirements.txt') from exc

    def load_records(state):
        rid=state['case']['reservation_id']
        p=payments[payments['reservation_id'].astype(str)==rid].fillna('').to_dict('records')
        s=settlements[settlements['reservation_id'].astype(str)==rid].fillna('').to_dict('records')
        return {'payment_rows':p,'settlement_rows':s,'evidence':[f'PMS reservation {rid}',f'{len(p)} payment ledger rows',f'{len(s)} OTA settlement rows']}

    def validate(state):
        c=state['case'];checks=[]
        checks.append(f"Expected ({c['payment_responsibility']}): {money(c['expected_cents'])}")
        checks.append(f"Confirmed received: {money(c['received_cents'])}")
        checks.append(f"Difference (expected - received): {money(c['discrepancy_cents'])}")
        checks.append(f"Status: {c['booking_status']}; category: {c['category']}")
        if c['evidence_flags']:checks.append(f"Integrity flags: {c['evidence_flags']}")
        if c['response_deadline']:checks.append(f"User-supplied reference date (not verified): {c['response_deadline']}")
        route='review' if c['category']!='RECONCILED' else 'clear'
        return {'checks':checks,'route':route}

    def recommend_review(state):
        cat=state['case']['category']; c=state['case']
        actions={
          'SHORTFALL':'Confirm the settlement cycle, review refunds and adjustments, and reconcile source records before opening a payment recovery case.',
          'PENDING_VERIFICATION':'Check whether the pending authorization or OTA settlement has posted; do not claim missing revenue yet.',
          'DATA_QUALITY_REVIEW':'Resolve repeated transaction identifiers against original payment records before computing a reliable net collection.',
          'POLICY_REVIEW':'Confirm the applicable cancellation/no-show policy, guest communications and charging eligibility before any claim.',
          'OVER_COLLECTION_REVIEW':'Investigate possible overcollection, duplicated deposits and refund obligations; do not assume this is revenue.'}
        return {'recommendation':f"Review required: {c['reason']}", 'next_step':actions.get(cat,'Request manual financial review and source verification.')}

    def recommend_clear(state):
        return {'recommendation':'Current synthetic records reconcile. No payment recovery action indicated.','next_step':'Monitor for later ledger adjustments and settlement reversals.'}

    def optional_explanation(state):
        if not use_ollama: return {'explanation':'Local LangGraph workflow completed; optional LLM narration was disabled.'}
        safe={'category':state['case']['category'],'checks':state['checks'],'recommendation':state['recommendation'],'next_step':state['next_step']}
        payload={'model':ollama_model,'stream':False,'options':{'temperature':0},'messages':[
          {'role':'system','content':'You summarize synthetic financial records. Use only provided facts. Never invent deadlines, collection rights, rules, amounts or successful submission. Keep concise. Mention that manual verification is required.'},
          {'role':'user','content':json.dumps(safe)}]}
        try:
            request=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(request,timeout=25) as response:
                data=json.load(response)
            return {'explanation':data.get('message',{}).get('content','No model response returned.')}
        except Exception as exc:
            return {'explanation':f'Optional Ollama narration unavailable ({type(exc).__name__}); deterministic investigation and recommendations remain valid.'}

    graph=StateGraph(InvestigationState)
    graph.add_node('retrieve_source_records',load_records)
    graph.add_node('validate_financial_facts',validate)
    graph.add_node('human_review_recommendation',recommend_review)
    graph.add_node('clear_case_recommendation',recommend_clear)
    graph.add_node('optional_ollama_explanation',optional_explanation)
    graph.add_edge(START,'retrieve_source_records')
    graph.add_edge('retrieve_source_records','validate_financial_facts')
    graph.add_conditional_edges('validate_financial_facts',lambda s:s['route'],{'review':'human_review_recommendation','clear':'clear_case_recommendation'})
    graph.add_edge('human_review_recommendation','optional_ollama_explanation')
    graph.add_edge('clear_case_recommendation','optional_ollama_explanation')
    graph.add_edge('optional_ollama_explanation',END)
    result=graph.compile().invoke({'case':case.to_dict()})
    return result
