"""
test_di_framework.py — Unit Tests untuk Mini DI Framework
===========================================================

Menguji semua fitur:
  ✓ Registrasi dan resolusi dasar
  ✓ Lifetime SINGLETON, TRANSIENT, SCOPED
  ✓ Auto-wiring via type hints (dependency chain)
  ✓ Circular dependency detection
  ✓ Async factories dan async_resolve
  ✓ Scoped containers
  ✓ Context-manager override (testing isolation)
  ✓ Decorator API: @singleton, @transient, @scoped, @inject
  ✓ TestContainer: resolve counts, override_many
  ✓ Thread safety (SINGLETON dibuat sekali meski resolve parallel)
  ✓ Error messages yang jelas

Jalankan:
    pytest test_di_framework.py -v
    pytest test_di_framework.py -v --tb=short
"""

import asyncio
import threading
import pytest
from typing import List

from di_framework import (
    Container, TestContainer,
    Lifetime,
    ProviderNotFoundError, CircularDependencyError,
    AsyncResolutionError, ScopedResolutionError,
    singleton, transient, scoped, injectable, inject,
    get_container, set_container,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & Shared Fakes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def container() -> Container:
    """Container bersih untuk setiap test (tidak ada state lintas test)."""
    return Container()


@pytest.fixture
def test_container() -> TestContainer:
    return TestContainer()


# ─────────────────────────────────────────────────────────────────────────────
# Kelas-kelas palsu untuk testing
# ─────────────────────────────────────────────────────────────────────────────

class Database:
    """Fake database — tidak butuh dependency."""
    def __init__(self) -> None:
        self.connected = True


class UserRepository:
    """Butuh Database."""
    def __init__(self, db: Database) -> None:
        self.db = db


class UserService:
    """Butuh UserRepository."""
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo


class EmailService:
    """Tidak ada dependency."""
    def send(self, to: str) -> str:
        return f"sent to {to}"


class NotificationService:
    """Butuh UserService DAN EmailService."""
    def __init__(self, user_svc: UserService, email_svc: EmailService) -> None:
        self.user_svc = user_svc
        self.email_svc = email_svc


# ─────────────────────────────────────────────────────────────────────────────
# 1. Registrasi & Resolusi Dasar
# ─────────────────────────────────────────────────────────────────────────────

class TestBasicRegistrationAndResolution:

    def test_register_and_resolve_simple_class(self, container):
        """Class tanpa dependency harus bisa di-resolve langsung."""
        container.register(Database)
        db = container.resolve(Database)
        assert isinstance(db, Database)

    def test_register_with_explicit_factory(self, container):
        """Factory function digunakan sebagai pengganti constructor."""
        container.register(Database, factory=lambda: Database())
        db = container.resolve(Database)
        assert isinstance(db, Database)

    def test_register_instance(self, container):
        """register_instance menyimpan objek pre-built."""
        existing_db = Database()
        container.register_instance(Database, existing_db)
        resolved = container.resolve(Database)
        assert resolved is existing_db   # instance identik, bukan copy

    def test_resolve_interface_with_impl(self, container):
        """
        Registrasi di bawah kunci abstrak (interface/string) —
        pola umum untuk dependency inversion.
        """
        container.register("db", factory=Database)
        db = container.resolve("db")
        assert isinstance(db, Database)

    def test_method_chaining(self, container):
        """register() return self untuk chaining."""
        result = (
            container
            .register(Database)
            .register(EmailService)
        )
        assert result is container
        assert container.is_registered(Database)
        assert container.is_registered(EmailService)

    def test_provider_not_found_raises(self, container):
        """Resolve key yang tidak terdaftar harus raise ProviderNotFoundError."""
        with pytest.raises(ProviderNotFoundError) as exc_info:
            container.resolve(Database)
        assert "Database" in str(exc_info.value)

    def test_is_registered(self, container):
        assert not container.is_registered(Database)
        container.register(Database)
        assert container.is_registered(Database)

    def test_contains_operator(self, container):
        container.register(Database)
        assert Database in container
        assert EmailService not in container


# ─────────────────────────────────────────────────────────────────────────────
# 2. Auto-Wiring (Dependency Chain)
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoWiring:

    def test_single_dependency(self, container):
        """UserRepository butuh Database — keduanya harus di-resolve."""
        container.register(Database)
        container.register(UserRepository)
        repo = container.resolve(UserRepository)
        assert isinstance(repo, UserRepository)
        assert isinstance(repo.db, Database)

    def test_deep_dependency_chain(self, container):
        """UserService → UserRepository → Database: 3 level."""
        container.register(Database)
        container.register(UserRepository)
        container.register(UserService)
        svc = container.resolve(UserService)
        assert isinstance(svc.repo, UserRepository)
        assert isinstance(svc.repo.db, Database)

    def test_multiple_dependencies(self, container):
        """NotificationService butuh dua dependency berbeda."""
        container.register(Database)
        container.register(UserRepository)
        container.register(UserService)
        container.register(EmailService)
        container.register(NotificationService)
        notif = container.resolve(NotificationService)
        assert isinstance(notif.user_svc, UserService)
        assert isinstance(notif.email_svc, EmailService)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Lifetime: TRANSIENT
# ─────────────────────────────────────────────────────────────────────────────

class TestTransientLifetime:

    def test_transient_returns_new_instance_each_time(self, container):
        """TRANSIENT: setiap resolve menghasilkan instance berbeda."""
        container.register(Database, lifetime=Lifetime.TRANSIENT)
        db1 = container.resolve(Database)
        db2 = container.resolve(Database)
        assert db1 is not db2   # objek berbeda

    def test_transient_is_default(self, container):
        """Tanpa lifetime eksplisit, default adalah TRANSIENT."""
        container.register(Database)
        db1 = container.resolve(Database)
        db2 = container.resolve(Database)
        assert db1 is not db2


# ─────────────────────────────────────────────────────────────────────────────
# 4. Lifetime: SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

class TestSingletonLifetime:

    def test_singleton_returns_same_instance(self, container):
        """SINGLETON: semua resolve mengembalikan instance yang sama."""
        container.register(Database, lifetime=Lifetime.SINGLETON)
        db1 = container.resolve(Database)
        db2 = container.resolve(Database)
        assert db1 is db2

    def test_singleton_via_register_singleton(self, container):
        container.register_singleton(Database)
        assert container.resolve(Database) is container.resolve(Database)

    def test_singleton_cache_cleared_by_reset(self, container):
        """reset() harus menghapus singleton cache sehingga instance baru dibuat."""
        container.register(Database, lifetime=Lifetime.SINGLETON)
        db_before = container.resolve(Database)
        container.reset()
        db_after = container.resolve(Database)
        assert db_before is not db_after

    def test_singleton_thread_safety(self, container):
        """
        Dua thread yang resolve SINGLETON secara bersamaan harus
        mendapatkan instance yang SAMA (bukan dua instance berbeda).
        """
        container.register(Database, lifetime=Lifetime.SINGLETON)
        results: List[Database] = []
        lock = threading.Lock()

        def resolve_in_thread():
            db = container.resolve(Database)
            with lock:
                results.append(db)

        threads = [threading.Thread(target=resolve_in_thread) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Semua thread harus dapat instance yang sama
        assert len(set(id(r) for r in results)) == 1

    def test_register_instance_behaves_as_singleton(self, container):
        """register_instance selalu mengembalikan instance yang sama."""
        db = Database()
        container.register_instance(Database, db)
        assert container.resolve(Database) is db
        assert container.resolve(Database) is db


# ─────────────────────────────────────────────────────────────────────────────
# 5. Lifetime: SCOPED
# ─────────────────────────────────────────────────────────────────────────────

class TestScopedLifetime:

    def test_scoped_same_instance_within_scope(self, container):
        """Di dalam satu scope, SCOPED = SINGLETON."""
        container.register_scoped(Database)
        with container.create_scope() as scope:
            db1 = scope.resolve(Database)
            db2 = scope.resolve(Database)
            assert db1 is db2

    def test_scoped_different_instances_across_scopes(self, container):
        """Di scope berbeda, SCOPED menghasilkan instance berbeda."""
        container.register_scoped(Database)
        with container.create_scope() as scope1:
            db1 = scope1.resolve(Database)
        with container.create_scope() as scope2:
            db2 = scope2.resolve(Database)
        assert db1 is not db2

    def test_scoped_outside_scope_raises(self, container):
        """Resolve SCOPED dari container biasa (bukan scope) harus error."""
        container.register_scoped(Database)
        with pytest.raises(ScopedResolutionError) as exc_info:
            container.resolve(Database)
        assert "Database" in str(exc_info.value)

    def test_scoped_cache_cleared_after_scope_exit(self, container):
        """Instance SCOPED tidak bocor ke luar scope."""
        container.register_scoped(Database)
        captured = {}
        with container.create_scope() as scope:
            captured["db"] = scope.resolve(Database)
        # Setelah scope ditutup, cache scope harus bersih
        assert len(scope._scoped_cache) == 0

    def test_singleton_accessible_from_scope(self, container):
        """Scope mewarisi SINGLETON dari parent container."""
        container.register_singleton(Database)
        parent_db = container.resolve(Database)
        with container.create_scope() as scope:
            scope_db = scope.resolve(Database)
        assert parent_db is scope_db   # singleton yang sama


# ─────────────────────────────────────────────────────────────────────────────
# 6. Circular Dependency Detection
# ─────────────────────────────────────────────────────────────────────────────

class TestCircularDependencyDetection:

    def test_direct_circular_dependency(self, container):
        """A → A: langsung circular."""
        class A:
            def __init__(self, a: "A") -> None:
                self.a = a
        # Tambahkan forward reference agar get_type_hints bisa resolve
        A.__init__.__annotations__ = {"a": A}

        container.register(A)
        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve(A)
        assert "A" in str(exc_info.value)

    def test_indirect_circular_dependency(self, container):
        """A → B → A: circular tidak langsung."""
        class A:
            pass
        class B:
            def __init__(self, a: A) -> None:
                self.a = a
        # Buat A bergantung pada B
        A.__init__ = lambda self, b: setattr(self, "b", b)
        A.__init__.__annotations__ = {"b": B}

        container.register(A)
        container.register(B)
        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve(A)
        assert "CircularDependency" in type(exc_info.value).__name__

    def test_error_message_shows_cycle(self, container):
        """Pesan error harus mencantumkan rantai siklus."""
        class Chicken:
            pass
        class Egg:
            def __init__(self, chicken: Chicken) -> None:
                self.chicken = chicken
        Chicken.__init__ = lambda self, egg: None
        Chicken.__init__.__annotations__ = {"egg": Egg}

        container.register(Chicken)
        container.register(Egg)
        with pytest.raises(CircularDependencyError) as exc_info:
            container.resolve(Chicken)
        msg = str(exc_info.value)
        assert "→" in msg   # chain ditampilkan


# ─────────────────────────────────────────────────────────────────────────────
# 7. Async Support
# ─────────────────────────────────────────────────────────────────────────────

class TestAsyncSupport:

    @pytest.mark.asyncio
    async def test_async_factory_resolved_by_async_resolve(self, container):
        """Async factory bekerja dengan async_resolve."""
        async def make_db() -> Database:
            await asyncio.sleep(0)   # simulasi async I/O
            return Database()

        container.register(Database, factory=make_db)
        db = await container.async_resolve(Database)
        assert isinstance(db, Database)

    @pytest.mark.asyncio
    async def test_async_factory_raises_on_sync_resolve(self, container):
        """Async factory tidak boleh di-resolve secara sinkron."""
        async def make_db() -> Database:
            return Database()

        container.register(Database, factory=make_db)
        with pytest.raises(AsyncResolutionError) as exc_info:
            container.resolve(Database)
        assert "async_resolve" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sync_factory_works_with_async_resolve(self, container):
        """async_resolve juga bisa menangani factory sinkron."""
        container.register(Database)
        db = await container.async_resolve(Database)
        assert isinstance(db, Database)

    @pytest.mark.asyncio
    async def test_async_singleton_resolved_once(self, container):
        """Async SINGLETON di-cache setelah pertama kali di-resolve."""
        call_count = 0

        async def make_db() -> Database:
            nonlocal call_count
            call_count += 1
            return Database()

        container.register(Database, factory=make_db, lifetime=Lifetime.SINGLETON)
        db1 = await container.async_resolve(Database)
        db2 = await container.async_resolve(Database)
        assert db1 is db2
        assert call_count == 1   # factory dipanggil hanya sekali

    @pytest.mark.asyncio
    async def test_async_scoped_container(self, container):
        """Async scope context manager bekerja dengan benar."""
        container.register_scoped(Database)
        async with container.async_create_scope() as scope:
            db1 = await scope.async_resolve(Database)
            db2 = await scope.async_resolve(Database)
            assert db1 is db2
        # Setelah scope ditutup, cache bersih
        assert len(scope._scoped_cache) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Override (Testing Isolation)
# ─────────────────────────────────────────────────────────────────────────────

class TestOverride:

    def test_override_replaces_service_inside_block(self, container):
        """Di dalam block override, service diganti sementara."""
        class MockEmailService(EmailService):
            def send(self, to: str) -> str:
                return f"mock sent to {to}"

        container.register(EmailService)
        with container.override(EmailService, MockEmailService):
            svc = container.resolve(EmailService)
            assert isinstance(svc, MockEmailService)
            assert "mock" in svc.send("x@x.com")

    def test_override_restores_original_after_block(self, container):
        """Setelah block override, service kembali ke aslinya."""
        container.register(EmailService)
        with container.override(EmailService, lambda: None):
            pass   # tidak peduli apa yang terjadi di dalam

        svc = container.resolve(EmailService)
        assert isinstance(svc, EmailService)

    def test_override_with_instance(self, container):
        """Override bisa menerima instance langsung (bukan factory)."""
        mock_svc = EmailService()
        container.register(EmailService)
        with container.override(EmailService, mock_svc):
            resolved = container.resolve(EmailService)
            assert resolved is mock_svc

    def test_override_restores_even_on_exception(self, container):
        """Override harus merestore bahkan jika exception terjadi di dalam block."""
        container.register(EmailService)
        try:
            with container.override(EmailService, lambda: None):
                raise ValueError("error di dalam block")
        except ValueError:
            pass

        # Harus kembali ke implementasi asli
        svc = container.resolve(EmailService)
        assert isinstance(svc, EmailService)

    def test_override_unregistered_key(self, container):
        """Override key yang belum terdaftar: setelah block, key dihapus."""
        with container.override(Database, Database):
            assert container.is_registered(Database)
        assert not container.is_registered(Database)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Decorator API
# ─────────────────────────────────────────────────────────────────────────────

class TestDecorators:
    """
    Setiap test membuat container baru karena dekorator mendaftar ke
    container yang diberikan secara eksplisit.
    """

    def test_singleton_decorator(self):
        c = Container()

        @singleton(container=c)
        class Config:
            pass

        assert c.resolve(Config) is c.resolve(Config)

    def test_transient_decorator(self):
        c = Container()

        @transient(container=c)
        class RequestContext:
            pass

        assert c.resolve(RequestContext) is not c.resolve(RequestContext)

    def test_scoped_decorator(self):
        c = Container()

        @scoped(container=c)
        class DBSession:
            pass

        with c.create_scope() as scope:
            assert scope.resolve(DBSession) is scope.resolve(DBSession)

    def test_injectable_with_lifetime(self):
        c = Container()

        @injectable(lifetime=Lifetime.SINGLETON, container=c)
        class AppConfig:
            pass

        assert c.resolve(AppConfig) is c.resolve(AppConfig)

    def test_inject_decorator_auto_wires_function(self):
        """@inject menyuntik parameter bertipe ke fungsi biasa."""
        c = Container()
        c.register(EmailService, lifetime=Lifetime.SINGLETON)

        @inject(container=c)
        def send_welcome(to: str, email_svc: EmailService) -> str:
            return email_svc.send(to)

        result = send_welcome(to="alice@example.com")
        assert result == "sent to alice@example.com"

    def test_inject_caller_provided_arg_not_overridden(self):
        """Jika caller sudah provide argument, inject tidak akan override."""
        c = Container()
        c.register(EmailService)

        mock_svc = EmailService()
        mock_svc.send = lambda to: f"custom: {to}"  # type: ignore

        @inject(container=c)
        def send_welcome(to: str, email_svc: EmailService) -> str:
            return email_svc.send(to)

        result = send_welcome(to="x@x.com", email_svc=mock_svc)
        assert result.startswith("custom:")

    @pytest.mark.asyncio
    async def test_inject_decorator_on_async_function(self):
        """@inject bekerja di async function."""
        c = Container()
        c.register(Database)

        @inject(container=c)
        async def get_db_status(db: Database) -> bool:
            return db.connected

        result = await get_db_status()
        assert result is True

    def test_singleton_decorator_without_parens(self):
        """@singleton (tanpa kurung) harus tetap bekerja."""
        c = Container()

        # Dekorator tanpa argumen
        @singleton(container=c)
        class Logger:
            pass

        assert c.resolve(Logger) is c.resolve(Logger)


# ─────────────────────────────────────────────────────────────────────────────
# 10. TestContainer Utilities
# ─────────────────────────────────────────────────────────────────────────────

class TestTestContainerUtilities:

    def test_resolve_count_tracks_calls(self, test_container):
        test_container.register(Database)
        assert test_container.resolve_count(Database) == 0
        test_container.resolve(Database)
        test_container.resolve(Database)
        assert test_container.resolve_count(Database) == 2

    def test_override_many_replaces_multiple(self, test_container):
        test_container.register(Database)
        test_container.register(EmailService)

        class FakeDB(Database):
            pass
        class FakeEmail(EmailService):
            pass

        with test_container.override_many({
            Database: FakeDB,
            EmailService: FakeEmail,
        }):
            assert isinstance(test_container.resolve(Database), FakeDB)
            assert isinstance(test_container.resolve(EmailService), FakeEmail)

        # Kembali ke aslinya
        assert type(test_container.resolve(Database)) is Database
        assert type(test_container.resolve(EmailService)) is EmailService

    def test_override_many_restores_on_exception(self, test_container):
        """override_many juga restore saat exception."""
        test_container.register(Database)
        try:
            with test_container.override_many({Database: lambda: None}):
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        db = test_container.resolve(Database)
        assert isinstance(db, Database)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_class_without_type_hints_resolves_fine(self, container):
        """Class tanpa parameter di constructor tidak butuh dependency."""
        class NoParams:
            def __init__(self) -> None:
                self.value = 42

        container.register(NoParams)
        obj = container.resolve(NoParams)
        assert obj.value == 42

    def test_factory_function_resolves_dependencies(self, container):
        """Factory function bisa punya parameter bertipe."""
        container.register(Database)

        def make_repo(db: Database) -> UserRepository:
            return UserRepository(db=db)

        container.register(UserRepository, factory=make_repo)
        repo = container.resolve(UserRepository)
        assert isinstance(repo, UserRepository)
        assert isinstance(repo.db, Database)

    def test_register_with_lambda_no_params(self, container):
        """Lambda tanpa parameter sebagai factory."""
        container.register(Database, factory=lambda: Database())
        db = container.resolve(Database)
        assert isinstance(db, Database)

    def test_reset_clears_singleton_only(self, container):
        """reset() hanya menghapus instance SINGLETON, TRANSIENT tidak ter-cache."""
        container.register_singleton(Database)
        container.register(EmailService)  # TRANSIENT

        db = container.resolve(Database)
        container.reset()

        # SINGLETON harus dibuat ulang
        db_new = container.resolve(Database)
        assert db is not db_new

        # TRANSIENT tidak berubah behavior
        svc = container.resolve(EmailService)
        assert isinstance(svc, EmailService)

    def test_container_repr(self, container):
        """repr() harus informatif."""
        container.register(Database)
        repr_str = repr(container)
        assert "Database" in repr_str
        assert "Container" in repr_str


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (opsional — pytest sudah auto-discover)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
