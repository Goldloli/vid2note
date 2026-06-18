"""产物文件系统存储"""

from pathlib import Path

from vid2note_core.types import NodeName

# 节点拓扑顺序（用于判断上下游）
_NODE_ORDER = [
    NodeName.DOWNLOAD,
    NodeName.EXTRACT_AUDIO,
    NodeName.TRANSCRIBE,
    NodeName.ORGANIZE,
    NodeName.MINDMAP,
    NodeName.CLEANUP,
]


class ArtifactStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, task_id: str) -> Path:
        return self.base_dir / task_id

    def ensure_task_dir(self, task_id: str) -> Path:
        d = self._task_dir(task_id)
        (d / "artifacts").mkdir(parents=True, exist_ok=True)
        (d / "logs").mkdir(parents=True, exist_ok=True)
        return d

    def artifact_path(self, task_id: str, node: str, name: str) -> Path:
        return self._task_dir(task_id) / "artifacts" / f"{node}_{name}"

    def write_artifact(self, task_id: str, node: str, name: str, data: bytes) -> Path:
        self.ensure_task_dir(task_id)
        path = self.artifact_path(task_id, node, name)
        path.write_bytes(data)
        return path

    def read_artifact(self, task_id: str, node: str, name: str) -> bytes:
        path = self.artifact_path(task_id, node, name)
        return path.read_bytes()

    def delete_artifact(self, task_id: str, node: str, name: str) -> None:
        path = self.artifact_path(task_id, node, name)
        if path.exists():
            path.unlink()

    def delete_downstream(self, task_id: str, from_node: str) -> None:
        """删除 from_node 及其下游的所有产物"""
        try:
            idx = _NODE_ORDER.index(NodeName(from_node))
        except ValueError:
            return
        targets = _NODE_ORDER[idx:]
        task_dir = self._task_dir(task_id) / "artifacts"
        if not task_dir.exists():
            return
        for f in task_dir.iterdir():
            for node in targets:
                if f.name.startswith(f"{node.value}_"):
                    f.unlink()
                    break

    def list_artifacts(self, task_id: str) -> list[Path]:
        d = self._task_dir(task_id) / "artifacts"
        if not d.exists():
            return []
        return list(d.iterdir())

    def exists(self, task_id: str, node: str, name: str) -> bool:
        return self.artifact_path(task_id, node, name).exists()
