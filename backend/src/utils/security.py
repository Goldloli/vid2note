"""
安全工具函数模块
提供文件名安全处理、路径验证等安全相关功能
"""
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional


def secure_filename(filename: str, max_length: int = 255) -> str:
    """
    将文件名转换为安全的格式，防止路径遍历攻击
    
    处理逻辑:
    1. 规范化Unicode字符(NFKC)
    2. 移除路径分隔符和特殊字符
    3. 移除控制字符
    4. 防止空文件名和隐藏文件
    5. 限制文件名长度
    
    Args:
        filename: 原始文件名
        max_length: 最大文件名长度，默认255
        
    Returns:
        安全的文件名
        
    Raises:
        ValueError: 如果文件名为空或只包含特殊字符
        
    Examples:
        >>> secure_filename("../../../etc/passwd")
        'etc_passwd'
        >>> secure_filename("file<s>name.txt")
        'filename.txt'
        >>> secure_filename(".hidden_file")
        'hidden_file'
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("文件名不能为空")
    
    # 规范化Unicode字符
    filename = unicodedata.normalize('NFKC', filename)
    
    # 首先将所有反斜杠替换为正斜杠，统一处理
    filename = filename.replace('\\', '/')
    
    # 移除路径遍历模式
    # 处理 ../ ./ .. ./ 等路径遍历模式
    while '/../' in filename or '/./' in filename:
        filename = filename.replace('/../', '/').replace('/./', '/')
    
    # 处理开头的 ../ 和 ./ 
    while filename.startswith('../') or filename.startswith('./'):
        if filename.startswith('../'):
            filename = filename[3:]
        elif filename.startswith('./'):
            filename = filename[2:]
    
    # 处理连续的多个点
    filename = re.sub(r'\.{2,}/', '', filename)
    
    # 移除所有路径分隔符，替换为下划线
    filename = filename.replace('/', '_')
    
    # 移除控制字符 (0x00-0x1f 和 0x7f-0x9f)
    filename = ''.join(char for char in filename if ord(char) > 31 and ord(char) not in range(127, 160))
    
    # 移除危险字符: < > : " | ? * 
    # 这些字符在Windows和Unix系统中都有特殊含义
    filename = re.sub(r'[<>:"|?*]', '', filename)
    
    # 移除前导和尾随的点和空格（防止隐藏文件和文件名混淆）
    filename = filename.strip('. ')
    
    # 如果文件名为空，使用默认名称
    if not filename:
        raise ValueError("文件名无效，清理后为空")
    
    # 限制长度，保留扩展名
    if len(filename) > max_length:
        # 尝试保留扩展名
        path = Path(filename)
        suffix = path.suffix
        stem = path.stem
        
        # 计算可用的stem长度
        available_length = max_length - len(suffix)
        if available_length < 1:
            # 扩展名太长，直接截断整个文件名
            filename = filename[:max_length]
        else:
            filename = stem[:available_length] + suffix
    
    return filename


def is_safe_path(base_path: Path, target_path: Path) -> bool:
    """
    验证目标路径是否在基础路径内，防止路径遍历
    
    Args:
        base_path: 基础安全路径
        target_path: 要验证的目标路径
        
    Returns:
        True如果目标路径在基础路径内，否则False
        
    Examples:
        >>> is_safe_path(Path("/app/output"), Path("/app/output/file.md"))
        True
        >>> is_safe_path(Path("/app/output"), Path("/etc/passwd"))
        False
        >>> is_safe_path(Path("/app/output"), Path("/app/output/../../../etc/passwd"))
        False
    """
    try:
        # 先做纯词法规范化，不在完成边界校验前对不可信路径触发文件系统解析。
        # Path.relative_to 按路径组件比较，避免 ``/output-evil`` 被字符串前缀
        # 误判为 ``/output`` 的子目录。
        base = Path(os.path.abspath(os.fspath(base_path)))
        target = Path(os.path.abspath(os.fspath(target_path)))
        target.relative_to(base)
        return True
    except (OSError, TypeError, ValueError):
        return False


def get_safe_output_path(
    base_dir: Path,
    filename: str,
    extension: Optional[str] = None
) -> Path:
    """
    生成安全的输出文件路径
    
    Args:
        base_dir: 基础输出目录
        filename: 原始文件名（不含扩展名或含扩展名）
        extension: 可选的强制扩展名
        
    Returns:
        安全的完整路径
        
    Raises:
        ValueError: 如果生成的路径不安全
    """
    # 安全化文件名
    safe_name = secure_filename(filename)
    
    # 如果指定了扩展名，替换原有扩展名
    if extension:
        # 确保扩展名以点开头
        if not extension.startswith('.'):
            extension = '.' + extension
        safe_name = Path(safe_name).stem + extension
    
    # 构建完整路径
    output_path = base_dir / safe_name
    
    # 验证路径安全
    if not is_safe_path(base_dir, output_path):
        raise ValueError(f"生成的路径不安全: {output_path}")
    
    return output_path


def sanitize_path_component(component: str) -> str:
    """
    清理路径组件（目录名或文件名）
    
    Args:
        component: 路径组件
        
    Returns:
        清理后的路径组件
    """
    if not component:
        return '_'
    
    # 规范化Unicode
    component = unicodedata.normalize('NFKC', component)
    
    # 移除路径分隔符
    component = component.replace('/', '_').replace('\\', '_')
    
    # 移除控制字符
    component = ''.join(char for char in component if ord(char) > 31 and ord(char) not in range(127, 160))
    
    # 移除特殊字符
    component = re.sub(r'[<>:"|?*]', '', component)
    
    # 移除前导和尾随的点和空格
    component = component.strip('. ')
    
    # 处理保留名称（Windows）
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
        'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4',
        'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    upper_component = component.upper()
    if upper_component in reserved_names or any(upper_component.startswith(f"{name}.") for name in reserved_names):
        component = f"_{component}"
    
    # 如果为空，使用下划线
    if not component:
        component = '_'
    
    return component[:255]  # 限制长度
