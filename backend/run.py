#!/usr/bin/env python3
"""
启动脚本 - 课程字幕整理工具后端服务
"""
import os
import sys

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.main import app, PORT, HOST, DEBUG
import uvicorn

if __name__ == "__main__":
    print("=" * 50)
    print("课程字幕整理工具 - 后端服务")
    print("=" * 50)
    print(f"服务地址: http://{HOST}:{PORT}")
    print(f"API文档: http://{HOST}:{PORT}/docs")
    print(f"调试模式: {DEBUG}")
    print("=" * 50)
    
    uvicorn.run(
        "src.main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info"
    )
