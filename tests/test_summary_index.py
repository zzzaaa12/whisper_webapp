import json
import tempfile
import time
import unittest
from pathlib import Path

from src.services.summary_index import SummaryIndexService


def write_summary(path, title="測試標題", channel="測試頻道", topic="第一個重點"):
    path.write_text(
        f"🎬 標題：{title}\n📺 頻道：{channel}\n\n# 核心主題\n{topic}\n# 詳細內容\n忽略內容",
        encoding="utf-8",
    )


class SummaryIndexServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.folder = Path(self.temporary.name)
        self.service = SummaryIndexService(self.folder, min_sync_interval=0)

    def tearDown(self):
        self.temporary.cleanup()

    def test_builds_and_reuses_index(self):
        write_summary(self.folder / "sample.txt")
        first = self.service.sync()
        second = self.service.sync()
        self.assertEqual(first["parsed_files"], 1)
        self.assertEqual(second["parsed_files"], 0)
        self.assertEqual(second["cache_hits"], 1)
        self.assertEqual(self.service.snapshot()[0]["title"], "測試標題")
        payload = json.loads((self.folder / ".summary_index.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)

    def test_incrementally_updates_and_removes_files(self):
        summary = self.folder / "sample.txt"
        write_summary(summary)
        self.service.sync()
        time.sleep(0.01)
        write_summary(summary, title="更新標題", topic="更新重點")
        self.assertEqual(self.service.sync()["parsed_files"], 1)
        self.assertEqual(self.service.snapshot()[0]["title"], "更新標題")
        summary.unlink()
        self.assertEqual(self.service.sync()["removed_files"], 1)
        self.assertEqual(self.service.snapshot(), [])

    def test_uses_filename_and_unknown_channel_fallbacks(self):
        (self.folder / "fallback_summary.txt").write_text("沒有中繼資料", encoding="utf-8")
        item = self.service.snapshot()[0]
        self.assertEqual(item["title"], "fallback")
        self.assertEqual(item["channel"], "未知頻道")
        self.assertEqual(item["preview"], "")


if __name__ == "__main__":
    unittest.main()
