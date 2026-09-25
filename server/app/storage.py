from pathlib import Path


def blob_path(data_dir: Path, file_id: str) -> Path:
    return data_dir / "blobs" / file_id


def write_blob(data_dir: Path, file_id: str, data: bytes) -> Path:
    path = blob_path(data_dir, file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def read_blob(data_dir: Path, file_id: str) -> bytes | None:
    path = blob_path(data_dir, file_id)
    if not path.is_file():
        return None
    return path.read_bytes()


def delete_blob(data_dir: Path, file_id: str) -> None:
    path = blob_path(data_dir, file_id)
    if path.is_file():
        path.unlink()
