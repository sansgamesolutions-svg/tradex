from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from tradex.storage.base import Storage


class S3Storage(Storage):
    """S3-compatible object storage backend.

    Works with AWS S3, Google Cloud Storage (interop), Azure Blob (interop),
    and MinIO by setting *endpoint_url* to the service address.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "tradex",
        endpoint_url: str | None = None,
    ):
        self._s3 = boto3.client("s3", endpoint_url=endpoint_url or None)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}"

    def get(self, key: str) -> bytes | None:
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=self._key(key))
            return resp["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    def put(self, key: str, data: bytes) -> None:
        self._s3.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError:
            return False
