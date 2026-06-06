from __future__ import annotations

from functools import lru_cache

from tradex.storage.base import Storage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    from tradex.config.settings import settings

    if settings.storage_backend == "s3":
        from tradex.storage.s3 import S3Storage

        return S3Storage(
            bucket=settings.s3_bucket,
            prefix=settings.s3_prefix,
            endpoint_url=settings.s3_endpoint_url or None,
        )

    from tradex.storage.local import LocalStorage

    # Base dir is the project root; keys are like "data/cache/BTC_1d.parquet"
    return LocalStorage(base_dir=settings.cache_dir.parent.parent)


def reset_storage() -> None:
    """Clear the cached storage instance (used in tests)."""
    get_storage.cache_clear()
