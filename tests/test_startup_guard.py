import ast,io,json,pathlib,types,unittest,subprocess
from unittest.mock import Mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
class StartupTests(unittest.TestCase):
 def boot(self,health=None,occupied=True):
  tree=ast.parse((ROOT/'local_server.py').read_text(encoding='utf-8-sig'))
  main=next(n for n in tree.body if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__')
  server=Mock(); factory=Mock(side_effect=OSError('occupied')) if occupied else Mock(return_value=server)
  opener=Mock(); opener.open.return_value=io.BytesIO(json.dumps(health).encode())
  req=Mock();req.build_opener.return_value=opener
  browser=Mock()
  scope=dict(LocalServer=factory,PORT=18765,Handler=object(),urllib=types.SimpleNamespace(request=req),json=json,sys=types.SimpleNamespace(argv=['server','--no-browser']),webbrowser=browser)
  code=None
  try:exec(compile(ast.Module(body=main.body,type_ignores=[]),'actual_server_main','exec'),scope)
  except SystemExit as e:code=e.code
  browser.open.assert_not_called()
  return code,server
 def test_old_process_not_reused(self):
  c,s=self.boot({'service':'local-ai-assistant','protocol':2});self.assertIsInstance(c,str);s.serve_forever.assert_not_called()
 def test_wrong_profile_not_reused(self):
  c,_=self.boot({'service':'local-ai-assistant','protocol':2,'cybersec_profile_version':999});self.assertIsInstance(c,str)
 def test_matching_process_reused(self):
  c,s=self.boot({'service':'local-ai-assistant','protocol':2,'cybersec_profile_version':1});self.assertEqual(c,0);s.serve_forever.assert_not_called()
 def test_unknown_service_not_reused(self):
  c,_=self.boot({'service':'other','protocol':2,'cybersec_profile_version':1});self.assertIsInstance(c,str)
 def test_free_port_serves(self):
  c,s=self.boot(occupied=False);self.assertIsNone(c);s.serve_forever.assert_called_once()
if __name__=='__main__':unittest.main(verbosity=2)
