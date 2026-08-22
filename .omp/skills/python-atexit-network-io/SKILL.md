---
name: python-atexit-network-io
description: "Fixing \"cannot schedule new futures after shutdown\" when Python atexit handlers do network I/O via async-backed sync clients (aiohttp/asyncio wrappers)"
---

# Network I/O in Python atexit handlers fails with async-backed clients

## Symptom
An `atexit`-registered handler that calls a sync client method (which internally does `loop.run_until_complete(...)` over aiohttp/asyncio) fails with:

```
RuntimeError: cannot schedule new futures after shutdown
```

The rest of the program worked fine; only the exit-time call fails. Often accompanied by `Unclosed client session` / `Unclosed connector` warnings.

## Cause
By the time regular `atexit` callbacks run, the interpreter has already begun tearing down thread pools / the asyncio default executor that the client's sync wrapper needs (e.g. for DNS resolution via `run_in_executor`). Any client built as `_run_async(coro) -> loop.run_until_complete(coro)` is affected (seen with `hindsight-client` 0.8.4).

## Fix pattern
1. Call the finalizer **explicitly** at the end of the main code path (`__main__`, CLI entrypoint, context-manager `__exit__`), before interpreter teardown starts.
2. Keep the `atexit.register(finalize)` as a **safety net only**, and make the finalizer **idempotent** with a module-level `_finalized` flag so the explicit call and the atexit call don't double-run:

```python
_finalized = False

def finalize_session():
    global _finalized
    if _finalized:
        return
    _finalized = True
    ...  # network I/O here

if __name__ == "__main__":
    main()
    finalize_session()  # explicit — atexit is too late for network I/O
```

3. If the finalizer must never crash the program, wrap the network calls in try/except with a `[WARN]` log (graceful degradation).

## Verification
Run the entrypoint and confirm the exit-time write actually landed (e.g. the record is recallable from the store) — absence of a traceback is NOT proof, since swallowed exceptions can hide the failed write.
