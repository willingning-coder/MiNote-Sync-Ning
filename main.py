# -*- coding: utf-8 -*-
"""
Project: MiNote-Sync Core (核心逻辑库)
Author: Ning (willingning-coder)
Date: 2025-12-29
Version: 1.1.0 (Refactored)

Description:
    纯净的逻辑处理核心，负责与小米服务器通信、数据清洗及文件写入。
    不包含任何 GUI 代码，可被 CLI 或 GUI 独立调用。
"""

import json
import os
import re
import requests
import time
import html
import random
from concurrent.futures import ThreadPoolExecutor

class MiNoteSyncCore:
    def __init__(self, cookie, save_path, log_callback=None):
        """
        :param cookie: 小米云服务 Cookie
        :param save_path: 笔记保存根目录
        :param log_callback: 日志回调函数 (接收 str 参数)
        """
        self.cookie = cookie
        self.vault_root = save_path
        self.assets_dir = os.path.join(save_path, "assets")
        self.log_callback = log_callback or print
        self.stop_flag = False  # 停止标志位

    def log(self, message):
        """统一日志出口"""
        self.log_callback(message)

    def stop(self):
        """外部调用此方法以中断同步"""
        self.stop_flag = True
        self.log("⚠️ 收到停止指令，正在结束当前任务...")

    def get_headers(self):
        return {
            "Cookie": self.cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Referer": "https://i.mi.com/note/h5",
            "Origin": "https://i.mi.com"
        }

    def request_with_retry(self, url, retries=3, stream=False):
        """指数退避重试网络请求"""
        for i in range(retries):
            if self.stop_flag: return None
            try:
                response = requests.get(url, headers=self.get_headers(), stream=stream, timeout=15)
                if response.status_code in [200, 404]:
                    return response
                elif response.status_code == 401:
                    self.log("❌ Cookie 已失效 (401 Unauthorized)")
                    return None
                elif response.status_code in [403, 429, 500, 502, 503]:
                    raise ValueError(f"Server Error {response.status_code}")
            except Exception as e:
                wait_time = (1 * (2 ** i)) + random.uniform(0, 1)
                if i < retries - 1:
                    self.log(f"    ⚠️ 网络抖动，{wait_time:.1f}s 后重试... ({e})")
                    time.sleep(wait_time)
                else:
                    self.log(f"    ❌ 请求最终失败: {url}")
                    return None
        return None

    def setup_dirs(self):
        if not os.path.exists(self.vault_root): os.makedirs(self.vault_root)
        if not os.path.exists(self.assets_dir): os.makedirs(self.assets_dir)

    def sanitize_filename(self, name):
        if not name: return "未命名"
        name = re.sub(r'[\x00-\x1f]', '', name)
        # 限制长度为 50，防止 Windows 路径溢出
        return re.sub(r'[\\/*?:"<>|]', "", name).replace('\n', ' ').strip()[:50]

    def clean_content(self, content):
        """HTML/XML 深度清洗"""
        if not content: return ""
        content = content.replace("<br>", "\n").replace("<br/>", "\n")
        content = content.replace("</div>", "\n").replace("</p>", "\n")
        content = re.sub(r'<text[^>]*>(.*?)</text>', r'\1', content, flags=re.S)
        content = re.sub(r'<background[^>]*>(.*?)</background>', r'\1', content, flags=re.S)
        content = re.sub(r'<[^>]+>', '', content)
        content = html.unescape(content)
        return content.strip()

    def get_real_extension(self, response):
        ctype = response.headers.get("Content-Type", "").lower()
        if "amr" in ctype: return ".amr"
        if "wav" in ctype: return ".wav"
        if "mpeg" in ctype or "mp3" in ctype or "audio" in ctype: return ".mp3"
        if "png" in ctype: return ".png"
        if "gif" in ctype: return ".gif"
        if "jpeg" in ctype or "jpg" in ctype: return ".jpg"
        return ".jpg"

    def download_resource(self, fid):
        # 增量检查
        for ext in [".jpg", ".png", ".gif", ".mp3", ".amr", ".wav", ".m4a", ".webp"]:
            fname = f"{fid}{ext}"
            fpath = os.path.join(self.assets_dir, fname)
            if os.path.exists(fpath) and os.path.getsize(fpath) > 1000:
                return fname

        types = ["note_img", "file", "note_voice", "note_audio"]
        for tp in types:
            if self.stop_flag: return None
            url = f"https://i.mi.com/file/full?type={tp}&fileid={fid}"
            r = self.request_with_retry(url, retries=2, stream=True)
            if r and r.status_code == 200:
                if int(r.headers.get('content-length', 0)) < 1000: continue
                real_ext = self.get_real_extension(r)
                fname = f"{fid}{real_ext}"
                try:
                    with open(os.path.join(self.assets_dir, fname), "wb") as f:
                        for chunk in r.iter_content(1024): f.write(chunk)
                    return fname
                except Exception as e:
                    self.log(f"    ⚠️ 资源写入失败: {e}")
        return None

    def fetch_note_list(self):
        self.log("📡 正在连接小米云服务...")
        all_entries = []
        folders_map = {'0': '未分类'}
        sync_tag = None
        current_page = 0
        
        while not self.stop_flag:
            current_page += 1
            url = f"https://i.mi.com/note/full/page/?limit=200&ts={int(time.time()*1000)}"
            if sync_tag: url += f"&syncTag={sync_tag}"
            
            r = self.request_with_retry(url)
            if not r: break # 重试耗尽或 Cookie 失效
            
            try:
                json_data = r.json()
                data = json_data.get('data', {})
                
                # 更新文件夹映射
                for f in data.get('folders', []):
                    folders_map[str(f.get('id'))] = f.get('subject')
                
                entries = data.get('entries', [])
                if not entries: break
                
                all_entries.extend(entries)
                self.log(f"    已索引 {len(all_entries)} 条笔记 (第 {current_page} 页)...")
                
                sync_tag = data.get('syncTag')
                if not sync_tag or current_page >= 500: break
                
                time.sleep(0.5)
            except Exception as e:
                self.log(f"❌ 解析列表失败: {e}")
                break
        
        return all_entries, folders_map

    def fetch_note_detail(self, note_id):
        url = f"https://i.mi.com/note/note/{note_id}/?ts={int(time.time()*1000)}"
        r = self.request_with_retry(url, retries=3)
        if r and r.status_code == 200:
            return r.json().get('data', {}).get('entry')
        return None

    def process_single_note(self, args):
        """单个任务处理函数 (由线程池调用)"""
        if self.stop_flag: return

        entry, folder_map = args
        nid = entry['id']
        
        try:
            folder_id = str(entry.get('folderId', '0'))
            folder_name = folder_map.get(folder_id, "未分类")
            
            extra = {}
            try: extra = json.loads(entry.get('extraInfo', '{}'))
            except: pass
            
            title = extra.get('title') or entry.get('snippet', '无标题')
            title = self.sanitize_filename(title)
            if not title: title = f"无标题"
            
            date_str = time.strftime("%Y%m%d", time.localtime(entry['createDate']/1000))
            target_dir = os.path.join(self.vault_root, self.sanitize_filename(folder_name))
            
            # 【重要优化】防止文件名冲突：添加 ID 后4位
            filename = f"{date_str}_{title}_{str(nid)[-4:]}.md"
            md_path = os.path.join(target_dir, filename)
            
            # 增量跳过
            if os.path.exists(md_path) and os.path.getsize(md_path) > 0:
                self.log(f"    ⏭️ [跳过] {title}")
                return 

            full_note = self.fetch_note_detail(nid)
            if not full_note:
                self.log(f"    ⚠️ [失败] 无法获取详情: {title}")
                return

            content = full_note.get('content', '')
            if not os.path.exists(target_dir): os.makedirs(target_dir, exist_ok=True)
            
            # --- 资源提取逻辑 ---
            ids = set()
            ids.update(re.findall(r'fileid=["\']?([\w\.\-]+)["\']?', content, re.I))
            ids.update(re.findall(r'☺\s*([\w\.\-]+)', content))
            ids.update(re.findall(r'<fileId:(\d+)', content))
            ids.update(re.findall(r'<sound[^>]+fileid=["\']?([\w\.\-]+)["\']?', content, re.I))
            
            voice_list = extra.get('voice_list') or extra.get('audio_list') or []
            voice_ids = [v['fileId'] for v in voice_list if v.get('fileId')]
            ids.update(voice_ids)
            
            if full_note.get('setting'):
                try:
                    for res in json.loads(full_note.get('setting', '{}')).get('data', []):
                        if res.get('fileId'): ids.add(res.get('fileId'))
                except: pass

            replacements = {}
            for fid in ids:
                if self.stop_flag: return
                fname = self.download_resource(fid)
                if fname: replacements[fid] = f"![[{fname}]]"

            # --- 内容替换 ---
            content = self.clean_content(content)
            for fid, link in replacements.items():
                content = re.sub(fr'<sound[^>]*{re.escape(fid)}[^>]*\/?>', f"\n{link}\n", content)
                content = re.sub(fr'<[^>]*{re.escape(fid)}[^>]*>', f"\n{link}\n", content)
                content = re.sub(fr'☺\s*{re.escape(fid)}.*', f"\n{link}\n", content)
                content = content.replace(f"<fileId:{fid}>", f"\n{link}\n")
                content = content.replace(f"<fileId:{fid}/>", f"\n{link}\n")

            if voice_ids:
                appended = False
                for vid in voice_ids:
                    if vid not in content and vid in replacements:
                        if not appended:
                            content += "\n\n---\n**🎙️ 附件录音：**\n"
                            appended = True
                        content += f"{replacements[vid]}\n"

            # --- 文件写入 ---
            ctime_struct = time.localtime(full_note['createDate']/1000)
            mtime_struct = time.localtime(full_note['modifyDate']/1000)
            ctime_str = time.strftime("%Y-%m-%d %H:%M:%S", ctime_struct)
            mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", mtime_struct)
            
            md_text = f"---\nid: {nid}\ncreated: {ctime_str}\nupdated: {mtime_str}\ntitle: \"{title}\"\nfolder: \"{folder_name}\"\nauthor: Ning\n---\n\n# {title}\n\n{content}\n"
            
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_text)
                
            # --- 时间戳修改 ---
            try:
                mtime_ts = full_note['modifyDate'] / 1000.0
                os.utime(md_path, (mtime_ts, mtime_ts))
            except: pass

            self.log(f"    ✅ [成功] {title}")
            
        except Exception as e:
            self.log(f"    ❌ [错误] 处理笔记 {nid} 失败: {e}")

# CLI 入口兼容
def main():
    print("请运行 gui.py 或自行调用 MiNoteSyncCore 类")

if __name__ == "__main__":
    main()
