from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BackgroundJob


class BackgroundJobsRepository:
    """Persistent queue behind the thumbnail / tag-sync background workers.

    Callers wrap operations in a ``session.begin()`` transaction; ``claim``
    uses ``FOR UPDATE SKIP LOCKED`` so concurrent workers (or a future
    multi-process deployment) never hand out the same job twice.
    """

    JOB_THUMB = "thumb"
    JOB_TAG_SYNC = "tag-sync"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(self, job_type: str, gallery_id: int, *, next_attempt_at=None) -> bool:
        """Queue ``gallery_id``; no-op when an identical job is already queued."""
        stmt = (
            pg_insert(BackgroundJob)
            .values(
                job_type=job_type,
                gallery_id=gallery_id,
                status="pending",
                next_attempt_at=next_attempt_at,
            )
            .on_conflict_do_nothing(index_elements=["job_type", "gallery_id"])
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0) > 0

    async def enqueue_many(self, job_type: str, gallery_ids: Sequence[int]) -> int:
        """Batch-queue many galleries; returns how many rows were actually added."""
        if not gallery_ids:
            return 0
        stmt = (
            pg_insert(BackgroundJob)
            .values(
                [
                    {"job_type": job_type, "gallery_id": int(gid), "status": "pending"}
                    for gid in gallery_ids
                ]
            )
            .on_conflict_do_nothing(index_elements=["job_type", "gallery_id"])
        )
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def requeue(
        self,
        job_type: str,
        gallery_id: int,
        *,
        next_attempt_at: datetime | None = None,
        increment_attempts: bool = True,
    ) -> None:
        """Return a claimed job to ``pending`` (retry / hold), bumping attempts."""
        values: dict[str, object] = {
            "status": "pending",
            "lease_until": None,
            "next_attempt_at": next_attempt_at,
            "updated_at": datetime.now(UTC),
        }
        if increment_attempts:
            values["attempts"] = BackgroundJob.attempts + 1
        result = await self.session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.job_type == job_type,
                BackgroundJob.gallery_id == gallery_id,
            )
            .values(**values)
        )
        if int(result.rowcount or 0) == 0:
            # The row was completed (deleted) meanwhile: re-create as pending.
            await self.enqueue(
                job_type,
                gallery_id,
                next_attempt_at=next_attempt_at,
            )

    async def claim(
        self,
        job_type: str,
        limit: int = 1,
        *,
        lease_seconds: int = 600,
        now: datetime | None = None,
    ) -> list[tuple[int, int]]:
        """Claim up to ``limit`` due jobs, returning ``(gallery_id, attempts)``."""
        now = now or datetime.now(UTC)
        dialect = ""
        try:
            bind = self.session.get_bind()
            dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
        except Exception:  # noqa: BLE001
            dialect = ""
        if dialect == "sqlite":
            subquery = (
                select(BackgroundJob.id)
                .where(
                    BackgroundJob.job_type == job_type,
                    BackgroundJob.status == "pending",
                    (BackgroundJob.next_attempt_at.is_(None))
                    | (BackgroundJob.next_attempt_at <= now),
                )
                .order_by(BackgroundJob.id)
                .limit(max(1, limit))
            )
        else:
            subquery = (
                select(BackgroundJob.id)
                .where(
                    BackgroundJob.job_type == job_type,
                    BackgroundJob.status == "pending",
                    (BackgroundJob.next_attempt_at.is_(None))
                    | (BackgroundJob.next_attempt_at <= now),
                )
                .order_by(BackgroundJob.id)
                .with_for_update(skip_locked=True)
                .limit(max(1, limit))
            )
        stmt = (
            update(BackgroundJob)
            .where(BackgroundJob.id.in_(subquery))
            .values(status="claimed", lease_until=now + timedelta(seconds=lease_seconds))
            .returning(BackgroundJob.gallery_id, BackgroundJob.attempts)
        )
        rows = await self.session.execute(stmt)
        return [(int(gallery_id), int(attempts)) for gallery_id, attempts in rows]

    async def complete(self, job_type: str, gallery_id: int) -> None:
        """Drop a finished job so the table stays small."""
        await self.session.execute(
            delete(BackgroundJob).where(
                BackgroundJob.job_type == job_type,
                BackgroundJob.gallery_id == gallery_id,
            )
        )

    async def mark_stale(self, now: datetime | None = None) -> int:
        """Reopen claimed jobs whose lease expired (worker died mid-job)."""
        now = now or datetime.now(UTC)
        result = await self.session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.status == "claimed",
                BackgroundJob.lease_until < now,
            )
            .values(status="pending", lease_until=None)
        )
        return int(result.rowcount or 0)

    async def clear(self, job_type: str) -> int:
        """Drop every queued/claimed job of a type (used by the cancel API)."""
        result = await self.session.execute(
            delete(BackgroundJob).where(BackgroundJob.job_type == job_type)
        )
        return int(result.rowcount or 0)

    async def count(self, job_type: str) -> int:
        """Number of not-yet-started jobs of a type (the UI's ``queued``)."""
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(BackgroundJob)
                .where(
                    BackgroundJob.job_type == job_type,
                    BackgroundJob.status == "pending",
                )
            )
            or 0
        )


