from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_peers(raw: str) -> list[tuple[int, str]]:
    peers: list[tuple[int, str]] = []
    if not raw.strip():
        return peers
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "@" not in part:
            raise ValueError(
                f"Invalid PEERS entry {part!r}; use node_id@base_url (e.g. 2@http://localhost:8002)"
            )
        node_s, url = part.split("@", 1)
        peers.append((int(node_s.strip()), url.strip().rstrip("/")))
    return peers


@dataclass(frozen=True)
class Settings:
    node_id: int
    data_dir: Path
    db_path: Path
    peers: list[tuple[int, str]]
    min_replicas: int
    target_replicas: int
    peer_token: str | None
    max_upload_bytes: int
    peer_timeout_seconds: float

    @property
    def all_node_ids(self) -> list[int]:
        ids = {self.node_id, *(p[0] for p in self.peers)}
        return sorted(ids)

    def peer_url_for(self, node_id: int) -> str | None:
        if node_id == self.node_id:
            return None
        for nid, url in self.peers:
            if nid == node_id:
                return url
        return None


def load_settings() -> Settings:
    node_id = int(os.environ.get("NODE_ID", "1"))
    data_dir = Path(os.environ.get("DATA_DIR", f"./data/node{node_id}")).resolve()
    db_path = Path(os.environ.get("DB_PATH", str(data_dir / "meta.db"))).resolve()
    peers = _parse_peers(os.environ.get("PEERS", ""))
    return Settings(
        node_id=node_id,
        data_dir=data_dir,
        db_path=db_path,
        peers=peers,
        min_replicas=int(os.environ.get("MIN_REPLICAS", "2")),
        target_replicas=int(os.environ.get("TARGET_REPLICAS", "3")),
        peer_token=os.environ.get("PEER_TOKEN") or None,
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))),
        peer_timeout_seconds=float(os.environ.get("PEER_TIMEOUT_SECONDS", "10")),
    )
