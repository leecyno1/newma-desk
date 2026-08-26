from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet


class SecretVault:
    def __init__(self, key_path: Path, master_key: str | bytes | None = None) -> None:
        self.key_path = key_path
        if master_key is not None:
            key = master_key.encode("ascii") if isinstance(master_key, str) else master_key
            self.source = "environment"
        else:
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.key_path.exists():
                self.key_path.write_bytes(Fernet.generate_key())
            os.chmod(self.key_path, 0o600)
            key = self.key_path.read_bytes().strip()
            self.source = "file"
        self._fernet = Fernet(key)
        self.key_id = hashlib.sha256(key).hexdigest()[:12]

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")

    def describe(self) -> dict[str, str]:
        return {"backend": self.source, "key_id": self.key_id}
