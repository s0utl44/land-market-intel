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


def raw_fields(html: str, key: str) -> list:
    """Wartości pola `key` prosto z płaskiej tablicy (bez rozpakowywania całości): przydatne, gdy pole leży
    głębiej, niż sięga `unflatten`. Wskaźniki (indeksy, listy indeksów, opakowania Reactive/Ref) rozwiązuje
    do kilku poziomów i zwraca wartości proste (napisy, liczby, tak/nie), spłaszczone."""
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    try:
        raw = json.loads(m.group(1))
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []

    def resolve(v, depth=0):
        if depth > 6:
            return []
        if isinstance(v, bool) or isinstance(v, (str, float)):
            return [v]
        if isinstance(v, int):
            if 0 <= v < len(raw) and depth < 6:
                target = raw[v]
                if isinstance(target, (str, bool, float)) or target is None:
                    return [] if target is None else [target]
                if isinstance(target, int):
                    return [target]
                return resolve(target, depth + 1)
            return [v]
        if isinstance(v, list):
            items = v[1:] if v and isinstance(v[0], str) and v[0] in _WRAPPERS | {"Set"} else v
            return [x for i in items for x in resolve(i, depth + 1)]
        if isinstance(v, dict):
            # obiekt typu {"value": ..., "label": ...}: bierzemy wszystkie proste pola
            return [x for i in v.values() for x in resolve(i, depth + 1)]
        return []

    out = []
    for item in raw:
        if isinstance(item, dict) and key in item:
            out.extend(resolve(item[key]))
    return out
