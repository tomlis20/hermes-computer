#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path("/opt/data")
sys.path.insert(0, "/opt/data/projects/hermes-computer")
from doctor import _load_yaml_platform_toolsets, merge_commands

def run_sets(profile: str | None, home: Path):
    os.environ["HERMES_HOME"] = str(home)
    ts = _load_yaml_platform_toolsets()
    cmds = merge_commands(ts)
    print(f"== {profile or 'default'} fixes={len(cmds)} keys={list(ts)}")
    for cmd in cmds:
        rest = cmd[len("hermes config set "):]
        key, val = rest.split(" ", 1)
        val = val.strip("'")
        argv = ["hermes"]
        if profile:
            argv += ["-p", profile]
        argv += ["config", "set", key, val]
        r = subprocess.run(argv, capture_output=True, text=True)
        print(" ", key, "ok" if r.returncode == 0 else r.stderr.strip()[-200:] or r.stdout.strip()[-200:])

run_sets(None, ROOT)
for d in sorted((ROOT / "profiles").iterdir()):
    if (d / "config.yaml").is_file():
        run_sets(d.name, d)
