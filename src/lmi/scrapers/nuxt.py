"""Rozpakowanie __NUXT_DATA__ (Nuxt 3, format "devalue": płaska tablica, obiekty wskazują indeksy)."""
from __future__ import annotations

import json
import re

_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef", "NuxtError"}
_SCALARS = {"Date", "BigInt", "RegExp", "null"}
_SPECIAL = {-1: None, -2: None, -3: None, -4: None, -5: None, -6: 0}


def unflatten(data: list):
    memo: dict[int, object] = {}

    def h(i, depth=0):
        if not isinstance(i, int) or isinstance(i, bool):
            return i
        if i < 0:
            return _SPECIAL.get(i)
        if i in memo:
            return memo[i]
        if depth > 80:
            return None
        v = data[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in _WRAPPERS:
                out = h(v[1], depth + 1) if len(v) > 1 else None
            elif v and isinstance(v[0], str) and v[0] in _SCALARS:
                out = v[1] if len(v) > 1 else None
            elif v and isinstance(v[0], str) and v[0] in ("Set", "Map"):
                out = [h(x, depth + 1) for x in v[1:]]
            else:
                out = []
                memo[i] = out
                out.extend(h(x, depth + 1) for x in v)
                return out
        elif isinstance(v, dict):
            out = {}
            memo[i] = out
            for k, x in v.items():
                out[k] = h(x, depth + 1)
            return out
        else:
            out = v
        memo[i] = out
        return out

    return h(0)


def nuxt_data(html: str):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    raw = json.loads(m.group(1))
    return unflatten(raw) if isinstance(raw, list) else raw


def find_first(obj, predicate, depth=0):
    """Pierwszy słownik spełniający `predicate` (przeszukiwanie w głąb)."""
    if depth > 40:
        return None
    if isinstance(obj, dict):
        if predicate(obj):
            return obj
        for v in obj.values():
            r = find_first(v, predicate, depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_first(v, predicate, depth + 1)
            if r is not None:
                return r
    return None
