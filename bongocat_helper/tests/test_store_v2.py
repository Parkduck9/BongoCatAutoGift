import sqlite3
from store import Store

def test_existing_chat_database_preserves_old_rows_and_adds_metadata(tmp_path):
    path=tmp_path/'existing.db'
    old=sqlite3.connect(path)
    old.execute('CREATE TABLE chat (id INTEGER PRIMARY KEY,ts REAL NOT NULL,date TEXT NOT NULL,speaker TEXT NOT NULL,text TEXT NOT NULL)')
    old.execute("INSERT INTO chat VALUES (1,100,'1970-01-01','리네','기존 기록')")
    old.commit();old.close()
    db=Store(path)
    assert db.query_chat()==[(100,'리네','기존 기록')]
    assert db.query_chat_records()[0]['status']=='recognized'
    db.add_chat(101,'Alucard','Hello',cat_id=9,status='estimated',score=.6)
    assert len(db.query_chat_records())==2
    db.close()
