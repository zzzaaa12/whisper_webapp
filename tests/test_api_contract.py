import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


EXPECTED_API_ROUTES = {
    ("POST", "/api/trash/move"),
    ("POST", "/api/trash/restore"),
    ("POST", "/api/trash/delete"),
    ("GET", "/api/trash/list"),
    ("POST", "/api/bookmarks/add"),
    ("POST", "/api/bookmarks/remove"),
    ("GET", "/api/bookmarks/list"),
    ("GET", "/api/bookmarks/check/<filename>"),
    ("POST", "/api/bookmark"),
    ("POST", "/api/batch-bookmark"),
    ("GET", "/api/system/config-status"),
    ("GET", "/api/system/transcription-schedule"),
    ("POST", "/api/system/transcription-schedule"),
    ("POST", "/api/verify_access_code"),
    ("POST", "/api/upload_subtitle"),
    ("POST", "/api/upload_media"),
    ("POST", "/api/queue/cancel"),
    ("POST", "/api/queue/cleanup"),
    ("POST", "/api/queue/delete"),
    ("POST", "/api/queue/delete-batch"),
    ("POST", "/api/queue/restart"),
    ("POST", "/api/queue/add"),
    ("POST", "/api/process"),
    ("POST", "/api/process2"),
    ("GET", "/api/queue/status"),
    ("GET", "/api/queue/list"),
    ("GET", "/api/queue/task/<task_id>"),
    ("POST", "/api/queue/force-start"),
    ("POST", "/api/delete"),
    ("POST", "/api/batch-delete"),
    ("POST", "/api/last_5_summary"),
    ("POST", "/api/get_summary"),
    ("POST", "/api/summaries/list"),
    ("POST", "/api/client-diagnostics"),
    ("GET", "/api/health"),
    ("GET", "/api/system/status"),
}

EXPECTED_DOWNLOAD_ROUTES = {
    ("GET", "/download/summary/<filename>"),
    ("GET", "/download/subtitle/<filename>"),
}

EXPECTED_SOCKET_INPUTS = {
    "connect",
    "disconnect",
    "clear_logs",
    "start_processing",
    "cancel_processing",
    "request_gpu_status",
}

EXPECTED_SOCKET_OUTPUTS = {
    "update_log",
    "task_log",
    "server_status_update",
    "gpu_status_update",
    "processing_finished",
    "access_code_error",
}


def collect_routes(path: Path, decorator_name: str, prefix: str = "") -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr != "route" or not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != decorator_name or not decorator.args:
                continue
            route = ast.literal_eval(decorator.args[0])
            methods = ["GET"]
            for keyword in decorator.keywords:
                if keyword.arg == "methods":
                    methods = ast.literal_eval(keyword.value)
            routes.update((method, prefix + route) for method in methods)
    return routes


class ApiContractTests(unittest.TestCase):
    def test_api_route_names_and_methods_are_stable(self):
        actual = collect_routes(ROOT / "src/routes/api.py", "api_bp", "/api")
        self.assertEqual(EXPECTED_API_ROUTES, actual)

    def test_external_download_routes_are_stable(self):
        actual = collect_routes(ROOT / "src/routes/main.py", "main_bp")
        actual = {item for item in actual if item[1].startswith("/download/")}
        self.assertEqual(EXPECTED_DOWNLOAD_ROUTES, actual)

    def test_socket_event_names_are_stable(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        socket_inputs = set(re.findall(r"@socketio\.on\(['\"]([^'\"]+)['\"]\)", app_source))
        self.assertEqual(EXPECTED_SOCKET_INPUTS, socket_inputs)

        output_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "app.py",
                ROOT / "src/services/socket_service.py",
                ROOT / "src/services/socketio_instance.py",
            )
        )
        socket_outputs = set(
            re.findall(r"(?:socketio|self\.socketio)\.emit\(['\"]([^'\"]+)['\"]", output_source)
        )
        self.assertEqual(EXPECTED_SOCKET_OUTPUTS, socket_outputs)

    def test_external_client_request_encodings_remain_documented(self):
        client = (ROOT / "app/model.py").read_text(encoding="utf-8")
        self.assertIn('f"{SERVER_URL}/api/queue/status"', client)
        self.assertRegex(client, r"/api/process[\s\S]+?json=youtube_payload")
        self.assertRegex(client, r"/api/verify_access_code[\s\S]+?data=access_code_payload")
        self.assertRegex(client, r"/api/upload_media[\s\S]+?files=files[\s\S]+?data=data")
        self.assertRegex(client, r"/api/upload_subtitle[\s\S]+?json=subtitle_payload")


if __name__ == "__main__":
    unittest.main()
