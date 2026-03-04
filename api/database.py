import asyncpg
import structlog
import os


logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host="db",
            port=5432,
            user="postgres",
            password=os.environ.get("POSTGRES_PASSWORD", "ChangeMe_DB_P@ssword!"),
            database="postgres",
            min_size=2,
            max_size=10,
        )
        logger.info("db_pool_created")
    return _pool


async def insert_file_metadata(file_id: str, user_email: str, filename: str, bucket_name: str, object_name: str, size_bytes: int, mime_type: str, sha256: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.file_metadata
                (id, user_email, filename, bucket_name, object_name, size_bytes, mime_type, sha256)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            file_id, user_email, filename, bucket_name, object_name, size_bytes, mime_type, sha256
        )
    logger.info("metadata_inserted", file_id=file_id, user=user_email)


async def list_user_files(user_email: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, filename, size_bytes, mime_type, sha256, uploaded_at
            FROM public.file_metadata
            WHERE user_email = $1 AND deleted_at IS NULL
            ORDER BY uploaded_at DESC
            """,
            user_email
        )
    return [dict(row) for row in rows]


async def delete_file_metadata(file_id: str, user_email: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE public.file_metadata
            SET deleted_at = NOW()
            WHERE id = $1 AND user_email = $2
            """,
            file_id, user_email
        )
    return result == "UPDATE 1"