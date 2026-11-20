import json
from pathlib import Path


def test_vercel_serves_only_the_frontend_spa():
    repo_root = Path(__file__).resolve().parents[2]
    config = json.loads((repo_root / "vercel.json").read_text(encoding="utf-8"))
    assert config["outputDirectory"] == "Frontend/dist"
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/index.html"}]
    assert all("api" not in rewrite["source"].lower() for rewrite in config["rewrites"])
