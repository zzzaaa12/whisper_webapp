#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import subprocess
from pathlib import Path

def print_help():
    """
    顯示幫助訊息
    """
    help_text = """
使用說明 (Usage):
  python clean_trailing_whitespace.py [PATH] [-h|--help]

描述 (Description):
  此腳本用於清除文件中的行末多餘空白和 Tab。
  It cleans trailing whitespace and tabs from files.

模式 (Modes):
  - 無參數 (No arguments):
    自動處理所有在 Git 暫存區中 (staged via `git add`) 的文件。

  - 指定路徑 (With a path):
    python clean_trailing_whitespace.py <file_or_directory_path>
    只處理指定的單一文件或目錄下的所有文件（與 Git 狀態無關）。

選項 (Options):
  -h, --help
    顯示此幫助訊息。
"""
    print(help_text)

def clean_trailing_whitespace_regex(file_path):
    """
    使用正規表示法清除文件中每行末尾的空白字符和 Tab。
    The regex `[ \t]+$` matches both spaces and tabs at the end of a line.
    """
    try:
        encodings = ['utf-8', 'gbk', 'big5', 'cp1252', 'iso-8859-1']
        content = None
        used_encoding = None

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                used_encoding = encoding
                break
            except UnicodeDecodeError:
                continue
            except (IOError, OSError):
                # print(f"  - 無法讀取或非文本文件，已跳過")
                return False

        if content is None:
            # print(f"  - 無法讀取文件 {file_path}: 編碼不支持")
            return False

        original_content = content
        cleaned_content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)

        if original_content != cleaned_content:
            with open(file_path, 'w', encoding=used_encoding) as f:
                f.write(cleaned_content)

            modified_lines_count = sum(1 for orig, clean in zip(original_content.splitlines(), cleaned_content.splitlines()) if orig != clean)
            print(f"  ✓ 已清除 {modified_lines_count} 行的行末空白 (編碼: {used_encoding})")
            return True
        else:
            return False

    except Exception as e:
        print(f"處理文件 {file_path} 時發生錯誤: {e}")
        return False

def get_staged_files():
    """
    使用 git 命令獲取暫存區中的文件列表
    """
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', '--cached', '--diff-filter=d'],
            capture_output=True, text=True, encoding='utf-8', check=True
        )
        return [line for line in result.stdout.strip().split('\n') if line]
    except FileNotFoundError:
        print("錯誤: 'git' 命令未找到。請確保您在一個 Git 倉庫中，並且 Git 已安裝。")
        return None
    except subprocess.CalledProcessError as e:
        print(f"執行 git 命令時發生錯誤: {e.stderr}")
        return None

def process_staged_files():
    """
    處理所有 Git 暫存區中的文件
    """
    staged_files = get_staged_files()

    if staged_files is None:
        return

    if not staged_files:
        print("沒有在 Git 暫存區中找到任何文件。")
        return

    print(f"檢測到 {len(staged_files)} 個在暫存區的文件，開始處理...")
    print("-" * 60)

    modified_count = 0

    try:
        git_root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True, encoding='utf-8').strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("錯誤：無法確定 Git 倉庫的根目錄。")
        return

    for file_path_relative in staged_files:
        file_path = Path(git_root) / file_path_relative

        if not file_path.exists() or not file_path.is_file():
            continue

        print(f"處理文件: {file_path_relative}")
        if clean_trailing_whitespace_regex(str(file_path)):
            modified_count += 1

    print("-" * 60)
    print("處理完成！")
    if modified_count > 0:
        print(f"總共修改了 {modified_count} 個文件。")
        print("\n重要提示：文件已被修改，您可能需要重新執行 'git add' 來更新暫存區。")
    else:
        print("所有已暫存的文件都無需修改。")

def process_single_file(file_path):
    """
    處理單個文件
    """
    print(f"處理文件: {file_path}")
    if clean_trailing_whitespace_regex(str(file_path)):
        print("文件已修改。")
    else:
        print("文件無需修改。")

def process_directory(directory_path):
    """
    遞歸處理目錄下的所有文件
    """
    directory = Path(directory_path)
    print(f"開始處理目錄: {directory_path}")
    print("-" * 60)

    modified_count = 0
    processed_count = 0

    for file_path in directory.rglob('*'):
        if file_path.is_file():
            print(f"處理文件: {file_path.relative_to(directory)}")
            if clean_trailing_whitespace_regex(str(file_path)):
                modified_count += 1
            processed_count += 1

    print("-" * 60)
    print(f"處理完成！")
    print(f"總共處理文件: {processed_count}")
    print(f"修改的文件: {modified_count}")

def main():
    """
    主函數：根據參數決定執行模式
    """
    # 檢查是否需要顯示幫助訊息
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print_help()
        return

    if len(sys.argv) > 1:
        # --- 指定路徑模式 ---
        target_path_str = sys.argv[1]
        target_path = Path(target_path_str)

        if not target_path.exists():
            print(f"錯誤: 路徑不存在: {target_path}")
            return

        if target_path.is_file():
            process_single_file(target_path)
        elif target_path.is_dir():
            process_directory(target_path)
    else:
        # --- 預設模式 (Git 暫存區) ---
        print("未提供特定路徑，將自動處理 Git 暫存區中的文件。")
        process_staged_files()

if __name__ == "__main__":
    main()
