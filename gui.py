# -*- coding: utf-8 -*-
"""
MiNote Sync GUI - 小米笔记同步助手 (v1.1.0)
Author: Ning (willingning-coder)
Date: 2025-12-29
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
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# 导入核心逻辑类
from main import MiNoteSyncCore

class MiNoteGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MiNote Sync Pro - 小米笔记同步助手 v1.2.0")
        self.root.geometry("850x650")
        
        self.config_file = "config.json"
        self.log_queue = queue.Queue()
        self.core_instance = None # 核心实例
        self.is_running = False
        
        self.load_config()
        self.create_widgets()
        self.update_log_display()
        
    def log(self, message):
        """核心类调用的回调函数，将日志推入队列"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                self.config = {"cookie": "", "path": os.path.join(os.getcwd(), "Data", "Notes")}
        except:
            self.config = {"cookie": "", "path": os.path.join(os.getcwd(), "Data", "Notes")}
            
    def save_config(self):
        self.config["cookie"] = self.cookie_var.get()
        self.config["path"] = self.path_var.get()
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"❌ 保存配置失败: {e}")

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- 标题 ---
        ttk.Label(main_frame, text="MiNote Sync Pro", font=("Microsoft YaHei", 16, "bold")).pack(pady=(0, 10))
        
        # --- 配置区 ---
        config_frame = ttk.LabelFrame(main_frame, text="同步配置", padding="10")
        config_frame.pack(fill=tk.X, pady=5)
        
        # Cookie
        row1 = ttk.Frame(config_frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="Cookie:").pack(side=tk.LEFT)
        self.cookie_var = tk.StringVar(value=self.config.get("cookie", ""))
        ttk.Entry(row1, textvariable=self.cookie_var, show="*").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row1, text="🌐 获取 Cookie", command=self.open_browser_for_cookie).pack(side=tk.LEFT)
        
        self.cookie_status = ttk.Label(config_frame, text="", foreground="green", font=("Microsoft YaHei", 8))
        self.cookie_status.pack(anchor=tk.W, padx=50)

        # Path
        row2 = ttk.Frame(config_frame)
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="保存至:").pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=self.config.get("path", ""))
        ttk.Entry(row2, textvariable=self.path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row2, text="📂 浏览...", command=self.browse_path).pack(side=tk.LEFT)
        
        # --- 控制区 ---
        ctrl_frame = ttk.Frame(main_frame, padding="10")
        ctrl_frame.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(ctrl_frame, text="🚀 开始同步", command=self.start_sync_thread)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(ctrl_frame, text="⏹️ 停止同步", command=self.stop_sync, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.progress_bar = ttk.Progressbar(ctrl_frame, mode='indeterminate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        # --- 日志区 ---
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, font=("Consolas", 9), state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 底部栏
        ttk.Button(main_frame, text="清除日志", command=self.clear_log).pack(anchor=tk.E, pady=5)

    def update_log_display(self):
        try:
            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
        except: pass
        self.root.after(100, self.update_log_display)

    def clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def open_browser_for_cookie(self):
        webbrowser.open("https://i.mi.com/note/h5")
        self.log("🌐 已打开浏览器，请登录小米笔记。")
        self.cookie_status.config(text="正在监听剪贴板 (请复制请求头中的 Cookie)...", foreground="orange")
        self.check_clipboard_loop()

    def check_clipboard_loop(self):
        """简单的剪贴板监听"""
        try:
            content = pyperclip.paste().strip()
            if "serviceToken" in content and ";" in content and len(content) > 50:
                self.cookie_var.set(content)
                self.cookie_status.config(text="✅ 已成功捕获 Cookie！", foreground="green")
                self.log("🎉 Cookie 自动捕获成功！")
                return
        except: pass
        self.root.after(1000, self.check_clipboard_loop)

    def browse_path(self):
        p = filedialog.askdirectory()
        if p: self.path_var.set(p)

    def start_sync_thread(self):
        if not self.cookie_var.get() or not self.path_var.get():
            messagebox.showwarning("提示", "请先配置 Cookie 和 保存路径")
            return
            
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_bar.start(10)
        self.save_config()
        
        threading.Thread(target=self.run_sync_logic, daemon=True).start()

    def run_sync_logic(self):
        try:
            self.log("🚀 初始化核心同步引擎...")
            # 实例化核心类，传入 self.log 作为回调
            self.core_instance = MiNoteSyncCore(
                cookie=self.cookie_var.get(),
                save_path=self.path_var.get(),
                log_callback=self.log
            )
            
            self.core_instance.setup_dirs()
            
            # 获取列表
            notes, folders = self.core_instance.fetch_note_list()
            if not notes:
                self.log("⚠️ 未获取到笔记，任务结束。")
            else:
                self.log(f"📦 开始处理 {len(notes)} 条笔记 (4线程并发)...")
                # 线程池执行
                with ThreadPoolExecutor(max_workers=4) as pool:
                    # 使用 map 可以按顺序提交，但这里我们需要随时检查 stop_flag
                    # 也可以直接提交所有任务，但在 task 内部检查 stop_flag
                    futures = [pool.submit(self.core_instance.process_single_note, (n, folders)) for n in notes]
                    
                    # 等待所有任务完成
                    for f in futures:
                        if self.core_instance.stop_flag: break
                        f.result() # 这里的异常已被内部捕获
                        
            self.log("🎉 任务流程结束。")
            
        except Exception as e:
            self.log(f"❌ 发生致命错误: {e}")
        finally:
            self.is_running = False
            self.root.after(0, self.on_sync_finished)

    def stop_sync(self):
        if self.core_instance:
            self.core_instance.stop()
            self.log("🛑 正在停止... (等待当前任务完成)")
            self.stop_btn.config(state=tk.DISABLED)

    def on_sync_finished(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.core_instance = None

def main():
    root = tk.Tk()
    try:
        import ttkbootstrap as ttk
        style = ttk.Style(theme="cosmo")
    except: pass
    app = MiNoteGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
