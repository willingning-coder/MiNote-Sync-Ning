# -*- coding: utf-8 -*-
"""
Project: MiNote-Sync Core (核心逻辑库)
Author: Ning (willingning-coder)
Date: 2025-12-29
Version: 1.3.0 (User-Configurable Edition)

Changelog:
    v1.3.0:
      - 新增: 文件名命名规则可配置（可选是否添加日期前缀）。
      - 修复: 强制去除 Cookie 中的换行符，解决 Invalid header value 报错。
      - 优化: 标题生成前优先清洗 CSS 垃圾词，防止文件名污染。
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
    def __init__(self, cookie, save_path, use_date_prefix=True, log_callback=None):
        """
        :param use_date_prefix: Boolean, True=文件名带日期, False=仅标题
        """
        # 【修复】强制清洗 Cookie，去除回车换行，防止 header 报错
        if cookie:
            self.cookie = cookie.replace('\n', '').replace('\r', '').strip()
        else:
            self.cookie = ""
            
        self.vault_root = save_path
        self.assets_dir = os.path.join(save_path, "assets")
        self.use_date_prefix = use_date_prefix # 新增配置项
        self.log_callback = log_callback or print
        self.stop_flag = False

    def log(self, message):
        self.log_callback(message)

    def stop(self):
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

    def clean_css_garbage(self, text):
        """【加强版】专门处理 CSS 样式残留"""
        if not text: return ""
        # 针对 text indent=1cpu 这种连体怪进行更宽泛的匹配
        # 匹配 text indent= 后面跟着的一串非空字符
        text = re.sub(r'text\s*indent\s*=\s*\S+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'class="[^"]+"', '', text)
        text = re.sub(r'style="[^"]+"', '', text)
        return text.strip()

    def sanitize_filename(self, name):
        if not name: return "未命名"
        name = self.clean_css_garbage(name) # 先洗代码
        name = re.sub(r'[\x00-\x1f]', '', name)
        name = re.sub(r'[\\/*?:"<>|]', "", name).replace('\n', ' ').strip()
        return name[:50]

    def clean_content(self, content):
        if not content: return ""
        content = content.replace("<br>", "\n").replace("<br/>", "\n")
        content = content.replace("</div>", "\n").replace("</p>", "\n")
        content = re.sub(r'<text[^>]*>(.*?)</text>', r'\1', content, flags=re.S)
        content = re.sub(r'<background[^>]*>(.*?)</background>', r'\1', content, flags=re.S)
        content = re.sub(r'<[^>]+>', '', content)
        content = self.clean_css_garbage(content) # CSS 清洗
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
            if not r: break
            
            try:
                json_data = r.json()
                data = json_data.get('data', {})
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
        if self.stop_flag: return

        entry, folder_map = args
        nid = entry['id']
        
        try:
            folder_id = str(entry.get('folderId', '0'))
            folder_name = folder_map.get(folder_id, "未分类")
            
            extra = {}
            try: extra = json.loads(entry.get('extraInfo', '{}'))
            except: pass
            
            # 1. 提取标题并【立刻清洗】
            raw_title = extra.get('title') or entry.get('snippet', '无标题')
            # 这里的清洗非常关键，确保 text indent 不会进入文件名
            title = self.sanitize_filename(raw_title)
            if not title: title = "无标题"
            
            target_dir = os.path.join(self.vault_root, self.sanitize_filename(folder_name))
            
            # 2. 【核心修改】根据用户配置决定文件名格式
            if self.use_date_prefix:
                date_str = time.strftime("%Y%m%d", time.localtime(entry['createDate']/1000))
                # 格式: 20250101_标题_ID后4位.md
                filename = f"{date_str}_{title}_{str(nid)[-4:]}.md"
            else:
                # 格式: 标题_ID后4位.md (ID后缀必须保留，否则重名笔记会覆盖)
                filename = f"{title}_{str(nid)[-4:]}.md"
                
            md_path = os.path.join(target_dir, filename)
            
            if os.path.exists(md_path) and os.path.getsize(md_path) > 0:
                self.log(f"    ⏭️ [跳过] {title}")
                return 

            full_note = self.fetch_note_detail(nid)
            if not full_note:
                self.log(f"    ⚠️ [失败] 无法获取详情: {title}")
                return

            content = full_note.get('content', '')
            if not os.path.exists(target_dir): os.makedirs(target_dir, exist_ok=True)
            
            # --- 资源提取 (省略，逻辑不变) ---
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

            # --- 内容清洗 ---
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
            
            md_text = f"---\nid: {nid}\ncreated: {ctime_str}\nupdated: {mtime_str}\ntitle: \"{title}\"\nfolder: \"{folder_name}\"\n---\n\n{content}\n"
            
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_text)
                
            try:
                mtime_ts = full_note['modifyDate'] / 1000.0
                os.utime(md_path, (mtime_ts, mtime_ts))
            except: pass

            self.log(f"    ✅ [成功] {title}")
            
        except Exception as e:
            self.log(f"    ❌ [错误] 处理笔记 {nid} 失败: {e}")

def main():
    print("请运行 gui.py 或自行调用 MiNoteSyncCore 类")

if __name__ == "__main__":
    main()
