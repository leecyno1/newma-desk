from pathlib import Path

import pytest

from vibe_visualization_api import mod_policy
from vibe_visualization_api.control_plane.repository import ModuleRepository, InvalidModuleStateError


@pytest.mark.parametrize('operation', ['publish', 'install_batch', 'rollback'])
def test_publication_gate_is_atomic(monkeypatch, tmp_path: Path, operation):
    repo = ModuleRepository(tmp_path / 'registry.db')
    manifest = {'id': 'test-page', 'version': '1', 'navigation': {'project': {'id': 'test-project'}}}
    monkeypatch.setattr(mod_policy, 'check_mod_publication', lambda *args: None)
    first = repo.create_draft(manifest)
    repo.publish(first.module_id, first.revision)
    second = repo.create_draft({**manifest, 'version': '2'})
    if operation == 'rollback':
        repo.publish(second.module_id, second.revision)
    before = repo.list_published()

    def reject(connection, manifests, error_type):
        assert connection.in_transaction
        assert manifests[0]['navigation']['project']['id'] == 'test-project'
        raise error_type('quota exceeded')

    monkeypatch.setattr(mod_policy, 'check_mod_publication', reject)
    with pytest.raises(InvalidModuleStateError, match='quota exceeded'):
        if operation == 'publish':
            repo.publish(second.module_id, second.revision)
        elif operation == 'rollback':
            repo.rollback(first.module_id, first.revision)
        else:
            repo.install_batch([{**manifest, 'version': '3'}])
    assert repo.list_published() == before
