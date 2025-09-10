
import time
from datetime import datetime
from threading import Lock
from flask import request

from src.config import get_config

class AuthService:
    """處理使用者驗證和存取控制"""

    def __init__(self):
        self.login_attempts = {}
        self.max_attempts = 3  # 改為3次錯誤後鎖定
        self.block_duration = 1800  # 鎖定30分鐘 (30 * 60 = 1800 秒)
        self.attempts_lock = Lock()

    def _clean_expired_attempts(self, ip: str, current_time: float):
        if ip in self.login_attempts:
            attempt_data = self.login_attempts[ip]
            if current_time - attempt_data['first_attempt'] > 3600:
                del self.login_attempts[ip]

    def get_client_ip(self) -> str:
        """獲取客戶端 IP 位址"""
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.remote_addr or '0.0.0.0'

    def is_locked(self, ip: str) -> bool:
        """檢查 IP 是否被鎖定"""
        with self.attempts_lock:
            current_time = time.time()
            self._clean_expired_attempts(ip, current_time)

            if ip not in self.login_attempts:
                return False

            attempt_data = self.login_attempts[ip]

            if 'locked_until' in attempt_data and current_time < attempt_data['locked_until']:
                return True

            return False

    def track_failed_attempt(self, ip: str) -> bool:
        """記錄失敗的登入嘗試，返回是否觸發鎖定"""
        with self.attempts_lock:
            current_time = time.time()
            if ip not in self.login_attempts:
                self.login_attempts[ip] = {'count': 1, 'first_attempt': current_time}
            else:
                self.login_attempts[ip]['count'] += 1

            # 檢查是否需要鎖定
            if self.login_attempts[ip]['count'] >= self.max_attempts:
                self.login_attempts[ip]['locked_until'] = current_time + self.block_duration
                return True  # 觸發鎖定

            return False  # 未觸發鎖定

    def reset_attempts(self, ip: str):
        """重置嘗試次數（成功登入時呼叫）"""
        with self.attempts_lock:
            if ip in self.login_attempts:
                del self.login_attempts[ip]

    def get_remaining_attempts(self, ip: str) -> int:
        """獲取剩餘嘗試次數"""
        with self.attempts_lock:
            if ip not in self.login_attempts:
                return self.max_attempts
            return max(0, self.max_attempts - self.login_attempts[ip]['count'])

    def get_lock_remaining_time(self, ip: str) -> int:
        """獲取鎖定剩餘時間（秒）"""
        with self.attempts_lock:
            if ip not in self.login_attempts or 'locked_until' not in self.login_attempts[ip]:
                return 0
            return max(0, int(self.login_attempts[ip]['locked_until'] - time.time()))

    def verify_access_code(self, user_code: str | None) -> bool:
        """驗證通行碼"""
        system_access_code = get_config("ACCESS_CODE")
        if not system_access_code:
            return True
        if not user_code:
            return False
        return user_code == system_access_code

    def get_failed_attempts_count(self, ip: str) -> int:
        """獲取指定 IP 的失敗嘗試次數"""
        with self.attempts_lock:
            if ip not in self.login_attempts:
                return 0
            return self.login_attempts[ip]['count']

    def get_login_attempts_info(self) -> list:
        """獲取所有登入嘗試資訊"""
        with self.attempts_lock:
            current_time = time.time()
            attempts_info = []
            for ip, data in self.login_attempts.items():
                is_locked = 'locked_until' in data and current_time < data['locked_until']
                lock_remaining = self.get_lock_remaining_time(ip) if is_locked else 0
                attempts_info.append({
                    'ip': ip,
                    'attempts': data['count'],
                    'remaining': self.get_remaining_attempts(ip),
                    'first_attempt': datetime.fromtimestamp(data['first_attempt']).strftime('%Y-%m-%d %H:%M:%S'),
                    'is_locked': is_locked,
                    'lock_remaining': f"{lock_remaining//60}分{lock_remaining%60}秒" if lock_remaining > 0 else "無"
                })
            return attempts_info
