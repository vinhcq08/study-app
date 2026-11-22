"""Download and restore a backup of everything you've recorded."""

import sqlite3

from fastapi import APIRouter, HTTPException, Request

from .. import backup, db

router = APIRouter(prefix="/api")


@router.get("/backup")
def download_backup():
    with db.connect() as conn:
        return backup.export(conn)


@router.post("/backup")
async def restore_backup(request: Request):
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(422, "This file isn't valid JSON.")
    conn = db.connect()
    try:
        with conn:  # one transaction: if anything fails, nothing changes
            counts = backup.restore(conn, data)
    except backup.BackupError as e:
        raise HTTPException(422, str(e))
    except sqlite3.Error as e:
        raise HTTPException(422, f"Couldn't restore the backup: {e}")
    finally:
        conn.close()
    return {"restored": counts}
