import json, os
from unittest.mock import patch, MagicMock
import pytest, httpx
from src.model import infer
PACK={'evidence':[{'id':'policy'}]}
def response(stop='end_turn',ids=None):
    r=MagicMock();r.json.return_value={'stop_reason':stop,'content':[{'type':'thinking','thinking':''},{'type':'text','text':json.dumps({'route':'manual_review','reason':'review','evidence_ids':ids or ['policy'],'gap_reason':''})}]};return r
@pytest.mark.parametrize('stop',['max_tokens','refusal','tool_use',None])
def test_stops(stop):
    with patch.dict(os.environ,{'MODEL_PROVIDER':'anthropic','FDE3_ANTHROPIC_API_KEY':'fake'}),patch('httpx.post',return_value=response(stop)):
        with pytest.raises(ValueError):infer(PACK,'review')
def test_request_and_ids():
    with patch.dict(os.environ,{'MODEL_PROVIDER':'anthropic','FDE3_ANTHROPIC_API_KEY':'fake'},clear=True),patch('httpx.post',return_value=response()) as post:
        assert infer(PACK,'review').route=='manual_review'
        args=post.call_args;assert args.args[0]=='https://api.anthropic.com/v1/messages'
        b=args.kwargs['json'];assert b['model']=='claude-sonnet-5-5' and b['max_tokens']==4096
        assert b['output_config']['format']['type']=='json_schema' and 'temperature' not in b
        post.return_value=response(ids=['unknown'])
        with pytest.raises(ValueError):infer(PACK,'review')
def test_missing_key():
    with patch.dict(os.environ,{'MODEL_PROVIDER':'anthropic'},clear=True),patch('httpx.post') as post:
        with pytest.raises(RuntimeError):infer(PACK,'review')
        post.assert_not_called()
@pytest.mark.parametrize('status',[401,429,500,503])
def test_http(status):
    req=httpx.Request('POST','https://api.anthropic.com/v1/messages');r=httpx.Response(status,request=req)
    with patch.dict(os.environ,{'MODEL_PROVIDER':'anthropic','FDE3_ANTHROPIC_API_KEY':'fake'}),patch('httpx.post',return_value=r):
        with pytest.raises(httpx.HTTPStatusError):infer(PACK,'review')
def test_timeout():
    with patch.dict(os.environ,{'MODEL_PROVIDER':'anthropic','FDE3_ANTHROPIC_API_KEY':'fake'}),patch('httpx.post',side_effect=httpx.ReadTimeout('timeout')):
        with pytest.raises(httpx.ReadTimeout):infer(PACK,'review')
def test_invalid_json():
    r=response();r.json.return_value['content'][1]['text']='not json'
    with patch.dict(os.environ,{'MODEL_PROVIDER':'anthropic','FDE3_ANTHROPIC_API_KEY':'fake'}),patch('httpx.post',return_value=r):
        with pytest.raises(ValueError):infer(PACK,'review')
