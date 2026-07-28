import urllib.request
try:
    r = urllib.request.urlopen("http://localhost:8501", timeout=5)
    exit(0)
except:
    exit(1)