"""Offline synthetic evaluation. Streams to loopback Ollama; never executes code/tools."""
import argparse,datetime,hashlib,json,pathlib,time,urllib.request,sys,statistics
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import local_assistant as core

def sha(data):return hashlib.sha256(data).hexdigest()
def strict_object(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate JSON key: '+key)
        value[key]=item
    return value

def evaluate(text,case):
    if case['expected']=='REVIEW':return {'requires_semantic_review':True}
    try:
        value=json.loads(text,object_pairs_hook=strict_object)
        valid=isinstance(value,dict) and value.get('verdict') in ('VULNERABLE','NOT_VULNERABLE','INSUFFICIENT_EVIDENCE') and all(isinstance(value.get(k),str) and value[k].strip() for k in ('evidence','reason','fix'))
    except (ValueError,TypeError):return {'format_valid':False,'verdict_match':False,'error':'invalid_json'}
    return {'format_valid':bool(valid),'verdict':value.get('verdict') if isinstance(value,dict) else None,'verdict_match':bool(valid and value['verdict']==case['expected']),'evidence_is_code_substring':bool(isinstance(value,dict) and isinstance(value.get('evidence'),str) and value.get('evidence') and value['evidence'] in case.get('code','')),'note':'Substring and verdict checks do not establish semantic correctness.'}

def infer(model,prompt,options,structured,system=None):
    body={'model':model,'messages':[{'role':'user','content':prompt}],'stream':True,'think':False,'keep_alive':'2m','options':options}
    if system is not None:
        body['messages'].insert(0,{'role':'system','content':system})
    if structured:body['format']='json'
    req=urllib.request.Request(core.ENDPOINT+'/api/chat',data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),core.NoRedirect())
    start=time.perf_counter();first=None;parts=[];events=0;final=None
    with opener.open(req,timeout=180) as response:
        for line in response:
            if time.perf_counter()-start>240:raise TimeoutError('overall response budget exceeded')
            event=json.loads(line)
            if event.get('error'):raise RuntimeError(event['error'])
            delta=event.get('message',{}).get('content','')
            if delta:
                if first is None:first=time.perf_counter()-start
                parts.append(delta);events+=1
            if event.get('done'):final=event;break
    if final is None:raise RuntimeError('stream ended without done')
    if final.get('model')!=model:raise RuntimeError('response model mismatch')
    duration=final.get('eval_duration',0);count=final.get('eval_count',0)
    return {'request':body,'output':''.join(parts),'first_content_seconds':first,'wall_seconds':time.perf_counter()-start,'content_events':events,'final':final,'tokens_per_second':count*1e9/duration if duration else None,'termination':(final.get('done_reason') or 'unknown') if parts else 'empty','complete':final.get('done_reason')=='stop' and bool(parts)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models',nargs='+',default=['company-local:latest','cybersec-base:latest']);parser.add_argument('--out',type=pathlib.Path,required=True);parser.add_argument('--repeat',type=int,default=1);parser.add_argument('--cases',type=pathlib.Path,default=ROOT/'cases.json');parser.add_argument('--ids',nargs='*');args=parser.parse_args()
    if args.repeat<1:parser.error('repeat must be positive')
    args.out.mkdir(parents=True,exist_ok=False)
    dataset=args.cases;data=json.loads(dataset.read_text(encoding='utf-8'));cases=[c for c in data['cases'] if not args.ids or c['id'] in args.ids]
    if not cases:parser.error('no matching cases')
    options={'num_ctx':8192,'num_predict':1024,'temperature':0,'seed':42}
    tags=core.api('/api/tags');available={m['name']:m for m in tags['models']}
    snapshots={}
    for model in args.models:
        if model not in available:raise ValueError('Model not installed; no pull allowed: '+model)
        info=core.api('/api/show',{'model':model})
        if info.get('remote_host') or info.get('remote_model') or 'cloud' in model:raise ValueError('Local model required')
        snapshots[model]={'tag':available[model],'show':info}
    meta={'started_at':datetime.datetime.now().astimezone().isoformat(),'ollama':core.api('/api/version'),'python':sys.version,'dataset_sha256':sha(dataset.read_bytes()),'dataset_version':data.get('version'),'dataset_file':dataset.name,'runner_sha256':sha(pathlib.Path(__file__).read_bytes()),'options':options,'repeat':args.repeat,'models':snapshots,'scoring':'Mechanical format/verdict only. Codex semantic review is separate.','mode':'model embedded system; no system override; one isolated chat per case; no tools'}
    (args.out/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.out/'cases.json').write_bytes(dataset.read_bytes())
    rows=[]
    with (args.out/'responses.jsonl').open('x',encoding='utf-8') as out:
        for model in args.models:
            for rep in range(args.repeat):
                for case in cases:
                    prompt=case['prompt']
                    structured=case['expected']!='REVIEW'
                    if structured:prompt+='\n只返回 JSON 对象，字段 verdict（VULNERABLE/NOT_VULNERABLE/INSUFFICIENT_EVIDENCE）、evidence（尽量逐字引用代码）、reason（解释数据流和条件）、fix（修复或保持现有措施）。不要声称执行了代码。'
                    else:prompt+='\n请在400字以内回答。'
                    row={'model':model,'id':case['id'],'group':case['group'],'expected':case['expected'],'repeat':rep,'input':prompt,'input_sha256':sha(prompt.encode()),'at':datetime.datetime.now().astimezone().isoformat()}
                    try:
                        row.update(infer(model,prompt,options,structured));row['checks']=evaluate(row['output'],case)
                    except Exception as error:row.update({'error':str(error),'termination':type(error).__name__,'complete':False})
                    rows.append(row);out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
                    print(model,case['id'],'complete='+str(row['complete']),row.get('checks',{}).get('verdict'),flush=True)
            # Release our evaluation model before the next one to limit 6GB VRAM use.
            core.api('/api/generate',{'model':model,'keep_alive':0,'stream':False})
    summary={}
    for model in args.models:
        selected=[r for r in rows if r['model']==model];main=[r for r in selected if r['group']=='classification'];valid=[r for r in main if r.get('complete')]
        summary[model]={'total':len(selected),'complete':sum(r['complete'] for r in selected),'classification_total':len(main),'verdict_matches':sum(r.get('checks',{}).get('verdict_match',False) for r in valid),'format_valid':sum(r.get('checks',{}).get('format_valid',False) for r in valid),'false_positive_count':sum(r.get('checks',{}).get('verdict')=='VULNERABLE' for r in valid if r['expected']=='NOT_VULNERABLE'),'false_negative_count':sum(r.get('checks',{}).get('verdict')=='NOT_VULNERABLE' for r in valid if r['expected']=='VULNERABLE'),'median_eval_tokens_per_second':statistics.median([r['tokens_per_second'] for r in selected if r.get('tokens_per_second')]) if any(r.get('tokens_per_second') for r in selected) else None,'semantic_review':'pending','performance_note':'Mixed prompts, cold/warm loads, small sample; not a stable throughput benchmark.'}
    (args.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 1 if any(not r['complete'] for r in rows) else 0
if __name__=='__main__':sys.exit(main())
