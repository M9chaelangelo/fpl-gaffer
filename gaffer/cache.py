import hashlib, json, os, time

CACHE_DIR = ".cache"
TTL = 6 * 3600


def cached(key, fn, ttl=TTL):
    """Disk cache for the expensive sequential sweeps over other managers'
    squads. Neither ownership nor the elite template moves between deadlines,
    and a full run makes over a hundred sequential API calls without this."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            return json.load(open(path))
        except Exception:
            pass
    val = fn()
    json.dump(val, open(path, "w"))
    return val
