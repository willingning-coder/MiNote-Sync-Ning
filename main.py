# -*- coding: utf-8 -*-
"""
Project: MiNote-Sync Pro (小米笔记同步助手)
Author: Ning (willingning-coder)
Date: 2025-12-29
Version: 1.1.0 (Robust Edition)

Changelog:
    v1.1.0: 
      - 修复 HTML 标签清洗不彻底导致“垃圾信息”残留的问题。
      - 新增文件系统时间戳同步 (os.utime)，让文件修改时间回归笔记真实时间。
      - 新增指数退避重试机制 (Exponential Backoff)，彻底解决“无法获取详情”的网络波动报错。
    v1.0.2: 
      - 修复列表抓取死循环。
"""

import json
import os
import re
import requests
import time
import html
import random
from concurrent.futures import ThreadPoolExecutor

# ================= 1. 配置区 =================

BASE_DIR = os.getcwd()
VAULT_ROOT = os.path.join(BASE_DIR, "Data", "Notes")
ASSETS_DIR = os.path.join(VAULT_ROOT, "assets")

# Cookie 全局变量
COOKIE = "" 

# ================= 2. 核心工具库 =================

def get_headers():
    global COOKIE
    if not COOKIE:
        print("\n" + "="*50)
        print("🔒 为了保护隐私，请手动输入 Cookie")
        print("   1. 登录 https://i.mi.com/note/h5")
        print("   2. 按 F12 打开控制台 -> 网络(Network)")
        print("   3. 刷新页面，点击任意请求，复制请求头中的 Cookie")
        print("="*50)
        COOKIE = input("👉 请粘贴 Cookie 并回车: ").strip()
    
    return {
        "Cookie": COOKIE,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Referer": "https://i.mi.com/note/h5",
        "Origin": "https://i.mi.com"
    }

def request_with_retry(url, headers, retries=3, stream=False):
    """
    【高阶修复】指数退避重试机制
    解决 Issue #1: "同步过程中出现警告无法获取详情"
    原理：失败后等待 1s, 2s, 4s... 避免因网络抖动直接熔断
    """
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, stream=stream, timeout=15)
            # 针对 API 限制的 403/429/502 错误进行特定重试
            if response.status_code in [200, 404]:
                return response
            elif response.status_code in [403, 429, 500, 502, 503]:
                raise ValueError(f"Server Error {response.status_code}")
        except Exception as e:
            wait_time = (1 * (2 ** i)) + random.uniform(0, 1) # 增加随机抖动
            if i < retries - 1:
                print(f"    ⚠️ 请求不稳定，{wait_time:.1f}秒后重试... ({e})")
                time.sleep(wait_time)
            else:
                print(f"    ❌ 重试耗尽，请求失败: {url}")
                return None
    return None

def setup_dirs():
    if not os.path.exists(VAULT_ROOT): os.makedirs(VAULT_ROOT)
    if not os.path.exists(ASSETS_DIR): os.makedirs(ASSETS_DIR)

def sanitize_filename(name):
    if not name: return "未命名"
    # 移除不可见字符和非法路径字符
    name = re.sub(r'[\x00-\x1f]', '', name)
    return re.sub(r'[\\/*?:"<>|]', "", name).replace('\n', ' ').strip()[:80]

def clean_content(content):
    """
    【高阶修复】深度清洗 HTML/XML 垃圾代码
    解决 Issue #2: "同步好的文件依然有垃圾信息"
    """
    if not content: return ""
    
    # 1. 将 HTML 换行符转换为 Markdown 换行
    content = content.replace("<br>", "\n").replace("<br/>", "\n")
    content = content.replace("</div>", "\n").replace("</p>", "\n")
    
    # 2. 移除特定标签保留内容 (如 text, background)
    content = re.sub(r'<text[^>]*>(.*?)</text>', r'\1', content, flags=re.S)
    content = re.sub(r'<background[^>]*>(.*?)</background>', r'\1', content, flags=re.S)
    
    # 3. 暴力移除所有剩余的 <xxx> 标签 (清理 div, font, span 等)
    content = re.sub(r'<[^>]+>', '', content)
    
    # 4. 解码 HTML 实体 (如 &nbsp; -> 空格, &lt; -> <)
    content = html.unescape(content)
    
    return content.strip()

def get_real_extension(response):
    ctype = response.headers.get("Content-Type", "").lower()
    if "amr" in ctype: return ".amr"
    if "wav" in ctype: return ".wav"
    if "mpeg" in ctype or "mp3" in ctype or "audio" in ctype: return ".mp3"
    if "png" in ctype: return ".png"
    if "gif" in ctype: return ".gif"
    if "jpeg" in ctype or "jpg" in ctype: return ".jpg"
    return ".jpg"

# ================= 3. 业务逻辑区 =================

def download_resource(fid):
    # 增量跳过检查
    for ext in [".jpg", ".png", ".gif", ".mp3", ".amr", ".wav", ".m4a", ".webp"]:
        fname = f"{fid}{ext}"
        fpath = os.path.join(ASSETS_DIR, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 1000:
            return fname

    headers = get_headers()
    types = ["note_img", "file", "note_voice", "note_audio"]
    
    for tp in types:
        url = f"https://i.mi.com/file/full?type={tp}&fileid={fid}"
        # 使用重试机制下载资源
        r = request_with_retry(url, headers, retries=2, stream=True)
        if r and r.status_code == 200:
            if int(r.headers.get('content-length', 0)) < 1000: continue
            real_ext = get_real_extension(r)
            fname = f"{fid}{real_ext}"
            try:
                with open(os.path.join(ASSETS_DIR, fname), "wb") as f:
                    for chunk in r.iter_content(1024): f.write(chunk)
                return fname
            except Exception as e:
                print(f"    ⚠️ 写入资源失败: {e}")
    return None

def fetch_note_list():
    print("📡 正在连接小米云服务...")
    headers = get_headers()
    all_entries = []
    folders_map = {'0': '未分类'}
    sync_tag = None
    max_pages = 500 
    current_page = 0
    
    while True:
        current_page += 1
        url = f"https://i.mi.com/note/full/page/?limit=200&ts={int(time.time()*1000)}"
        if sync_tag: url += f"&syncTag={sync_tag}"
        
        # 使用重试机制获取列表
        r = request_with_retry(url, headers)
        
        if not r:
            print("❌ 网络连接严重错误，无法获取列表。")
            break
            
        if r.status_code == 401:
            print("❌ Cookie 已失效，请重新获取！")
            return None, None
        
        try:
            json_data = r.json()
            data = json_data.get('data', {})
            
            for f in data.get('folders', []):
                folders_map[str(f.get('id'))] = f.get('subject')
            
            entries = data.get('entries', [])
            if not entries:
                print("    ✅ 已到达最后一页，停止抓取列表。")
                break
            
            all_entries.extend(entries)
            print(f"    已索引 {len(all_entries)} 条笔记 (第 {current_page} 页)...")
            
            sync_tag = data.get('syncTag')
            if not sync_tag or current_page >= max_pages: 
                break
            
            time.sleep(0.5) # 基础限流
        except Exception as e:
            print(f"❌ 解析列表数据失败: {e}")
            break
            
    return all_entries, folders_map

def fetch_note_detail(note_id):
    url = f"https://i.mi.com/note/note/{note_id}/?ts={int(time.time()*1000)}"
    # 使用重试机制
    r = request_with_retry(url, get_headers(), retries=3)
    if r and r.status_code == 200:
        return r.json().get('data', {}).get('entry')
    return None

def process_single_note(args):
    """单条笔记处理流程"""
    try:
        entry, folder_map = args
        nid = entry['id']
        
        # 1. 基础元数据提取
        folder_id = str(entry.get('folderId', '0'))
        folder_name = folder_map.get(folder_id, "未分类")
        
        extra = {}
        try: extra = json.loads(entry.get('extraInfo', '{}'))
        except: pass
        
        title = extra.get('title') or entry.get('snippet', '无标题')
        title = sanitize_filename(title)
        if not title: title = f"无标题_{nid}"
        
        # 2. 准备文件路径
        date_str = time.strftime("%Y%m%d", time.localtime(entry['createDate']/1000))
        target_dir = os.path.join(VAULT_ROOT, sanitize_filename(folder_name))
        md_path = os.path.join(target_dir, f"{date_str}_{title}.md")
        
        # 3. 增量检测 (如果本地已存在且文件大小>0，跳过)
        if os.path.exists(md_path) and os.path.getsize(md_path) > 0:
            print(f"    ⏭️ [跳过] 本地已存在: {title}")
            return 
            
        # 4. 获取详情 (含重试)
        full_note = fetch_note_detail(nid)
        if not full_note: 
            print(f"    ⚠️ [警告] 无法获取详情 (重试耗尽): {title}")
            return

        content = full_note.get('content', '')
        
        if not os.path.exists(target_dir): 
            os.makedirs(target_dir, exist_ok=True)
        
        # 5. 资源提取与下载
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
            fname = download_resource(fid)
            if fname:
                replacements[fid] = f"![[{fname}]]"

        # 6. 内容深度清洗与替换
        content = clean_content(content) # 使用新的清洗函数
        
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

        # 7. 生成 Markdown 文件
        ctime_struct = time.localtime(full_note['createDate']/1000)
        mtime_struct = time.localtime(full_note['modifyDate']/1000)
        ctime_str = time.strftime("%Y-%m-%d %H:%M:%S", ctime_struct)
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", mtime_struct)
        
        md_text = f"---\nid: {nid}\ncreated: {ctime_str}\nupdated: {mtime_str}\ntitle: \"{title}\"\nfolder: \"{folder_name}\"\nauthor: Ning\n---\n\n# {title}\n\n{content}\n"
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
            
        # 8. 【核心修复】强制修改文件系统时间戳
        # 解决 Issue #2: "定格都是创建日期"
        try:
            mtime_timestamp = full_note['modifyDate'] / 1000.0
            # os.utime(path, (access_time, modification_time))
            os.utime(md_path, (mtime_timestamp, mtime_timestamp))
        except Exception as e:
            pass # 时间戳修改失败不影响文件内容，静默处理

        print(f"    ✅ [同步成功] [{folder_name}] {title}")
        
    except Exception as e:
        print(f"    ❌ [错误] 处理笔记 {entry.get('id', 'Unknown')} 失败: {e}")

def main():
    print(f"🚀 MiNote Sync Pro - By Ning (v1.1.0 Robust)")
    setup_dirs()
    
    notes_list, folder_map = fetch_note_list()
    if not notes_list: 
        print("⚠️ 未发现笔记或 Cookie 失效")
        return

    print(f"📦 发现云端笔记 {len(notes_list)} 条，准备开始同步...")
    print(f"⚙️  线程池模式 (Max Workers: 4) - 降低并发以提高稳定性")
    
    # 降低并发数，配合重试机制，确保稳定性
    with ThreadPoolExecutor(max_workers=4) as pool:
        pool.map(process_single_note, [(n, folder_map) for n in notes_list])
        
    print(f"\n🎉 全部同步完成！数据已保存至: {VAULT_ROOT}")

if __name__ == "__main__":
    main()
