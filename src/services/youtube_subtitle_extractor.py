"""
YouTube 字幕擷取服務
整合到現有流程中，優先使用 YouTube 原生字幕
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import yt_dlp
from src.utils.logger_manager import get_logger_manager
from src.config import get_config


class YouTubeSubtitleExtractor:
    """YouTube 字幕擷取器"""

    def __init__(self):
        self.logger_manager = get_logger_manager()

        # 支援的語言優先順序
        self.supported_languages = get_config(
            "SUBTITLE_EXTRACTION.preferred_languages",
            ["zh-TW", "zh-CN", "zh", "en", "ja"]
        )

        # 品質閾值
        self.quality_threshold = get_config(
            "SUBTITLE_EXTRACTION.quality_threshold",
            7
        )

    def extract_subtitles(self, url: str, temp_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        擷取 YouTube 字幕

        Args:
            url: YouTube URL
            temp_dir: 臨時目錄，如果不提供會自動創建

        Returns:
            Dict containing:
            - success: bool
            - content: str (字幕內容)
            - language: str (字幕語言)
            - source: str ('manual', 'auto', 'none')
            - quality_score: int (1-10)
            - message: str
        """
        result = {
            'success': False,
            'content': '',
            'language': '',
            'source': 'none',
            'quality_score': 0,
            'message': ''
        }

        try:
            # 創建臨時目錄
            if temp_dir is None:
                temp_dir = Path(tempfile.mkdtemp())
            else:
                temp_dir.mkdir(exist_ok=True)

            self.logger_manager.info(f"開始擷取字幕: {url}", "subtitle_extractor")

            # 配置 yt-dlp 選項
            ydl_opts = {
                'writesubtitles': True,           # 下載手動字幕
                'writeautomaticsub': True,        # 下載自動字幕
                'subtitleslangs': self.supported_languages,  # 語言優先順序
                'subtitlesformat': 'srt',         # 字幕格式
                'skip_download': True,            # 只下載字幕
                'outtmpl': str(temp_dir / '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 獲取影片資訊
                info = ydl.extract_info(url, download=False)

                # 檢查可用字幕
                available_subs = info.get('subtitles', {})
                auto_subs = info.get('automatic_captions', {})

                self.logger_manager.info(
                    f"可用字幕: {list(available_subs.keys())}, "
                    f"自動字幕: {list(auto_subs.keys())}",
                    "subtitle_extractor"
                )

                # 選擇最佳字幕
                selected_lang, selected_source = self._select_best_subtitle(
                    available_subs, auto_subs
                )

                if not selected_lang:
                    result['message'] = '沒有找到支援的字幕語言'
                    return result

                # 下載選定的字幕
                ydl_opts['subtitleslangs'] = [selected_lang]
                ydl_opts['writesubtitles'] = selected_source == 'manual'
                ydl_opts['writeautomaticsub'] = selected_source == 'auto'

                with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                    ydl_download.download([url])

                # 尋找下載的字幕檔案
                subtitle_file = self._find_subtitle_file(temp_dir, selected_lang)

                if not subtitle_file or not subtitle_file.exists():
                    result['message'] = f'字幕檔案下載失敗: {selected_lang}'
                    return result

                # 讀取字幕內容
                subtitle_content = subtitle_file.read_text(encoding='utf-8')

                # 評估字幕品質
                quality_assessment = self._assess_subtitle_quality(
                    subtitle_content, selected_source
                )

                result.update({
                    'success': True,
                    'content': subtitle_content,
                    'language': selected_lang,
                    'source': selected_source,
                    'quality_score': quality_assessment['score'],
                    'message': f'成功擷取 {selected_lang} 字幕 (來源: {selected_source})'
                })

                self.logger_manager.info(
                    f"字幕擷取成功: {selected_lang} ({selected_source}), "
                    f"品質分數: {quality_assessment['score']}",
                    "subtitle_extractor"
                )

        except Exception as e:
            error_msg = f"字幕擷取失敗: {str(e)}"
            self.logger_manager.error(error_msg, "subtitle_extractor")
            result['message'] = error_msg

        finally:
            # 清理臨時檔案
            try:
                if temp_dir and temp_dir.exists():
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                self.logger_manager.warning(f"清理臨時檔案失敗: {e}", "subtitle_extractor")

        return result

    def _select_best_subtitle(self, manual_subs: Dict, auto_subs: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        選擇最佳字幕語言和來源

        Returns:
            Tuple[language, source] where source is 'manual' or 'auto'
        """
        # 優先選擇手動字幕
        for lang in self.supported_languages:
            if lang in manual_subs:
                return lang, 'manual'

        # 其次選擇自動字幕
        for lang in self.supported_languages:
            if lang in auto_subs:
                return lang, 'auto'

        # 如果沒有找到支援的語言，選擇第一個可用的
        if manual_subs:
            first_lang = list(manual_subs.keys())[0]
            return first_lang, 'manual'

        if auto_subs:
            first_lang = list(auto_subs.keys())[0]
            return first_lang, 'auto'

        return None, None

    def _find_subtitle_file(self, temp_dir: Path, language: str) -> Optional[Path]:
        """尋找下載的字幕檔案"""
        # 可能的檔案名稱模式
        patterns = [
            f"*.{language}.srt",
            f"*.{language}.vtt",
            "*.srt",
            "*.vtt"
        ]

        for pattern in patterns:
            files = list(temp_dir.glob(pattern))
            if files:
                return files[0]

        return None

    def _assess_subtitle_quality(self, content: str, source: str) -> Dict[str, Any]:
        """
        評估字幕品質

        Returns:
            Dict with 'score' (1-10) and 'issues' list
        """
        assessment = {
            'score': 5,  # 基礎分數
            'issues': []
        }

        try:
            lines = content.strip().split('\n')

            # 1. 檢查字幕長度 (20%)
            if len(content) < 100:
                assessment['score'] -= 3
                assessment['issues'].append('字幕內容過短')
            elif len(content) > 1000:
                assessment['score'] += 1

            # 2. 檢查時間軸格式 (30%)
            time_pattern = r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}'
            time_matches = re.findall(time_pattern, content)

            if len(time_matches) == 0:
                assessment['score'] -= 4
                assessment['issues'].append('缺少時間軸資訊')
            elif len(time_matches) < 5:
                assessment['score'] -= 2
                assessment['issues'].append('時間軸資訊不完整')
            else:
                assessment['score'] += 1

            # 3. 檢查文字內容品質 (30%)
            text_lines = [line for line in lines if not re.match(r'^\d+$', line.strip())
                         and not re.match(time_pattern, line)]

            if text_lines:
                avg_line_length = sum(len(line) for line in text_lines) / len(text_lines)

                if avg_line_length < 5:
                    assessment['score'] -= 2
                    assessment['issues'].append('文字內容過短')
                elif avg_line_length > 20:
                    assessment['score'] += 1

                # 檢查中文內容比例
                chinese_chars = sum(1 for line in text_lines for char in line
                                  if '\u4e00' <= char <= '\u9fff')
                total_chars = sum(len(line) for line in text_lines)

                if total_chars > 0:
                    chinese_ratio = chinese_chars / total_chars
                    if chinese_ratio > 0.3:  # 中文內容比例高
                        assessment['score'] += 1

            # 4. 來源類型調整 (20%)
            if source == 'manual':
                assessment['score'] += 2  # 手動字幕通常品質更好
            elif source == 'auto':
                assessment['score'] -= 1  # 自動字幕可能有錯誤

            # 確保分數在 1-10 範圍內
            assessment['score'] = max(1, min(10, assessment['score']))

        except Exception as e:
            self.logger_manager.warning(f"字幕品質評估失敗: {e}", "subtitle_extractor")
            assessment['score'] = 3
            assessment['issues'].append('品質評估失敗')

        return assessment

    def should_use_subtitle(self, quality_score: int, source: str) -> bool:
        """
        判斷是否應該使用擷取的字幕

        Args:
            quality_score: 品質分數 (1-10)
            source: 字幕來源 ('manual' or 'auto')

        Returns:
            bool: True 如果應該使用字幕
        """
        # 手動字幕的閾值較低
        if source == 'manual':
            return quality_score >= max(5, self.quality_threshold - 2)

        # 自動字幕需要較高的品質分數
        return quality_score >= self.quality_threshold

    def convert_to_standard_srt(self, content: str) -> str:
        """
        將字幕內容轉換為標準 SRT 格式

        Args:
            content: 原始字幕內容

        Returns:
            str: 標準化的 SRT 內容
        """
        try:
            # 如果已經是 SRT 格式，直接返回
            if '-->' in content and re.search(r'\d{2}:\d{2}:\d{2},\d{3}', content):
                return content

            # TODO: 實作 VTT 到 SRT 的轉換
            # 這裡可以添加其他格式的轉換邏輯

            return content

        except Exception as e:
            self.logger_manager.warning(f"字幕格式轉換失敗: {e}", "subtitle_extractor")
            return content


# 全域實例
_subtitle_extractor_instance = None

def get_youtube_subtitle_extractor() -> YouTubeSubtitleExtractor:
    """獲取 YouTube 字幕擷取器實例（單例模式）"""
    global _subtitle_extractor_instance
    if _subtitle_extractor_instance is None:
        _subtitle_extractor_instance = YouTubeSubtitleExtractor()
    return _subtitle_extractor_instance