
import time
from datetime import datetime
from threading import Lock
from flask import request

from src.config import get_config

class AuthService:
    """處理使用者驗證和存取控制"""

    def __init__(self):
        self.login_attempts = {}
        self.max_attempts = get_config("MAX_ATTEMPTS", 5)
        self.block_duration = get_config("BLOCK_DURATION", 300)
        self.attempts_lock = Lock()

    def get_client_ip(self) -> str:
        """獲取客戶端 IP 位址"""
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr

    def is_ip_blocked(self, ip: str) -> bool:
        """檢查 IP 是否被封鎖"""
        with self.attempts_lock:
            if ip not in self.login_attempts:
                return False

            attempt_data = self.login_attempts[ip]
            current_time = time.time()

            if 'blocked_until' in attempt_data and current_time < attempt_data['blocked_until']:
                return True

            if current_time - attempt_data['first_attempt'] > 3600:
                del self.login_attempts[ip]
                return False

            return False

    def record_failed_attempt(self, ip: str):
        """記錄失敗的登入嘗試"""
        with self.attempts_lock:
            current_time = time.time()
            if ip not in self.login_attempts:
                self.login_attempts[ip] = {'count': 1, 'first_attempt': current_time}
            else:
                self.login_attempts[ip]['count'] += 1
                if self.login_attempts[ip]['count'] >= self.max_attempts:
                    self.login_attempts[ip]['blocked_until'] = current_time + self.block_duration

    def record_successful_attempt(self, ip: str):
        """記錄成功的登入嘗試"""
        with self.attempts_lock:
            if ip in self.login_attempts:
                del self.login_attempts[ip]

    def get_remaining_attempts(self, ip: str) -> int:
        """獲取剩餘嘗試次數"""
        with self.attempts_lock:
            if ip not in self.login_attempts:
                return self.max_attempts
            return max(0, self.max_attempts - self.login_attempts[ip]['count'])

    def get_block_remaining_time(self, ip: str) -> int:
        """獲取封鎖剩餘時間"""
        with self.attempts_lock:
            if ip not in self.login_attempts or 'blocked_until' not in self.login_attempts[ip]:
                return 0
            return max(0, int(self.login_attempts[ip]['blocked_until'] - time.time()))

    def verify_access_code(self, user_code: str) -> bool:
        """驗證通行碼"""
        system_access_code = get_config("ACCESS_CODE")
        if not system_access_code:
            return True
        return user_code == system_access_code

    def get_login_attempts_info(self) -> list:
        """獲取所有登入嘗試資訊"""
        with self.attempts_lock:
            current_time = time.time()
            attempts_info = []
            for ip, data in self.login_attempts.items():
                is_blocked = 'blocked_until' in data and current_time < data['blocked_until']
                block_remaining = self.get_block_remaining_time(ip) if is_blocked else 0
                attempts_info.append({
                    'ip': ip,
                    'attempts': data['count'],
                    'remaining': self.get_remaining_attempts(ip),
                    'first_attempt': datetime.fromtimestamp(data['first_attempt']).strftime('%Y-%m-%d %H:%M:%S'),
                    'is_blocked': is_blocked,
                    'block_remaining': f"{block_remaining//60}分{block_remaining%60}秒" if block_remaining > 0 else "無"
                })
            return attempts_info
