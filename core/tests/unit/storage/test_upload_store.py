"""UploadStore 单元测试"""

from pathlib import Path

import pytest
from vid2note_core.storage.upload_store import UploadStore
from vid2note_core.utils.security import validate_file_id


@pytest.fixture
def store(tmp_path):
    return UploadStore(base_dir=tmp_path)


def test_generate_file_id_format():
    fid = UploadStore.generate_file_id()
    assert validate_file_id(fid), f"file_id 格式不合法: {fid}"
    # 唯一性
    assert UploadStore.generate_file_id() != UploadStore.generate_file_id()


def test_save_and_get(store):
    fid = UploadStore.generate_file_id()
    path = store.save(fid, "notes.srt", b"1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    assert path.exists()
    assert store.exists(fid)
    assert store.get_name(fid) == "notes.srt"
    assert store.get_path(fid).read_bytes() == b"1\n00:00:00,000 --> 00:00:01,000\nhi\n"


def test_save_sanitizes_filename(store):
    """危险文件名被清理（防路径遍历）"""
    fid = UploadStore.generate_file_id()
    path = store.save(fid, "../../etc/passwd", b"x")
    # 文件名应被清理，且落在 file_id 目录内（不逃逸）
    assert path.parent == Path(store.base_dir) / fid
    assert ".." not in path.name
    assert store.get_name(fid) != "../../etc/passwd"


def test_save_empty_filename(store):
    fid = UploadStore.generate_file_id()
    path = store.save(fid, "", b"x")
    assert path.name == "unnamed"


def test_get_nonexistent(store):
    assert store.get_path("file_000000000000") is None
    assert store.get_name("file_000000000000") is None
    assert store.exists("file_000000000000") is False


def test_delete(store):
    fid = UploadStore.generate_file_id()
    store.save(fid, "a.txt", b"x")
    assert store.delete(fid) is True
    assert store.exists(fid) is False
    # 重复删除返回 False
    assert store.delete(fid) is False


def test_illegal_file_id_rejected(store):
    with pytest.raises(ValueError):
        store._file_dir("../escape")
    with pytest.raises(ValueError):
        store._file_dir("not_a_file_id")
    with pytest.raises(ValueError):
        store._file_dir("file_x/y")


def test_overwrite_same_name(store):
    """同名再次上传覆盖旧内容"""
    fid = UploadStore.generate_file_id()
    store.save(fid, "a.srt", b"old")
    store.save(fid, "a.srt", b"new")
    assert store.get_path(fid).read_bytes() == b"new"
