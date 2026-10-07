"""Shreyansh Arora | 24bcs10252. Advisory procurement UI."""
import os
import json
import streamlit as st
from src.data_access import load_requests
from src.solution import analyze_request
st.set_page_config(page_title='Procurement Copilot | Shreyansh Arora',layout='wide')
st.title('AI Procurement Request Copilot')
st.caption('Shreyansh Arora | 24bcs10252 | Synthetic assessment data | Policy date: 2026-09-30')
mode=os.getenv('COPILOT_MODE','offline')
if mode=='offline': st.warning('Offline rule preview. No LLM calls are made. Live AI evaluation is pending.')
else: st.info('Live AI mode. All recommendations remain subject to code checks and human approval.')
requests=load_requests()
choice=st.sidebar.selectbox('Request',range(len(requests)),format_func=lambda i: requests[i]['request_id']+' - '+requests[i]['product_name'])
architecture=st.sidebar.radio('Architecture',['single','staged'])
st.sidebar.caption('A: Procurement Agent. B: Analyst -> Policy/Risk Reviewer. Both share the same five read-only tools and deterministic controls.')
left,right=st.columns([1,1.2])
req=dict(requests[choice])
with left:
    st.subheader('Request details')
    req['product_name']=st.text_input('Product',req['product_name'])
    req['vendor_name']=st.text_input('Vendor',req['vendor_name'])
    req['category']=st.text_input('Category',req['category'])
    req['requester_id']=st.text_input('Requester ID',req['requester_id'])
    cost=st.text_input('Annual cost (USD)',str(req['annual_cost_usd']) if req['annual_cost_usd'] is not None else '')
    users=st.text_input('Users/licenses',str(req['user_count'] or ''))
    req['annual_cost_usd']=cost or None
    req['user_count']=int(users) if users.isdigit() else None
    req['business_justification']=st.text_area('Business need',req['business_justification'])
    req['data_access_level']=st.text_input('Data access level',req['data_access_level'])
    integrations=st.text_input('Integrations (comma separated)',', '.join(req['requested_integrations']))
    req['requested_integrations']=[x.strip() for x in integrations.split(',') if x.strip()]
    run=st.button('Gather evidence and recommend',type='primary')
if run:
    with st.spinner('Checking budget, catalog, vendor evidence and policy...'):
        try:
            st.session_state['decision']=analyze_request(req,architecture).model_dump()
        except Exception as exc:
            st.error('Analysis could not complete: '+type(exc).__name__+'. Check configuration and source data. No approval inferred.')
            st.stop()
        st.session_state['signature']=json.dumps(req,sort_keys=True)+architecture
signature=json.dumps(req,sort_keys=True)+architecture
with right:
    st.subheader('Recommendation and human handoff')
    result=st.session_state.get('decision')
    if result and st.session_state.get('signature')!=signature:
        st.warning('Request changed. Rerun analysis; previous recommendation is hidden.')
        result=None
    if result:
        st.write(result['recommendation'])
        st.error('No purchase or approval has been executed.')
        st.markdown('**Approvals required:** '+(', '.join(result['required_approvals']) or 'Cannot determine until missing amount/identity is supplied'))
        st.markdown('**Risk flags:** '+(', '.join(result['risk_flags']) or 'None identified by available checks'))
        if result['missing_information']: st.warning('Missing: '+ '; '.join(result['missing_information']))
        st.info(result['next_step'])
        st.download_button('Download human review packet',json.dumps(result,indent=2),'review_packet.json','application/json')
        st.subheader('Evidence panel')
        for e in result['evidence']:
            with st.expander(e['source']+' | '+(e['reference'] or ''),expanded=e['source']=='controls'):
                st.json(json.loads(e['finding']))
        st.caption('Actual telemetry: '+json.dumps(result['telemetry']))
    else: st.info('Run analysis to see source-backed evidence and the human review packet.')
st.divider()
st.caption('AI interprets and recommends. Code applies thresholds and freshness. Humans approve sensitive decisions and exceptions. No write, purchasing or budget tools exist.')
