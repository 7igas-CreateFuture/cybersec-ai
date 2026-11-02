"""Start this checkout on an isolated port; never call a model or use real history."""
import argparse,json,os,pathlib,re,socket,subprocess,sys,time,urllib.request

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--port',type=int,default=18766);a=p.parse_args()
 root=pathlib.Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 with socket.socket() as sock:sock.bind(('127.0.0.1',a.port))
 env=dict(os.environ,LOCAL_AI_PORT=str(a.port),LOCAL_AI_HISTORY_DB=str(out/'history.sqlite3'))
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}));base=f'http://127.0.0.1:{a.port}'
 proof={};log=(out/'server.log').open('w',encoding='utf-8')
 proc=subprocess.Popen([sys.executable,str(root/'local_server.py'),'--no-browser'],cwd=root,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:
  for attempt in range(60):
   if proc.poll() is not None:raise RuntimeError('Checkout server exited')
   try:
    with op.open(base+'/health',timeout=2) as r:health=json.load(r)
    break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('Checkout server did not become ready')
  assert health['pid']==proc.pid and health['cybersec_profile_version']==1
  with op.open(base+'/',timeout=5) as r:html=r.read().decode()
  token=re.search(r'window.LOCAL_TOKEN\s*=\s*[\'"]([^\'"]+)',html).group(1)
  for asset in ['/ui.js','/ui.css']:
   with op.open(base+asset,timeout=5) as r:assert r.status==200 and len(r.read())>0
  with op.open(urllib.request.Request(base+'/api/conversations',headers={'X-Local-Token':token}),timeout=5) as r:assert json.load(r)['conversations']==[]
  proof={'passed':True,'checks':['fresh_process_version','html_token','js_asset','css_asset','empty_isolated_history'],'model_calls':0,'real_history_used':False}
  print(json.dumps(proof))
 finally:
  proc.terminate();proc.wait(timeout=10);log.close()
  (out/'smoke-result.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')

if __name__=='__main__':main()
