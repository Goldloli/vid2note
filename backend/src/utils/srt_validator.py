"""
SRT字幕文件验证器
提供SRT格式验证和安全检查功能
"""
import re
from pathlib import Path
from typing import List
from dataclasses import dataclass


@dataclass
class SRTValidationResult:
    """SRT验证结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    entry_count: int
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class SRTValidator:
    """SRT字幕文件验证器"""
    
    # SRT时间戳格式: HH:MM:SS,mmm --> HH:MM:SS,mmm
    TIMESTAMP_PATTERN = re.compile(
        r'^(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})$'
    )
    
    # 序号格式
    SEQUENCE_PATTERN = re.compile(r'^\d+$')
    
    # 最大允许的字幕条目数
    MAX_ENTRIES = 100000
    
    # 最大允许的文件大小 (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    # 最大单行长度
    MAX_LINE_LENGTH = 5000
    
    @classmethod
    def validate_file(cls, file_path: str | Path) -> SRTValidationResult:
        """
        验证SRT文件格式
        
        Args:
            file_path: SRT文件路径
            
        Returns:
            SRTValidationResult: 验证结果
        """
        file_warnings = []  # 文件级别的警告
        
        path = Path(file_path)
        
        # 检查文件是否存在
        if not path.exists():
            return SRTValidationResult(
                is_valid=False,
                errors=[f"文件不存在: {file_path}"],
                warnings=[],
                entry_count=0
            )
        
        # 检查是否为文件
        if not path.is_file():
            return SRTValidationResult(
                is_valid=False,
                errors=[f"路径不是文件: {file_path}"],
                warnings=[],
                entry_count=0
            )
        
        # 检查文件大小
        file_size = path.stat().st_size
        if file_size > cls.MAX_FILE_SIZE:
            return SRTValidationResult(
                is_valid=False,
                errors=[f"文件大小超过限制: {file_size} bytes (最大允许: {cls.MAX_FILE_SIZE} bytes)"],
                warnings=[],
                entry_count=0
            )
        
        if file_size == 0:
            return SRTValidationResult(
                is_valid=False,
                errors=["文件为空"],
                warnings=[],
                entry_count=0
            )
        
        # 检查扩展名
        if path.suffix.lower() != '.srt':
            file_warnings.append(f"文件扩展名不是.srt: {path.suffix}")
        
        # 读取并验证内容
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                # 尝试其他编码
                with open(path, 'r', encoding='latin-1') as f:
                    content = f.read()
                file_warnings.append("文件使用非UTF-8编码，建议转换为UTF-8")
            except Exception as e:
                return SRTValidationResult(
                    is_valid=False,
                    errors=[f"无法读取文件编码: {str(e)}"],
                    warnings=file_warnings,
                    entry_count=0
                )
        except Exception as e:
            return SRTValidationResult(
                is_valid=False,
                errors=[f"读取文件失败: {str(e)}"],
                warnings=file_warnings,
                entry_count=0
            )
        
        # 验证内容结构
        content_result = cls.validate_content(content)
        
        # 合并文件级别警告和内容级别警告
        all_warnings = file_warnings + content_result.warnings
        
        return SRTValidationResult(
            is_valid=content_result.is_valid,
            errors=content_result.errors,
            warnings=all_warnings,
            entry_count=content_result.entry_count
        )
    
    @classmethod
    def validate_content(cls, content: str) -> SRTValidationResult:
        """
        验证SRT内容格式
        
        Args:
            content: SRT文件内容
            
        Returns:
            SRTValidationResult: 验证结果
        """
        errors = []
        warnings = []
        entry_count = 0
        
        if not content or not content.strip():
            return SRTValidationResult(
                is_valid=False,
                errors=["内容为空"],
                warnings=[],
                entry_count=0
            )
        
        # 检查内容长度
        if len(content) > cls.MAX_FILE_SIZE:
            return SRTValidationResult(
                is_valid=False,
                errors=[f"内容长度超过限制: {len(content)} 字符"],
                warnings=[],
                entry_count=0
            )
        
        # 按空行分割条目
        entries = re.split(r'\n\s*\n', content.strip())
        
        if not entries:
            return SRTValidationResult(
                is_valid=False,
                errors=["没有找到有效的字幕条目"],
                warnings=[],
                entry_count=0
            )
        
        expected_sequence = 1
        
        for i, entry in enumerate(entries, 1):
            entry = entry.strip()
            if not entry:
                continue
            
            lines = entry.split('\n')
            if not lines:
                continue
            
            # 验证序号
            if not lines[0].strip().isdigit():
                errors.append(f"第 {i} 个条目: 缺少有效的序号")
                continue
            
            sequence = int(lines[0].strip())
            if sequence != expected_sequence:
                warnings.append(f"第 {i} 个条目: 序号不连续，期望 {expected_sequence}，实际 {sequence}")
            expected_sequence = sequence + 1
            
            # 验证时间戳行
            if len(lines) < 2:
                errors.append(f"条目 {sequence}: 缺少时间戳行")
                continue
            
            timestamp_line = lines[1].strip()
            if not cls.TIMESTAMP_PATTERN.match(timestamp_line):
                errors.append(f"条目 {sequence}: 时间戳格式无效: {timestamp_line[:50]}...")
                continue
            
            # 解析时间戳
            match = cls.TIMESTAMP_PATTERN.match(timestamp_line)
            if match:
                start_h, start_m, start_s, start_ms, end_h, end_m, end_s, end_ms = map(int, match.groups())
                
                # 验证时间范围
                if not (0 <= start_m < 60 and 0 <= start_s < 60 and 0 <= end_m < 60 and 0 <= end_s < 60):
                    errors.append(f"条目 {sequence}: 时间值超出有效范围")
                    continue
                
                # 验证结束时间 > 开始时间
                start_ms_total = start_h * 3600000 + start_m * 60000 + start_s * 1000 + start_ms
                end_ms_total = end_h * 3600000 + end_m * 60000 + end_s * 1000 + end_ms
                
                if end_ms_total <= start_ms_total:
                    errors.append(f"条目 {sequence}: 结束时间必须大于开始时间")
                    continue
                
                # 检查时长是否合理（不超过10小时）
                if end_ms_total > 36000000:  # 10小时
                    warnings.append(f"条目 {sequence}: 时间戳超过10小时，请确认是否正确")
            
            # 验证文本内容
            if len(lines) < 3:
                warnings.append(f"条目 {sequence}: 没有文本内容")
            else:
                text_lines = lines[2:]
                for line in text_lines:
                    if len(line) > cls.MAX_LINE_LENGTH:
                        warnings.append(f"条目 {sequence}: 单行文本过长 ({len(line)} 字符)")
            
            entry_count += 1
            
            # 检查条目数限制
            if entry_count > cls.MAX_ENTRIES:
                errors.append(f"条目数超过最大限制 {cls.MAX_ENTRIES}")
                break
        
        # 如果没有找到任何有效条目，标记为无效
        if entry_count == 0 and not errors:
            errors.append("没有找到有效的字幕条目")
        
        return SRTValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            entry_count=entry_count
        )
    
    @classmethod
    def is_valid_srt(cls, file_path: str | Path) -> bool:
        """
        快速检查文件是否为有效的SRT文件
        
        Args:
            file_path: SRT文件路径
            
        Returns:
            bool: 是否为有效的SRT文件
        """
        result = cls.validate_file(file_path)
        return result.is_valid
    
    @classmethod
    def get_validation_summary(cls, result: SRTValidationResult) -> str:
        """
        获取验证结果的摘要信息
        
        Args:
            result: 验证结果
            
        Returns:
            摘要字符串
        """
        if result.is_valid:
            summary = f"✓ SRT文件验证通过，共 {result.entry_count} 个字幕条目"
            if result.warnings:
                summary += f"，{len(result.warnings)} 个警告"
        else:
            summary = f"✗ SRT文件验证失败，共 {len(result.errors)} 个错误"
            if result.warnings:
                summary += f"，{len(result.warnings)} 个警告"
        
        return summary
