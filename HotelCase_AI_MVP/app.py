"""HotelCase AI — offline-first synthetic hotel revenue recovery demonstration."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import streamlit as st
from hotelcase.sample_data import create_data
from hotelcase.reconciliation import reconcile,DataValidationError,money
from hotelcase.storage import connect,create_session_workspace,sync_cases,get_statuses,get_audit,update_status,log,STATES
from hotelcase.agent import investigate
from hotelcase.evidence import build_packet

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
st.set_page_config(page_title='HotelCase AI | Revenue Recovery',page_icon='🏨',layout='wide')
st.markdown('''<style>
.block-container {padding-top:1.5rem;max-width:1450px;}
[data-testid="stMetric"] {padding:12px 16px;border:1px solid #D5DEE8;border-radius:12px;}
.small-muted {opacity:0.68;font-size:0.85rem;}
</style>''',unsafe_allow_html=True)

if not all((DATA/x).exists() for x in ('reservations.csv','payments.csv','settlements.csv')):create_data(DATA)

st.title('🏨 HotelCase AI')
st.caption('Revenue reconciliation • LangGraph investigations • Evidence packets • Local audit trail')
st.warning('**Demo / synthetic data only.** No live OTA/PMS integration, no real chargebacks, and no automatic submissions or collection actions.',icon='🧪')

# A separate temporary SQLite file is assigned to each Streamlit browser session.
# Never use a repository-global database for public visitors.
if 'hotelcase_db_path' not in st.session_state:
    st.session_state['hotelcase_db_path'] = str(create_session_workspace())
if 'upload_generation' not in st.session_state:
    st.session_state['upload_generation'] = 0
DB_PATH = Path(st.session_state['hotelcase_db_path'])

st.sidebar.header('Workspace')
property_filter=st.sidebar.selectbox('Property',['All properties','CLT-01','RDU-02'])
st.sidebar.markdown('**Data inputs**')
st.sidebar.caption('CSV uploads replace demo files only in your browser session. Upload synthetic data only; do NOT upload actual guest, personal or payment records. Files are limited to 2 MB each.')
files={}
for key in ('reservations','payments','settlements'):
    files[key]=st.sidebar.file_uploader(f'{key.title()} CSV',type=['csv'],key=f"upload_{key}_{st.session_state['upload_generation']}")
st.sidebar.caption('Each browser session has a private temporary review database. Data disappears when the session resets or hosting restarts.')
if st.sidebar.button('Reset my demo workspace', use_container_width=True):
    # Reset this visitor only. Old session's temporary DB is not reused.
    st.session_state['hotelcase_db_path'] = str(create_session_workspace())
    st.session_state['upload_generation'] += 1
    st.session_state.pop('investigation_result', None)
    st.rerun()
st.sidebar.divider()
use_ollama=st.sidebar.toggle('Optional local Ollama narration',value=False,help='Requires Ollama running at http://127.0.0.1:11434 and llama3.2:3b. Financial calculations remain unchanged.')
model=st.sidebar.text_input('Ollama model',value='llama3.2:3b') if use_ollama else 'llama3.2:3b'
actor=st.sidebar.text_input('Reviewer / actor (demo)',value='Demo Manager',max_chars=60)
st.sidebar.caption('Public demonstration: visitor workspaces are temporary and isolated. Reviewer names are not authenticated identities.')
st.sidebar.divider()
st.sidebar.download_button('Download sample reservations',DATA.joinpath('reservations.csv').read_bytes(),'reservations_sample.csv','text/csv',use_container_width=True)
st.sidebar.download_button('Download sample payments',DATA.joinpath('payments.csv').read_bytes(),'payments_sample.csv','text/csv',use_container_width=True)
st.sidebar.download_button('Download sample settlements',DATA.joinpath('settlements.csv').read_bytes(),'settlements_sample.csv','text/csv',use_container_width=True)

try:
    for key, uploaded in files.items():
        if uploaded is not None and uploaded.size > 2 * 1024 * 1024:
            raise ValueError(f'{key.title()} CSV is too large for the public demo (2 MB maximum).')
    frames={key:pd.read_csv(files[key] if files[key] is not None else DATA/f'{key}.csv',dtype=str,keep_default_na=False) for key in files}
    cases,warnings=reconcile(frames['reservations'],frames['payments'],frames['settlements'])
except Exception as e:
    st.error(f'Could not load/reconcile current data: {e}')
    st.stop()

# Per-visitor workspace: no shared cases or audit entries across browsers.
db=connect(DB_PATH)
sync_cases(db,cases)
statuses=get_statuses(db)
for w in warnings:st.info(f'Data integrity: {w}',icon='⚠️')
visible=[x for x in cases if property_filter=='All properties' or x.property_id==property_filter]
issue=[x for x in visible if x.category!='RECONCILED']
shortfalls=[x for x in visible if x.category=='SHORTFALL']
# 'Potential' values only: not a receivable or verified amount.
potential=sum(c.discrepancy_cents for c in shortfalls)

summary,queue,investigation,audit,data_tab=st.tabs(['📊 Overview','🚩 Exceptions & Cases','🧠 LangGraph Investigation','🧾 Audit Trail','🗄️ Source Data'])

with summary:
    a,b,c,d=st.columns(4)
    a.metric('Reservations',len(visible));b.metric('Exceptions to review',len(issue));c.metric('Potential shortfall (unverified)',money(potential));d.metric('Reconciled',sum(c.category=='RECONCILED' for c in visible))
    st.caption('Potential shortfall includes only confirmed-ledger SHORTFALL categories. It excludes pending, policy, and duplicate-ID cases. It is not confirmed recoverable revenue.')
    col1,col2=st.columns(2)
    with col1:
        st.subheader('Case categories')
        counts=pd.Series([x.category for x in visible]).value_counts()
        st.bar_chart(counts)
    with col2:
        st.subheader('By property')
        property_counts=pd.DataFrame([{'Property':x.property_id,'Exceptions':int(x.category!='RECONCILED')} for x in visible])
        if not property_counts.empty:st.bar_chart(property_counts.groupby('Property')['Exceptions'].sum())
    st.subheader('How recovery is calculated')
    st.markdown('''**HOTEL responsible:** expected = gross − approved refunds − adjustments; received = unique captured payments.  
**OTA responsible:** expected = gross − approved refunds − adjustments − OTA commission; received = unique settled OTA transfers.  
Pending/voided transactions are not counted as received. Duplicate transaction IDs are excluded from totals and flagged for integrity review. Booking cancellations/no-shows require policy review independent of the mathematical difference.''')

with queue:
    st.subheader('Exception queue')
    category_filter=st.multiselect('Categories',sorted({c.category for c in visible}),default=sorted({c.category for c in visible if c.category!='RECONCILED'}))
    rows=[{'Reservation':c.reservation_id,'Property':c.property_id,'Channel':c.channel,'Collection owner':c.payment_responsibility,'Category':c.category,'Severity':c.severity,'Expected USD':round(c.expected_cents/100,2),'Confirmed USD':round(c.received_cents/100,2),'Difference USD':round(c.discrepancy_cents/100,2),'Review state':statuses[c.reservation_id]['state'],'Flags':c.evidence_flags} for c in visible if c.category in category_filter]
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    if rows:st.download_button('Download filtered queue CSV',pd.DataFrame(rows).to_csv(index=False).encode(),'hotelcase_exception_queue.csv','text/csv')
    st.markdown('#### Case review status')
    if visible:
        sel_id=st.selectbox('Reservation',options=[c.reservation_id for c in visible],key='case_queue_id')
        selected=next(c for c in visible if c.reservation_id==sel_id)
        current=statuses[sel_id]
        st.write(f"**Category:** {selected.category} | **Difference:** {money(selected.discrepancy_cents)} | **Current state:** {current['state']}")
        st.caption(selected.reason)
        state=st.selectbox('New case state',STATES,index=STATES.index(current['state']),key='case_state_select')
        note=st.text_area('Reason for review or approval',key='case_review_note',placeholder='Reference verified settlement data, policies or missing documentation. Required for approval.')
        st.caption('Approval authorizes manual preparation only. It never sends a dispute or charges a card.')
        if st.button('Record review decision',type='primary'):
            try:
                update_status(db,sel_id,state,actor,note)
                st.success('Case state saved and audit event recorded. No external action performed.')
                st.rerun()
            except ValueError as exc:st.error(str(exc))

with investigation:
    st.subheader('Agent investigation')
    if visible:
        case_id=st.selectbox('Select reservation to investigate',[c.reservation_id for c in visible],key='investigation_id')
        target=next(c for c in visible if c.reservation_id==case_id)
        col1,col2,col3=st.columns(3)
        col1.metric('Expected',money(target.expected_cents));col2.metric('Confirmed received',money(target.received_cents));col3.metric('Difference',money(target.discrepancy_cents))
        st.caption(f'{target.category} | {target.reason}')
        if st.button('Run LangGraph investigation',type='primary'):
            with st.spinner('Retrieving evidence and reviewing exception...'):
                try:
                    outcome=investigate(target,frames['payments'],frames['settlements'],use_ollama,model)
                    st.session_state['investigation_result']=(case_id,target.to_dict(),outcome)
                    log(db,case_id,'INVESTIGATION_RUN',actor,{'category':target.category,'llm_requested':use_ollama,'recommendation':outcome.get('recommendation'),'no_external_action':True})
                    # Only change OPEN->INVESTIGATED, never overwrite human decisions.
                    if statuses[case_id]['state']=='OPEN':update_status(db,case_id,'INVESTIGATED',actor,'LangGraph evidence review generated; pending human verification.')
                except Exception as exc:st.error(f'Investigation failed: {exc}')
        saved=st.session_state.get('investigation_result')
        if saved and saved[0]==case_id and saved[1]==target.to_dict():
            result=saved[2]
            st.markdown('#### Recommendation')
            st.info(result.get('recommendation',''))
            st.markdown('**Next recommended action**')
            st.write(result.get('next_step',''))
            st.markdown('**Optional model narration**')
            st.write(result.get('explanation',''))
            with st.expander('Inspect evidence, deterministic checks and agent state',expanded=True):
                st.write('**Checks:**');st.write(result.get('checks',[]))
                st.write('**Source evidence:**');st.write(result.get('evidence',[]))
                st.write('**Payment rows:**');st.dataframe(pd.DataFrame(result.get('payment_rows',[])),hide_index=True)
                st.write('**Settlement rows:**');st.dataframe(pd.DataFrame(result.get('settlement_rows',[])),hide_index=True)
                st.write('**Graph route:**',result.get('route'))
            packet=build_packet(target,result,get_audit(db,case_id),get_statuses(db)[case_id]['state'])
            st.download_button('📄 Download evidence PDF',packet,f'{case_id}_evidence_packet.pdf','application/pdf')
            st.download_button('Download machine-readable investigation JSON',__import__('json').dumps(result,indent=2).encode(),f'{case_id}_investigation.json','application/json')
        else:st.caption('Run an investigation to generate recommendations, review evidence, and prepare a downloadable PDF packet.')

with audit:
    st.subheader('My session audit history')
    record=get_audit(db)
    if record:
        st.dataframe(pd.DataFrame(record),hide_index=True,use_container_width=True)
        st.download_button('Export audit CSV',pd.DataFrame(record).to_csv(index=False).encode(),'hotelcase_audit.csv','text/csv')
    else:st.caption('No events yet.')
    st.caption('This is a session-specific temporary audit trail. It is not tamper-proof, durable or legally certified.')

with data_tab:
    st.subheader('Source data (synthetic defaults)')
    for title,frame in frames.items():
        with st.expander(title.title(),expanded=title=='reservations'):
            st.dataframe(frame,hide_index=True,use_container_width=True)
    st.info('Production use would require verified source integration, authenticated users, encryption, regulatory review, immutable event logging, and secure credential management.')

st.divider()
st.caption('HotelCase AI MVP v0.2 • Per-session synthetic demo • No OTA submissions, payment processing, or guarantees of recovery.')
