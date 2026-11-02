"""파일 저장소 — 로컬 디스크와 S3 호환(MinIO 포함)을 같은 표면으로 가른다.

`STORAGE_BACKEND=s3` 면 boto3 로 업로드한다. 반환 참조는 백엔드마다 다르다 —
로컬은 파일 경로, s3 는 `s3://bucket/key`. 소비처는 그 문자열을 그대로 보관했다가
`download()` 에 되돌려주면 된다.
"""
import os
import shutil

from svkit.loader import conf


class LocalStorage:
    def __init__(self, root: str):
        self._root = root

    def save(self, src_path, key):
        os.makedirs(self._root, exist_ok=True)
        dst = os.path.join(self._root, key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(src_path) != os.path.abspath(dst):
            shutil.move(src_path, dst)
        return dst

    def delete(self, ref):
        if ref and os.path.exists(ref):
            try:
                os.remove(ref)
            except OSError:
                pass

    def download(self, ref, dst):
        if not ref or not os.path.exists(ref):
            return False
        if os.path.abspath(ref) != os.path.abspath(dst):
            shutil.copyfile(ref, dst)
        return True


class S3Storage:
    """S3 호환 저장. 버킷이 없으면 만든다 (MinIO 자동 프로비저닝)."""

    def __init__(self):
        import boto3

        self._bucket = conf.require("S3_BUCKET")
        self._client = boto3.client(
            "s3",
            endpoint_url=conf.get_str("S3_ENDPOINT") or None,
            aws_access_key_id=conf.get_str("S3_ACCESS_KEY"),
            aws_secret_access_key=conf.get_str("S3_SECRET_KEY"),
            region_name=conf.get_str("S3_REGION", "us-east-1"))
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:  # noqa: BLE001 — 없거나 권한이 없거나, 둘 다 생성 시도로 갈린다
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except Exception:  # noqa: BLE001
                pass

    def save(self, src_path, key):
        self._client.upload_file(src_path, self._bucket, key)
        try:
            os.remove(src_path)
        except OSError:
            pass
        return f"s3://{self._bucket}/{key}"

    def delete(self, ref):
        if ref and ref.startswith("s3://"):
            bucket, _, key = ref[len("s3://"):].partition("/")
            self._client.delete_object(Bucket=bucket, Key=key)

    def download(self, ref, dst):
        if not ref or not ref.startswith("s3://"):
            return False
        bucket, _, key = ref[len("s3://"):].partition("/")
        try:
            self._client.download_file(bucket, key, dst)
        except Exception:  # noqa: BLE001 — 없는 키·끊긴 저장소 모두 "못 받았다"로 같다
            return False
        return True


_backend = None


def backend():
    global _backend
    if _backend is None:
        if conf.get_str("STORAGE_BACKEND", "local").lower() == "s3":
            _backend = S3Storage()
        else:
            _backend = LocalStorage(conf.require("STORAGE_LOCAL_DIR"))
    return _backend


def save(src_path, key):
    """완성 파일을 저장소로 옮기고 참조를 돌려준다 (원본은 사라진다)."""
    return backend().save(src_path, key)


def delete(ref):
    backend().delete(ref)


def download(ref, dst):
    """저장된 파일을 로컬 경로로 가져온다. 반환: 성공 여부."""
    return backend().download(ref, dst)
