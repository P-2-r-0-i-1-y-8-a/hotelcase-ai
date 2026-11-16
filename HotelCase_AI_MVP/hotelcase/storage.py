"""Local SQLite review queue and append-only audit records."""
from pathlib import Path
from datetime import datetime,timezone
import json, sqlite3

STATES=('OPEN','INVESTIGATED','APPROVED_FOR_MANUAL_SUBMISSION','CLOSED','REJECTED')

def connect(path: str | Path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS cases (
        reservation_id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        discrepancy_cents INTEGER NOT NULL,
        state TEXT NOT NULL DEFAULT 'OPEN',
        reviewer TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reservation_id TEXT NOT NULL,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        detail TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS audit_reservation_idx ON audit(reservation_id);
    ''')
    db.commit()
    return db

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def log(db, reservation_id, action, actor, detail):
    db.execute('INSERT INTO audit(reservation_id,action,actor,detail,created_at) VALUES (?,?,?,?,?)',
               (reservation_id,action,actor,json.dumps(detail,sort_keys=True,default=str),now()))
    db.commit()

def sync_cases(db,cases):
    """Refresh monetary facts; preserve human review states; log important changes."""
    for case in cases:
        old=db.execute('SELECT * FROM cases WHERE reservation_id=?',(case.reservation_id,)).fetchone()
        if not old:
            db.execute('INSERT INTO cases(reservation_id,category,discrepancy_cents,updated_at) VALUES (?,?,?,?)',
                       (case.reservation_id,case.category,case.discrepancy_cents,now()))
            log(db,case.reservation_id,'CASE_CREATED','system',{'category':case.category,'discrepancy_cents':case.discrepancy_cents})
        elif old['category']!=case.category or old['discrepancy_cents']!=case.discrepancy_cents:
            db.execute('UPDATE cases SET category=?,discrepancy_cents=?,state=?,reviewer=?,note=?,updated_at=? WHERE reservation_id=?',
                       (case.category,case.discrepancy_cents,'OPEN','','',now(),case.reservation_id))
            log(db,case.reservation_id,'SOURCE_DATA_CHANGED','system',{'old_category':old['category'],'new_category':case.category,'old_discrepancy_cents':old['discrepancy_cents'],'new_discrepancy_cents':case.discrepancy_cents,'state_reset':'OPEN'})
    db.commit()

def update_status(db,rid,state,reviewer,note):
    if state not in STATES: raise ValueError('Invalid review state')
    if not reviewer.strip(): raise ValueError('Reviewer required')
    old=db.execute('SELECT state FROM cases WHERE reservation_id=?',(rid,)).fetchone()
    if old is None: raise ValueError('Case not found')
    if state=='APPROVED_FOR_MANUAL_SUBMISSION' and not note.strip(): raise ValueError('Approval rationale required')
    db.execute('UPDATE cases SET state=?,reviewer=?,note=?,updated_at=? WHERE reservation_id=?',
               (state,reviewer.strip(),note.strip(),now(),rid))
    log(db,rid,'REVIEW_STATE_CHANGED',reviewer.strip(),{'from':old['state'],'to':state,'note':note.strip(),'submission':'NOT_PERFORMED'})

def get_statuses(db):
    return {r['reservation_id']:dict(r) for r in db.execute('SELECT * FROM cases')}

def get_audit(db,rid=None):
    if rid:
        rows=db.execute('SELECT * FROM audit WHERE reservation_id=? ORDER BY id DESC',(rid,))
    else: rows=db.execute('SELECT * FROM audit ORDER BY id DESC')
    return [dict(r) for r in rows]
