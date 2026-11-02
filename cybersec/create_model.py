"""Create a new local alias only; never overwrite or pull a model."""
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import local_assistant as core
import local_profiles
config=json.loads((ROOT/'cybersec/profile.json').read_text(encoding='utf-8'))
p=local_profiles.get_profile(config['model'])
source=p['source_model'];target=p['model']
before=core.api('/api/tags');names={m['name'] for m in before['models']}
if source not in names:raise SystemExit('Source absent: refusing download')
if target in names:raise SystemExit('Target exists: refusing overwrite')
info=core.api('/api/show',{'model':source})
if info.get('remote_model') or info.get('remote_host'):raise SystemExit('Source must be local')
modelfile='FROM '+source+'\n'+''.join(f'PARAMETER {k} {v}\n' for k,v in p['options'].items())+'SYSTEM """\n'+p['system']+'\n"""\n'
(ROOT/'cybersec/Modelfile').write_text(modelfile,encoding='utf-8')
result=core.api('/api/create',{'model':target,'from':source,'system':p['system'],'parameters':p['options'],'stream':False})
after=core.api('/api/tags');info_after=core.api('/api/show',{'model':source})
assert info_after==info,'Original model configuration changed'
assert next(m['digest'] for m in before['models'] if m['name']==source)==next(m['digest'] for m in after['models'] if m['name']==source)
new=core.api('/api/show',{'model':target});assert new['system'].strip()==p['system']
out=ROOT/'cybersec/results';out.mkdir(exist_ok=True)
(out/'model-creation.json').write_text(json.dumps({'result':result,'models_before':before,'models_after':after,'new_model':new,'original_show_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'result':result,'original_unchanged':True,'target':target},ensure_ascii=False))
