from dataclasses import replace

from vid2note_core.config.manager import ConfigManager
from vid2note_core.paths import RuntimePaths
from vid2note_core.storage.db import Database
from vid2note_server.dependencies import build_services


def test_build_services_uses_configured_external_vault(tmp_path):
    paths = RuntimePaths.from_data_root(tmp_path / "data")
    external_vault = tmp_path / "knowledge"
    manager = ConfigManager(paths.config)
    config = manager.load()
    config.workspace.vault_path = str(external_vault)
    manager.save(config)

    Database.reset_instance()
    services = build_services(paths)
    try:
        assert services.vault_layout.root == external_vault.resolve()
        assert services.paths == replace(
            paths,
            vault=external_vault.resolve(),
            database=external_vault.resolve() / ".vid2note" / "state.sqlite3",
        )
    finally:
        Database.reset_instance()
