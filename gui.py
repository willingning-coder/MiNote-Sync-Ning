# -*- coding: utf-8 -*-
"""
MiNote Sync GUI - 小米笔记同步助手图形界面 (Final Fixed Version)
Author: Ning (willingning-coder)
Date: 2025-12-26
Version: 1.0.2 (Stable)

Description:
    基于 main.py 的图形界面版本。
    修复了日志捕获问题、命名冲突问题，实现了完美的控制台输出重定向。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import queue
import json
import os
import time
import webbrowser
import pyperclip
import sys
from datetime import datetime

# ================= 核心修复 1: 别名导入 =================
# 使用别名 'core' 避免与下方 def main() 函数名冲突
import main as core

class MiNoteGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MiNote Sync Pro - 小米笔记同步助手")
        self.root.geometry("800x600")
        
        # 配置文件路径
        self.config_file = "config.json"
        
        # 剪贴板监听相关
        self.clipboard_monitoring = False
        self.last_clipboard_content = ""
        
        # 日志队列 (线程安全)
        self.log_queue = queue.Queue()
        
        # 加载配置
        self.load_config()
        
        # 创建界面
        self.create_widgets()
        
        # 启动日志更新循环
        self.update_log_display()
        
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                self.config = {
                    "cookie": "",
                    "path": os.path.join(os.getcwd(), "Data", "Notes")
                }
        except Exception:
            self.config = {
                "cookie": "",
                "path": os.path.join(os.getcwd(), "Data", "Notes")
            }
            
    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_queue.put(f"❌ 保存配置失败: {e}")
            
    def create_widgets(self):
        """创建界面组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(10, weight=1) # 让日志框自动伸缩
        
        # --- 1. Cookie 区域 ---
        ttk.Label(main_frame, text="Cookie 配置:", font=("Microsoft YaHei", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        
        ttk.Label(main_frame, text="Cookie:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        self.cookie_var = tk.StringVar(value=self.config.get("cookie", ""))
        self.cookie_entry = ttk.Entry(main_frame, textvariable=self.cookie_var, width=60, show="*") # 默认隐藏
        self.cookie_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        
        self.get_cookie_btn = ttk.Button(main_frame, text="🚀 打开浏览器获取 Cookie", command=self.open_browser_for_cookie)
        self.get_cookie_btn.grid(row=1, column=2, padx=(0, 5))
        
        self.cookie_status = ttk.Label(main_frame, text="", foreground="green")
        self.cookie_status.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(2, 10))
        
        # --- 2. 路径区域 ---
        ttk.Label(main_frame, text="保存路径:", font=("Microsoft YaHei", 10, "bold")).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
        
        ttk.Label(main_frame, text="路径:").grid(row=4, column=0, sticky=tk.W, padx=(0, 5))
        self.path_var = tk.StringVar(value=self.config.get("path", ""))
        self.path_entry = ttk.Entry(main_frame, textvariable=self.path_var, width=60)
        self.path_entry.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        
        self.browse_btn = ttk.Button(main_frame, text="浏览...", command=self.browse_path)
        self.browse_btn.grid(row=4, column=2, padx=(0, 5))
        
        # --- 3. 按钮区域 ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=20)
        
        self.start_btn = ttk.Button(button_frame, text="🚀 开始同步", command=self.start_sync, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_btn = ttk.Button(button_frame, text="⏹️ 停止同步", command=self.stop_sync, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.save_config_btn = ttk.Button(button_frame, text="💾 保存配置", command=self.save_current_config)
        self.save_config_btn.pack(side=tk.LEFT)
        
        # --- 4. 进度条 ---
        self.progress_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.progress_var).grid(row=7, column=0, columnspan=3, sticky=tk.W)
        
        self.progress_bar = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress_bar.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 10))
        
        # --- 5. 日志区域 ---
        ttk.Label(main_frame, text="运行日志:", font=("Microsoft YaHei", 10, "bold")).grid(row=9, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
        
        self.log_text = scrolledtext.ScrolledText(main_frame, height=15, width=80, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.grid(row=10, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        
        self.clear_log_btn = ttk.Button(main_frame, text="🗑️ 清空日志", command=self.clear_log)
        self.clear_log_btn.grid(row=11, column=2, sticky=tk.E, pady=(5, 0))
        
        # 初始日志
        self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 MiNote Sync Pro GUI 已启动")
        
    def update_log_display(self):
        """主线程定时刷新日志显示"""
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
        except:
            pass
        self.root.after(100, self.update_log_display)
        
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        
    def open_browser_for_cookie(self):
        """打开浏览器并开始监听剪贴板"""
        try:
            webbrowser.open("https://i.mi.com/note/h5")
            self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] 🌐 已打开浏览器，请登录小米笔记")
            
            self.clipboard_monitoring = True
            self.last_clipboard_content = pyperclip.paste()
            self.cookie_status.config(text="🔍 正在监听剪贴板...", foreground="orange")
            self.get_cookie_btn.config(text="⏸️ 停止监听", command=self.stop_clipboard_monitoring)
            
            threading.Thread(target=self.monitor_clipboard, daemon=True).start()
        except Exception as e:
            messagebox.showerror("错误", f"打开浏览器失败: {e}")
            
    def stop_clipboard_monitoring(self):
        self.clipboard_monitoring = False
        self.cookie_status.config(text="", foreground="green")
        self.get_cookie_btn.config(text="🚀 打开浏览器获取 Cookie", command=self.open_browser_for_cookie)
        
    def monitor_clipboard(self):
        while self.clipboard_monitoring:
            try:
                current_content = pyperclip.paste()
                if current_content != self.last_clipboard_content and current_content.strip():
                    self.last_clipboard_content = current_content
                    if self.is_xiaomi_cookie(current_content):
                        self.cookie_var.set(current_content.strip())
                        self.clipboard_monitoring = False
                        
                        # 在主线程更新UI
                        self.root.after(0, lambda: self.cookie_status.config(text="✅ 已自动捕获 Cookie", foreground="green"))
                        self.root.after(0, lambda: self.get_cookie_btn.config(text="🚀 打开浏览器获取 Cookie", command=self.open_browser_for_cookie))
                        self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] 🎉 已自动捕获并填入 Cookie")
                        break
            except:
                pass
            time.sleep(1)
            
    def is_xiaomi_cookie(self, content):
        content = content.strip()
        if len(content) < 50: return False
        if "serviceToken" in content: return True
        if content.count("=") >= 3 and ";" in content: return True
        return False
        
    def browse_path(self):
        path = filedialog.askdirectory(initialdir=self.path_var.get())
        if path:
            self.path_var.set(path)
            
    def save_current_config(self):
        self.config["cookie"] = self.cookie_var.get()
        self.config["path"] = self.path_var.get()
        self.save_config()
        self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] 💾 配置已保存")
        messagebox.showinfo("成功", "配置已保存")
        
    def start_sync(self):
        cookie = self.cookie_var.get().strip()
        path = self.path_var.get().strip()
        
        if not cookie:
            messagebox.showerror("错误", "请先输入 Cookie")
            return
        if not path:
            messagebox.showerror("错误", "请选择保存路径")
            return
        
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"创建目录失败: {e}")
            return
            
        # UI 更新
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_bar.start()
        self.progress_var.set("正在同步...")
        self.save_current_config()
        
        # === 核心修复 2: 变量注入 (使用 core 别名) ===
        core.COOKIE = cookie
        core.VAULT_ROOT = path
        core.ASSETS_DIR = os.path.join(path, "assets")
        
        # 启动后台线程
        self.sync_thread = threading.Thread(target=self.run_sync, daemon=True)
        self.sync_thread.start()
        
    def stop_sync(self):
        self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] ⏹️ 停止功能暂未实现 (需强制关闭)")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.progress_var.set("已停止")

    # ================= 核心修复 3: 标准输出重定向 =================
    def run_sync(self):
        """后台同步线程"""
        
        # 定义一个简单的重定向器，把 print 写到 log_queue
        class StdoutRedirector:
            def __init__(self, queue):
                self.queue = queue
            def write(self, string):
                if string.strip():
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    # 去掉原有 print 可能自带的换行，避免重复换行
                    clean_str = string.strip()
                    self.queue.put(f"[{timestamp}] {clean_str}")
            def flush(self):
                pass

        # 保存原始 stdout，防止程序崩坏
        original_stdout = sys.stdout
        
        try:
            # 劫持 sys.stdout
            sys.stdout = StdoutRedirector(self.log_queue)
            
            # 调用 core (main.py) 的逻辑
            self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 开始调用核心同步逻辑...")
            
            core.setup_dirs()
            notes_list, folder_map = core.fetch_note_list()
            
            if not notes_list:
                self.log_queue.put("❌ 未获取到笔记列表，请检查 Cookie")
            else:
                self.log_queue.put(f"📦 发现云端笔记 {len(notes_list)} 条，开始处理...")
                # 线程池执行
                with core.ThreadPoolExecutor(max_workers=8) as pool:
                    list(pool.map(core.process_single_note, [(n, folder_map) for n in notes_list]))
                
                self.log_queue.put(f"🎉 全部同步完成！")

        except Exception as e:
            # 这里的 print 也会被捕获并显示在 GUI
            print(f"❌ 发生未知错误: {e}")
        finally:
            # 无论如何，最后都要还原 stdout，否则关掉 GUI 后控制台会报错
            sys.stdout = original_stdout
            # 通知主线程任务结束
            self.root.after(0, lambda: self.sync_finished(True))

    def sync_finished(self, success):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.progress_var.set("任务结束")
        if success:
            messagebox.showinfo("提示", "同步任务流程已结束 (详见日志)")

def main():
    root = tk.Tk()
    try:
        import ttkbootstrap as ttk
        style = ttk.Style(theme="cosmo")
        app = MiNoteGUI(root)
    except ImportError:
        import tkinter.ttk as ttk
        app = MiNoteGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()