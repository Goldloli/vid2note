"""
SRT验证器测试
测试 SRTValidator 的验证功能
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.srt_validator import SRTValidator, SRTValidationResult


class TestSRTValidator:
    """测试SRT验证器"""
    
    def test_valid_srt_content(self):
        """测试有效的SRT内容"""
        content = """1
00:00:01,000 --> 00:00:04,000
Hello, world!

2
00:00:05,000 --> 00:00:08,000
This is a test subtitle."""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is True
        assert result.entry_count == 2
        assert len(result.errors) == 0
    
    def test_empty_content(self):
        """测试空内容"""
        result = SRTValidator.validate_content("")
        assert result.is_valid is False
        assert "内容为空" in result.errors[0]
    
    def test_invalid_timestamp_format(self):
        """测试无效的时间戳格式"""
        content = """1
00:00:01.000 --> 00:00:04.000
Invalid timestamp uses dot instead of comma."""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is False
        assert any("时间戳格式无效" in error for error in result.errors)
    
    def test_missing_sequence_number(self):
        """测试缺少序号"""
        content = """00:00:01,000 --> 00:00:04,000
Missing sequence number."""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is False
        assert any("序号" in error for error in result.errors)
    
    def test_end_time_before_start_time(self):
        """测试结束时间在开始时间之前"""
        content = """1
00:00:05,000 --> 00:00:01,000
End time is before start time."""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is False
        assert any("结束时间必须大于开始时间" in error for error in result.errors)
    
    def test_non_sequential_numbers(self):
        """测试不连续的序号（应该是警告，不是错误）"""
        content = """1
00:00:01,000 --> 00:00:04,000
First subtitle.

3
00:00:05,000 --> 00:00:08,000
Third subtitle with missing 2."""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is True  # 不连续是警告，不是错误
        assert any("序号不连续" in warning for warning in result.warnings)
    
    def test_chinese_content(self):
        """测试中文内容"""
        content = """1
00:00:01,000 --> 00:00:04,000
你好，世界！

2
00:00:05,000 --> 00:00:08,000
这是一段测试字幕。"""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is True
        assert result.entry_count == 2
    
    def test_multiline_text(self):
        """测试多行文本"""
        content = """1
00:00:01,000 --> 00:00:04,000
Line 1
Line 2
Line 3"""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is True
        assert result.entry_count == 1


class TestSRTFileValidation:
    """测试SRT文件验证"""
    
    def test_valid_srt_file(self):
        """测试有效的SRT文件"""
        content = """1
00:00:01,000 --> 00:00:04,000
Hello, world!

2
00:00:05,000 --> 00:00:08,000
This is a test subtitle."""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
            f.write(content)
            temp_path = f.name
        
        try:
            result = SRTValidator.validate_file(temp_path)
            assert result.is_valid is True
            assert result.entry_count == 2
        finally:
            os.unlink(temp_path)
    
    def test_nonexistent_file(self):
        """测试不存在的文件"""
        result = SRTValidator.validate_file("/nonexistent/path/file.srt")
        assert result.is_valid is False
        assert any("文件不存在" in error for error in result.errors)
    
    def test_empty_file(self):
        """测试空文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
            f.write("")
            temp_path = f.name
        
        try:
            result = SRTValidator.validate_file(temp_path)
            assert result.is_valid is False
            assert any("文件为空" in error for error in result.errors)
        finally:
            os.unlink(temp_path)
    
    def test_wrong_extension(self):
        """测试错误的扩展名（应该是警告，不是错误）"""
        content = """1
00:00:01,000 --> 00:00:04,000
Hello!"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(content)
            temp_path = f.name
        
        try:
            result = SRTValidator.validate_file(temp_path)
            assert result.is_valid is True
            assert any("扩展名不是.srt" in warning for warning in result.warnings)
        finally:
            os.unlink(temp_path)
    
    def test_is_valid_srt_quick_check(self):
        """测试快速检查函数"""
        content = """1
00:00:01,000 --> 00:00:04,000
Hello!"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
            f.write(content)
            temp_path = f.name
        
        try:
            assert SRTValidator.is_valid_srt(temp_path) is True
        finally:
            os.unlink(temp_path)
    
    def test_get_validation_summary(self):
        """测试验证摘要"""
        # 有效结果
        valid_result = SRTValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            entry_count=10
        )
        summary = SRTValidator.get_validation_summary(valid_result)
        assert "验证通过" in summary
        assert "10 个字幕条目" in summary
        
        # 无效结果
        invalid_result = SRTValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
            entry_count=0
        )
        summary = SRTValidator.get_validation_summary(invalid_result)
        assert "验证失败" in summary
        assert "2 个错误" in summary
        assert "1 个警告" in summary


class TestEdgeCases:
    """测试边界情况"""
    
    def test_very_long_line(self):
        """测试超长行"""
        long_text = "A" * 6000
        content = f"""1
00:00:01,000 --> 00:00:04,000
{long_text}"""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is True
        assert any("单行文本过长" in warning for warning in result.warnings)
    
    def test_no_text_content(self):
        """测试没有文本内容"""
        content = """1
00:00:01,000 --> 00:00:04,000"""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is True
        assert any("没有文本内容" in warning for warning in result.warnings)
    
    def test_invalid_time_values(self):
        """测试无效的时间值"""
        content = """1
00:90:01,000 --> 00:00:04,000
Invalid minutes."""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is False
        assert any("时间值超出有效范围" in error for error in result.errors)
    
    def test_very_long_duration(self):
        """测试超长的时长（应该是警告）"""
        content = """1
00:00:01,000 --> 15:00:00,000
Very long duration."""
        
        result = SRTValidator.validate_content(content)
        assert result.is_valid is True
        assert any("超过10小时" in warning for warning in result.warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
