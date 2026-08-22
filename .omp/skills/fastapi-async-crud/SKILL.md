---
name: fastapi-async-crud
description: "Production-ready FastAPI + SQLAlchemy 2.0 async CRUD: file layout, patterns, test isolation, JWT dual-token, rate limiting"
---

## FastAPI Async CRUD — Canonical Stack

### File Layout
```
config.py          # Pydantic Settings (DATABASE_URL, JWT_*, RATE_LIMIT_*)
database.py        # create_async_engine + async_sessionmaker + Base
models.py          # ORM models (UUID PK, soft-delete, server_default timestamps)
schemas.py         # Pydantic v2: *Base / *Create / *Update / *Patch / *Response
auth.py            # bcrypt (passlib) + JWT (python-jose): access + refresh tokens
dependencies.py    # get_db, get_current_user, require_admin, PaginationParams
crud.py            # All DB queries — no query logic in routers
routers/
  auth.py          # POST /login /refresh /logout, GET /me
  users.py         # GET/POST/PUT/PATCH/DELETE /users
  posts.py         # Post CRUD + nested /comments
main.py            # FastAPI factory: CORS, SlowAPI, middleware, exception handlers
tests/
  conftest.py      # Test DB, per-test ROLLBACK isolation, token fixtures
  test_*.py        # pytest-asyncio + anyio, AsyncClient via ASGITransport
```

### Key Patterns

**Async session dependency (get_db)**
```python
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**PATCH semantics — only update sent fields**
```python
update_data = data.model_dump(exclude_unset=True)
for field, value in update_data.items():
    setattr(obj, field, value)
```

**Pagination with batch aggregation (no N+1)**
```python
total = await db.scalar(select(func.count()).select_from(base_query.subquery()))
rows  = await db.execute(base_query.limit(page_size).offset((page-1)*page_size))
# Batch counts in one GROUP BY query:
counts = {row.post_id: row.cnt for row in await db.execute(count_query)}
```

**Soft delete** — never `DELETE FROM`; set `is_deleted=True`, filter all queries with `.where(Model.is_deleted == False)`

**JWT dual-token** with timing-safe login
```python
# Prevent timing attack: always run bcrypt even when user missing
dummy = "$2b$12$invalidhash..."
hashed = user.hashed_password if user else dummy
if not user or not verify_password(plain, hashed):
    raise 401
```

**Rate limiting (SlowAPI)**
```python
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
```

**Test isolation — ROLLBACK per test (no truncate)**
```python
@pytest_asyncio.fixture
async def db_session():
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await conn.rollback()   # ← wipes all test changes
```

**Dependency override in tests**
```python
async def override_get_db():
    yield db_session   # same session as the test
app.dependency_overrides[get_db] = override_get_db
```

### Requirements (core)
```
fastapi, uvicorn[standard], sqlalchemy==2.0.x, asyncpg,
pydantic[email]>=2, pydantic-settings,
python-jose[cryptography], passlib[bcrypt],
slowapi, limits,
pytest, pytest-asyncio, httpx, anyio
```
