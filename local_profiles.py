"""Exact-ID profile routing; existing models retain original behavior."""
import json
from pathlib import Path
ROOT = Path(__file__).with_name('cybersec')
def get_profile(model):
    # Keep unrelated models independent of malformed CyberSec configuration.
    if not isinstance(model,str) or not model.startswith('cybersec-'):
        return None
    path = ROOT / 'profile.json'
    if not path.exists(): return None
    value = json.loads(path.read_text(encoding='utf-8'))
    if model != value['model']: return None
    prompt_path = (ROOT / value['system_file']).resolve()
    if prompt_path.parent != ROOT.resolve():
        raise ValueError('模型提示词文件必须位于 cybersec 目录。')
    prompt = prompt_path.read_text(encoding='utf-8').strip()
    if not prompt: raise ValueError('模型提示词不能为空。')
    return {**value, 'system': prompt}
def system_for(model, fallback):
    profile = get_profile(model)
    return profile['system'] if profile else fallback
