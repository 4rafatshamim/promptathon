from __future__ import annotations

import json
import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


def _peer_headers(settings: Settings) -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.peer_token:
        headers["X-Peer-Token"] = settings.peer_token
    return headers


async def replicate_to_peer(
    settings: Settings,
    peer_node_id: int,
    peer_url: str,
    *,
    file_id: str,
    sha256: str,
    original_filename: str,
    data: bytes,
    replica_map_json: str,
    replication_complete: bool,
) -> bool:
    url = f"{peer_url}/internal/files"
    files = {"file": (original_filename, data)}
    form = {
        "file_id": file_id,
        "sha256": sha256,
        "original_filename": original_filename,
        "replica_map_json": replica_map_json,
        "replication_complete": "true" if replication_complete else "false",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.peer_timeout_seconds) as client:
            resp = await client.post(
                url, data=form, files=files, headers=_peer_headers(settings)
            )
            if resp.status_code >= 400:
                logger.warning("Peer %s replicate failed: %s %s", peer_node_id, resp.status_code, resp.text)
                return False
            return True
    except httpx.HTTPError as exc:
        logger.warning("Peer %s unreachable: %s", peer_node_id, exc)
        return False


async def fetch_file_from_peer(settings: Settings, peer_url: str, file_id: str) -> bytes | None:
    url = f"{peer_url}/internal/files/{file_id}"
    try:
        async with httpx.AsyncClient(timeout=settings.peer_timeout_seconds) as client:
            resp = await client.get(url, headers=_peer_headers(settings))
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as exc:
        logger.warning("Peer fetch failed %s: %s", url, exc)
        return None


async def fetch_meta_from_peer(settings: Settings, peer_url: str, file_id: str) -> dict | None:
    url = f"{peer_url}/files/{file_id}/meta"
    try:
        async with httpx.AsyncClient(timeout=settings.peer_timeout_seconds) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return None


async def find_meta_on_peers(settings: Settings, file_id: str) -> dict | None:
    for _nid, url in settings.peers:
        meta = await fetch_meta_from_peer(settings, url, file_id)
        if meta:
            return meta
    return None


def replica_map_to_json(replica_map: dict[str, str]) -> str:
    return json.dumps(replica_map, sort_keys=True)
