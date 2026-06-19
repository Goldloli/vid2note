#!/usr/bin/env python3
import json
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else "echo"
prompt = sys.stdin.read()
if mode == "echo":
    print(json.dumps({"prompt": prompt}), flush=True)
elif mode == "sleep":
    time.sleep(30)
elif mode == "crash":
    sys.stderr.write("API_KEY=super-secret " + "x" * 70000)
    raise SystemExit(7)
