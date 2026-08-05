"""공통 스토리지 — 로컬 디스크/S3 호환(MinIO 포함) 스위칭.

기본 local(디스크). STORAGE_BACKEND=s3 로 전환하면 boto3 로 S3 호환 저장소에
업로드한다(추가 코드 수정 없이 env 만으로 스위칭).

**구현은 `base` 의 백엔드 클래스 그대로**다 — 파일 이동/업로드는 프레임워크와
무관한 블로킹 I/O 라 두 판이 나눌 수 있는 자리다. svkit2 는 같은 클래스를
스레드풀에서 호출한다(그쪽 `save`/`delete` 는 async).

env: STORAGE_BACKEND(local|s3), DOWNLOAD_DIR,
     S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION
반환 참조: local → 파일 경로, s3 → s3://bucket/key
"""
import os

from svkit.base import BaseLocalStorage, BaseS3Storage

STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'local').lower()
DOWNLOAD_DIR = os.environ.get('DOWNLOAD_DIR', '/app/data/files')

#: svkit2 와 이름을 맞춘 별칭
BACKEND = STORAGE_BACKEND


class LocalStorage(BaseLocalStorage):
    """로컬 디스크 저장. save 반환값 = 로컬 경로"""

    def __init__(self):
        super().__init__(DOWNLOAD_DIR)


class S3Storage(BaseS3Storage):
    """S3 호환 저장(MinIO 등). save 반환값 = s3://bucket/key. 활성화 시 boto3 필요."""


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


__all__ = ['STORAGE_BACKEND', 'BACKEND', 'DOWNLOAD_DIR',
           'LocalStorage', 'S3Storage', 'backend', 'save', 'delete']