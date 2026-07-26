"""
速率限制器配置
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# 创建全局速率限制器实例
# 使用IP地址作为限制键
limiter = Limiter(key_func=get_remote_address)
