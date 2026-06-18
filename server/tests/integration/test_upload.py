"""上传 API 集成测试

覆盖 SRT/PDF/TXT 上传成功、类型拒绝、大小限制、空文件、file_id 可用性。
UploadStore 落盘目录被 monkeypatch 到 tmp_path 隔离。
"""

import io

from vid2note_core.utils.security import validate_file_id


def test_upload_srt_success(client):
    content = "1\n00:00:00,000 --> 00:00:01,000\n你好\n"
    resp = client.post(
        "/api/v1/upload/srt",
        files={"file": ("notes.srt", io.BytesIO(content.encode("utf-8")), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert validate_file_id(data["file_id"])
    assert data["filename"] == "notes.srt"
    assert data["size"] == len(content.encode("utf-8"))
    # 文件确实落盘
    store = client.app.state.services.uploads
    path = store.get_path(data["file_id"])
    assert path is not None
    assert path.read_bytes() == content.encode("utf-8")


def test_upload_pdf_success(client):
    resp = client.post(
        "/api/v1/upload/pdf",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert resp.status_code == 200
    assert validate_file_id(resp.json()["file_id"])


def test_upload_txt_success(client):
    resp = client.post(
        "/api/v1/upload/txt",
        files={"file": ("raw.txt", io.BytesIO("纯文本".encode()), "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["filename"] == "raw.txt"


def test_upload_wrong_extension_rejected(client):
    """srt 端点拒绝 .pdf 文件"""
    resp = client.post(
        "/api/v1/upload/srt",
        files={"file": ("notes.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert resp.status_code == 400


def test_upload_no_extension_rejected(client):
    """无扩展名拒绝"""
    resp = client.post(
        "/api/v1/upload/srt",
        files={"file": ("noext", io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_empty_file_rejected(client):
    """空文件拒绝"""
    resp = client.post(
        "/api/v1/upload/txt",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_size_limit(client, monkeypatch):
    """超过大小限制拒绝（临时把限制调小便于测试）"""
    from vid2note_server.api import upload as upload_mod

    # 直接 patch MAX_SIZE 为很小值
    monkeypatch.setattr(upload_mod, "MAX_SIZE", 10)
    resp = client.post(
        "/api/v1/upload/txt",
        files={"file": ("big.txt", io.BytesIO(b"x" * 100), "text/plain")},
    )
    assert resp.status_code == 413


def test_uploaded_file_id_persists_and_retrievable(client):
    """上传后 file_id 可被 UploadStore 取回"""
    resp = client.post(
        "/api/v1/upload/srt",
        files={"file": ("a.srt", io.BytesIO(b"srt content"), "text/plain")},
    )
    fid = resp.json()["file_id"]
    store = client.app.state.services.uploads
    assert store.exists(fid)
    assert store.get_name(fid) == "a.srt"


def test_upload_filename_traversal_sanitized(client):
    """恶意文件名被清理，不逃逸出 uploads 目录"""
    resp = client.post(
        "/api/v1/upload/txt",
        files={"file": ("../../etc/passwd.txt", io.BytesIO(b"secret"), "text/plain")},
    )
    assert resp.status_code == 200
    fid = resp.json()["file_id"]
    store = client.app.state.services.uploads
    path = store.get_path(fid)
    # 路径必须在 uploads 目录内
    assert path.parent == store.base_dir / fid
    assert ".." not in path.name
