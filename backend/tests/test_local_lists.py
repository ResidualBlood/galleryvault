import pytest
from sqlalchemy.dialects import postgresql

from galleryvault.db.repositories.lists import LocalListRepository


class _Rows:
    def __init__(self, rows=None, rowcount=0):
        self.rows = rows or []
        self.rowcount = rowcount

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self):
        self.sql = []
        self.added = []

    def _compile(self, statement) -> str:
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.sql.append(sql)
        return sql

    async def execute(self, statement):
        self._compile(statement)
        return _Rows(rowcount=1)

    async def scalars(self, statement):
        self._compile(statement)
        return _Rows([1, 2])

    async def scalar(self, statement):
        self._compile(statement)

    async def get(self, model, ident):
        return None

    def add(self, obj):
        obj.id = 9
        self.added.append(obj)

    async def flush(self):
        pass

    async def delete(self, obj):
        pass


@pytest.mark.asyncio
async def test_local_list_add_and_remove_sql() -> None:
    session = _FakeSession()
    repo = LocalListRepository(session)
    await repo.add_items(3, [1, 2, 2])
    assert any("local_list_items" in sql.lower() for sql in session.sql)
    session.sql.clear()
    removed = await repo.remove_items(3, [1])
    assert removed == 1
    assert "delete" in session.sql[-1].lower()
    assert "local_list_items" in session.sql[-1].lower()
