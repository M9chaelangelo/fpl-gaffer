"""Checks everything works before you deploy. `python preflight.py`"""
import importlib, os, sys, yaml

ok = True


def check(label, cond, hint=""):
    global ok
    print(f"  [{'ok' if cond else 'FAIL'}] {label}" + ("" if cond else f" — {hint}"))
    ok = ok and cond


print("dependencies")
for mod in ("requests", "pulp", "yaml", "pandas", "sklearn", "joblib"):
    try:
        importlib.import_module(mod)
        check(mod, True)
    except ImportError:
        check(mod, False, "pip install -r requirements.txt")

print("config")
cfg = yaml.safe_load(open("config.yaml"))
check("entry_id set", bool(cfg.get("entry_id")))
check("league_id set", bool(cfg.get("league_id")))
check("current_squad has 15", len(cfg.get("current_squad") or []) == 15,
      "list your actual fifteen, or comment the block out")
chips = cfg.get("chip_plan") or {}
check("no two chips in one gameweek",
      len(set(chips.values())) == len(chips), f"chip_plan: {chips}")

print("files")
for path in ("gaffer/main.py", ".github/workflows/gaffer.yml", "requirements.txt"):
    check(path, os.path.exists(path))
check("trained models present", os.path.exists("models/minutes.joblib"),
      "run python -m gaffer.learn")

print("network")
try:
    from gaffer import fetch
    b = fetch.bootstrap()
    check("FPL API", len(b["elements"]) > 500)
    check("your team readable", bool(fetch.entry(cfg["entry_id"])))
    check("Solio feed", bool(fetch.solio(cfg["solio_url"])),
          "not fatal — the local model still runs")
except Exception as e:
    check("FPL API", False, str(e))

print()
print("ready to deploy" if ok else "fix the failures above first")
sys.exit(0 if ok else 1)
