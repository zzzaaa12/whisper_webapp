#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
from pathlib import Path

def clean_trailing_whitespace_regex(file_path):
    """
    使用正規表示法清除文件中每行末尾的空白字符和tab
    """
    try:
        # 嘗試不同的編碼
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
        
        if content is None:
            print(f"無法讀取文件 {file_path}: 編碼不支持")
            return False
        
        # 保存原始內容
        original_content = content
        
        # 使用正規表示法移除行末的空白字符和tab
        # [ \t]+(?=\n|$) 匹配行末的空格和tab（在換行符前或文件末）
        cleaned_content = re.sub(r'[ \t]+(?=\n|$)', '', content, flags=re.MULTILINE)
        
        # 避免在文件末尾添加額外的換行符
        # 如果原文件末尾沒有換行符，清理後也不應該有
        if not original_content.endswith('\n') and cleaned_content.endswith('\n'):
            cleaned_content = cleaned_content.rstrip('\n')
        elif original_content.endswith('\n') and not cleaned_content.endswith('\n'):
            cleaned_content += '\n'
        
        # 檢查是否有修改
        if original_content != cleaned_content:
            # 寫回文件，使用相同的編碼
            with open(file_path, 'w', encoding=used_encoding) as f:
                f.write(cleaned_content)
            
            # 計算清除了多少行的空白
            original_lines = original_content.split('\n')
            cleaned_lines = cleaned_content.split('\n')
            modified_lines = 0
            
            for i, (orig, clean) in enumerate(zip(original_lines, cleaned_lines)):
                if orig != clean:
                    modified_lines += 1
            
            print(f"  ✓ 已清除 {modified_lines} 行的行末空白 (編碼: {used_encoding})")
            return True
        else:
            print(f"  - 無需修改 (編碼: {used_encoding})")
            return False
            
    except Exception as e:
        print(f"處理文件 {file_path} 時發生錯誤: {e}")
        return False

def process_single_file(file_path):
    """
    處理單個文件
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"文件不存在: {file_path}")
        return False
    
    if not file_path.is_file():
        print(f"路徑不是文件: {file_path}")
        return False
    
    # 支持的文件擴展名（不區分大小寫）
    target_extensions = {'.py', '.md', '.html', '.htm', '.c', '.h', '.txt', '.cpp', '.cc', '.cxx', '.js'}
    if file_path.suffix.lower() not in target_extensions:
        print(f"不支持的文件類型: {file_path.suffix}")
        print(f"支持的類型: {', '.join(sorted(target_extensions))}")
        return False
    
    print(f"處理文件: {file_path}")
    return clean_trailing_whitespace_regex(file_path)

def process_directory(directory_path):
    """
    處理目錄下的所有指定類型文件
    """
    target_extensions = {'.py', '.md', '.html', '.htm', '.c', '.h', '.txt', '.cpp', '.cc', '.cxx', '.js'}
    
    directory = Path(directory_path)
    
    if not directory.exists():
        print(f"目錄不存在: {directory_path}")
        return
    
    if not directory.is_dir():
        print(f"路徑不是目錄: {directory_path}")
        return
    
    processed_count = 0
    modified_count = 0
    
    print(f"開始處理目錄: {directory_path}")
    print(f"目標文件類型: {', '.join(sorted(target_extensions))}")
    print("-" * 60)
    
    # 遞歸處理所有子目錄
    for file_path in directory.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in target_extensions:
            print(f"處理文件: {file_path.relative_to(directory)}")
            
            if clean_trailing_whitespace_regex(file_path):
                modified_count += 1
            
            processed_count += 1
    
    print("-" * 60)
    print(f"處理完成！")
    print(f"總共處理文件: {processed_count}")
    print(f"修改的文件: {modified_count}")
    
    return processed_count, modified_count

def preview_changes(file_path):
    """
    預覽將要進行的修改（不實際修改文件）
    """
    try:
        encodings = ['utf-8', 'gbk', 'big5', 'cp1252', 'iso-8859-1']
        content = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            return False
        
        # 找出有行末空白的行
        lines = content.split('\n')
        whitespace_lines = []
        
        for i, line in enumerate(lines, 1):
            if re.search(r'[ \t]+$', line):
                # 顯示行末空白字符
                visible_line = line.replace(' ', '·').replace('\t', '→')
                whitespace_lines.append(f"  第 {i} 行: {visible_line}")
        
        if whitespace_lines:
            print(f"發現 {len(whitespace_lines)} 行有行末空白:")
            for line in whitespace_lines[:10]:  # 最多顯示前10行
                print(line)
            if len(whitespace_lines) > 10:
                print(f"  ... 還有 {len(whitespace_lines) - 10} 行")
            return True
        else:
            print("未發現行末空白")
            return False
            
    except Exception as e:
        print(f"預覽失敗: {e}")
        return False

def main():
    """
    主函數
    """
    # 解析命令行參數
    preview_mode = False
    target_path = None
    
    args = sys.argv[1:]
    if '--preview' in args or '-p' in args:
        preview_mode = True
        args = [arg for arg in args if arg not in ['--preview', '-p']]
    
    if args:
        target_path = args[0]
    else:
        target_path = input("請輸入要處理的文件或目錄路徑（按Enter使用當前目錄）: ").strip()
        if not target_path:
            target_path = "."
    
    target_path = Path(target_path)
    
    if not target_path.exists():
        print(f"路徑不存在: {target_path}")
        return
    
    # 判斷是文件還是目錄
    if target_path.is_file():
        # 處理單個文件
        print(f"目標文件: {target_path.absolute()}")
        
        if preview_mode:
            print("=== 預覽模式 ===")
            preview_changes(target_path)
            return
        
        confirm = input("確認清除行末空白？(y/N): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            print("操作已取消")
            return
        
        process_single_file(target_path)
        
    elif target_path.is_dir():
        # 處理目錄
        print(f"目標目錄: {target_path.absolute()}")
        print("將清除所有支持文件類型的行末空白和tab")
        
        if preview_mode:
            print("預覽模式不支持目錄處理")
            return
        
        confirm = input("確認繼續？(y/N): ").strip().lower()
        if confirm not in ['y', 'yes', '是']:
            print("操作已取消")
            return
        
        process_directory(target_path)
    
    print("\n使用說明:")
    print("  python script.py file.py              # 處理單個文件")
    print("  python script.py directory/           # 處理整個目錄")
    print("  python script.py file.py --preview    # 預覽單個文件的修改")

if __name__ == "__main__":
    main()
