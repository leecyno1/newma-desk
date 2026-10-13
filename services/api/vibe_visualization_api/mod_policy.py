"""Managed deployment adapter; standalone/local Desk retains its own ownership."""
import importlib.util
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def _module():
    spec = importlib.util.spec_from_file_location('newma_shared_mod_policy', '/opt/newma-policy/newma_mod_policy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_mod_publication(connection, manifests, error_type):
    if not Path('/etc/newma/mod-policy.json').exists():
        return
    try:
        _module().check_repository_transition(connection, manifests, error_type)
    except error_type:
        raise
    except Exception as error:
        raise error_type('会员权益暂时无法核验，请稍后重试。已有模组可继续使用。') from error
