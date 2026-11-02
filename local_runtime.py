"""Read-only local metrics. No prompts, arbitrary commands, or remote endpoints."""
import csv,io,os,subprocess,threading,time
from pathlib import Path
import local_assistant as core

_lock=threading.Lock()
_at=0.0
_cache={}

def models():
    items=core.api('/api/tags',timeout=5).get('models',[])
    return [{'name':m['name'],'details':m.get('details',{}),'size':m.get('size'),
             'available':not (m.get('remote_host') or m.get('remote_model') or 'cloud' in m['name'].split(':')[-1].lower())}
            for m in items if isinstance(m.get('name'),str)]

def validate_model(name):
    if not isinstance(name,str) or not name or len(name)>200:raise ValueError('请选择已安装的本地模型。')
    item=next((m for m in models() if m['name']==name),None)
    if not item:raise ValueError('该模型不在本机列表中，请刷新后重试。')
    info=core.api('/api/show',{'model':name},timeout=10)
    if not item['available'] or info.get('remote_host') or info.get('remote_model'):
        raise ValueError('此助手只允许本地模型，不允许云端模型。')
    if 'completion' not in info.get('capabilities',[]):raise ValueError('该模型未声明文本生成能力，不能用于聊天。')
    return item

def gpu_sample():
    # A fixed, trusted executable and fixed arguments; no input from the browser.
    exe=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/nvidia-smi.exe'
    try:
        result=subprocess.run([str(exe),'--query-gpu=index,name,memory.used,memory.total','--format=csv,noheader,nounits'],
                              capture_output=True,text=True,timeout=2,check=True,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        devices=[]
        for row in csv.reader(io.StringIO(result.stdout)):
            index,name,used,total=[x.strip() for x in row];used=float(used);total=float(total)
            if total<=0:raise ValueError()
            devices.append({'index':int(index),'name':name,'used_mib':used,'total_mib':total,'percent':round(used/total*100,1)})
        return {'available':bool(devices),'devices':devices,'source':'nvidia-smi','sampled_at':time.time()}
    except (OSError,ValueError,subprocess.SubprocessError):
        return {'available':False,'devices':[],'source':'nvidia-smi','error':'显存监控不可用','sampled_at':time.time()}

def runtime():
    global _at,_cache
    with _lock:
        if time.monotonic()-_at<2:return dict(_cache)
        gpu=gpu_sample()
        try:
            loaded=core.api('/api/ps',timeout=2).get('models',[])
            loaded=[{k:m.get(k) for k in ('name','size','size_vram','context_length')} for m in loaded]
            reachable=True
        except RuntimeError:loaded=[];reachable=False
        _cache={'gpu':gpu,'loaded_models':loaded,'ollama_reachable':reachable};_at=time.monotonic()
        return dict(_cache)
