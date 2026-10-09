import os
import time
import mimetypes
from pathlib import Path
import requests

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "inspectai"

# Local development only: STORAGE_BACKEND=local keeps objects on disk instead of Emergent Object Storage.
LOCAL_MODE = (os.environ.get("STORAGE_BACKEND") or "").strip().lower() == "local"
LOCAL_STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR") or Path(__file__).parent / "local_storage").resolve()

# STORAGE_BACKEND=s3 keeps objects in any S3-compatible bucket (AWS S3, Cloudflare R2, ...).
S3_MODE = (os.environ.get("STORAGE_BACKEND") or "").strip().lower() == "s3"
S3_BUCKET = (os.environ.get("S3_BUCKET") or "").strip()

_storage_key = None
_s3_client = None


def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        from botocore.config import Config
        _s3_client = boto3.client(
            "s3",
            endpoint_url=(os.environ.get("S3_ENDPOINT_URL") or "").strip() or None,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
            region_name=(os.environ.get("S3_REGION") or "auto").strip(),
            config=Config(retries={"max_attempts": 5, "mode": "standard"}),
        )
    return _s3_client


def _local_path(path: str) -> Path:
    """Resolve a logical object path under LOCAL_STORAGE_DIR, rejecting anything that escapes it."""
    full = (LOCAL_STORAGE_DIR / path).resolve()
    if not full.is_relative_to(LOCAL_STORAGE_DIR) or full == LOCAL_STORAGE_DIR:
        raise ValueError(f"invalid storage path: {path!r}")
    return full


def init_storage(force: bool = False):
    global _storage_key
    if LOCAL_MODE:
        LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return str(LOCAL_STORAGE_DIR)
    if S3_MODE:
        if not S3_BUCKET:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET")
        _s3().head_bucket(Bucket=S3_BUCKET)
        return S3_BUCKET
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _request_with_retry(method: str, path: str, **kwargs):
    """5xx -> exponential backoff retry; 404 -> force a fresh storage key once."""
    last = None
    for attempt in range(4):
        key = init_storage(force=(attempt == 1 and last == 404))
        headers = kwargs.pop("_headers", {})
        resp = requests.request(
            method, f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, **headers}, **kwargs,
        )
        if resp.status_code < 500 and resp.status_code != 404:
            resp.raise_for_status()
            return resp
        last = resp.status_code
        if resp.status_code == 404 and attempt >= 1:
            resp.raise_for_status()
        if resp.status_code >= 500:
            time.sleep(0.6 * (2 ** attempt))
    resp.raise_for_status()
    return resp


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if LOCAL_MODE:
        full = _local_path(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return {"path": path, "size": len(data), "content_type": content_type}
    if S3_MODE:
        _s3().put_object(Bucket=S3_BUCKET, Key=path, Body=data, ContentType=content_type)
        return {"path": path, "size": len(data), "content_type": content_type}
    resp = _request_with_retry("PUT", path, data=data, timeout=180,
                               _headers={"Content-Type": content_type})
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    if LOCAL_MODE:
        full = _local_path(path)
        if not full.is_file():
            raise FileNotFoundError(f"object not found in local storage: {path}")
        return full.read_bytes(), mimetypes.guess_type(full.name)[0] or "application/octet-stream"
    if S3_MODE:
        obj = _s3().get_object(Bucket=S3_BUCKET, Key=path)
        return obj["Body"].read(), obj.get("ContentType") or "application/octet-stream"
    resp = _request_with_retry("GET", path, timeout=120)
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
