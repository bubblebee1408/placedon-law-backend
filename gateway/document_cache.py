"""Bounded, expiring process cache for legacy upload references.

Durable documents belong in the vault. Evicted legacy references are reported as
unreadable by the conversation resolver; cache misses must never substitute prompt text.
"""
from collections import OrderedDict
from collections.abc import MutableMapping
import json
from copy import deepcopy
import threading
import time


class DocumentCache:
    def __init__(self, *, total_bytes=64 * 1024 * 1024, tenant_bytes=16 * 1024 * 1024,
                 max_entries=256, ttl_seconds=1800, clock=time.monotonic):
        self.total_bytes, self.tenant_bytes = total_bytes, tenant_bytes
        self.max_entries, self.ttl_seconds, self.clock = max_entries, ttl_seconds, clock
        self._rows = OrderedDict()
        self._lock = threading.RLock()

    def _expire(self):
        now = self.clock()
        for key, (_, _, expires) in list(self._rows.items()):
            if expires <= now:
                del self._rows[key]

    def for_tenant(self, tenant):
        return _Documents(self, tenant)


class _Documents(MutableMapping):
    def __init__(self, cache, tenant):
        self.cache, self.tenant = cache, tenant

    def __getitem__(self, document_id):
        with self.cache._lock:
            self.cache._expire()
            key = (self.tenant, document_id)
            value, _, _ = self.cache._rows[key]
            self.cache._rows.move_to_end(key)
            return deepcopy(value)

    def __setitem__(self, document_id, value):
        # Account for metadata as well as text. Inputs are JSON document records.
        size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        if size > min(self.cache.tenant_bytes, self.cache.total_bytes):
            raise ValueError("This legacy document exceeds cache capacity. Use the durable vault.")
        with self.cache._lock:
            self.cache._expire()
            key = (self.tenant, document_id)
            self.cache._rows.pop(key, None)
            self.cache._rows[key] = (deepcopy(value), size, self.cache.clock() + self.cache.ttl_seconds)
            while sum(s for (tenant, _), (_, s, _) in self.cache._rows.items() if tenant == self.tenant) > self.cache.tenant_bytes:
                oldest = next(k for k in self.cache._rows if k[0] == self.tenant)
                del self.cache._rows[oldest]
            while len(self.cache._rows) > self.cache.max_entries or sum(s for _, s, _ in self.cache._rows.values()) > self.cache.total_bytes:
                self.cache._rows.popitem(last=False)

    def __delitem__(self, document_id):
        with self.cache._lock:
            del self.cache._rows[(self.tenant, document_id)]

    def __iter__(self):
        with self.cache._lock:
            self.cache._expire()
            return iter([key for tenant, key in self.cache._rows if tenant == self.tenant])

    def __len__(self):
        return sum(1 for _ in self)


def _test():
    now = [0]
    cache = DocumentCache(total_bytes=150, tenant_bytes=80, max_entries=3, ttl_seconds=10, clock=lambda: now[0])
    a, b = cache.for_tenant("a"), cache.for_tenant("b")
    tests = []
    a["same"] = {"text": "x"*35}
    tests.append((b.get("same") is None, "tenant views cannot read another tenant's entry"))
    a["new"] = {"text": "y"*35}
    tests.append((a.get("same") is None and a.get("new") is not None, "tenant byte cap evicts oldest legacy reference"))
    b["same"] = {"text": "z"*35}
    tests.append((b["same"]["text"] != a["new"]["text"], "identical document keys remain tenant scoped"))
    observed = b["same"]
    observed["text"] = "oversized" * 1000
    tests.append((len(b["same"]["text"]) == 35, "readers cannot mutate retained content outside byte accounting"))
    value = {"text": "tiny", "nested": {"value": "small"}}
    b["nested"] = value
    value["nested"]["value"] = "oversized" * 1000
    tests.append((b["nested"]["nested"]["value"] == "small", "writers cannot retain a mutable alias to nested cached metadata"))
    now[0] = 11
    tests.append((len(a) == len(b) == 0, "expired private document text is discarded"))
    rejected = False
    try:
        a["huge"] = {"text": "a"*200}
    except ValueError:
        rejected = True
    tests.append((rejected and not a, "oversized entries cannot exceed cache limits"))
    for i in range(10):
        cache.for_tenant(str(i))["doc"] = {"text": "x"*35}
    tests.append((len(cache._rows) <= 3 and sum(s for _, s, _ in cache._rows.values()) <= 150, "global budget bounds many tenants"))
    for good, label in tests:
        print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    good = sum(ok for ok, _ in tests)
    print(f"\n{good}/{len(tests)} passed")
    return int(good != len(tests))

if __name__ == "__main__":
    raise SystemExit(_test())
