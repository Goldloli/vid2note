from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.config.manager import ConfigManager
from vid2note_core.media.service import MediaService
from vid2note_core.paths import RuntimePaths
from vid2note_core.source.registrar import SourceRegistrar
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.db import Database
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.storage.upload_store import UploadStore
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.vault.watcher import VaultWatcher
from vid2note_core.wiki.applier import ChangeSetApplier
from vid2note_core.wiki.store import ChangeSetStore
from vid2note_core.wiki.validator import ChangeSetValidator
from vid2note_core.worker import TaskWorker


@dataclass(slots=True)
class Services:
    paths: RuntimePaths
    database: Database
    tasks: TaskRepository
    artifacts: ArtifactStore
    uploads: UploadStore
    models: ModelManager
    config: ConfigManager
    vault_layout: VaultLayout
    vault: VaultRepository
    source_registrar: SourceRegistrar
    media: MediaService
    watcher: VaultWatcher
    changesets: ChangeSetStore
    validator: ChangeSetValidator
    applier: ChangeSetApplier
    worker: TaskWorker


def build_services(paths: RuntimePaths) -> Services:
    database = Database(paths.database)
    tasks = TaskRepository(database)
    artifacts = ArtifactStore(paths.tasks)
    uploads = UploadStore(paths.uploads)
    models = ModelManager(paths.models)
    config = ConfigManager(paths.config)
    vault_layout = VaultLayout.initialize(paths.vault)
    vault = VaultRepository(vault_layout)
    source_registrar = SourceRegistrar(vault_layout)
    media = MediaService(vault_layout)
    watcher = VaultWatcher(vault_layout)
    changesets = ChangeSetStore(vault_layout.root)
    validator = ChangeSetValidator(vault_layout, vault)
    applier = ChangeSetApplier(vault_layout, vault, changesets, validator)
    vault.internal_edit_observer = watcher.ignore
    source_registrar.internal_edit_observer = watcher.ignore
    applier.internal_edit_observer = watcher.ignore
    worker = TaskWorker(
        tasks,
        artifacts,
        uploads=uploads,
        models=models,
        source_registrar=source_registrar,
        vault=vault,
        changesets=changesets,
        applier=applier,
        autonomy_mode_provider=lambda: config.load().autonomy_mode,
    )
    return Services(
        paths,
        database,
        tasks,
        artifacts,
        uploads,
        models,
        config,
        vault_layout,
        vault,
        source_registrar,
        media,
        watcher,
        changesets,
        validator,
        applier,
        worker,
    )


def get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


ServicesDependency = Annotated[Services, Depends(get_services)]
