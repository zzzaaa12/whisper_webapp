"""
安全管理器
處理登入限制、IP 封鎖等安全功能
"""

import time
import threading
from typing import Dict, Any
from flask import request


class SecurityManager:
    """安全管理器"""
    
    def __init__(self, max_attempts: int = 5, block_duration: int = 300):
        self.max_attempts = max_attempts
        self.block_duration = block_duration  # 封鎖時間（秒）
        self.login_attempts: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def get_client_ip(self) -> str:
        """取得客戶端 IP 地址"""
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            return request.headers.get('X-Real-IP') or ''
        else:
            return request.remote_addr or '127.0.0.1'
    
    def is_ip_blocked(self, ip: str) -> bool:
        """檢查 IP 是否被封鎖"""
        with self._lock:
            if ip not in self.login_attempts:
                return False

            attempt_data = self.login_attempts[ip]
            current_time = time.time()

            # 檢查是否在封鎖期內
            if 'blocked_until' in attempt_data and current_time < attempt_data['blocked_until']:
                return True

            # 檢查是否超過重置時間（1小時）
            if current_time - attempt_data['first_attempt'] > 3600:
                # 重置嘗試次數
                del self.login_attempts[ip]
                return False

            return False
    
    def record_failed_attempt(self, ip: str):
        """記錄失敗的登入嘗試"""
        with self._lock:
            current_time = time.time()

            if ip not in self.login_attempts:
                self.login_attempts[ip] = {
                    'count': 1,
                    'first_attempt': current_time
                }
            else:
                self.login_attempts[ip]['count'] += 1

                # 如果達到最大嘗試次數，設定封鎖時間
                if self.login_attempts[ip]['count'] >= self.max_attempts:
                    self.login_attempts[ip]['blocked_until'] = current_time + self.block_duration
    
    def record_successful_attempt(self, ip: str):
        """記錄成功的登入嘗試，重置計數器"""
        with self._lock:
            if ip in self.login_attempts:
                del self.login_attempts[ip]
    
    def get_remaining_attempts(self, ip: str) -> int:
        """取得剩餘嘗試次數"""
        with self._lock:
            if ip not in self.login_attempts:
                return self.max_attempts
            return max(0, self.max_attempts - self.login_attempts[ip]['count'])
    
    def get_block_remaining_time(self, ip: str) -> int:
        """取得封鎖剩餘時間（秒）"""
        with self._lock:
            if ip not in self.login_attempts or 'blocked_until' not in self.login_attempts[ip]:
                return 0
            return max(0, int(self.login_attempts[ip]['blocked_until'] - time.time()))
    
    def get_login_attempts_info(self) -> Dict[str, Any]:
        """取得所有登入嘗試資訊（供管理介面使用）"""
        with self._lock:
            result = {}
            current_time = time.time()
            
            for ip, data in self.login_attempts.items():
                result[ip] = {
                    'attempts': data['count'],
                    'first_attempt': data['first_attempt'],
                    'blocked_until': data.get('blocked_until', 0),
                    'is_blocked': data.get('blocked_until', 0) > current_time,
                    'remaining_time': max(0, int(data.get('blocked_until', 0) - current_time))
                }
            
            return result
    
    def clear_ip_attempts(self, ip: str) -> bool:
        """清除指定 IP 的嘗試記錄"""
        with self._lock:
            if ip in self.login_attempts:
                del self.login_attempts[ip]
                return True
            return False 