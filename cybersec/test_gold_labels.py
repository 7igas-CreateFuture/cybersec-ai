"""Executable checks for synthetic gold labels; no network or user files."""
import sqlite3,unittest,pathlib,types
class GoldLabels(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:')
  self.db.executescript("CREATE TABLE books(title,author); INSERT INTO books VALUES('one','Alice'),('two','Bob'); CREATE TABLE orders(id,user_id); INSERT INTO orders VALUES(101,1),(202,2);")
 def tearDown(self):self.db.close()
 def test_sql_pair(self):
  name="' OR 1=1 --"
  self.assertEqual(len(self.db.execute("SELECT title FROM books WHERE author='"+name+"'").fetchall()),2)
  self.assertEqual(self.db.execute('SELECT title FROM books WHERE author=?',(name,)).fetchall(),[])
 def test_authorization_pair(self):
  self.assertEqual(self.db.execute('SELECT * FROM orders WHERE id=?',(202,)).fetchone(),(202,2))
  self.assertIsNone(self.db.execute('SELECT * FROM orders WHERE id=? AND user_id=?',(202,1)).fetchone())
 def test_path_mapping(self):
  base=pathlib.PureWindowsPath('C:/data/files');name='../outside.txt'
  # Pure paths only: demonstrate the ID map excludes path input without opening files.
  self.assertIn('..',(base/name).parts)
  files={'guide':base/'guide.txt','faq':base/'faq.txt'}
  self.assertNotIn(name,files);self.assertNotIn('C:/outside.txt',files)
 def test_ssrf_mapping(self):
  endpoints={'status':'https://api.example.com/status'}
  self.assertNotIn('http://127.0.0.1',endpoints)
  self.assertEqual(endpoints['status'],'https://api.example.com/status')
  # Redirect=False is a requests contract documented in README; never send a request here.
if __name__=='__main__':unittest.main(verbosity=2)
