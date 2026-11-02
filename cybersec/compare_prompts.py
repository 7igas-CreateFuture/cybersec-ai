"""Frozen candidate vs original system, same installed local model. Never deploys."""
import json,pathlib,sys,argparse,random,datetime,statistics,hashlib
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));import evaluate as ev

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False)
 model='cybersec-base:latest';show=ev.core.api('/api/show',{'model':model})
 if show.get('remote_model') or show.get('remote_host'):raise ValueError('Local model required')
 candidate=(ROOT/'experiments/system-candidate-v2.md').read_text(encoding='utf-8')
 plan=json.loads((ROOT/'experiments/experiment-plan.json').read_text(encoding='utf-8'))
 assert ev.sha(candidate.encode())==plan['candidate_sha256'],'Candidate changed after freeze'
 systems={'original':show['system'],'candidate':candidate.strip()}
 regression=json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))['cases']
 for case in regression:case['split']='regression'
 holdout=json.loads((ROOT/'experiments/holdout-v2.json').read_text(encoding='utf-8'))['cases']
 for case in holdout:case['split']='holdout'
 cases=regression+holdout
 rng=random.Random(42);rng.shuffle(cases)
 options={'num_ctx':8192,'num_predict':1024,'temperature':0,'seed':42}
 schedule=[]
 for i,c in enumerate(cases):
  for variant in (['original','candidate'] if i%2==0 else ['candidate','original']):schedule.append({'id':c['id'],'variant':variant})
 before=ev.core.api('/api/tags')
 metadata={'at':datetime.datetime.now().astimezone().isoformat(),'model':model,'models_before':before,'model_show':show,'ollama':ev.core.api('/api/version'),'options':options,'think':False,'systems':systems,'system_hashes':{k:ev.sha(v.encode()) for k,v in systems.items()},'plan':plan,'schedule':schedule,'runner_hash':ev.sha(pathlib.Path(__file__).read_bytes()),'infer_hash':ev.sha((ROOT/'evaluate.py').read_bytes()),'cases_hash':ev.sha(json.dumps(cases,ensure_ascii=False,sort_keys=True).encode()),'no_retry':True,'no_deployment':True,'warmup':'One unscored short response per system; model stays loaded; order/cache effects remain.'}
 (args.out/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
 (args.out/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
 warmups=[]
 for variant,system in systems.items():warmups.append({'variant':variant,**ev.infer(model,'只回答：就绪',dict(options,num_predict=32),False,system=system)})
 (args.out/'warmups.json').write_text(json.dumps(warmups,ensure_ascii=False,indent=2),encoding='utf-8')
 rows=[];mapping={c['id']:c for c in cases}
 with (args.out/'responses.jsonl').open('x',encoding='utf-8') as out:
  for job in schedule:
   c=mapping[job['id']];variant=job['variant'];structured=c['expected']!='REVIEW';prompt=c['prompt']
   prompt+=('\n只返回 JSON 对象，字段 verdict（VULNERABLE/NOT_VULNERABLE/INSUFFICIENT_EVIDENCE）、evidence（尽量逐字引用代码）、reason（解释数据流和条件）、fix（修复或保持现有措施）。不要声称执行了代码。' if structured else '\n请在400字以内回答。')
   row={**job,'model':model,'split':c['split'],'group':c['group'],'expected':c['expected'],'input':prompt,'input_hash':ev.sha(prompt.encode()),'at':datetime.datetime.now().astimezone().isoformat()}
   try:
    row.update(ev.infer(model,prompt,options,structured,system=systems[variant]));row['checks']=ev.evaluate(row['output'],c)
   except Exception as e:row.update({'complete':False,'error':str(e),'termination':type(e).__name__})
   rows.append(row);out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
   print(variant,c['id'],row.get('termination'),row.get('checks',{}).get('verdict'),flush=True)
 summary={}
 for variant in systems:
  summary[variant]={}
  for split in ('regression','holdout'):
   rs=[r for r in rows if r['variant']==variant and r['split']==split];classified=[r for r in rs if r['expected']!='REVIEW' and r['group'] not in ('uncertainty',)]
   valid=[r for r in classified if r['complete'] and r.get('checks',{}).get('format_valid')]
   summary[variant][split]={'requests':len(rs),'complete':sum(r['complete'] for r in rs),'classification_n':len(classified),'format_valid':len(valid),'usable_correct':sum(r['checks']['verdict_match'] for r in valid),'false_positive':sum(r['expected']=='NOT_VULNERABLE' and r['checks']['verdict']=='VULNERABLE' for r in valid),'false_negative':sum(r['expected']=='VULNERABLE' and r['checks']['verdict']=='NOT_VULNERABLE' for r in valid),'truncated':sum(r.get('termination')=='length' for r in rs),'median_tokens_per_second':statistics.median(r['tokens_per_second'] for r in rs if r.get('tokens_per_second')),'median_wall_seconds':statistics.median(r['wall_seconds'] for r in rs if 'wall_seconds' in r),'semantic_review':'pending'}
 assert ev.core.api('/api/show',{'model':model})==show,'Model configuration changed during experiment'
 (args.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
 return 1 if any(not r['complete'] for r in rows) else 0
if __name__=='__main__':sys.exit(main())
