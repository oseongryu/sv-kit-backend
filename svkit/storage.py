"""공통 스토리지 — 로컬 디스크/S3 호환(MinIO 포함) 스위칭.

기본 local(디스크). STORAGE_BACKEND=s3 로 전환하면 boto3 로 S3 호환 저장소에
업로드한다(추가 코드 수정 없이 env 만으로 스위칭).

env: STORAGE_BACKEND(local|s3), DOWNLOAD_DIR,
     S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION
반환 참조: local → 파일 경로, s3 → s3://bucket/key
"""
import os
import shutil

STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'local').lower()
DOWNLOAD_DIR = os.environ.get('DOWNLOAD_DIR', '/app/data/files')


class LocalStorage:
    """로컬 디스크 저장. save 반환값 = 로컬 경로"""

    def save(self, src_path, key):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        dst = os.path.join(DOWNLOAD_DIR, key)
        if os.path.abspath(src_path) != os.path.abspath(dst):
            shutil.move(src_path, dst)
        return dst

    def delete(self, ref):
        if ref and os.path.exists(ref):
            try:
                os.remove(ref)
            except OSError:
                pass


class S3Storage:
    """S3 호환 저장(MinIO 등). save 반환값 = s3://bucket/key. 활성화 시 boto3 필요."""

    def __init__(self):
        import boto3
        self._bucket = os.environ['S3_BUCKET']
        self._client = boto3.client(
            's3',
            endpoint_url=os.environ.get('S3_ENDPOINT') or None,
            aws_access_key_id=os.environ.get('S3_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('S3_SECRET_KEY'),
            region_name=os.environ.get('S3_REGION', 'us-east-1'))
        self._ensure_bucket()

    def _ensure_bucket(self):
        """버킷 없으면 생성(MinIO 자동 프로비저닝)"""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except Exception:
                pass

    def save(self, src_path, key):
        self._client.upload_file(src_path, self._bucket, key)
        try:
            os.remove(src_path)
        except OSError:
            pass
        return f's3://{self._bucket}/{key}'

    def delete(self, ref):
        if ref and ref.startswith('s3://'):
            _, _, rest = ref.partition('s3://')
            bucket, _, key = rest.partition('/')
            self._client.delete_object(Bucket=bucket, Key=key)


_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = S3Storage() if STORAGE_BACKEND == 's3' else LocalStorage()
    return _backend


def save(src_path, key):
    """완성 파일을 저장소로 이동/업로드하고 참조(경로/URI) 반환"""
    return backend().save(src_path, key)


def delete(ref):
    backend().delete(ref)
