"""Protocol tests and curated counterexamples. No LLM or network calls.

Bad/good snippets below are manually authored semantic transcriptions, not
execution of model output. Passing tests prove these bounded counterexamples,
not general repair quality. JDBC is compile-only against the installed JDK.
"""
import io
import os
import json
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import evaluate

JAVAC = os.environ.get("CYBERSEC_JAVAC") or shutil.which("javac")


class EvaluationProtocol(unittest.TestCase):
    def infer(self, reason='stop', system=None, model='cybersec-base:latest', done=True, text='answer'):
        events = [{'message': {'content': text}}]
        if done:
            final = {'done': True, 'model': model, 'eval_count': 2, 'eval_duration': 100000000}
            if reason is not None:
                final['done_reason'] = reason
            events.append(final)
        payloads = []
        class Opener:
            def open(self, request, timeout):
                payloads.append(json.loads(request.data))
                return io.BytesIO(('\n'.join(json.dumps(e) for e in events)+'\n').encode())
        with mock.patch.object(evaluate.urllib.request, 'build_opener', return_value=Opener()):
            result = evaluate.infer('cybersec-base:latest', 'question', {'seed': 42}, True, system=system)
        return result, payloads[0]

    def test_embedded_system_default_is_preserved(self):
        result, request = self.infer()
        self.assertEqual(request['messages'], [{'role': 'user', 'content': 'question'}])
        self.assertTrue(result['complete'])
        self.assertEqual(result['tokens_per_second'], 20)

    def test_explicit_system_and_options_are_observable(self):
        _, request = self.infer(system='frozen candidate')
        self.assertEqual(request['messages'][0], {'role': 'system', 'content': 'frozen candidate'})
        self.assertEqual(request['options'], {'seed': 42})
        self.assertFalse(request['think'])
        self.assertEqual(request['format'], 'json')

    def test_truncated_or_unknown_finish_is_not_success(self):
        for reason in ('length', 'error', 'cancelled', None):
            with self.subTest(reason=reason):
                result, _ = self.infer(reason=reason)
                self.assertFalse(result['complete'])
                self.assertEqual(result['termination'], reason or 'unknown')
                self.assertEqual(result['output'], 'answer')

    def test_empty_stop_is_not_success(self):
        result, _ = self.infer(text='')
        self.assertFalse(result['complete'])
        self.assertEqual(result['termination'], 'empty')

    def test_missing_done_is_error(self):
        with self.assertRaisesRegex(RuntimeError, 'without done'):
            self.infer(done=False)

    def test_wrong_model_is_error(self):
        with self.assertRaisesRegex(RuntimeError, 'model mismatch'):
            self.infer(model='different:latest')

    def test_non_string_evidence_cannot_crash_or_pass(self):
        for value in (None, [], {}, 7, True, ''):
            with self.subTest(evidence=value):
                result = evaluate.evaluate(json.dumps({'verdict': 'VULNERABLE', 'evidence': value,
                                                        'reason': 'reason', 'fix': 'fix'}),
                                           {'expected': 'VULNERABLE', 'code': 'source'})
                self.assertFalse(result['format_valid'])
                self.assertFalse(result['verdict_match'])
                self.assertFalse(result['evidence_is_code_substring'])


class RepairCounterexamples(unittest.TestCase):
    def test_order_id_comparison_allows_wrong_owner_and_denies_owner(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE orders(id,user_id); INSERT INTO orders VALUES(1,2),(101,1);')
            def bad(oid, uid):
                if oid != uid:
                    return None
                return db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
            def good(oid, uid):
                return db.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (oid,uid)).fetchone()
            self.assertEqual(bad(1,1), (1,2), 'ID collision leaks another owner record')
            self.assertIsNone(bad(101,1), 'Legitimate owner incorrectly denied')
            self.assertIsNone(good(1,1))
            self.assertEqual(good(101,1), (101,1))
            self.assertIsNone(good(999,1))

    def test_document_object_comparison_is_not_owner_check(self):
        user = types.SimpleNamespace(user_id=1)
        own = types.SimpleNamespace(id=101, owner_id=1)
        foreign = types.SimpleNamespace(id=202, owner_id=2)
        def bad(doc, current_user):
            if doc != current_user:
                return None
            return doc
        def good(doc, current_user):
            if current_user is None or doc is None or doc.owner_id != current_user.user_id:
                return None
            return doc
        self.assertIsNone(bad(own,user), 'Bad suggestion rejects legitimate owner')
        self.assertIs(good(own,user), own)
        self.assertIsNone(good(foreign,user))
        self.assertIsNone(good(None,user))
        self.assertIsNone(good(own,None))

    def test_relative_then_absolute_check_denies_valid_path(self):
        base = pathlib.PureWindowsPath('C:/synthetic/files')
        resolved = base/'guide.txt'
        relative = resolved.relative_to(base)
        self.assertFalse(relative.is_relative_to(base), 'Candidate compares different coordinate systems')
        self.assertTrue(resolved.is_relative_to(base))
        self.assertFalse(pathlib.PureWindowsPath('C:/synthetic/outside.txt').is_relative_to(base))
        # Pure paths demonstrate this logical error only, not real symlink/TOCTOU safety.

    def test_ssrf_destination_selection_without_network(self):
        calls=[]
        def fake_get(url, **kwargs):
            calls.append((url,kwargs))
        endpoints={'status':'https://api.example.com/status'}
        def bad(url):
            fake_get(url,timeout=3)
        def good(key):
            if key not in endpoints:
                return False
            fake_get(endpoints[key],timeout=3,allow_redirects=False)
            return True
        bad('http://127.0.0.1/synthetic')
        self.assertEqual(calls[-1][0], 'http://127.0.0.1/synthetic')
        calls.clear()
        self.assertFalse(good('http://127.0.0.1/synthetic'))
        self.assertEqual(calls, [])
        self.assertTrue(good('status'))
        self.assertEqual(calls, [('https://api.example.com/status', {'timeout':3,'allow_redirects':False})])
        # Tests routing only; trusted DNS is an explicit assumption, not verified here.

    @unittest.skipUnless(JAVAC, 'JDK unavailable: compile verification not performed')
    def test_jdbc_declaration_bad_fails_good_compiles(self):
        template = '''import java.sql.*;
class Repair {
  static void check(Connection conn, String name) throws SQLException {
    TYPE st = conn.prepareStatement("SELECT * FROM users WHERE name=?");
    st.setString(1, name);
  }
}
'''
        with tempfile.TemporaryDirectory(prefix='cybersec-jdbc-') as td:
            source=pathlib.Path(td)/'Repair.java'
            for declared, expected_success in [('Statement',False), ('PreparedStatement',True)]:
                with self.subTest(declared=declared):
                    source.write_text(template.replace('TYPE',declared),encoding='utf-8')
                    result=subprocess.run([JAVAC,'-proc:none','-encoding','UTF-8',str(source)],
                                          capture_output=True,text=True,timeout=30)
                    self.assertEqual(result.returncode==0, expected_success, result.stderr)
                    if not expected_success:
                        self.assertIn('setString', result.stderr)
        # No compiled class is executed; no database connection is opened.


class DatasetVersion(unittest.TestCase):
    def test_only_ssrf_threat_assumptions_change(self):
        root=pathlib.Path(__file__).parent
        original=json.loads((root/'cases.json').read_text(encoding='utf-8'))
        revised=json.loads((root/'cases-v2.json').read_text(encoding='utf-8'))
        self.assertEqual(revised['version'],2)
        a={x['id']:x for x in original['cases']};b={x['id']:x for x in revised['cases']}
        self.assertEqual(set(a),set(b))
        for key in a:
            if key.startswith('SSRF-'):
                self.assertEqual(a[key]['code'],b[key]['code'])
                self.assertEqual(a[key]['expected'],b[key]['expected'])
                self.assertEqual(b[key]['threat_model_version'],2)
                self.assertNotEqual(a[key]['prompt'],b[key]['prompt'])
            else:
                self.assertEqual(a[key],b[key])


if __name__=='__main__':
    unittest.main(verbosity=2)
