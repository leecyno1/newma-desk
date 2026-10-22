import subprocess
import sys
import os
from pathlib import Path


def test_standalone_serves_deep_links_and_preserves_api(tmp_path):
    (tmp_path / "index.html").write_text("<html>research</html>")
    code = '''
import sys
from fastapi.testclient import TestClient
from standalone import create_app
app = create_app(sys.argv[1])
with TestClient(app) as client:
    assert client.get('/api/health').json()['ok'] is True
    for route in ('/', '/earnings-workbench', '/sectors/hbm', '/mod-runtime/research/valuation-workbench'):
        assert client.get(route).text == '<html>research</html>'
    assert client.get('/missing.js').status_code == 404
    assert any(getattr(route, 'path', '') == '/api/chat' for route in app.routes)
'''
    subprocess.run([sys.executable, "-c", code, str(tmp_path)],
                   cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
                   check=True, capture_output=True, text=True, timeout=30)
