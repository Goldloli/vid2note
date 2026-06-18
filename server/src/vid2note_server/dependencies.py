from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request
from vid2note_core.asr.local.model_manager import ModelManager
from vid2note_core.config.manager import ConfigManager
from vid2note_core.paths import RuntimePaths
from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.storage.db import Database
from vid2note_core.storage.task_repo import TaskRepository
from vid2note_core.storage.upload_store import UploadStore
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
    worker: TaskWorker


def build_services(paths: RuntimePaths) -> Services:
    database = Database(paths.database)
    tasks = TaskRepository(database)
    artifacts = ArtifactStore(paths.tasks)
    uploads = UploadStore(paths.uploads)
    models = ModelManager(paths.models)
    config = ConfigManager(paths.config)
    worker = TaskWorker(tasks, artifacts)
    return Services(paths, database, tasks, artifacts, uploads, models, config, worker)


def get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


ServicesDependency = Annotated[Services, Depends(get_services)]
