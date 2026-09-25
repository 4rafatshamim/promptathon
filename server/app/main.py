from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app import replication as repl
from app.checksum import sha256_bytes, sha256_file
from app.config import Settings, load_settings
from app.db import init_db
from app.models import FileRecord
from app.peers import (
    fetch_file_from_peer,
    find_meta_on_peers,
    replicate_to_peer,
    replica_map_to_json,
)
from app.storage import blob_path, delete_blob, read_blob, write_blob

settings = load_settings()
SessionLocal = init_db(settings)

app = FastAPI(title=f"BUGS node {settings.node_id}", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_peer_token(x_peer_token: str | None = Header(default=None)) -> None:
    if settings.peer_token and x_peer_token != settings.peer_token:
        raise HTTPException(status_code=403, detail="Invalid peer token")


def record_to_meta(record: FileRecord) -> dict:
    fields = repl.build_response_fields(settings, record.get_replica_map())
    return {
        "id": record.id,
        "original_filename": record.original_filename,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "local_status": record.local_status,
        **fields,
        "last_checked_at": record.last_checked_at.isoformat() if record.last_checked_at else None,
    }


async def push_to_all_peers(
    *,
    file_id: str,
    sha256: str,
    original_filename: str,
    data: bytes,
    replica_map: dict[str, str],
) -> dict[str, str]:
    updated = dict(replica_map)
    complete = repl.replication_complete(settings, updated)

    async def one(peer_node_id: int, peer_url: str) -> tuple[int, bool]:
        ok = await replicate_to_peer(
            settings,
            peer_node_id,
            peer_url,
            file_id=file_id,
            sha256=sha256,
            original_filename=original_filename,
            data=data,
            replica_map_json=replica_map_to_json(updated),
            replication_complete=complete,
        )
        return peer_node_id, ok

    tasks = [one(nid, url) for nid, url in settings.peers]
    if tasks:
        results = await asyncio.gather(*tasks)
        for peer_node_id, ok in results:
            updated[str(peer_node_id)] = repl.REPLICA_OK if ok else repl.REPLICA_MISSING
    return updated


def find_peer_with_ok_copy(replica_map: dict[str, str], exclude_node: int | None = None) -> int | None:
    for nid_s, status in replica_map.items():
        nid = int(nid_s)
        if exclude_node is not None and nid == exclude_node:
            continue
        if status == repl.REPLICA_OK and settings.peer_url_for(nid):
            return nid
    for nid_s, status in replica_map.items():
        if status == repl.REPLICA_OK and int(nid_s) != settings.node_id:
            return int(nid_s)
    return None


@app.get("/health")
def health():
    return {"node_id": settings.node_id, "ok": True}


@app.post("/files", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    digest = sha256_bytes(data)
    file_id = str(uuid.uuid4())
    filename = file.filename or "upload.bin"

    write_blob(settings.data_dir, file_id, data)

    replica_map = repl.empty_replica_map(settings)
    replica_map[str(settings.node_id)] = repl.REPLICA_OK

    replica_map = await push_to_all_peers(
        file_id=file_id,
        sha256=digest,
        original_filename=filename,
        data=data,
        replica_map=replica_map,
    )

    ok_count = repl.count_ok(replica_map)
    if ok_count < settings.min_replicas:
        delete_blob(settings.data_dir, file_id)
        raise HTTPException(
            status_code=507,
            detail={
                "message": f"Upload rejected: only {ok_count} replica(s) stored; need at least {settings.min_replicas} of {settings.target_replicas}.",
                **repl.build_response_fields(settings, replica_map),
            },
        )

    complete = repl.replication_complete(settings, replica_map)
    record = FileRecord(
        id=file_id,
        original_filename=filename,
        sha256=digest,
        size_bytes=len(data),
        local_status=repl.REPLICA_OK,
        replication_complete=complete,
    )
    record.set_replica_map(replica_map)
    db.add(record)
    db.commit()

    return {
        "id": file_id,
        "sha256": digest,
        "size_bytes": len(data),
        **repl.build_response_fields(settings, replica_map),
    }


@app.get("/files/{file_id}")
async def get_file(file_id: str, db: Session = Depends(get_db)):
    record = db.get(FileRecord, file_id)
    data = read_blob(settings.data_dir, file_id)
    if data is not None and record and record.local_status == repl.REPLICA_OK:
        path = blob_path(settings.data_dir, file_id)
        if sha256_file(path) == record.sha256:
            return StreamingResponse(
                iter([data]),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{record.original_filename}"'},
            )

    replica_map = record.get_replica_map() if record else {}
    if not replica_map:
        raise HTTPException(status_code=404, detail="File not found")

    for nid in settings.all_node_ids:
        if nid == settings.node_id:
            continue
        if replica_map.get(str(nid)) != repl.REPLICA_OK:
            continue
        url = settings.peer_url_for(nid)
        if not url:
            continue
        peer_data = await fetch_file_from_peer(settings, url, file_id)
        if peer_data is None:
            continue
        name = record.original_filename if record else f"{file_id}.bin"
        return StreamingResponse(
            iter([peer_data]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    raise HTTPException(status_code=404, detail="No readable replica available")


@app.get("/files/{file_id}/meta")
def get_meta(file_id: str, db: Session = Depends(get_db)):
    record = db.get(FileRecord, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return record_to_meta(record)


@app.post("/files/{file_id}/check")
def check_file(file_id: str, db: Session = Depends(get_db)):
    record = db.get(FileRecord, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    path = blob_path(settings.data_dir, file_id)
    if not path.is_file():
        record.local_status = repl.REPLICA_MISSING
        db.commit()
        return {
            "ok": False,
            "expected": record.sha256,
            "actual": None,
            "local_status": record.local_status,
        }

    actual = sha256_file(path)
    ok = actual == record.sha256
    record.local_status = repl.REPLICA_OK if ok else repl.REPLICA_CORRUPT
    record.last_checked_at = datetime.now(timezone.utc)
    replica_map = record.get_replica_map()
    replica_map[str(settings.node_id)] = record.local_status
    record.set_replica_map(replica_map)
    db.commit()

    return {
        "ok": ok,
        "expected": record.sha256,
        "actual": actual,
        "local_status": record.local_status,
    }


@app.post("/files/{file_id}/repair")
async def repair_file(file_id: str, db: Session = Depends(get_db)):
    record = db.get(FileRecord, file_id)
    if not record:
        meta = await find_meta_on_peers(settings, file_id)
        if not meta:
            raise HTTPException(status_code=404, detail="File not found on this node or peers")
        record = FileRecord(
            id=file_id,
            original_filename=meta["original_filename"],
            sha256=meta["sha256"],
            size_bytes=meta["size_bytes"],
            local_status=repl.REPLICA_MISSING,
            replication_complete=bool(meta.get("replication_complete", False)),
        )
        record.set_replica_map(meta.get("replicas", {}))
        db.add(record)
        db.flush()

    replica_map = record.get_replica_map()
    local = replica_map.get(str(settings.node_id), repl.REPLICA_MISSING)
    needs_repair = local != repl.REPLICA_OK

    if not needs_repair:
        path = blob_path(settings.data_dir, file_id)
        if path.is_file() and sha256_file(path) == record.sha256:
            return {"repaired": False, "message": "Local copy already ok", **record_to_meta(record)}

    source_node = find_peer_with_ok_copy(replica_map, exclude_node=settings.node_id)
    if source_node is None:
        raise HTTPException(status_code=503, detail="No peer with a good copy available")

    url = settings.peer_url_for(source_node)
    if not url:
        raise HTTPException(status_code=503, detail="Peer URL not configured for source node")

    data = await fetch_file_from_peer(settings, url, file_id)
    if data is None or sha256_bytes(data) != record.sha256:
        raise HTTPException(status_code=503, detail="Failed to fetch valid copy from peer")

    write_blob(settings.data_dir, file_id, data)
    record.local_status = repl.REPLICA_OK
    replica_map[str(settings.node_id)] = repl.REPLICA_OK
    record.set_replica_map(replica_map)
    record.replication_complete = repl.replication_complete(settings, replica_map)
    record.last_checked_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "repaired": True,
        "source_node": source_node,
        **record_to_meta(record),
    }


@app.post("/internal/files")
async def internal_replicate(
    _: None = Depends(verify_peer_token),
    file_id: str = Form(...),
    sha256: str = Form(...),
    original_filename: str = Form(...),
    replica_map_json: str = Form(...),
    replication_complete: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = await file.read()
    if sha256_bytes(data) != sha256:
        raise HTTPException(status_code=400, detail="Checksum mismatch")

    write_blob(settings.data_dir, file_id, data)
    complete = replication_complete.lower() == "true"

    record = db.get(FileRecord, file_id)
    if record is None:
        record = FileRecord(
            id=file_id,
            original_filename=original_filename,
            sha256=sha256,
            size_bytes=len(data),
            local_status=repl.REPLICA_OK,
            replication_complete=complete,
        )
        db.add(record)
    else:
        record.original_filename = original_filename
        record.sha256 = sha256
        record.size_bytes = len(data)
        record.local_status = repl.REPLICA_OK
        record.replication_complete = complete

    try:
        raw = json.loads(replica_map_json)
        replica_map = {str(k): str(v) for k, v in raw.items()}
    except json.JSONDecodeError:
        replica_map = repl.empty_replica_map(settings)
        replica_map[str(settings.node_id)] = repl.REPLICA_OK

    replica_map[str(settings.node_id)] = repl.REPLICA_OK
    record.set_replica_map(replica_map)
    record.replication_complete = repl.replication_complete(settings, replica_map)
    db.commit()
    return {"stored": True, "node_id": settings.node_id}


@app.get("/internal/files/{file_id}")
def internal_get_file(
    file_id: str,
    _: None = Depends(verify_peer_token),
    db: Session = Depends(get_db),
):
    record = db.get(FileRecord, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    data = read_blob(settings.data_dir, file_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Blob missing")
    path = blob_path(settings.data_dir, file_id)
    if sha256_file(path) != record.sha256:
        raise HTTPException(status_code=404, detail="Corrupt local copy")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{record.original_filename}"'},
    )
