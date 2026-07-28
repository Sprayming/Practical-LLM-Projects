import urllib.request
import time
import sys

for i in range(5):
    try:
        r = urllib.request.urlopen("http://localhost:8501", timeout=5)
        # DON"T use exit() inside try - it raises SystemExit caught by bare except!
        if r.status == 200:
            sys.exit(0)
    except Exception as e:
        if i < 4:
            time.sleep(2)
        continue

sys.exit(1)