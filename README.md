# MiNote-Sync-Ning 🚀

**全网最完善的小米笔记导出/同步方案：支持文件夹分类、录音/图片完美下载、Obsidian 格式深度适配。**

> Created by **Ning (willingning-coder)**

## ✨ 核心特性

市面上的导出脚本大多存在录音无法下载、排版混乱或丢失文件夹结构的问题。本项目通过逆向分析小米最新 API，实现了：

* **🎧 录音完美修复**：独家算法解决“长 ID”录音无法下载的问题（自动识别 `note_img` 接口中的音频文件）。
* **⚡ 极速增量同步**：智能比对本地文件，只下载新增或修改的笔记，秒级完成同步。
* **📂 完美还原目录**：自动读取小米笔记的文件夹结构，并在本地建立对应的文件夹分类归档。
* **🧹 深度文本清洗**：自动剔除 XML 垃圾代码（如 `<text indent="1">`），还原纯净 Markdown。
* **🔗 Obsidian 友好**：生成的图片/录音链接采用 `![[assets/xxx]]` 标准格式，开箱即用。

## 🛠️ 使用方法

### 1. 安装依赖
需要 Python 3.x 环境。
```bash
pip install -r requirements.txt

2. 获取 Cookie
登录 小米云服务笔记页面。

按 F12 打开开发者工具 -> 网络 (Network)。

刷新页面，点击任意请求，复制 请求头 (Request Headers) 中的 Cookie。

3. 运行脚本
Bash

python main.py
首次运行脚本会提示输入 Cookie，粘贴并回车即可。

4. 导入 Obsidian
脚本运行完成后，会在当前目录下生成 Data/Notes 文件夹。 打开 Obsidian -> "打开文件夹作为库" -> 选择 Data/Notes 文件夹即可。

⚠️ 免责声明
本项目仅供学习交流使用，请勿用于非法用途。使用本工具产生的任何数据风险由用户自行承担。

📄 许可证
MIT License © 2025 Ning
