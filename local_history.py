"""Local SQLite conversation storage. Never stores attachment bytes or extracts."""
import json,sqlite3,time,uuid
from pathlib import Path

class HistoryStore:
    def __init__(self,path):self.path=Path(path)
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=5)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY,title TEXT NOT NULL,created REAL NOT NULL,
          updated REAL NOT NULL,revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS turns (
          request_id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id),
          prompt TEXT NOT NULL,answer TEXT NOT NULL,model TEXT NOT NULL,
          attachment_name TEXT NOT NULL,metrics TEXT,created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS turns_conversation ON turns(conversation_id,created);
        ''')
        return db
    def list(self):
        db=self.connect()
        try:return [dict(row) for row in db.execute('SELECT * FROM conversations ORDER BY updated DESC')]
        finally:db.close()
    def get(self,conversation_id):
        db=self.connect()
        try:
            row=db.execute('SELECT * FROM conversations WHERE id=?',(conversation_id,)).fetchone()
            if row is None:raise ValueError('找不到这条本地历史对话，请刷新列表。')
            result=dict(row)
            result['turns']=[dict(r) for r in db.execute('SELECT * FROM turns WHERE conversation_id=? ORDER BY created,rowid',(conversation_id,))]
            for turn in result['turns']:turn['metrics']=json.loads(turn['metrics']) if turn['metrics'] else None
            return result
        finally:db.close()
    def save(self,conversation_id,revision,request_id,prompt,answer,model,attachment_name='',metrics=None):
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT conversation_id FROM turns WHERE request_id=?',(request_id,)).fetchone()
            if existing:raise ValueError('该请求已保存，拒绝重复提交。')
            now=time.time()
            if conversation_id:
                row=db.execute('SELECT revision FROM conversations WHERE id=?',(conversation_id,)).fetchone()
                if row is None or row['revision']!=revision:raise ValueError('历史已在其他页面更新，请重新打开该对话。')
            else:
                conversation_id=str(uuid.uuid4());revision=0
                db.execute('INSERT INTO conversations VALUES(?,?,?,?,0)',(conversation_id,prompt[:50],now,now))
            db.execute('INSERT INTO turns VALUES(?,?,?,?,?,?,?,?)',(request_id,conversation_id,prompt,answer,model,attachment_name,json.dumps(metrics) if metrics else None,now))
            db.execute('UPDATE conversations SET updated=?,revision=? WHERE id=?',(now,revision+1,conversation_id))
            db.commit()
            return {'id':conversation_id,'revision':revision+1}
        except Exception:db.rollback();raise
        finally:db.close()
