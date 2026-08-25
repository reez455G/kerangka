"""
di_framework.py — Mini Dependency Injection Framework
=======================================================

Arsitektur:
───────────

  ┌─────────────────────────────────────────────────────────────────┐
  │  Container                                                       │
  │  ┌────────────┐   register()   ┌──────────────────────────────┐ │
  │  │  Registry  │◄───────────────│  Provider(factory, lifetime) │ │
  │  │ {key→Prov} │                └──────────────────────────────┘ │
  │  └─────┬──────┘                                                  │
  │        │ resolve(key)                                            │
  │        ▼                                                         │
  │  ┌─────────────────────┐                                         │
  │  │  Resolver           │  1. Cek _resolving_stack (cycle?)       │
  │  │  - sync / async     │  2. Inspect type hints → resolve deps   │
  │  │  - lifetime cache   │  3. Panggil factory(**resolved_deps)    │
  │  │  - scope propagation│  4. Cache jika SINGLETON/SCOPED         │
  │  └─────────────────────┘                                         │
  └─────────────────────────────────────────────────────────────────┘

Fitur:
  ✓ Lifetime: SINGLETON, TRANSIENT, SCOPED
  ✓ Auto-wiring via type hints (inspect.get_annotations / typing.get_type_hints)
  ✓ Circular dependency detection (DFS stack tracking)
  ✓ Async factories & async_resolve()
  ✓ Scoped containers (satu instance per scope / per-request)
  ✓ Context-manager override untuk testing
  ✓ Decorator API: @singleton, @transient, @scoped, @inject

Lifetime semantics:
  SINGLETON  → satu instance per Container (dibuat sekali, di-cache)
  TRANSIENT  → instance baru setiap resolve()
  SCOPED     → satu instance per Scope, baru saat Scope baru dibuat
               (mirip SINGLETON di dalam scope, tapi berbeda antar scope)
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import typing
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import wraps
from typing import Any, Callable, Dict, Generator, Generic, Iterator, List, Optional, Set, Type, TypeVar

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Lifetime
# ─────────────────────────────────────────────────────────────────────────────
class Lifetime(Enum):
    """
    Menentukan kapan instance baru dibuat dan berapa lama ia hidup.

    SINGLETON : Dibuat sekali saat pertama di-resolve, di-cache dalam Container.
                Semua resolve berikutnya mengembalikan instance yang sama.
                ⚠ Hati-hati menyuntik TRANSIENT ke SINGLETON (captive dependency).

    TRANSIENT : Instance baru dibuat setiap kali resolve() dipanggil.
                Tidak ada caching. Cocok untuk stateless service / value object.

    SCOPED    : Instance baru per Scope. Dalam satu Scope, instance di-cache
                (mirip SINGLETON). Di Scope berbeda, instance berbeda.
                Contoh penggunaan: satu DB session per HTTP request.
    """
    SINGLETON = auto()
    TRANSIENT = auto()
    SCOPED = auto()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Exceptions
# ─────────────────────────────────────────────────────────────────────────────
class DIError(Exception):
    """Base exception untuk semua error DI."""


class ProviderNotFoundError(DIError):
    """Key tidak terdaftar di container."""
    def __init__(self, key: Any) -> None:
        name = getattr(key, "__name__", repr(key))
        super().__init__(f"Provider tidak ditemukan untuk: '{name}'")


class CircularDependencyError(DIError):
    """
    Terdeteksi siklus dependensi: A → B → C → A.
    Ini selalu merupakan bug desain, bukan kondisi runtime yang valid.
    """
    def __init__(self, cycle: List[Any]) -> None:
        names = [getattr(k, "__name__", repr(k)) for k in cycle]
        chain = " → ".join(names)
        super().__init__(f"Circular dependency terdeteksi: {chain}")


class AsyncResolutionError(DIError):
    """Factory async dipanggil dari resolve() sinkron."""
    def __init__(self, key: Any) -> None:
        name = getattr(key, "__name__", repr(key))
        super().__init__(
            f"'{name}' memiliki async factory. Gunakan 'await container.async_resolve({name})'."
        )


class ScopedResolutionError(DIError):
    """SCOPED service di-resolve di luar scope."""
    def __init__(self, key: Any) -> None:
        name = getattr(key, "__name__", repr(key))
        super().__init__(
            f"SCOPED service '{name}' di-resolve di luar Scope. "
            "Gunakan 'with container.create_scope() as scope: ...'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Provider
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Provider:
    """
    Deskripsi cara membuat satu service.

    factory  : callable yang menerima resolved dependencies sebagai kwargs,
               atau instance langsung (pre-built).
    lifetime : SINGLETON / TRANSIENT / SCOPED
    _instance: cache untuk SINGLETON (None sampai pertama di-resolve)
    is_async : True jika factory adalah coroutine function
    """
    factory: Callable
    lifetime: Lifetime
    _instance: Any = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    @property
    def is_async(self) -> bool:
        return asyncio.iscoroutinefunction(self.factory)

    def has_cached_instance(self) -> bool:
        return self._instance is not None

    def get_cached(self) -> Any:
        return self._instance

    def set_cached(self, instance: Any) -> None:
        self._instance = instance

    def clear_cache(self) -> None:
        self._instance = None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Container
# ─────────────────────────────────────────────────────────────────────────────
class Container:
    """
    Pusat registrasi dan resolusi dependensi.

    Tiga cara registrasi:
      container.register(ServiceClass)           # auto-detect lifetime dari dekorator
      container.register(IFace, impl_factory, Lifetime.SINGLETON)
      container.register_instance(IFace, obj)    # instance yang sudah dibuat

    Dua cara resolusi:
      obj = container.resolve(ServiceClass)       # sync
      obj = await container.async_resolve(Svc)   # sync + async factories

    Testing override (context manager):
      with container.override(IFace, MockImpl):
          ...   # IFace di-resolve sebagai MockImpl di dalam block ini
    """

    def __init__(self, parent: Optional["Container"] = None) -> None:
        # Registry: key → Provider
        self._registry: Dict[Any, Provider] = {}
        # Parent untuk scope hierarchy
        self._parent = parent
        # Cache SCOPED instances (hanya relevan di scope container)
        self._scoped_cache: Dict[Any, Any] = {}
        # Lock untuk thread-safety saat resolve SINGLETON
        self._resolve_lock = threading.Lock()
        # Stack untuk deteksi circular dependency (per-thread)
        self._local = threading.local()

    # ── Registrasi ────────────────────────────────────────────────────────────

    def register(
        self,
        key: Any,
        factory: Optional[Callable] = None,
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> "Container":
        """
        Daftarkan service dengan key, factory, dan lifetime.

        Jika factory tidak diberikan, key HARUS callable (class/function)
        dan akan digunakan sebagai factory-nya sendiri.

        Return self untuk method chaining:
            container.register(A).register(B).register(C)
        """
        if factory is None:
            if not callable(key):
                raise DIError(f"'{key}' bukan callable; berikan factory secara eksplisit.")
            factory = key

        # Ambil lifetime dari atribut __di_lifetime__ jika ada (dari dekorator)
        if lifetime == Lifetime.TRANSIENT:
            detected = getattr(factory, "__di_lifetime__", None)
            if detected is not None:
                lifetime = detected

        self._registry[key] = Provider(factory=factory, lifetime=lifetime)
        return self

    def register_singleton(self, key: Any, factory: Optional[Callable] = None) -> "Container":
        """Shorthand: register dengan Lifetime.SINGLETON."""
        return self.register(key, factory, Lifetime.SINGLETON)

    def register_transient(self, key: Any, factory: Optional[Callable] = None) -> "Container":
        """Shorthand: register dengan Lifetime.TRANSIENT."""
        return self.register(key, factory, Lifetime.TRANSIENT)

    def register_scoped(self, key: Any, factory: Optional[Callable] = None) -> "Container":
        """Shorthand: register dengan Lifetime.SCOPED."""
        return self.register(key, factory, Lifetime.SCOPED)

    def register_instance(self, key: Any, instance: Any) -> "Container":
        """
        Daftarkan instance yang sudah dibuat (pre-built object).
        Selalu di-resolve sebagai instance yang sama (efektif SINGLETON).
        """
        provider = Provider(factory=lambda: instance, lifetime=Lifetime.SINGLETON)
        provider.set_cached(instance)
        self._registry[key] = provider
        return self

    # ── Resolusi Sinkron ──────────────────────────────────────────────────────

    def resolve(self, key: Any) -> Any:
        """
        Resolve service secara sinkron.
        Raise AsyncResolutionError jika factory-nya async.
        Raise CircularDependencyError jika ada siklus.
        Raise ProviderNotFoundError jika key tidak terdaftar.
        """
        # Inisialisasi stack per-thread jika belum ada
        if not hasattr(self._local, "resolving_stack"):
            self._local.resolving_stack = []

        stack: List[Any] = self._local.resolving_stack

        # ── Deteksi Circular Dependency ───────────────────────────────────
        if key in stack:
            cycle = stack[stack.index(key):] + [key]
            raise CircularDependencyError(cycle)

        provider = self._get_provider(key)

        # ── Cek async factory ─────────────────────────────────────────────
        if provider.is_async:
            raise AsyncResolutionError(key)

        # ── Cek SCOPED di luar scope ──────────────────────────────────────
        if provider.lifetime == Lifetime.SCOPED and not self._is_scope:
            raise ScopedResolutionError(key)

        # ── Return dari cache ─────────────────────────────────────────────
        if provider.lifetime == Lifetime.SINGLETON and provider.has_cached_instance():
            return provider.get_cached()

        if provider.lifetime == Lifetime.SCOPED:
            if key in self._scoped_cache:
                return self._scoped_cache[key]

        # ── Build instance ────────────────────────────────────────────────
        stack.append(key)
        try:
            kwargs = self._resolve_params(provider.factory, async_mode=False)
            instance = provider.factory(**kwargs)
        finally:
            stack.pop()

        # ── Cache sesuai lifetime ─────────────────────────────────────────
        if provider.lifetime == Lifetime.SINGLETON:
            with provider._lock:
                if not provider.has_cached_instance():  # double-checked locking
                    provider.set_cached(instance)
                else:
                    instance = provider.get_cached()

        elif provider.lifetime == Lifetime.SCOPED:
            self._scoped_cache[key] = instance

        return instance

    # ── Resolusi Async ────────────────────────────────────────────────────────

    async def async_resolve(self, key: Any) -> Any:
        """
        Resolve service secara async.
        Mendukung factory sinkron maupun async (coroutine function).
        """
        if not hasattr(self._local, "resolving_stack"):
            self._local.resolving_stack = []
        stack: List[Any] = self._local.resolving_stack

        if key in stack:
            cycle = stack[stack.index(key):] + [key]
            raise CircularDependencyError(cycle)

        provider = self._get_provider(key)

        if provider.lifetime == Lifetime.SCOPED and not self._is_scope:
            raise ScopedResolutionError(key)

        if provider.lifetime == Lifetime.SINGLETON and provider.has_cached_instance():
            return provider.get_cached()

        if provider.lifetime == Lifetime.SCOPED and key in self._scoped_cache:
            return self._scoped_cache[key]

        stack.append(key)
        try:
            kwargs = await self._async_resolve_params(provider.factory)
            if provider.is_async:
                instance = await provider.factory(**kwargs)
            else:
                instance = provider.factory(**kwargs)
        finally:
            stack.pop()

        if provider.lifetime == Lifetime.SINGLETON:
            with provider._lock:
                if not provider.has_cached_instance():
                    provider.set_cached(instance)
                else:
                    instance = provider.get_cached()
        elif provider.lifetime == Lifetime.SCOPED:
            self._scoped_cache[key] = instance

        return instance

    # ── Scope ─────────────────────────────────────────────────────────────────

    @contextmanager
    def create_scope(self) -> Iterator["Container"]:
        """
        Buat scope baru (konteks terbatas).

        Penggunaan (contoh: per-request dalam web framework):
            with container.create_scope() as scope:
                session = scope.resolve(DBSession)   # SCOPED → satu per scope
                service = scope.resolve(UserService)
                # ... handle request
            # scope ditutup: SCOPED instances di-GC

        Scope container mewarisi SEMUA registrasi dari parent.
        SCOPED instances di-cache dalam scope container, bukan parent.
        """
        scope = _ScopeContainer(parent=self)
        try:
            yield scope
        finally:
            scope._scoped_cache.clear()

    @asynccontextmanager
    async def async_create_scope(self) -> typing.AsyncIterator["Container"]:
        """Async version dari create_scope."""
        scope = _ScopeContainer(parent=self)
        try:
            yield scope
        finally:
            scope._scoped_cache.clear()

    # ── Testing Override ──────────────────────────────────────────────────────

    @contextmanager
    def override(
        self,
        key: Any,
        factory: Any,
        lifetime: Lifetime = Lifetime.TRANSIENT,
    ) -> Iterator[None]:
        """
        Context manager untuk mengganti registrasi sementara (testing).

        Contoh:
            with container.override(EmailService, MockEmailService):
                result = service.send_email(...)
                assert mock_was_called()
            # EmailService kembali ke implementasi asli
        """
        old_provider = self._registry.get(key)
        # Register instance langsung jika factory bukan callable
        if not callable(factory):
            self.register_instance(key, factory)
        else:
            self.register(key, factory, lifetime)
        try:
            yield
        finally:
            if old_provider is not None:
                self._registry[key] = old_provider
            else:
                del self._registry[key]

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _get_provider(self, key: Any) -> Provider:
        """Cari provider: cek container ini dulu, lalu parent (untuk scope)."""
        if key in self._registry:
            return self._registry[key]
        if self._parent is not None:
            return self._parent._get_provider(key)
        raise ProviderNotFoundError(key)

    @property
    def _is_scope(self) -> bool:
        """True jika container ini adalah scope (bukan root container)."""
        return isinstance(self, _ScopeContainer)

    def _get_init_hints(self, factory: Callable) -> Dict[str, Any]:
        """
        Ambil type hints dari constructor atau callable.

        Untuk class: ambil dari __init__
        Untuk function: ambil langsung dari function signature
        Skip parameter 'self', 'return', dan parameter tanpa type hint.
        """
        if inspect.isclass(factory):
            func = factory.__init__
        else:
            func = factory

        try:
            hints = typing.get_type_hints(func)
        except Exception:
            hints = {}

        # Hapus 'return' annotation dan 'self'
        hints.pop("return", None)

        # Hanya ambil parameter yang punya annotation (lewati *args, **kwargs)
        sig = inspect.signature(func)
        valid_params = {
            name
            for name, param in sig.parameters.items()
            if name != "self"
            and param.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        }

        return {k: v for k, v in hints.items() if k in valid_params}

    def _resolve_params(self, factory: Callable, async_mode: bool) -> Dict[str, Any]:
        """
        Resolve semua parameter bertipe dari factory secara rekursif (sync).
        Parameter tanpa type hint diabaikan (harus punya default value).
        """
        hints = self._get_init_hints(factory)
        return {
            param_name: self.resolve(param_type)
            for param_name, param_type in hints.items()
        }

    async def _async_resolve_params(self, factory: Callable) -> Dict[str, Any]:
        """Async version: resolve semua parameter."""
        hints = self._get_init_hints(factory)
        result = {}
        for param_name, param_type in hints.items():
            result[param_name] = await self.async_resolve(param_type)
        return result

    def is_registered(self, key: Any) -> bool:
        """Cek apakah key sudah terdaftar di container ini atau parent-nya."""
        if key in self._registry:
            return True
        if self._parent is not None:
            return self._parent.is_registered(key)
        return False

    def reset(self) -> None:
        """
        Hapus semua singleton cache.
        Berguna di antara test cases untuk memastikan isolasi.
        """
        for provider in self._registry.values():
            provider.clear_cache()
        self._scoped_cache.clear()

    def __contains__(self, key: Any) -> bool:
        return self.is_registered(key)

    def __repr__(self) -> str:
        keys = [getattr(k, "__name__", repr(k)) for k in self._registry]
        return f"Container(registered={keys})"


class _ScopeContainer(Container):
    """
    Internal: container yang merepresentasikan satu scope.
    Mewarisi registry dari parent, tapi punya scoped_cache sendiri.
    Resolve SCOPED dari scope ini sendiri; SINGLETON dari parent (via _get_provider).
    """

    def __init__(self, parent: Container) -> None:
        super().__init__(parent=parent)
        # Override _is_scope
        self.__class__ = _ScopeContainer

    @property
    def _is_scope(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
# 5. Decorators
# ─────────────────────────────────────────────────────────────────────────────

# Global default container — bisa diganti untuk testing
_default_container = Container()


def get_container() -> Container:
    """Return global default container."""
    return _default_container


def set_container(container: Container) -> None:
    """Ganti global default container (berguna di testing)."""
    global _default_container
    _default_container = container


def injectable(
    lifetime: Lifetime = Lifetime.TRANSIENT,
    container: Optional[Container] = None,
    key: Optional[Any] = None,
):
    """
    Dekorator kelas: tandai class sebagai injectable dan daftarkan ke container.

    Contoh:
        @injectable(lifetime=Lifetime.SINGLETON)
        class UserRepository:
            def __init__(self, db: Database): ...

        @injectable()   # TRANSIENT by default
        class UserService:
            def __init__(self, repo: UserRepository): ...
    """
    def decorator(cls):
        # Simpan lifetime di atribut class (container bisa baca ini)
        cls.__di_lifetime__ = lifetime
        # Daftarkan ke container
        target = container or _default_container
        registration_key = key or cls
        target.register(registration_key, cls, lifetime)
        return cls
    return decorator


def singleton(cls=None, *, container: Optional[Container] = None):
    """
    Shorthand untuk @injectable(lifetime=Lifetime.SINGLETON).

    Bisa dipakai dengan atau tanpa argumen:
        @singleton
        class Config: ...

        @singleton(container=my_container)
        class Config: ...
    """
    if cls is None:
        # Dipanggil dengan argumen: @singleton(container=...)
        return lambda c: singleton(c, container=container)
    # Dipanggil tanpa argumen: @singleton
    cls.__di_lifetime__ = Lifetime.SINGLETON
    target = container or _default_container
    target.register(cls, cls, Lifetime.SINGLETON)
    return cls


def transient(cls=None, *, container: Optional[Container] = None):
    """Shorthand untuk @injectable(lifetime=Lifetime.TRANSIENT)."""
    if cls is None:
        return lambda c: transient(c, container=container)
    cls.__di_lifetime__ = Lifetime.TRANSIENT
    target = container or _default_container
    target.register(cls, cls, Lifetime.TRANSIENT)
    return cls


def scoped(cls=None, *, container: Optional[Container] = None):
    """Shorthand untuk @injectable(lifetime=Lifetime.SCOPED)."""
    if cls is None:
        return lambda c: scoped(c, container=container)
    cls.__di_lifetime__ = Lifetime.SCOPED
    target = container or _default_container
    target.register(cls, cls, Lifetime.SCOPED)
    return cls


def inject(container: Optional[Container] = None):
    """
    Dekorator fungsi: auto-inject parameter bertipe dari container.

    Berguna untuk handler/command function yang butuh dependency
    tanpa harus menjadi class:

        @inject()
        def handle_order(order_id: int, service: OrderService):
            return service.process(order_id)

        # Setara dengan:
        handle_order(order_id=123)
        # service di-resolve otomatis dari container
    """
    def decorator(func: Callable) -> Callable:
        c = container or _default_container
        hints = typing.get_type_hints(func)
        hints.pop("return", None)

        # Pisahkan param yang punya type hint (akan di-inject) dari yang lain
        sig = inspect.signature(func)
        injectable_params: Dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name in hints:
                injectable_params[name] = hints[name]

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Resolve hanya param yang tidak disediakan caller
            for param_name, param_type in injectable_params.items():
                if param_name not in kwargs:
                    kwargs[param_name] = c.resolve(param_type)
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            for param_name, param_type in injectable_params.items():
                if param_name not in kwargs:
                    kwargs[param_name] = await c.async_resolve(param_type)
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# 6. Testing Utilities
# ─────────────────────────────────────────────────────────────────────────────

class TestContainer(Container):
    """
    Container khusus testing.

    Tambahan fitur:
      - reset() bersihkan semua singleton cache antar test
      - override_many() batch override
      - spy(key) catat berapa kali service di-resolve
    """

    def __init__(self) -> None:
        super().__init__()
        self._resolve_counts: Dict[Any, int] = {}

    def resolve(self, key: Any) -> Any:
        self._resolve_counts[key] = self._resolve_counts.get(key, 0) + 1
        return super().resolve(key)

    def resolve_count(self, key: Any) -> int:
        """Berapa kali key ini di-resolve."""
        return self._resolve_counts.get(key, 0)

    @contextmanager
    def override_many(self, overrides: Dict[Any, Any]) -> Iterator[None]:
        """
        Override banyak key sekaligus.

            with test_container.override_many({
                EmailService: MockEmailService,
                Database: FakeDatabase(),
            }):
                ...
        """
        managers = [self.override(k, v) for k, v in overrides.items()]
        # Masuk ke semua context manager
        for m in managers:
            m.__enter__()
        try:
            yield
        finally:
            for m in reversed(managers):
                m.__exit__(None, None, None)
