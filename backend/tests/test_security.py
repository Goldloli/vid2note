"""
安全模块测试
测试 secure_filename, is_safe_path, get_safe_output_path 等功能
"""
import pytest
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.security import secure_filename, is_safe_path, get_safe_output_path, sanitize_path_component


class TestSecureFilename:
    """测试 secure_filename 函数"""
    
    def test_normal_filename(self):
        """测试正常文件名"""
        assert secure_filename("normal.txt") == "normal.txt"
        assert secure_filename("file_name.md") == "file_name.md"
        assert secure_filename("my-document.pdf") == "my-document.pdf"
    
    def test_path_traversal_prevention(self):
        """测试路径遍历防护"""
        # Unix 风格路径遍历
        assert secure_filename("../../../etc/passwd") == "etc_passwd"
        assert secure_filename("../secret.txt") == "secret.txt"
        assert secure_filename("./file.txt") == "file.txt"
        
        # Windows 风格路径遍历 - 使用原始字符串
        assert secure_filename(r"..\secret.txt") == "secret.txt"
        assert secure_filename(r".\file.txt") == "file.txt"
        assert secure_filename(r"C:\Windows\System32\cmd.exe") == "C_Windows_System32_cmd.exe"
    
    def test_special_characters_removal(self):
        """测试特殊字符移除"""
        assert secure_filename("file<name>.txt") == "filename.txt"
        assert secure_filename('file:name".txt') == "filename.txt"
        assert secure_filename("file|name?.txt") == "filename.txt"
        assert secure_filename("file*name.txt") == "filename.txt"
    
    def test_unicode_normalization(self):
        """测试Unicode规范化"""
        # 测试中日韩字符
        assert secure_filename("中文文件.md") == "中文文件.md"
        assert secure_filename("日本語ファイル.txt") == "日本語ファイル.txt"
        assert secure_filename("한국어파일.pdf") == "한국어파일.pdf"
    
    def test_hidden_file_prevention(self):
        """测试隐藏文件防护"""
        assert secure_filename(".hidden") == "hidden"
        assert secure_filename("..hidden") == "hidden"
        assert secure_filename("...file") == "file"
        assert secure_filename("  .file  ") == "file"
    
    def test_length_limit(self):
        """测试长度限制"""
        long_name = "a" * 300 + ".txt"
        result = secure_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".txt")
    
    def test_empty_filename_raises(self):
        """测试空文件名抛出异常"""
        with pytest.raises(ValueError):
            secure_filename("")
        
        with pytest.raises(ValueError):
            secure_filename(None)
        
        with pytest.raises(ValueError):
            secure_filename("   ")
        
        with pytest.raises(ValueError):
            secure_filename("...")
    
    def test_control_characters_removal(self):
        """测试控制字符移除"""
        assert secure_filename("file\x00name.txt") == "filename.txt"
        assert secure_filename("file\x1fname.txt") == "filename.txt"
        assert secure_filename("file\x7fname.txt") == "filename.txt"
        assert secure_filename("file\x9fname.txt") == "filename.txt"


class TestIsSafePath:
    """测试 is_safe_path 函数"""
    
    def test_safe_paths(self):
        """测试安全路径"""
        base = Path("/app/output")
        assert is_safe_path(base, Path("/app/output/file.md")) == True
        assert is_safe_path(base, Path("/app/output/subdir/file.md")) == True
        assert is_safe_path(base, Path("/app/output")) == True
    
    def test_unsafe_paths(self):
        """测试不安全路径"""
        base = Path("/app/output")
        assert is_safe_path(base, Path("/etc/passwd")) == False
        assert is_safe_path(base, Path("/app/output/../../../etc/passwd")) == False
        assert is_safe_path(base, Path("/other/path")) == False

    def test_sibling_prefix_is_not_treated_as_child(self):
        """目录名仅共享字符串前缀时仍必须拒绝。"""
        base = Path("/app/output")
        assert is_safe_path(base, Path("/app/output-archive/file.md")) is False
        assert is_safe_path(base, Path("/app/output2/file.md")) is False


class TestGetSafeOutputPath:
    """测试 get_safe_output_path 函数"""
    
    def test_safe_output_path(self):
        """测试安全输出路径生成"""
        base = Path("/app/output")
        result = get_safe_output_path(base, "file.txt", ".md")
        assert result == Path("/app/output/file.md")
    
    def test_path_traversal_in_filename(self):
        """测试文件名中的路径遍历"""
        base = Path("/app/output")
        result = get_safe_output_path(base, "../../../etc/passwd", ".md")
        assert result == Path("/app/output/etc_passwd.md")
        assert is_safe_path(base, result) == True
    
    def test_extension_handling(self):
        """测试扩展名处理"""
        base = Path("/app/output")
        # 强制替换扩展名
        result = get_safe_output_path(base, "file.txt", ".md")
        assert result == Path("/app/output/file.md")
        
        # 不带点的扩展名
        result = get_safe_output_path(base, "file", "md")
        assert result == Path("/app/output/file.md")


class TestSanitizePathComponent:
    """测试 sanitize_path_component 函数"""
    
    def test_normal_component(self):
        """测试正常组件"""
        assert sanitize_path_component("folder") == "folder"
        assert sanitize_path_component("my_folder") == "my_folder"
    
    def test_windows_reserved_names(self):
        """测试Windows保留名称"""
        assert sanitize_path_component("CON") == "_CON"
        assert sanitize_path_component("PRN") == "_PRN"
        assert sanitize_path_component("AUX") == "_AUX"
        assert sanitize_path_component("NUL") == "_NUL"
        assert sanitize_path_component("COM1") == "_COM1"
        assert sanitize_path_component("LPT1") == "_LPT1"
    
    def test_empty_component(self):
        """测试空组件"""
        assert sanitize_path_component("") == "_"
        assert sanitize_path_component("   ") == "_"
        assert sanitize_path_component("...") == "_"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
