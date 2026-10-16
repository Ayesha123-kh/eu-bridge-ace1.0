from app import db
from app.services import audit


def _seed(n=4):
    for i in range(n):
        audit.log("alice", "approved", "scan1", f"f{i}", {"i": i})


def test_intact_chain_verifies(db):
    assert audit.verify() == {"ok": True, "broken_at": None, "entries": 0}
    _seed()
    assert audit.verify()["ok"] is True


def test_editing_a_row_breaks_chain_at_that_row(db):
    _seed()
    conn = db_conn()
    conn.execute("UPDATE audit_log SET actor='mallory' WHERE seq=2")
    conn.commit()
    assert audit.verify()["broken_at"] == 2


def test_deleting_a_middle_row_is_detected(db):
    _seed()
    conn = db_conn()
    conn.execute("DELETE FROM audit_log WHERE seq=2")
    conn.commit()
    r = audit.verify()
    assert r["ok"] is False and r["broken_at"] == 3


def db_conn():
    return db.connect()
