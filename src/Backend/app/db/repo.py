"""Repository-Funktionen. Rückgabe sind dicts, die API validiert sie über ihre Pydantic-Modelle."""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from app.db.database import Database
from app.errors import ConflictError, NotFoundError
from app.schemas.devices import slugify


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _one(row: sqlite3.Row | None, what: str) -> dict[str, Any]:
    if row is None:
        raise NotFoundError(f"{what} nicht gefunden")
    return dict(row)


# --- Skills ------------------------------------------------------------------

SKILL_FIELDS = ("name", "description", "status", "fine_tuned_model")


def list_skills(db: Database) -> list[dict[str, Any]]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM skills ORDER BY id")]


def get_skill(db: Database, skill_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        return _one(conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone(), f"Skill {skill_id}")


def create_skill(db: Database, data: dict[str, Any]) -> dict[str, Any]:
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO skills (name, description, status, fine_tuned_model, created_at) VALUES (?, ?, ?, ?, ?)",
                (*(data[f] for f in SKILL_FIELDS), now()),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"Skill '{data['name']}' existiert bereits") from exc
    return get_skill(db, int(cur.lastrowid or 0))


def update_skill(db: Database, skill_id: int, data: dict[str, Any]) -> dict[str, Any]:
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "UPDATE skills SET name = ?, description = ?, status = ?, fine_tuned_model = ? WHERE id = ?",
                (*(data[f] for f in SKILL_FIELDS), skill_id),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"Skill '{data['name']}' existiert bereits") from exc
    if cur.rowcount == 0:
        raise NotFoundError(f"Skill {skill_id} nicht gefunden")
    return get_skill(db, skill_id)


def delete_skill(db: Database, skill_id: int) -> None:
    with db.connect() as conn:
        if conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,)).rowcount == 0:
            raise NotFoundError(f"Skill {skill_id} nicht gefunden")


# --- Workflows ---------------------------------------------------------------


def _workflow(row: sqlite3.Row | None, workflow_id: int) -> dict[str, Any]:
    data = _one(row, f"Workflow {workflow_id}")
    data["definition"] = json.loads(data["definition"])
    return data


def list_workflows(db: Database) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT id, name, created_at, updated_at FROM workflows ORDER BY updated_at DESC, id DESC")
        return [dict(r) for r in rows]


def get_workflow(db: Database, workflow_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        return _workflow(conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone(), workflow_id)


def create_workflow(db: Database, name: str, definition: dict[str, Any]) -> dict[str, Any]:
    ts = now()
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO workflows (name, definition, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, json.dumps(definition), ts, ts),
        )
    return get_workflow(db, int(cur.lastrowid or 0))


def update_workflow(db: Database, workflow_id: int, name: str, definition: dict[str, Any]) -> dict[str, Any]:
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE workflows SET name = ?, definition = ?, updated_at = ? WHERE id = ?",
            (name, json.dumps(definition), now(), workflow_id),
        )
    if cur.rowcount == 0:
        raise NotFoundError(f"Workflow {workflow_id} nicht gefunden")
    return get_workflow(db, workflow_id)


def delete_workflow(db: Database, workflow_id: int) -> None:
    """Löscht den Workflow; seine Läufe bleiben erhalten (runs.workflow_id wird NULL)."""
    with db.connect() as conn:
        if conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,)).rowcount == 0:
            raise NotFoundError(f"Workflow {workflow_id} nicht gefunden")


# --- Geräte ------------------------------------------------------------------

DEVICE_USING_BLOCKS = {"wait_sensor", "condition", "set_actuator"}


def _device(row: sqlite3.Row | None, device_id: str) -> dict[str, Any]:
    data = _one(row, f"Gerät '{device_id}'")
    data["config"] = json.loads(data["config"])
    return data


def _device_values(data: dict[str, Any]) -> tuple[Any, ...]:
    config = data["config"]
    return (data["name"], data["type"], config["protocol"], json.dumps(config), data["unit"], data["min"], data["max"])


def list_devices(db: Database) -> list[dict[str, Any]]:
    with db.connect() as conn:
        return [_device(r, r["id"]) for r in conn.execute("SELECT * FROM devices ORDER BY created_at, rowid")]


def get_device(db: Database, device_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        return _device(conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone(), device_id)


def _insert_device(conn: sqlite3.Connection, device_id: str, data: dict[str, Any]) -> None:
    ts = now()
    conn.execute(
        "INSERT INTO devices (id, name, type, protocol, config, unit, min, max, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (device_id, *_device_values(data), ts, ts),
    )


def create_device(db: Database, data: dict[str, Any]) -> dict[str, Any]:
    """Legt ein Gerät an; die ID wird aus dem Namen gebildet (bei Kollision -2, -3 …) und bleibt danach fest."""
    base = slugify(data["name"])
    with db.connect() as conn:
        taken = {r["id"] for r in conn.execute("SELECT id FROM devices WHERE id = ? OR id LIKE ?", (base, f"{base}-%"))}
        device_id, n = base, 1
        while device_id in taken:
            n += 1
            device_id = f"{base}-{n}"
        _insert_device(conn, device_id, data)
    return get_device(db, device_id)


def update_device(db: Database, device_id: str, data: dict[str, Any]) -> dict[str, Any]:
    with db.connect() as conn:
        cur = conn.execute(
            "UPDATE devices SET name = ?, type = ?, protocol = ?, config = ?, unit = ?, min = ?, max = ?,"
            " updated_at = ?"
            " WHERE id = ?",
            (*_device_values(data), now(), device_id),
        )
    if cur.rowcount == 0:
        raise NotFoundError(f"Gerät '{device_id}' nicht gefunden")
    return get_device(db, device_id)


def delete_device(db: Database, device_id: str) -> None:
    with db.connect() as conn:
        if conn.execute("DELETE FROM devices WHERE id = ?", (device_id,)).rowcount == 0:
            raise NotFoundError(f"Gerät '{device_id}' nicht gefunden")


def seed_devices(db: Database, devices: Iterable[dict[str, Any]]) -> None:
    """Startbestand nur in eine leere Tabelle schreiben (gelöschte Geräte kommen nicht zurück)."""
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM devices LIMIT 1").fetchone() is not None:
            return
        for data in devices:
            _insert_device(conn, data["id"], data)


def workflows_using_device(db: Database, device_id: str) -> list[dict[str, Any]]:
    """Gespeicherte Workflows, deren Sensor-/Aktor-Blöcke auf das Gerät verweisen."""
    using = []
    with db.connect() as conn:
        for row in conn.execute("SELECT id, name, definition FROM workflows ORDER BY id"):
            blocks = json.loads(row["definition"]).get("blocks", [])
            if any(
                b.get("type") in DEVICE_USING_BLOCKS and (b.get("params") or {}).get("device") == device_id
                for b in blocks
            ):
                using.append({"id": row["id"], "name": row["name"]})
    return using


# --- Läufe und Protokoll -----------------------------------------------------


def create_run(db: Database, workflow_id: int | None, api_mode: str, credits_estimate: int) -> int:
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (workflow_id, status, api_mode, started_at, credits_estimate) VALUES (?, ?, ?, ?, ?)",
            (workflow_id, "running", api_mode, now(), credits_estimate),
        )
    return int(cur.lastrowid or 0)


def get_run(db: Database, run_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        return _one(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone(), f"Lauf {run_id}")


def list_runs(db: Database, limit: int = 50) -> list[dict[str, Any]]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]


def set_run_status(db: Database, run_id: int, status: str) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))


def finish_run(db: Database, run_id: int, status: str, error: str | None) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, error = ?, finished_at = ? WHERE id = ?", (status, error, now(), run_id)
        )


def add_credits(db: Database, run_id: int, amount: int) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE runs SET credits_used = credits_used + ? WHERE id = ?", (amount, run_id))


def fail_open_runs(db: Database) -> None:
    """Nach einem Neustart sind Läufe ohne Ende verwaist."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE runs SET status = 'failed', error = 'Backend neu gestartet', finished_at = ? "
            "WHERE status IN ('running', 'paused')",
            (now(),),
        )


def add_log(
    db: Database,
    run_id: int,
    message: str,
    *,
    level: str = "info",
    block_id: str | None = None,
    api_status: str | None = None,
    duration_ms: float | None = None,
) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO run_log (run_id, timestamp, level, block_id, api_status, duration_ms, message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                now(),
                level,
                block_id,
                api_status,
                round(duration_ms, 1) if duration_ms is not None else None,
                message,
            ),
        )


def get_log(db: Database, run_id: int, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, level, block_id, api_status, duration_ms, message FROM run_log "
            "WHERE run_id = ? AND id > ? ORDER BY id LIMIT ?",
            (run_id, after, limit),
        )
        return [dict(r) for r in rows]
