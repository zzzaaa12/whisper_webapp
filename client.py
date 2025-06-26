#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whisper WebApp Python Client
用於發送 YouTube URL 到 Whisper WebApp 並獲取處理狀態
"""

import requests
import json
import time
import sys
from typing import Dict, Optional, Union

class WhisperClient:
    """Whisper WebApp 客戶端"""
    
    def __init__(self, server_url: str = "http://localhost:5000"):
        """
        初始化客戶端
        
        Args:
            server_url: Whisper WebApp 伺服器網址
        """
        self.server_url = server_url.rstrip('/')
        self.api_endpoint = f"{self.server_url}/api/process"
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'WhisperClient/1.0'
        })
    
    def send_youtube_url(self, youtube_url: str) -> Dict[str, Union[str, int]]:
        """
        發送 YouTube URL 到伺服器
        
        Args:
            youtube_url: YouTube 影片網址
            
        Returns:
            Dict 包含狀態資訊
        """
        try:
            # 準備請求資料
            data = {
                'youtube_url': youtube_url
            }
            
            # 發送 POST 請求
            response = self.session.post(
                self.api_endpoint,
                json=data,
                timeout=30
            )
            
            # 解析回應
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'status': result.get('status'),
                    'message': result.get('message'),
                    'task_id': result.get('task_id'),
                    'http_code': response.status_code
                }
            else:
                try:
                    error_data = response.json()
                    return {
                        'success': False,
                        'status': 'error',
                        'message': error_data.get('message', f'HTTP {response.status_code}'),
                        'http_code': response.status_code
                    }
                except:
                    return {
                        'success': False,
                        'status': 'error',
                        'message': f'HTTP {response.status_code}: {response.text}',
                        'http_code': response.status_code
                    }
                    
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'status': 'error',
                'message': '無法連接到伺服器，請確認伺服器是否正在運行',
                'http_code': 0
            }
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'status': 'error',
                'message': '請求超時',
                'http_code': 0
            }
        except Exception as e:
            return {
                'success': False,
                'status': 'error',
                'message': f'發生錯誤：{str(e)}',
                'http_code': 0
            }
    
    def check_server_status(self) -> Dict[str, Union[str, int]]:
        """
        檢查伺服器狀態
        
        Returns:
            Dict 包含伺服器狀態資訊
        """
        try:
            response = self.session.get(f"{self.server_url}/", timeout=10)
            if response.status_code == 200:
                return {
                    'success': True,
                    'status': 'online',
                    'message': '伺服器正在運行',
                    'http_code': response.status_code
                }
            else:
                return {
                    'success': False,
                    'status': 'error',
                    'message': f'伺服器回應異常：HTTP {response.status_code}',
                    'http_code': response.status_code
                }
        except Exception as e:
            return {
                'success': False,
                'status': 'error',
                'message': f'無法連接到伺服器：{str(e)}',
                'http_code': 0
            }

def main():
    """主函數 - 命令列介面"""
    if len(sys.argv) < 2:
        print("使用方法：")
        print("  python client.py <YouTube_URL>")
        print("  python client.py <YouTube_URL> --server <SERVER_URL>")
        print("")
        print("範例：")
        print("  python client.py https://www.youtube.com/watch?v=example")
        print("  python client.py https://www.youtube.com/watch?v=example --server http://192.168.1.100:5000")
        sys.exit(1)
    
    # 解析命令列參數
    youtube_url = sys.argv[1]
    server_url = "http://localhost:5000"
    
    if len(sys.argv) > 3 and sys.argv[2] == "--server":
        server_url = sys.argv[3]
    
    # 建立客戶端
    client = WhisperClient(server_url)
    
    print(f"連接到伺服器：{server_url}")
    print(f"YouTube URL：{youtube_url}")
    print("-" * 50)
    
    # 檢查伺服器狀態
    print("檢查伺服器狀態...")
    status_result = client.check_server_status()
    if not status_result['success']:
        print(f"❌ {status_result['message']}")
        sys.exit(1)
    else:
        print(f"✅ {status_result['message']}")
    
    # 發送 YouTube URL
    print("\n發送 YouTube URL...")
    result = client.send_youtube_url(youtube_url)
    
    # 顯示結果
    print(f"\n結果：")
    print(f"狀態：{result['status']}")
    print(f"訊息：{result['message']}")
    
    if result.get('task_id'):
        print(f"任務 ID：{result['task_id']}")
    
    if result['success']:
        print("\n✅ 請求已成功發送")
        if result['status'] == 'busy':
            print("⚠️  伺服器目前忙碌中，請稍後再試")
        elif result['status'] == 'processing':
            print("🔄 任務已加入佇列，正在處理中")
    else:
        print(f"\n❌ 請求失敗：{result['message']}")
        sys.exit(1)

if __name__ == "__main__":
    main() 