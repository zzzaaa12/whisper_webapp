

class SRTConverter:
    """統一SRT字幕轉換器"""

    @staticmethod
    def segments_to_srt(segments) -> str:
        """統一字幕轉換函數"""
        def format_timestamp(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds - int(seconds)) * 1000)
            return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

        srt_lines = []
        for idx, segment in enumerate(segments, 1):
            start = format_timestamp(segment.start)
            end = format_timestamp(segment.end)
            text = segment.text.strip()
            srt_lines.append(f"{idx}\n{start} --> {end}\n{text}\n")

        return "\n".join(srt_lines)

# 便捷函數導出
def segments_to_srt(segments) -> str:
    """便捷SRT轉換函數"""
    return SRTConverter.segments_to_srt(segments)

