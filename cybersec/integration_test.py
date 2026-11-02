"""Real HTTP integration with a separate database and no user history writes."""
import os,pathlib,sys,json,re,subprocess,time,urllib.request,urllib.error,uuid,argparse
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--out',type=pathlib.Path,required=True);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
port=18766;base=f'http://127.0.0.1:{port}'
env=dict(os.environ,LOCAL_AI_PORT=str(port),LOCAL_AI_HISTORY_DB=str((args.out/'history.sqlite3').resolve()),PYTHONIOENCODING='utf-8')
# A test-only wrapper captures the outgoing system/model/options, never production prompts.
wrapper=args.out/'server_wrapper.py'
wrapper.write_text('import sys,runpy,json,pathlib,urllib.request\nsys.path.insert(0,'+repr(str(ROOT))+')\noriginal=urllib.request.OpenerDirector.open\ndef audited(self,request,*args,**kwargs):\n if isinstance(request,urllib.request.Request) and request.full_url.endswith("/api/chat"):\n  body=json.loads(request.data)\n  record={"model":body["model"],"system":body["messages"][0],"options":body["options"],"think":body["think"]}\n  with pathlib.Path('+repr(str((args.out/'requests.jsonl').resolve()))+').open("a",encoding="utf-8") as out:out.write(json.dumps(record,ensure_ascii=False)+"\\n")\n return original(self,request,*args,**kwargs)\nurllib.request.OpenerDirector.open=audited\nsys.argv=["local_server.py","--no-browser"]\nrunpy.run_path('+repr(str(ROOT/'local_server.py'))+',run_name="__main__")\n',encoding='utf-8')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
log=(args.out/'server.log').open('w',encoding='utf-8')
proc=subprocess.Popen([sys.executable,str(wrapper.resolve())],env=env,cwd=str(ROOT),stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
checks=[];token=None

def open_request(path,body=None,authenticated=True,headers=None):
 h={'Content-Type':'application/json'}
 if authenticated and token:h['X-Local-Token']=token
 if headers:h.update(headers)
 return opener.open(urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=h),timeout=90)
def request(path,body=None,**kw):
 with open_request(path,body,**kw) as response:return json.load(response)
def passed(name):checks.append({'name':name,'passed':True});print(name,'OK',flush=True)
try:
 for attempt in range(60):
  if proc.poll() is not None:raise RuntimeError('test server exited')
  try:health=request('/health');break
  except OSError:time.sleep(.2)
 else:raise RuntimeError('test server did not start')
 assert health['pid']==proc.pid and health.get('cybersec_profile_version')==1;passed('isolated_process_and_new_profile_version')
 with open_request('/') as response:html=response.read().decode()
 token=re.search(r'window.LOCAL_TOKEN\s*=\s*[\'"]([^\'"]+)',html).group(1)
 for kwargs in ({'authenticated':False},{'headers':{'Origin':'https://example.invalid'}}):
  try:request('/api/models',**kwargs);raise AssertionError('guard bypass')
  except urllib.error.HTTPError as e:assert e.code==403
 passed('missing_token_and_foreign_origin_rejected')
 models=request('/api/models');assert models['default_model']=='company-local:latest'
 assert {'company-local:latest','cybersec-base:latest'} <= {m['name'] for m in models['models']};passed('old_default_and_both_models_listed')
 for model in ['company-local:latest','cybersec-base:latest']:
  assert request('/api/model',{'model':model})['model']['name']==model
  body={'model':model,'prompt':'这是合成连通性测试。只回复：本地测试成功','request_id':str(uuid.uuid4()),'history':[],'revision':0}
  with open_request('/process',body) as response:events=[json.loads(line) for line in response if line.strip()]
  (args.out/(model.split(':')[0]+'-events.json')).write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
  assert any(e['type']=='delta' for e in events);assert not any(e['type']=='error' for e in events)
  done=next(e['value'] for e in events if e['type']=='done');assert done['model']==model and done['conversation']['id'];assert done['metrics']['eval_count']>0
  stored=request('/api/conversations?id='+done['conversation']['id']);assert stored['turns'][0]['answer']==done['text'];passed(model+'_stream_metrics_history')
 before=len(request('/api/conversations')['conversations']);rid=str(uuid.uuid4())
 body={'model':'cybersec-base:latest','prompt':'请详细讲解十种安全代码审计方法，每种至少200字。','request_id':rid,'history':[],'revision':0}
 with open_request('/process',body) as response:
  for line in response:
   event=json.loads(line)
   if event['type']=='delta':
    assert request('/api/cancel',{'request_id':rid})['cancel_requested'];break
  remaining=[json.loads(line) for line in response if line.strip()]
 assert not any(e['type']=='done' for e in remaining)
 assert any(e['type']=='cancelled' for e in remaining)
 assert len(request('/api/conversations')['conversations'])==before;passed('real_cancellation_no_history_commit')
 runtime=request('/api/runtime');assert runtime['ollama_reachable'] and not runtime['busy'];passed('runtime_endpoint_idle')
 records=[json.loads(line) for line in (args.out/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
 old,new=records[:2]
 assert old['model']=='company-local:latest' and '本地 AI 工作助手' in old['system']['content'] and old['options']['num_predict']==3072
 expected=(ROOT/'cybersec/system.md').read_text(encoding='utf-8').strip()
 assert new['model']=='cybersec-base:latest' and new['system']['content']==expected and new['options']['num_predict']==1536
 passed('observed_outbound_profile_isolation')
except Exception as e:
 checks.append({'name':'exception','passed':False,'error':repr(e)});raise
finally:
 proc.terminate();proc.wait(timeout=10);log.close()
 (args.out/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
