from pathlib import Path

import pytest
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.paths import RuntimePaths
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.db import Database
from vid2note_core.storage.upload_store import UploadStore


def test_runtime_paths_derive_every_directory_from_data_root(tmp_path: Path) -> None:
    paths = RuntimePaths.from_data_root(tmp_path / "data")

    assert paths.database == tmp_path / "data" / "vault" / ".vid2note" / "state.sqlite3"
    assert paths.tasks == tmp_path / "data" / "tasks"
    assert paths.uploads == tmp_path / "data" / "uploads"
    assert paths.models == tmp_path / "data" / "models"
    assert paths.config == tmp_path / "data" / "config.yaml"
    assert paths.vault == tmp_path / "data" / "vault"


@pytest.mark.parametrize("factory", [Database, ArtifactStore, UploadStore, ModelManager])
def test_runtime_storage_requires_an_explicit_path(factory) -> None:
    Database.reset_instance()
    with pytest.raises(TypeError):
        factory()
