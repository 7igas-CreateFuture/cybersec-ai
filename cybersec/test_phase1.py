import unittest,sys,pathlib,json,io,unittest.mock as mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import local_profiles as profiles
import local_assistant as core
sys.path.insert(0,str(ROOT/'cybersec'))
import evaluate
class ProfilesTest(unittest.TestCase):
 def test_exact_model_routing(self):
  self.assertIsNone(profiles.get_profile('company-local:latest'))

  for name in ('cybersec-base:other','cybersec-base','CYBERSEC-BASE:latest','cybersec-base2:latest'):
   self.assertIsNone(profiles.get_profile(name))
  self.assertEqual(profiles.system_for('company-local:latest','old prompt'),'old prompt')
  self.assertIn('CyberSec AI',profiles.system_for('cybersec-base:latest','old prompt'))
 def test_old_model_survives_broken_security_config(self):
  with mock.patch.object(pathlib.Path,'read_text',side_effect=ValueError('broken config')):
   self.assertIsNone(profiles.get_profile('company-local:latest'))
   with self.assertRaises(ValueError):profiles.get_profile('cybersec-base:latest')
 def test_model_creation_system_matches_profile(self):
  self.assertIn(profiles.get_profile('cybersec-base:latest')['system'],(ROOT/'cybersec/Modelfile').read_text(encoding='utf-8'))
 def fake_chat(self,model,final=True):
  captured=[]
  class Opener:
   def open(self,request,timeout):
    captured.append(json.loads(request.data))
    events=[{'message':{'content':'测试'}}]
    if final:events.append({'done':True,'done_reason':'stop','model':model,'eval_count':2,'eval_duration':100000000})
    return io.BytesIO(('\n'.join(json.dumps(e) for e in events)+'\n').encode())
  with mock.patch.object(core.urllib.request,'build_opener',return_value=Opener()):
   result=core.chat('chosen system','test',model=model)
  return captured[0],result
 def test_existing_payload_unchanged(self):
  body,result=self.fake_chat('company-local:latest')
  self.assertEqual(body['options'],{'num_ctx':8192,'num_predict':3072,'temperature':0})
  self.assertEqual(body['messages'][0]['content'],'chosen system')
  self.assertEqual(result,'测试')
 def test_cybersec_options(self):
  body,_=self.fake_chat('cybersec-base:latest')
  self.assertEqual(body['options'],profiles.get_profile('cybersec-base:latest')['options'])
  self.assertFalse(body['think'])
 def test_interrupted_stream_is_not_success(self):
  with self.assertRaisesRegex(RuntimeError,'模型连接中断'):self.fake_chat('cybersec-base:latest',False)
 def test_metrics_do_not_grade_semantics(self):
  c={'expected':'VULNERABLE','code':'x'}
  good=json.dumps({'verdict':'VULNERABLE','evidence':'invented','reason':'wrong','fix':'wrong'})
  checks=evaluate.evaluate(good,c)
  self.assertTrue(checks['verdict_match']);self.assertFalse(checks['evidence_is_code_substring'])
  self.assertFalse(evaluate.evaluate('[]',c)['format_valid'])
  self.assertFalse(evaluate.evaluate('bad',c)['format_valid'])
  self.assertFalse(evaluate.evaluate('{"verdict":"VULNERABLE","verdict":"NOT_VULNERABLE"}',c)['format_valid'])
 def test_cancellation(self):
  cancel=core.Cancellation();cancel.cancel()
  with self.assertRaises(core.Cancelled):cancel.check()
if __name__=='__main__':unittest.main(verbosity=2)
