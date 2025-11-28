"""
摘要 API 服務 - 處理摘要數據的讀取和管理
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from src.utils.path_manager import get_path_manager
from src.utils.channel_mapping import get_display_name

class SummaryAPIService:
    """摘要 API 服務類"""

    def __init__(self):
        self.path_manager = get_path_manager()
        self.summary_folder = self.path_manager.get_summary_folder()

    def get_latest_summaries(self, limit: int = 10) -> List[Dict]:
        """
        獲取最新的摘要列表

        Args:
            limit: 返回的摘要數量限制

        Returns:
            List[Dict]: 摘要列表，包含 index, title, created_at
        """
        try:
            # 獲取所有 .txt 摘要文件
            summary_files = []
            if self.summary_folder.exists():
                for file_path in self.summary_folder.glob("*.txt"):
                    if file_path.is_file():
                        # 獲取文件修改時間
                        mtime = file_path.stat().st_mtime
                        summary_files.append({
                            'path': file_path,
                            'mtime': mtime,
                            'name': file_path.stem
                        })

            # 按修改時間排序（最新的在前）
            summary_files.sort(key=lambda x: x['mtime'], reverse=True)

            # 限制數量並添加索引
            result = []
            for i, file_info in enumerate(summary_files[:limit]):
                # 讀取文件第一行作為標題，如果沒有則使用文件名
                title = self._extract_title(file_info['path'])

                result.append({
                    'index': i + 1,
                    'title': title,
                    'created_at': datetime.fromtimestamp(file_info['mtime']).strftime('%Y-%m-%d %H:%M:%S'),
                    'file_name': file_info['name']
                })

            return result

        except Exception as e:
            print(f"Error getting latest summaries: {e}")
            return []

    def get_summary_by_index(self, index: int) -> Optional[Dict]:
        """
        根據索引獲取摘要內容

        Args:
            index: 摘要索引（1-5，1是最新的）

        Returns:
            Optional[Dict]: 摘要詳細信息，包含 index, title, content, created_at, file_name
        """
        try:
            # 驗證索引範圍
            if index < 1 or index > 10:
                return None

            # 獲取最新的摘要列表
            summaries = self.get_latest_summaries(10)

            # 檢查索引是否存在
            if index > len(summaries):
                return None

            # 獲取對應的摘要信息
            summary_info = summaries[index - 1]

            # 讀取完整內容
            file_path = self.summary_folder / f"{summary_info['file_name']}.txt"
            content = self._read_file_content(file_path)

            if content is None:
                return None

            return {
                'index': index,
                'title': summary_info['title'],
                'content': content,
                'created_at': summary_info['created_at'],
                'file_name': summary_info['file_name']
            }

        except Exception as e:
            print(f"Error getting summary by index {index}: {e}")
            return None

    def _extract_title(self, file_path: Path) -> str:
        """
        從摘要文件中提取標題

        Args:
            file_path: 文件路徑

        Returns:
            str: 標題文本
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

                # 如果第一行不為空且不太長，使用作為標題
                if first_line and len(first_line) <= 100:
                    # 移除可能的標題標記
                    title = first_line.lstrip('#').strip()
                    if title:
                        return title

                # 否則使用文件名
                return file_path.stem

        except Exception:
            # 如果讀取失敗，使用文件名
            return file_path.stem

    def _read_file_content(self, file_path: Path) -> Optional[str]:
        """
        讀取文件完整內容

        Args:
            file_path: 文件路徑

        Returns:
            Optional[str]: 文件內容，失敗時返回 None
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None

    def search_summary_by_title(self, search_title: str) -> Optional[Dict]:
        """
        根據標題搜尋摘要檔案，使用與處理佇列相同的檔名比對邏輯

        Args:
            search_title: 要搜尋的影片標題

        Returns:
            Optional[Dict]: 找到的摘要詳細信息，包含 title, content, created_at, file_name
        """
        try:
            if not search_title.strip():
                return None

            # 使用與 queue_worker 相同的檔名生成邏輯
            from src.utils.file_sanitizer import sanitize_filename
            from src.utils.time_formatter import get_timestamp
            from src.utils.filename_matcher import FilenameMatcher
            from datetime import datetime

            # 生成當日的標題格式 (因為我們不知道確切的處理日期)
            date_str = datetime.now().strftime('%Y.%m.%d')
            base_name = f"{date_str} - {search_title}"
            sanitized_title = sanitize_filename(base_name)

            # 也嘗試 Auto 模式的格式
            auto_sanitized_title = f"{date_str} - [Auto] " + sanitize_filename(search_title)

            # 使用 FilenameMatcher 搜尋相同內容的檔案
            matching_files = []

            # 搜尋一般格式
            matching_files.extend(FilenameMatcher.find_matching_files(
                f"{sanitized_title}.txt", self.summary_folder, ['.txt']
            ))

            # 搜尋 Auto 格式
            matching_files.extend(FilenameMatcher.find_matching_files(
                f"{auto_sanitized_title}.txt", self.summary_folder, ['.txt']
            ))

            # 找到最新的有效摘要檔案
            valid_files = []
            for file_path in matching_files:
                if file_path.is_file() and file_path.stat().st_size > 500:
                    valid_files.append((file_path, file_path.stat().st_mtime))

            if not valid_files:
                return None

            # 選擇最新的檔案
            latest_file_path, _ = max(valid_files, key=lambda x: x[1])

            # 讀取摘要內容
            content = self._read_file_content(latest_file_path)
            if content is None:
                return None

            title = self._extract_title(latest_file_path)
            mtime = latest_file_path.stat().st_mtime

            return {
                'title': title,
                'content': content,
                'created_at': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'file_name': latest_file_path.stem,
                'file_path': str(latest_file_path),
                'file_size': latest_file_path.stat().st_size
            }

        except Exception as e:
            print(f"Error searching summary by title '{search_title}': {e}")
            return None

    def get_summaries_list(self, page: int = 1, per_page: int = 30,
                          channel: Optional[str] = None,
                          search: Optional[str] = None,
                          bookmarked_only: bool = False,
                          bookmarked_files: Optional[List[str]] = None) -> Dict:
        """
        獲取摘要列表（支援分頁、篩選、搜尋）

        Args:
            page: 頁碼（從1開始）
            per_page: 每頁數量
            channel: 頻道篩選（原始頻道名稱或顯示名稱）
            search: 搜尋關鍵字（搜尋標題）
            bookmarked_only: 只顯示書籤
            bookmarked_files: 書籤檔案列表（從外部傳入，避免循環依賴）

        Returns:
            Dict: 包含 summaries（摘要列表）、pagination（分頁資訊）、channels（頻道統計）
        """
        try:
            # 獲取所有摘要檔案
            all_files = []
            if self.summary_folder.exists():
                for file_path in self.summary_folder.glob("*.txt"):
                    if file_path.is_file():
                        all_files.append(file_path)

            # 按修改時間排序（最新的在前）
            all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # 提取所有檔案的資訊
            all_summaries = []
            channel_counts = {}

            for file_path in all_files:
                # 提取頻道和標題
                channel_name = self._extract_channel(file_path)
                title = self._extract_title(file_path)
                channel_display = get_display_name(channel_name)

                # 統計頻道數量
                if channel_display not in channel_counts:
                    channel_counts[channel_display] = {
                        'name': channel_name,
                        'display_name': channel_display,
                        'count': 0
                    }
                channel_counts[channel_display]['count'] += 1

                # 提取核心主題作為預覽
                preview = self._extract_core_topics(file_path)

                # 建立摘要項目
                summary_item = {
                    'filename': file_path.name,
                    'title': title,
                    'channel': channel_name,
                    'channel_display': channel_display,
                    'created_at': datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'file_size': file_path.stat().st_size,
                    'is_bookmarked': bookmarked_files and file_path.name in bookmarked_files,
                    'preview': preview
                }

                all_summaries.append(summary_item)

            # 篩選：書籤
            if bookmarked_only and bookmarked_files:
                all_summaries = [s for s in all_summaries if s['is_bookmarked']]

            # 篩選：頻道
            if channel:
                # 同時支援原始名稱和顯示名稱
                all_summaries = [
                    s for s in all_summaries
                    if s['channel'] == channel or s['channel_display'] == channel
                ]

            # 篩選：搜尋
            if search:
                search_lower = search.lower()
                all_summaries = [
                    s for s in all_summaries
                    if search_lower in s['title'].lower()
                ]

            # 計算分頁
            total_count = len(all_summaries)
            total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0

            # 驗證頁碼
            if page < 1:
                page = 1
            if page > total_pages and total_pages > 0:
                page = total_pages

            # 計算起始和結束索引
            start_index = (page - 1) * per_page
            end_index = start_index + per_page

            # 取得當前頁的摘要
            page_summaries = all_summaries[start_index:end_index]

            # 整理頻道列表（按數量降序排列）
            channels_list = sorted(
                channel_counts.values(),
                key=lambda x: (-x['count'], x['display_name'])
            )

            return {
                'summaries': page_summaries,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total_count': total_count,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_prev': page > 1
                },
                'channels': channels_list
            }

        except Exception as e:
            print(f"Error getting summaries list: {e}")
            return {
                'summaries': [],
                'pagination': {
                    'page': 1,
                    'per_page': per_page,
                    'total_count': 0,
                    'total_pages': 0,
                    'has_next': False,
                    'has_prev': False
                },
                'channels': []
            }

    def _extract_channel(self, file_path: Path) -> str:
        """
        從摘要文件中提取頻道信息

        Args:
            file_path: 文件路徑

        Returns:
            str: 頻道名稱
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # 只讀取前10行來尋找頻道信息
                for i, line in enumerate(f):
                    if i > 10:
                        break

                    line = line.strip()

                    # 尋找 "📺 頻道：" 格式
                    if '📺 頻道：' in line:
                        return line.split('📺 頻道：')[1].strip()
                    elif '頻道：' in line:
                        return line.split('頻道：')[1].strip()

                return "未知頻道"
        except Exception:
            return "未知頻道"

    def _extract_core_topics(self, file_path: Path) -> str:
        """
        從摘要文件中提取核心主題內容作為預覽

        Args:
            file_path: 文件路徑

        Returns:
            str: 核心主題內容（最多200字）
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

                # 尋找核心主題區塊
                in_core_topics = False
                core_topics_lines = []

                for line in lines:
                    line_stripped = line.strip()

                    # 找到核心主題標題
                    if '核心主題' in line_stripped and line_stripped.startswith('#'):
                        in_core_topics = True
                        continue

                    # 如果在核心主題區塊中
                    if in_core_topics:
                        # 遇到下一個標題就停止
                        if line_stripped.startswith('#'):
                            break

                        # 收集非空行
                        if line_stripped and not line_stripped.startswith('='):
                            core_topics_lines.append(line_stripped)

                # 合併內容並限制長度
                if core_topics_lines:
                    content = ' '.join(core_topics_lines)
                    # 限制在200字以內
                    if len(content) > 200:
                        content = content[:200] + '...'
                    return content

                return ""
        except Exception as e:
            print(f"Error extracting core topics from {file_path}: {e}")
            return ""


# 全域服務實例
_summary_api_service = None

def get_summary_api_service() -> SummaryAPIService:
    """獲取摘要 API 服務實例"""
    global _summary_api_service
    if _summary_api_service is None:
        _summary_api_service = SummaryAPIService()
    return _summary_api_service