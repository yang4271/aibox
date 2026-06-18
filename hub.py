#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AIBox v5 - 安全沙盒多文件智能开发工具
新增特性：
- 强制路径沙盒：AI 任何文件操作不得跳出项目根目录，否则拒绝执行
- 执行隔离：所有代码在临时副本中运行，原始文件完全不受影响
- 原有全部功能：多文件管理、依赖自动安装、备份、历史记忆、Markdown 预览、重点文件等

启动：python aibox.py -gui true   (GUI 模式)
      python aibox.py -gui false  (命令行模式)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# 可选 markdown 支持
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False


class FileNode:
    """单个文件的表示"""
    def __init__(self, path: str):
        self.path = path
        self.lines: List[str] = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, 'r', encoding='utf-8') as f:
                self.lines = f.read().splitlines()
        else:
            self.lines = []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.lines))

    def delete(self):
        if os.path.exists(self.path):
            os.remove(self.path)


class Project:
    """项目文件管理，并负责路径安全检查与沙盒执行"""

    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)
        self.files: Dict[str, FileNode] = {}
        os.makedirs(self.root_dir, exist_ok=True)

    # ---------- 路径安全检查 ----------
    def _safe_abspath(self, rel_path: str) -> str:
        """
        将相对路径转换为绝对路径，并确认其位于 root_dir 内。
        若路径试图逃逸，抛出 ValueError。
        """
        # 必须使用相对路径，不允许以 / 或盘符开头
        if os.path.isabs(rel_path):
            raise ValueError(f"禁止使用绝对路径: {rel_path}")
        # 解析拼接后的绝对路径
        full = os.path.abspath(os.path.join(self.root_dir, rel_path))
        # 确保规范化后仍以 root_dir 开头
        if not full.startswith(self.root_dir + os.sep) and full != self.root_dir:
            raise ValueError(f"路径逃逸被阻止: {rel_path} -> {full}")
        return full

    def _check_path_pair(self, path1: str, path2: str):
        """检查一对路径（如移动、复制）的安全性"""
        self._safe_abspath(path1)
        self._safe_abspath(path2)

    # ---------- 文件管理 ----------
    def add_file(self, rel_path: str):
        full = self._safe_abspath(rel_path)
        self.files[rel_path] = FileNode(full)

    def remove_file_record(self, rel_path: str):
        if rel_path in self.files:
            del self.files[rel_path]

    def scan_directory(self, extensions=None):
        """扫描目录树，加载代码文件"""
        if extensions is None:
            extensions = ('.py', '.cpp', '.c', '.js', '.html', '.css', '.json', '.txt')
        self.files.clear()
        for dirpath, _, filenames in os.walk(self.root_dir):
            for fname in filenames:
                if any(fname.endswith(ext) for ext in extensions):
                    rel = os.path.relpath(os.path.join(dirpath, fname), self.root_dir)
                    self.add_file(rel)

    def get_all_files_data(self) -> List[Dict]:
        """返回所有文件的 {file_path, lines} 列表"""
        data = []
        for rel in sorted(self.files.keys()):
            node = self.files[rel]
            data.append({
                "file_path": rel,
                "lines": [{"ln": i+1, "code": line} for i, line in enumerate(node.lines)]
            })
        return data

    def apply_changes(self, changes: List[Dict]) -> Tuple[bool, str]:
        """
        应用 AI 返回的文件操作，每个操作都经过路径安全检查。
        支持 modify, add, delete, move, copy, rename, mkdir, rmdir, cpdir。
        """
        try:
            for op in changes:
                action = op.get("action")

                # ===== 路径安全检查 =====
                if action in ("modify", "add", "delete", "mkdir", "rmdir"):
                    rel = op.get("file_path") or op.get("path")
                    if rel:
                        self._safe_abspath(rel)
                elif action in ("move", "copy"):
                    src = op.get("source")
                    dst = op.get("destination")
                    if src and dst:
                        self._check_path_pair(src, dst)
                elif action == "rename":
                    old = op.get("path")
                    new = op.get("new_name")
                    if old and new:
                        self._check_path_pair(old, new)
                elif action == "cpdir":
                    src = op.get("source")
                    dst = op.get("destination")
                    if src and dst:
                        self._check_path_pair(src, dst)

                # ===== 执行操作 =====
                if action == "modify":
                    rel = op["file_path"]
                    ch_list = op.get("changes", [])
                    if rel not in self.files:
                        self.add_file(rel)
                    node = self.files[rel]
                    new_lines = node.lines[:]
                    for ch in ch_list:
                        ln = ch["ln"]
                        code = ch["code"]
                        if 1 <= ln <= len(new_lines):
                            new_lines[ln-1] = code
                        elif ln > len(new_lines):
                            while len(new_lines) < ln-1:
                                new_lines.append('')
                            new_lines.append(code)
                        else:
                            return False, f"无效行号 {ln} in {rel}"
                    node.lines = new_lines
                    node.save()

                elif action == "add":
                    rel = op["file_path"]
                    content = op.get("content", "")
                    full = self._safe_abspath(rel)
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.add_file(rel)

                elif action == "delete":
                    rel = op["file_path"]
                    full = self._safe_abspath(rel)
                    if os.path.exists(full):
                        os.remove(full)
                    if rel in self.files:
                        del self.files[rel]

                elif action == "move":
                    src = op["source"]
                    dst = op["destination"]
                    src_full = self._safe_abspath(src)
                    dst_full = self._safe_abspath(dst)
                    os.makedirs(os.path.dirname(dst_full), exist_ok=True)
                    shutil.move(src_full, dst_full)
                    if src in self.files:
                        self.files[dst] = self.files.pop(src)
                        self.files[dst].path = dst_full
                    elif os.path.exists(dst_full):
                        self.add_file(dst)

                elif action == "copy":
                    src = op["source"]
                    dst = op["destination"]
                    src_full = self._safe_abspath(src)
                    dst_full = self._safe_abspath(dst)
                    os.makedirs(os.path.dirname(dst_full), exist_ok=True)
                    if os.path.isdir(src_full):
                        shutil.copytree(src_full, dst_full, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src_full, dst_full)
                    self.add_file(dst)

                elif action == "rename":
                    old = op["path"]
                    new = op["new_name"]
                    old_full = self._safe_abspath(old)
                    new_full = self._safe_abspath(new)
                    os.makedirs(os.path.dirname(new_full), exist_ok=True)
                    os.rename(old_full, new_full)
                    if old in self.files:
                        self.files[new] = self.files.pop(old)
                        self.files[new].path = new_full

                elif action == "mkdir":
                    dir_path = op["path"]
                    full = self._safe_abspath(dir_path)
                    os.makedirs(full, exist_ok=True)

                elif action == "rmdir":
                    dir_path = op["path"]
                    full = self._safe_abspath(dir_path)
                    if os.path.exists(full):
                        shutil.rmtree(full)
                    to_del = [rel for rel in self.files if rel.startswith(dir_path + os.sep)]
                    for rel in to_del:
                        del self.files[rel]

                elif action == "cpdir":
                    src = op["source"]
                    dst = op["destination"]
                    src_full = self._safe_abspath(src)
                    dst_full = self._safe_abspath(dst)
                    shutil.copytree(src_full, dst_full, dirs_exist_ok=True)
                    self.scan_directory()

                else:
                    return False, f"未知操作: {action}"

            return True, "所有操作已应用。"
        except ValueError as e:
            return False, f"路径安全拦截: {e}"
        except Exception as e:
            return False, str(e)

    # ---------- 沙盒执行 ----------
    def _run_file_in_path(self, lang: str, full_path: str, cwd: str) -> str:
        """实际执行某个文件，返回输出字符串"""
        if not os.path.exists(full_path):
            return f"文件不存在: {full_path}"

        if lang == 'py':
            # 添加项目内的 python_packages 到路径
            lib_dir = os.path.join(cwd, "python_packages")
            env = os.environ.copy()
            if os.path.exists(lib_dir):
                env["PYTHONPATH"] = lib_dir + os.pathsep + env.get("PYTHONPATH", "")
            cmd = [sys.executable, full_path]
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=30, cwd=cwd, env=env)
        elif lang == 'node':
            cmd = ['node', full_path]
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=30, cwd=cwd)
        elif lang == 'html':
            try:
                webbrowser.open(full_path)
                return "已在浏览器中打开 HTML 文件。"
            except Exception as e:
                return f"无法打开浏览器: {e}"
        elif lang == 'c':
            exe_path = os.path.splitext(full_path)[0] + '.out'
            comp = subprocess.run(['gcc', full_path, '-o', exe_path],
                                  capture_output=True, text=True, cwd=cwd)
            if comp.returncode != 0:
                return f"编译失败:\n{comp.stderr}"
            res = subprocess.run([exe_path], capture_output=True, text=True,
                                 timeout=30, cwd=cwd)
        elif lang == 'cpp':
            exe_path = os.path.splitext(full_path)[0] + '.out'
            comp = subprocess.run(['g++', full_path, '-o', exe_path],
                                  capture_output=True, text=True, cwd=cwd)
            if comp.returncode != 0:
                return f"编译失败:\n{comp.stderr}"
            res = subprocess.run([exe_path], capture_output=True, text=True,
                                 timeout=30, cwd=cwd)
        else:
            return f"不支持的语言: {lang}"

        output = res.stdout
        if res.stderr:
            output += "\n[stderr]:\n" + res.stderr
        return output

    def execute(self, lang: str, rel_path: str, sandbox: bool = True) -> str:
        """执行项目中的文件，默认在沙盒临时副本中运行"""
        if sandbox:
            with tempfile.TemporaryDirectory() as tmpdir:
                sandbox_root = os.path.join(tmpdir, 'sandbox')
                shutil.copytree(self.root_dir, sandbox_root, symlinks=True)
                entry_full = os.path.join(sandbox_root, rel_path)
                return self._run_file_in_path(lang, entry_full, cwd=sandbox_root)
        else:
            full = os.path.join(self.root_dir, rel_path)
            return self._run_file_in_path(lang, full, cwd=self.root_dir)


class AIDevTool:
    """顶层控制器：语言、项目、历史、依赖管理"""

    def __init__(self, lang: str, project_dir: str, personality: bool = False):
        self.lang = lang
        self.project = Project(project_dir)
        self.personality = personality
        self.history: List[Dict] = []  # 最近 5 轮对话
        self.entry_point = self.load_entry_point()

    def load_entry_point(self) -> Optional[str]:
        entry_file = os.path.join(self.project.root_dir, "entry.json")
        if os.path.exists(entry_file):
            with open(entry_file, 'r', encoding='utf-8') as f:
                return json.load(f).get("entry_point")
        return None

    def save_entry_point(self, path: str):
        self.entry_point = path
        entry_file = os.path.join(self.project.root_dir, "entry.json")
        with open(entry_file, 'w', encoding='utf-8') as f:
            json.dump({"entry_point": path}, f, indent=2)

    def get_dependency_info(self) -> Dict:
        info = {"language": self.lang, "version": ""}
        if self.lang == 'py':
            info["version"] = sys.version.split()[0]
            req_path = os.path.join(self.project.root_dir, "requirements.txt")
            if os.path.exists(req_path):
                with open(req_path, 'r', encoding='utf-8') as f:
                    info["requirements"] = f.read()
            else:
                info["requirements"] = ""
        elif self.lang == 'node':
            try:
                v = subprocess.run(['node', '--version'], capture_output=True,
                                   text=True).stdout.strip()
                info["version"] = v
            except Exception:
                info["version"] = "unknown"
            pkg_path = os.path.join(self.project.root_dir, "package.json")
            if os.path.exists(pkg_path):
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    info["package.json"] = f.read()
            else:
                info["package.json"] = ""
        elif self.lang in ('c', 'cpp'):
            try:
                v = subprocess.run(['gcc', '--version'], capture_output=True,
                                   text=True).stdout.split('\n')[0]
                info["version"] = v
            except Exception:
                info["version"] = "unknown"
        return info

    def generate_input_json(self, request_text: str, focused_files: List[str] = None) -> str:
        system_prompt = (
            "你是智能编程助手，通过工具生成的 JSON 与自动化系统交互。\n"
            "用户不知道 JSON 的存在，他们只用自然语言描述需求。\n"
            "你的回复必须是严格的 JSON 对象，包含：\n"
            '1. "response": 给用户的自然语言回答（友好、有帮助）。\n'
            '2. "file_changes": 文件操作数组，具体操作类型：\n'
            '   - modify: {"action":"modify","file_path":"...","changes":[{"ln":行号,"code":"新代码"}]}\n'
            '   - add: {"action":"add","file_path":"...","content":"完整文件内容"}\n'
            '   - delete: {"action":"delete","file_path":"..."}\n'
            '   - move: {"action":"move","source":"...","destination":"..."}\n'
            '   - copy: {"action":"copy","source":"...","destination":"..."}\n'
            '   - rename: {"action":"rename","path":"...","new_name":"..."}\n'
            '   - mkdir: {"action":"mkdir","path":"..."}\n'
            '   - rmdir: {"action":"rmdir","path":"..."}\n'
            '   - cpdir: {"action":"cpdir","source":"...","destination":"..."}\n'
            '3. "entry_point": 字符串，指定项目入口文件（可选）。\n'
            '4. "dependencies": 依赖对象，如 {"pip":["requests"], "npm":["express"]}，用于自动安装。\n'
            "【安全警告】所有文件路径必须保持在项目根目录内，禁止使用绝对路径或 '../' 跳出，否则会被系统拦截。\n"
        )
        if self.personality:
            system_prompt += "\n请在 response 中使用友好、鼓励的语气，可加入语助词。"

        payload = {
            "system": system_prompt,
            "project_dir": self.project.root_dir,
            "language": self.lang,
            "entry_point": self.entry_point,
            "dependencies_info": self.get_dependency_info(),
            "files": self.project.get_all_files_data(),
            "focused_files": focused_files or [],
            "history": self.history[-5:],
            "request": request_text
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def apply_ai_response(self, ai_json_str: str) -> Tuple[bool, str, str]:
        """
        解析 AI 回复，应用变更、安装依赖、保存入口。
        返回 (成功, 用户消息, 日志消息)
        """
        try:
            ai = json.loads(ai_json_str)
            response_text = ai.get("response", "（无回复）")
            file_changes = ai.get("file_changes", [])
            entry_point = ai.get("entry_point")
            dependencies = ai.get("dependencies")

            if file_changes:
                ok, msg = self.project.apply_changes(file_changes)
                if not ok:
                    return False, response_text, msg

            if entry_point:
                self.save_entry_point(entry_point)

            dep_msg = ""
            if dependencies:
                dep_ok, dep_log = self.install_dependencies(dependencies)
                if dep_ok:
                    dep_msg = "依赖已安装。"
                else:
                    dep_msg = f"依赖安装失败: {dep_log}"
            else:
                dep_msg = "无新依赖。"

            self.history.append({"request": "<用户最新请求>", "response": response_text})
            if len(self.history) > 5:
                self.history.pop(0)

            return True, response_text, f"变更已应用。{dep_msg}"
        except json.JSONDecodeError as e:
            return False, "AI 返回 JSON 格式错误", str(e)
        except Exception as e:
            return False, "处理 AI 回复时出错", str(e)

    def install_dependencies(self, deps: Dict) -> Tuple[bool, str]:
        """自动安装依赖（项目隔离）"""
        msgs = []
        if "pip" in deps and self.lang == "py":
            packages = deps["pip"]
            if packages:
                target_dir = os.path.join(self.project.root_dir, "python_packages")
                os.makedirs(target_dir, exist_ok=True)
                cmd = [sys.executable, "-m", "pip", "install", "--target", target_dir] + packages
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if res.returncode == 0:
                        msgs.append("pip 安装成功")
                    else:
                        msgs.append(f"pip 失败: {res.stderr}")
                except Exception as e:
                    msgs.append(f"pip 异常: {e}")
        if "npm" in deps and self.lang == "node":
            packages = deps["npm"]
            if packages:
                cmd = ["npm", "install"] + packages
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                         cwd=self.project.root_dir)
                    if res.returncode == 0:
                        msgs.append("npm 安装成功")
                    else:
                        msgs.append(f"npm 失败: {res.stderr}")
                except Exception as e:
                    msgs.append(f"npm 异常: {e}")
        if not msgs:
            return True, "没有要安装的依赖。"
        return True, "; ".join(msgs)

    def backup_project(self) -> str:
        backup_root = os.path.join(os.path.dirname(self.project.root_dir), "aibox_backups")
        os.makedirs(backup_root, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(backup_root, f"backup_{timestamp}")
        shutil.copytree(self.project.root_dir, dest)
        return dest


# ===================== GUI 模式 =====================
def run_gui():
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("AIBox v5 - 安全沙盒智能开发工具")
    root.geometry("1000x700")

    tool: Optional[AIDevTool] = None
    focused_set = set()

    def toggle_topmost():
        root.attributes('-topmost', pin_var.get())

    def init_tool():
        nonlocal tool
        lang = lang_var.get()
        proj_dir = proj_dir_var.get().strip()
        if not proj_dir:
            messagebox.showwarning("路径错误", "请输入项目目录。")
            return
        personality = personality_var.get()
        tool = AIDevTool(lang, proj_dir, personality)
        tool.project.scan_directory()
        refresh_file_list()
        status_var.set(f"项目已加载：{proj_dir}（{len(tool.project.files)} 个文件）")

    def refresh_file_list():
        file_list.delete(0, tk.END)
        if tool:
            for f in sorted(tool.project.files.keys()):
                file_list.insert(tk.END, f)
        focused_set.clear()

    def on_file_select(event):
        pass

    def toggle_focused():
        selection = file_list.curselection()
        for i in selection:
            fname = file_list.get(i)
            if fname in focused_set:
                focused_set.discard(fname)
            else:
                focused_set.add(fname)
        for i in range(file_list.size()):
            fname = file_list.get(i)
            if fname in focused_set:
                file_list.itemconfig(i, {'bg': '#d1e7dd'})
            else:
                file_list.itemconfig(i, {'bg': 'white'})
        status_var.set(f"重点文件：{', '.join(focused_set) if focused_set else '无'}")

    def on_submit():
        if tool is None:
            init_tool()
        if tool is None:
            return
        req = req_text.get("1.0", "end-1c").strip()
        if not req:
            messagebox.showwarning("缺少要求", "请输入修改要求。")
            return

        with open("aibox_log.txt", "a", encoding='utf-8') as log:
            log.write(f"[{time.ctime()}] 请求: {req}\n")

        try:
            focused_list = list(focused_set) if focused_set else None
            json_str = tool.generate_input_json(req, focused_list)
            root.clipboard_clear()
            root.clipboard_append(json_str)
            status_var.set("输入 JSON 已复制到剪贴板。请粘贴给 AI，然后点击“粘贴 AI 返回”。")
        except Exception as e:
            messagebox.showerror("生成失败", str(e))

    def paste_ai_json():
        if tool is None:
            init_tool()
        if tool is None:
            return
        try:
            clip_text = root.clipboard_get()
        except Exception:
            messagebox.showerror("剪贴板错误", "无法读取剪贴板内容。")
            return
        if not clip_text.strip():
            messagebox.showwarning("空内容", "剪贴板为空。")
            return
        try:
            ai = json.loads(clip_text)
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON 格式错误", f"剪贴板内容不是有效 JSON：{e}")
            return

        response_text = ai.get("response", "")
        file_changes = ai.get("file_changes", [])
        entry_point = ai.get("entry_point")
        dependencies = ai.get("dependencies")

        PreviewWindow(root, response_text, file_changes, entry_point, dependencies,
                      tool, status_var, refresh_file_list)

    def on_execute():
        if tool is None:
            init_tool()
        if tool is None:
            return
        entry = tool.entry_point
        if not entry:
            if tool.project.files:
                entry = next(iter(tool.project.files.keys()))
            else:
                messagebox.showwarning("无文件", "项目中没有文件，请先生成。")
                return
        # 沙盒执行（默认）
        output = tool.project.execute(tool.lang, entry, sandbox=True)
        messagebox.showinfo("执行输出（沙盒模式）", output if output else "（无输出）")
        status_var.set(f"已沙盒执行 {entry}")

    def backup():
        if tool is None:
            messagebox.showwarning("未加载", "请先加载项目。")
            return
        dest = tool.backup_project()
        messagebox.showinfo("备份完成", f"项目已备份至：\n{dest}")
        status_var.set(f"备份完成：{dest}")

    # ================= 预览窗口 =================
    class PreviewWindow(tk.Toplevel):
        def __init__(self, parent, response_text, file_changes, entry_point, dependencies,
                     tool_obj, status_var, refresh_callback):
            super().__init__(parent)
            self.title("AI 回复预览")
            self.tool = tool_obj
            self.status_var = status_var
            self.refresh_callback = refresh_callback
            self.response = response_text
            self.file_changes = file_changes
            self.entry_point = entry_point
            self.dependencies = dependencies
            self.result_action = None

            # AI 回复展示区
            if response_text:
                resp_frame = tk.LabelFrame(self, text="💬 AI 的回复", font=('Arial', 9, 'bold'))
                resp_text = tk.Text(resp_frame, height=5, width=80, wrap=tk.WORD)
                resp_text.insert("1.0", response_text)
                resp_text.config(state='disabled')
                resp_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scroll = ttk.Scrollbar(resp_frame, command=resp_text.yview)
                scroll.pack(side=tk.RIGHT, fill=tk.Y)
                resp_text.config(yscrollcommand=scroll.set)
                resp_frame.pack(padx=10, pady=5, fill=tk.BOTH)
                tk.Button(resp_frame, text="Markdown 预览", command=self.show_md_preview).pack(pady=2)

            # 文件变更预览（带颜色）
            if file_changes:
                ch_frame = tk.LabelFrame(self, text="📁 文件变更预览", font=('Arial', 9, 'bold'))
                tree = ttk.Treeview(ch_frame, columns=("操作", "文件", "详情"), show="headings", height=8)
                tree.heading("操作", text="操作")
                tree.heading("文件", text="文件")
                tree.heading("详情", text="详情")
                tree.column("操作", width=60, anchor='center')
                tree.column("文件", width=200)
                tree.column("详情", width=400)

                color_map = {
                    "add": "#d1e7dd", "modify": "#fff3cd", "delete": "#f8d7da",
                    "copy": "#e2d9f3", "move": "#cfe2ff",
                }
                for fc in file_changes:
                    action = fc.get("action", "?")
                    if action == "modify":
                        fpath = fc.get("file_path", "")
                        changes = fc.get("changes", [])
                        detail = ", ".join([f"行{c['ln']}" for c in changes[:3]])
                        if len(changes) > 3: detail += f" 等{len(changes)}处"
                    elif action == "add":
                        fpath = fc.get("file_path", ""); detail = "新建文件"
                    elif action == "delete":
                        fpath = fc.get("file_path", ""); detail = "删除"
                    elif action in ("move", "copy"):
                        fpath = f"{fc.get('source')} → {fc.get('destination')}"; detail = ""
                    elif action == "rename":
                        fpath = f"{fc.get('path')} → {fc.get('new_name')}"; detail = ""
                    elif action in ("mkdir", "rmdir", "cpdir"):
                        fpath = fc.get("path") or fc.get("source") + " → " + fc.get("destination", ""); detail = ""
                    else:
                        fpath = ""; detail = "未知"
                    item = tree.insert("", "end", values=(action, fpath, detail))
                    bg = color_map.get(action, "white")
                    if bg:
                        tree.tag_configure(bg, background=bg)
                        tree.item(item, tags=(bg,))
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scroll_y = ttk.Scrollbar(ch_frame, orient=tk.VERTICAL, command=tree.yview)
                scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
                tree.config(yscrollcommand=scroll_y.set)
                ch_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

            if entry_point:
                tk.Label(self, text=f"🏁 入口文件：{entry_point}", fg="blue").pack(anchor='w', padx=10)
            if dependencies:
                dep_str = json.dumps(dependencies, ensure_ascii=False)
                tk.Label(self, text=f"📦 依赖安装：{dep_str}", fg="green").pack(anchor='w', padx=10)

            # 操作按钮（三个选项）
            btn_frame = tk.Frame(self)
            btn_backup_apply_run = tk.Button(btn_frame, text="备份并应用执行", bg="#cfe2ff",
                                             command=lambda: self.finish("backup_apply_run"))
            btn_apply_run = tk.Button(btn_frame, text="应用并执行", bg="#d1e7dd",
                                      command=lambda: self.finish("apply_run"))
            btn_apply_only = tk.Button(btn_frame, text="仅应用（不执行）", bg="#f8d7da",
                                       command=lambda: self.finish("apply_only"))
            btn_backup_apply_run.pack(side=tk.LEFT, padx=5, pady=10)
            btn_apply_run.pack(side=tk.LEFT, padx=5)
            btn_apply_only.pack(side=tk.LEFT, padx=5)
            btn_frame.pack()

            self.protocol("WM_DELETE_WINDOW", lambda: self.finish("cancel"))
            self.grab_set()
            self.wait_window()

        def show_md_preview(self):
            if not self.response: return
            if HAS_MARKDOWN:
                html = markdown.markdown(self.response)
            else:
                html = f"<pre>{self.response}</pre>"
            tmp = os.path.join(tempfile.gettempdir(), "aibox_md_preview.html")
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(f"<html><body>{html}</body></html>")
            webbrowser.open(tmp)

        def finish(self, action):
            if action == "cancel":
                self.destroy()
                return

            if action == "backup_apply_run":
                dest = self.tool.backup_project()
                self.status_var.set(f"已备份到 {dest}")

            ai_json = json.dumps({
                "response": self.response,
                "file_changes": self.file_changes,
                "entry_point": self.entry_point,
                "dependencies": self.dependencies
            }, ensure_ascii=False)

            success, user_msg, log = self.tool.apply_ai_response(ai_json)
            if not success:
                messagebox.showerror("应用失败", log)
                self.destroy()
                return

            self.status_var.set(log)
            self.refresh_callback()

            if self.dependencies:
                messagebox.showinfo("依赖已安装", "AI 指定的依赖已自动安装。")

            if action in ("backup_apply_run", "apply_run"):
                entry = self.tool.entry_point
                if not entry:
                    if self.tool.project.files:
                        entry = next(iter(self.tool.project.files.keys()))
                    else:
                        messagebox.showwarning("无文件", "项目中没有可执行文件。")
                        self.destroy()
                        return
                # 沙盒执行
                output = self.tool.project.execute(self.tool.lang, entry, sandbox=True)
                messagebox.showinfo("执行输出（沙盒模式）", output if output else "（无输出）")
                self.status_var.set(f"沙盒执行 {entry} 完成。")

            self.destroy()

    # ================= 主界面布局 =================
    config_frame = tk.Frame(root)
    tk.Label(config_frame, text="语言:").pack(side=tk.LEFT)
    lang_var = tk.StringVar(value="py")
    lang_menu = tk.OptionMenu(config_frame, lang_var, "py", "cpp", "c", "node", "html")
    lang_menu.pack(side=tk.LEFT, padx=5)

    tk.Label(config_frame, text="项目目录:").pack(side=tk.LEFT, padx=(10,0))
    proj_dir_var = tk.StringVar(value="./myproject")
    proj_entry = tk.Entry(config_frame, textvariable=proj_dir_var, width=25)
    proj_entry.pack(side=tk.LEFT, padx=5)

    personality_var = tk.BooleanVar(value=False)
    tk.Checkbutton(config_frame, text="加入语助词", variable=personality_var).pack(side=tk.LEFT, padx=10)
    tk.Button(config_frame, text="加载项目", command=init_tool).pack(side=tk.LEFT, padx=5)
    config_frame.pack(pady=5, anchor='w')

    action_bar = tk.Frame(root)
    pin_var = tk.BooleanVar(value=False)
    tk.Checkbutton(action_bar, text="置顶", variable=pin_var, command=toggle_topmost).pack(side=tk.LEFT, padx=5)

    btn_submit = tk.Button(action_bar, text="① 提交并复制输入JSON", command=on_submit, bg="#cfe2ff")
    btn_submit.pack(side=tk.LEFT, padx=5)
    btn_paste = tk.Button(action_bar, text="② 粘贴AI返回并预览", command=paste_ai_json, bg="#d1e7dd")
    btn_paste.pack(side=tk.LEFT, padx=5)
    btn_exec = tk.Button(action_bar, text="③ 沙盒执行", command=on_execute, bg="#f8d7da")
    btn_exec.pack(side=tk.LEFT, padx=5)
    action_bar.pack(pady=5, anchor='w')

    main_panel = tk.Frame(root)
    left_frame = tk.Frame(main_panel)
    tk.Label(left_frame, text="项目文件", font=('Arial', 9, 'bold')).pack(anchor='w')
    list_frame = tk.Frame(left_frame)
    file_list = tk.Listbox(list_frame, height=15, width=35, selectmode=tk.EXTENDED)
    file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll_list = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=file_list.yview)
    scroll_list.pack(side=tk.RIGHT, fill=tk.Y)
    file_list.config(yscrollcommand=scroll_list.set)
    list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
    btn_focus = tk.Button(left_frame, text="切换重点标记", command=toggle_focused)
    btn_focus.pack(pady=2)
    left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(5,2))

    right_frame = tk.Frame(main_panel)
    tk.Label(right_frame, text="输入修改要求:", font=('Arial', 9, 'bold')).pack(anchor='w')
    req_text = tk.Text(right_frame, height=10, width=60)
    req_text.pack(fill=tk.BOTH, expand=True, pady=5)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=2)
    main_panel.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    status_frame = tk.Frame(root)
    status_var = tk.StringVar(value="就绪。请设置项目目录并加载。")
    status_bar = tk.Label(status_frame, textvariable=status_var, bd=1, relief=tk.SUNKEN, anchor='w')
    status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
    btn_backup = tk.Button(status_frame, text="📦 备份", command=backup, bg="#f0f0f0")
    btn_backup.pack(side=tk.RIGHT, padx=5)
    status_frame.pack(side=tk.BOTTOM, fill=tk.X)

    init_tool()
    root.mainloop()


# ===================== 命令行模式 =====================
def run_cli():
    print("AIBox v5 (安全沙盒命令行模式)")
    lang = input("选择语言 (py/cpp/c/node/html): ").strip().lower()
    while lang not in ('py', 'cpp', 'c', 'node', 'html'):
        lang = input("无效，重新输入: ").strip().lower()
    proj_dir = input("项目目录 (默认 ./myproject): ").strip() or "./myproject"
    pers = input("加入语助词？(y/n): ").strip().lower() == 'y'
    tool = AIDevTool(lang, proj_dir, pers)
    tool.project.scan_directory()
    print(f"已加载 {len(tool.project.files)} 个文件。")

    while True:
        req = input("\n要求 (q 退出): ")
        if req.lower() == 'q':
            break
        focused = input("重点文件 (逗号分隔，回车跳过): ").strip()
        focused_list = [f.strip() for f in focused.split(',') if f.strip()] if focused else None
        json_in = tool.generate_input_json(req, focused_list)
        print("\n复制以下 JSON 给 AI:\n" + json_in)
        print("\n粘贴 AI 返回 (输入 END 结束):")
        lines = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        ai_str = '\n'.join(lines)
        success, user_msg, log = tool.apply_ai_response(ai_str)
        print(f"\nAI: {user_msg}")
        print(f"状态: {log}")
        exe = input("沙盒执行入口文件？(直接回车跳过，或输入相对路径): ").strip()
        if exe:
            out = tool.project.execute(tool.lang, exe, sandbox=True)
            print(f"沙盒执行输出:\n{out}")

    print("AIBox 已退出。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIBox v5 - 安全沙盒智能开发工具")
    parser.add_argument('-gui', type=str, default='true', choices=['true', 'false'],
                        help="true: GUI (默认), false: 命令行")
    args = parser.parse_args()

    if args.gui.lower() == 'true':
        try:
            run_gui()
        except ImportError:
            print("tkinter 不可用，请使用 -gui false 进入命令行模式。")
            sys.exit(1)
    else:
        run_cli()