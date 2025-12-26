# -*- coding: utf-8 -*-
"""
Project: MiNote-Sync (小米笔记同步助手)
Author: Ning (willingning-coder)
Date: 2025-12-26
Version: 1.0.0

Description:
    全网最完善的小米笔记导出/同步方案。
    支持文件夹分类、录音/图片完美下载（修复长ID问题）、增量更新、Obsidian 深度适配。
    
    This tool is designed to sync Xiaomi Notes to local Markdown files 
    optimized for Obsidian, featuring incremental updates and audio repair.
"""

import json
import os
import re
import requests
import time
from concurrent.futures import ThreadPoolExecutor

# ================= 1. 配置区 =================

# 默认将笔记保存在当前脚本目录下的 "Data" 文件夹中
BASE_DIR = os.getcwd()
VAULT_ROOT = os.path.join(BASE_DIR, "Data", "Notes")
ASSETS_DIR = os.path.join(VAULT_ROOT, "assets")

# Cookie 全局变量
COOKIE = "" 

# ================= 2. 核心逻辑区 =================

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

def setup_dirs():
    if not os.path.exists(VAULT_ROOT): os.makedirs(VAULT_ROOT)
    if not os.path.exists(ASSETS_DIR): os.makedirs(ASSETS_DIR)

def sanitize_filename(name):
    """清洗文件名，防止系统报错"""
    return re.sub(r'[\\/*?:"<>|]', "", name).replace('\n', ' ').strip()[:50]

def clean_content(content):
    """深度清洗 XML 垃圾代码"""
    if not content: return ""
    content = re.sub(r'<text[^>]*>(.*?)</text>', r'\1', content, flags=re.S)
    content = re.sub(r'<background[^>]*>(.*?)</background>', r'\1', content, flags=re.S)
    content = content.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
    return content

def get_real_extension(response):
    """智能后缀识别"""
    ctype = response.headers.get("Content-Type", "").lower()
    if "amr" in ctype: return ".amr"
    if "wav" in ctype: return ".wav"
    if "mpeg" in ctype or "mp3" in ctype or "audio" in ctype: return ".mp3"
    if "png" in ctype: return ".png"
    if "gif" in ctype: return ".gif"
    return ".jpg"

def download_resource(fid):
    """万能资源下载器 (增量 + 接口穷举)"""
    # 增量跳过
    for ext in [".jpg", ".png", ".gif", ".mp3", ".amr", ".wav", ".m4a", ".webp"]:
        fname = f"{fid}{ext}"
        fpath = os.path.join(ASSETS_DIR, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 1000:
            return fname

    # 接口穷举
    headers = get_headers()
    types = ["note_img", "file", "note_voice", "note_audio"]
    for tp in types:
        try:
            url = f"https://i.mi.com/file/full?type={tp}&fileid={fid}"
            r = requests.get(url, headers=headers, stream=True, timeout=10)
            if r.status_code == 200:
                if int(r.headers.get('content-length', 0)) < 1000: continue
                real_ext = get_real_extension(r)
                fname = f"{fid}{real_ext}"
                with open(os.path.join(ASSETS_DIR, fname), "wb") as f:
                    for chunk in r.iter_content(1024): f.write(chunk)
                return fname
        except: pass
    return None

def fetch_note_list():
    """爬虫：自动翻页获取列表"""
    print("📡 正在连接小米云服务...")
    headers = get_headers()
    all_entries = []
    folders_map = {'0': '未分类'}
    sync_tag = None
    
    while True:
        url = f"https://i.mi.com/note/full/page/?limit=200&ts={int(time.time()*1000)}"
        if sync_tag: url += f"&syncTag={sync_tag}"
        
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 401:
                print("❌ Cookie 已失效，请重新获取！")
                return None, None
                
            data = r.json().get('data', {})
            
            for f in data.get('folders', []):
                folders_map[str(f.get('id'))] = f.get('subject')
            
            entries = data.get('entries', [])
            all_entries.extend(entries)
            print(f"    已索引 {len(all_entries)} 条笔记...")
            
            sync_tag = data.get('syncTag')
            if not sync_tag: break
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ 网络请求错误: {e}")
            break
            
    return all_entries, folders_map

def fetch_note_detail(note_id):
    """获取详情"""
    url = f"https://i.mi.com/note/note/{note_id}/?ts={int(time.time()*1000)}"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        return r.json().get('data', {}).get('entry')
    except:
        return None

def process_single_note(args):
    """单条笔记处理流程 (含增量检测)"""
    entry, folder_map = args
    nid = entry['id']
    
    # 路径计算
    folder_id = str(entry.get('folderId', '0'))
    folder_name = folder_map.get(folder_id, "未分类")
    
    extra = {}
    try: extra = json.loads(entry.get('extraInfo', '{}'))
    except: pass
    
    title = extra.get('title') or entry.get('snippet', '无标题')
    title = sanitize_filename(title)
    if not title: title = f"无标题_{nid}"
    
    date_str = time.strftime("%Y%m%d", time.localtime(entry['createDate']/1000))
    target_dir = os.path.join(VAULT_ROOT, sanitize_filename(folder_name))
    md_path = os.path.join(target_dir, f"{date_str}_{title}.md")
    
    # === 增量检测 ===
    if os.path.exists(md_path):
        return # 本地已存在，跳过
        
    # === 下载与处理 ===
    full_note = fetch_note_detail(nid)
    if not full_note: return
    content = full_note.get('content', '')
    
    if not os.path.exists(target_dir): 
        os.makedirs(target_dir, exist_ok=True)
    
    # 提取资源ID
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

    # 下载资源
    replacements = {}
    for fid in ids:
        fname = download_resource(fid)
        if fname:
            replacements[fid] = f"![[{fname}]]"

    # 清洗与替换
    content = clean_content(content)
    for fid, link in replacements.items():
        content = re.sub(fr'<sound[^>]*{re.escape(fid)}[^>]*\/?>', f"\n{link}\n", content)
        content = re.sub(fr'<[^>]*{re.escape(fid)}[^>]*>', f"\n{link}\n", content)
        content = re.sub(fr'☺\s*{re.escape(fid)}.*', f"\n{link}\n", content)
        content = content.replace(f"<fileId:{fid}>", f"\n{link}\n")
        content = content.replace(f"<fileId:{fid}/>", f"\n{link}\n")

    # 追加录音
    if voice_ids:
        appended = False
        for vid in voice_ids:
            if vid not in content and vid in replacements:
                if not appended:
                    content += "\n\n---\n**🎙️ 附件录音：**\n"
                    appended = True
                content += f"{replacements[vid]}\n"

    # 生成 Markdown
    ctime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(full_note['createDate']/1000))
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(full_note['modifyDate']/1000))
    
    md_text = f"---\nid: {nid}\ncreated: {ctime}\nupdated: {mtime}\ntitle: \"{title}\"\nfolder: \"{folder_name}\"\nauthor: Ning\n---\n\n# {title}\n\n{content}\n"
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"    ✅ 同步成功: [{folder_name}] {title}")

def main():
    print(f"🚀 MiNote Sync Pro - By Ning")
    setup_dirs()
    
    notes_list, folder_map = fetch_note_list()
    if not notes_list: return

    print(f"📦 发现云端笔记 {len(notes_list)} 条，开始增量同步...")
    
    with ThreadPoolExecutor(max_workers=8) as pool:
        pool.map(process_single_note, [(n, folder_map) for n in notes_list])
        
    print(f"\n🎉 全部同步完成！数据已保存至: {VAULT_ROOT}")

if __name__ == "__main__":
    main()