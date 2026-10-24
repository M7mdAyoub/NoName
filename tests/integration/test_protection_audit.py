from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.db import protection
from app.db.connection import Database
from app.db.ids import new_id, utc_now
from app.logging_setup import request_id_var
from app.repositories import audit
from app.repositories.audit import write_audit


def _insert_file(conn, file_id: str) -> None:  # type: ignore[no-untyped-def]
    now = utc_now()
    conn.execute(
        text(
            "INSERT INTO file (id, sha256, mime_type, size_bytes, original_name, storage_path, "
            "created_at, updated_at) VALUES (:id, 's', 'text/plain', 1, 'a.txt', 'p', :n, :n)"
        ),
        {"id": file_id, "n": now},
    )


def test_hard_delete_of_a_business_table_row_fails(db: Database) -> None:
    file_id = new_id()
    with db.write_tx() as conn:
        _insert_file(conn, file_id)
    with (
        pytest.raises(Exception, match="hard delete forbidden; set deleted_at"),
        db.write_tx() as conn,
    ):
        conn.execute(text("DELETE FROM file WHERE id = :id"), {"id": file_id})
    with db.write_tx() as conn:  # soft delete is the supported path
        conn.execute(
            text("UPDATE file SET deleted_at = :n WHERE id = :id"), {"id": file_id, "n": utc_now()}
        )
    with db.read_tx() as conn:
        assert conn.execute(text("SELECT count(*) FROM file")).scalar() == 1


def test_job_rows_may_be_deleted_because_the_table_is_exempt(db: Database) -> None:
    with db.write_tx() as conn:
        conn.execute(
            text(
                "INSERT INTO job (id,type,status,payload,run_after,created_at) "
                "VALUES ('j','noop','queued','{}','t','t')"
            )
        )
        conn.execute(text("DELETE FROM job"))


def test_audit_log_is_insert_only(db: Database) -> None:
    with db.write_tx() as conn:
        row_id = write_audit(conn, action="create", table_name="file", row_id="f1")
    for sql in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
        with pytest.raises(Exception, match="audit_log is insert-only"), db.write_tx() as conn:
            conn.exec_driver_sql(sql)
    with db.read_tx() as conn:
        assert conn.execute(text("SELECT id FROM audit_log")).scalar() == row_id


def test_exempt_and_protected_lists_are_consistent(db: Database) -> None:
    assert {
        "membership_component",
        "indicator_field_link",
        "qual_coding",
        "indicator_dirty",
        "refresh_token",
        "password_reset",
        "entity_alias",
        "job",
    } <= protection.EXEMPT
    assert not protection.EXEMPT & protection.HISTORY
    with db.read_tx() as conn:
        assert protection.protected_tables(conn) == ["file"]
        assert protection.unclassified_tables(conn) == []
        assert protection.verify_triggers(conn) == []


def test_verify_detects_a_missing_trigger(db: Database) -> None:
    with db.write_tx() as conn:
        conn.exec_driver_sql("DROP TRIGGER file_no_delete")
    with db.read_tx() as conn:
        assert any("file_no_delete" in p for p in protection.verify_triggers(conn))
    with db.write_tx() as conn:
        assert protection.ensure_triggers(conn) == ["file"]
        assert protection.ensure_triggers(conn) == []


def test_audit_row_is_written_in_the_same_transaction(db: Database) -> None:
    token = request_id_var.set("req-audit-0001")
    try:
        with pytest.raises(RuntimeError), db.write_tx() as conn:
            write_audit(
                conn,
                action="create",
                table_name="file",
                row_id="f1",
                after={"b": 2, "a": 1},
                user_id="u1",
                project_id="p1",
            )
            raise RuntimeError("rolled back")
        with db.read_tx() as conn:
            assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar() == 0
        with db.write_tx() as conn:
            write_audit(
                conn,
                action="update",
                table_name="file",
                row_id="f1",
                before={"a": 1},
                after={"b": 2, "a": 1},
                user_id="u1",
                project_id="p1",
            )
    finally:
        request_id_var.reset(token)
    with db.read_tx() as conn:
        row = conn.execute(text("SELECT * FROM audit_log")).mappings().one()
    assert row["action"] == "update" and row["table_name"] == "file" and row["row_id"] == "f1"
    assert row["user_id"] == "u1" and row["project_id"] == "p1"
    assert row["request_id"] == "req-audit-0001"  # picked up from the context
    assert json.loads(row["after"]) == {"a": 1, "b": 2}
    assert row["after"] == '{"a": 1, "b": 2}'  # sorted keys
    assert row["at"].endswith("Z")


def test_write_audit_refuses_to_run_outside_a_write_transaction(db: Database) -> None:
    with db.read_tx() as conn, pytest.raises(RuntimeError, match="write_tx"):
        write_audit(conn, action="create", table_name="file")


def test_pii_mask_hook_is_applied_to_before_and_after(db: Database) -> None:
    audit.set_pii_masker(
        lambda table, data: {k: "[pii]" if k == "national_id" else v for k, v in data.items()}
    )
    try:
        with db.write_tx() as conn:
            write_audit(
                conn,
                action="create",
                table_name="entity",
                after={"national_id": "123", "name": "n"},
            )
    finally:
        audit.set_pii_masker(None)
    with db.read_tx() as conn:
        after = json.loads(conn.execute(text("SELECT after FROM audit_log")).scalar_one())
    assert after == {"national_id": "[pii]", "name": "n"}
