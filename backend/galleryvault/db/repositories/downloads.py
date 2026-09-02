from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DownloadAttempt, DownloadTask


class DownloadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        gid: int,
        token: str,
        title: str | None = None,
        mode: str | None = None,
        max_pages: int | None = None,
        quality: str | None = None,
        title_jpn: str | None = None,
    ) -> DownloadTask | None:
        active = await self.session.scalar(
            select(DownloadTask).where(
                DownloadTask.gid == gid, DownloadTask.status.in_(["pending", "downloading"])
            )
        )
        if active:
            return None
        task = DownloadTask(
            gid=gid,
            token=token,
            title=title,
            title_jpn=title_jpn,
            mode=mode,
            status="pending",
            retry_count=0,
            max_retries=10,
            max_pages=max_pages,
            quality=quality,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def retarget(
        self,
        task_id: int,
        new_gid: int,
        new_token: str,
        title: str | None = None,
        title_jpn: str | None = None,
    ) -> bool:
        """Point an active task at a newer gid/token. False if the new gid is already queued."""
        row = await self.session.get(DownloadTask, task_id)
        if row is None:
            return False
        active = await self.session.scalar(
            select(DownloadTask).where(
                DownloadTask.gid == new_gid,
                DownloadTask.status.in_(["pending", "downloading"]),
                DownloadTask.id != task_id,
            )
        )
        if active is not None:
            row.status = "cancelled"
            row.error_message = f"newer version {new_gid} already queued"
            row.updated_at = datetime.now(UTC)
            return False
        row.gid = new_gid
        row.token = new_token
        if title:
            row.title = title
        if title_jpn:
            row.title_jpn = title_jpn
        row.updated_at = datetime.now(UTC)
        return True

    async def recover_orphans(self) -> int:
        result = await self.session.execute(
            update(DownloadTask)
            .where(DownloadTask.status == "downloading")
            .values(status="pending", updated_at=datetime.now(UTC))
        )
        return int(result.rowcount or 0)

    async def claim_pending(self) -> DownloadTask | None:
        now = datetime.now(UTC)
        # SKIP LOCKED is not supported on SQLite (tests) — omit locking there to avoid
        # silent duplication or errors.
        dialect = ""
        try:
            bind = self.session.get_bind()
            dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
        except Exception:  # noqa: BLE001
            dialect = ""
        if dialect == "sqlite":
            stmt = (
                select(DownloadTask)
                .where(
                    DownloadTask.status == "pending",
                    DownloadTask.retry_count < DownloadTask.max_retries,
                    (DownloadTask.retry_at.is_(None)) | (DownloadTask.retry_at <= now),
                )
                .order_by(DownloadTask.id)
                .limit(1)
            )
        else:
            stmt = (
                select(DownloadTask)
                .where(
                    DownloadTask.status == "pending",
                    DownloadTask.retry_count < DownloadTask.max_retries,
                    (DownloadTask.retry_at.is_(None)) | (DownloadTask.retry_at <= now),
                )
                .order_by(DownloadTask.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        row = await self.session.scalar(stmt)
        if row is not None:
            row.status = "downloading"
            row.started_at = datetime.now(UTC)
            row.updated_at = row.started_at
        return row

    async def rearm_failed(self) -> int:
        """Requeue failed tasks that still have retry budget left.

        Called by the periodic sweep so a download that exhausted its immediate
        attempts is tried again later instead of waiting for a manual retry.
        """
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(DownloadTask)
            .where(
                DownloadTask.status == "failed",
                DownloadTask.retry_count < DownloadTask.max_retries,
            )
            .values(status="pending", retry_at=now, updated_at=now)
        )
        return int(result.rowcount or 0)

    async def sweep_auto_retry(self) -> int:
        """Alias for the retry sweep expected by download_worker_loop.

        The worker imports ``sweep_auto_retry``; keep it as a thin wrapper
        over ``rearm_failed`` so tests that patch either name work. Future
        improvements could filter by error type (skip ArchiveNotRetryable).
        """
        return await self.rearm_failed()

    async def count_active(self) -> int:
        """Number of download tasks still pending or in progress."""
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(DownloadTask)
                .where(DownloadTask.status.in_(["pending", "downloading"]))
            )
            or 0
        )

    async def record_attempt(
        self, task_id: int, attempt: int, status: str, error: str | None = None
    ) -> None:
        self.session.add(
            DownloadAttempt(task_id=task_id, attempt=attempt, status=status, error_message=error)
        )
        await self.session.flush()

    async def progress(self, task_id: int, current_page: int, total_pages: int) -> None:
        row = await self.session.get(DownloadTask, task_id)
        if row is not None:
            row.current_page = current_page
            row.total_pages = total_pages
            row.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def list_page(
        self, page: int, page_size: int, status: str | None = None
    ) -> tuple[int, list[DownloadTask]]:
        query = select(DownloadTask)
        if status:
            query = query.where(DownloadTask.status == status)
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = (
            await self.session.scalars(
                query.order_by(DownloadTask.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return total, list(rows)

    async def cancel(self, task_id: int) -> bool:
        task = await self.session.get(DownloadTask, task_id)
        if task is None:
            return False
        if task.status in {"pending", "downloading"}:
            task.status = "cancelled"
        return True

    async def delete(self, task_id: int) -> bool:
        """Permanently remove a download task (and its attempt log)."""
        task = await self.session.get(DownloadTask, task_id)
        if task is None:
            return False
        await self.session.delete(task)
        return True

    async def delete_success(self) -> int:
        result = await self.session.execute(
            delete(DownloadTask).where(DownloadTask.status == "success")
        )
        return int(result.rowcount or 0)


