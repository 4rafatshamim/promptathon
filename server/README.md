# BUGS — milestone 1 backend (3 nodes, 2-of-3 replication)

Python + FastAPI file service. Each node stores files on disk and metadata in SQLite. Uploads succeed only when **at least 2 of 3** nodes have a copy.

## Setup (once)

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional shared secret between nodes:

```powershell
$env:PEER_TOKEN = "dev-peer-secret"
```

Use the same value on all three nodes.

## Run three nodes (three terminals)

From `server/` with the venv activated:

**Terminal 1 — node 1**

```powershell
$env:NODE_ID = "1"
$env:DATA_DIR = ".\data\node1"
$env:PEERS = "2@http://127.0.0.1:8002,3@http://127.0.0.1:8003"
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

**Terminal 2 — node 2**

```powershell
$env:NODE_ID = "2"
$env:DATA_DIR = ".\data\node2"
$env:PEERS = "1@http://127.0.0.1:8001,3@http://127.0.0.1:8003"
uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

**Terminal 3 — node 3**

```powershell
$env:NODE_ID = "3"
$env:DATA_DIR = ".\data\node3"
$env:PEERS = "1@http://127.0.0.1:8001,2@http://127.0.0.1:8002"
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload
```

Open API docs: http://127.0.0.1:8001/docs

## Quick demo (curl)

Upload (all nodes up):

```powershell
curl.exe -F "file=@README.md" http://127.0.0.1:8001/files
```

Stop node 3, upload again — response should show `"3": "missing"` and `replication_complete: false`.

Download while node 3 is down:

```powershell
curl.exe -O -J http://127.0.0.1:8002/files/<file-id>
```

Repair third copy (node 3 back online):

```powershell
curl.exe -X POST http://127.0.0.1:8003/files/<file-id>/repair
```

Check / repair corruption:

```powershell
curl.exe -X POST http://127.0.0.1:8001/files/<file-id>/check
curl.exe -X POST http://127.0.0.1:8001/files/<file-id>/repair
```

## Environment reference

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `NODE_ID` | `1` | This node's id (1, 2, or 3) |
| `DATA_DIR` | `./data/node{N}` | Blob storage + SQLite path parent |
| `PEERS` | empty | `id@url` pairs, comma-separated |
| `MIN_REPLICAS` | `2` | Minimum copies required on upload |
| `TARGET_REPLICAS` | `3` | Expected cluster size |
| `PEER_TOKEN` | none | If set, required on `/internal/*` |
| `MAX_UPLOAD_BYTES` | 52428800 | 50 MB cap |
