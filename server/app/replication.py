from __future__ import annotations

from app.config import Settings

REPLICA_OK = "ok"
REPLICA_MISSING = "missing"
REPLICA_CORRUPT = "corrupt"


def empty_replica_map(settings: Settings) -> dict[str, str]:
    return {str(nid): REPLICA_MISSING for nid in settings.all_node_ids}


def count_ok(replica_map: dict[str, str]) -> int:
    return sum(1 for v in replica_map.values() if v == REPLICA_OK)


def pending_repair_nodes(replica_map: dict[str, str]) -> list[int]:
    return sorted(int(nid) for nid, status in replica_map.items() if status != REPLICA_OK)


def replication_complete(settings: Settings, replica_map: dict[str, str]) -> bool:
    return all(replica_map.get(str(nid)) == REPLICA_OK for nid in settings.all_node_ids)


def build_response_fields(settings: Settings, replica_map: dict[str, str]) -> dict:
    return {
        "replicas": replica_map,
        "replication_complete": replication_complete(settings, replica_map),
        "pending_repair_nodes": pending_repair_nodes(replica_map),
    }
