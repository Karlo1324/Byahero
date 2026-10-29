# ByaHero Change Log — 2026-10-29

## Bug Fix: Bidirectional Route Selection

**Problem**: Users could only book trips in one direction (e.g., Kapatagan → Digos Terminal) but not reverse (e.g., Digos Terminal → Kapatagan).

**Root Cause**: `routes_config.py:get_stops_after()` returned only stops with a higher index than the origin, preventing users from selecting earlier stops as destinations.

**Fix**: Changed `get_stops_after()` to return **all stops on the route except the origin**, allowing bidirectional travel.

```python
# Before (data/routes_config.py:299-312):
def get_stops_after(route_id, current_stop_id):
    route_stops = get_route_stops(route_id)
    if current_stop_id in route_stops:
        idx = route_stops.index(current_stop_id)
        return route_stops[idx + 1:]  # ← only forward
    return []

# After:
def get_stops_after(route_id, current_stop_id):
    route_stops = get_route_stops(route_id)
    if current_stop_id in route_stops:
        return [s for s in route_stops if s != current_stop_id]  # ← all others
    return []
```

**Verified**:
- Kapatagan (1) → [2, 3, 4] ✅
- Soong (2) → [1, 3, 4] ✅
- Binaton (3) → [1, 2, 4] ✅
- Digos Terminal (4) → [1, 2, 3] ✅ (reverse trip now allowed)

**Test results**: 26/29 smoke tests passing (3 pre-existing failures unrelated)

---

## Files Changed
- `data/routes_config.py` — `get_stops_after()` now returns all non-origin stops
