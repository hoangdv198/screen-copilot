import io
import json
import base64
import threading
import time
import ctypes
import os
import re
import math
import asyncio
import tempfile
import tkinter as tk
from tkinter import ttk
import requests
import mss
from PIL import Image
import pygetwindow as gw
import speech_recognition as sr
import edge_tts
import pygame

# Windows API
user32 = ctypes.windll.user32
VK_MENU = 0x12  # Alt
VK_Q = 0x51     # Q

API_URL = "http://127.0.0.1:20128/v1/chat/completions"
MODEL = "ag/gemini-3.8-flash-medium"
HISTORY_FILE = r"E:\GameAssistant\chat_history.json"
VOICE_NAME = "vi-VN-HoaiMyNeural"  # Giọng nữ tiếng Việt tự nhiên chuẩn

def get_api_key():
    config_path = os.path.expanduser(r"~\.openclaw\openclaw.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("models", {}).get("providers", {}).get("9router", {}).get("apiKey", "")
    except Exception:
        return ""

DEFAULT_PROMPT = "Đây là ảnh chụp màn hình game MapleStory của tôi. Hãy nhìn kỹ nội dung, tóm tắt trạng thái và đưa ra lời khuyên hoặc hướng dẫn ngắn gọn, dễ hiểu nhất bằng tiếng Việt."

SYSTEM_INSTRUCTION = (
    "Bạn là MapleStory AI Copilot chuyên sâu về bản Global (GMS Reboot/Heroic & Regular). "
    "Luôn trả lời ngắn gọn, súc tích, đi thẳng vào trọng tâm, dùng đúng thuật ngữ game thủ "
    "(Legion, Link Skill, Starforce, WSE, Nodes, V-Matrix, Hexa Matrix, Boss Mechanics, v.v.). "
    "Nếu so sánh hoặc liệt kê nhiều thuộc tính, hãy dùng bảng Markdown (| Cột 1 | Cột 2 |) chuẩn để hiển thị rõ ràng."
)

class OverlayApp:
    def __init__(self):
        self.root = None
        self.is_active = False
        
        # Drag window state
        self._drag_start_x = 0
        self._drag_start_y = 0
        
        # Resize window state
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._orig_w = 0
        self._orig_h = 0
        
        # Live voice loop state
        self.live_voice_enabled = True
        self.is_processing = False
        self.is_speaking_tts = False
        self.tts_enabled = True  # Mặc định BẬT đọc câu trả lời
        
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        
        # Audio level state for visualizer
        self.current_volume = 0.0
        self.is_user_speaking = False
        
        # Pygame mixer init
        try:
            pygame.mixer.init()
        except Exception:
            pass
        
        # Chat history state: list of dicts {"role": "user"|"assistant", "content": ...}
        self.chat_history = []
        self.window_map = {}
        self.load_history()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.chat_history = json.load(f)
            except Exception:
                self.chat_history = []

    def save_history(self):
        try:
            to_save = self.chat_history[-40:]
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Error saving history:", e)

    def create_window(self):
        self.root = tk.Tk()
        self.root.title("Game AI Assistant")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.configure(bg="#181825")
        self.root.attributes("-alpha", 0.97)

        w = 540
        h = 720
        x = 1330
        y = 40
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(380, 420)

        # ==========================================
        # 1. HEADER (Kéo thả di chuyển + Nút đóng + Xóa lịch sử)
        # ==========================================
        self.header = tk.Frame(self.root, bg="#1e1e2e", height=38, cursor="fleur")
        self.header.pack(fill=tk.X, side=tk.TOP)

        self.title_lbl = tk.Label(self.header, text="✨ Game AI Copilot 1:1", 
                                  bg="#1e1e2e", fg="#a6e3a1", font=("Segoe UI", 10, "bold"), cursor="fleur")
        self.title_lbl.pack(side=tk.LEFT, padx=12, pady=7)

        sub_title = tk.Label(self.header, text="(Alt+Q: Ẩn/Hiện)", bg="#1e1e2e", fg="#6c7086", font=("Segoe UI", 8), cursor="fleur")
        sub_title.pack(side=tk.LEFT, pady=7)

        for widget in (self.header, self.title_lbl, sub_title):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

        close_btn = tk.Label(self.header, text="✕", bg="#1e1e2e", fg="#f38ba8", 
                             font=("Segoe UI", 11, "bold"), cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=12, pady=7)
        close_btn.bind("<Button-1>", lambda e: self.hide())

        clear_btn = tk.Label(self.header, text="🗑️ Xóa lịch sử", bg="#1e1e2e", fg="#f38ba8",
                             font=("Segoe UI", 8, "bold"), cursor="hand2")
        clear_btn.pack(side=tk.RIGHT, padx=8, pady=7)
        clear_btn.bind("<Button-1>", lambda e: self.clear_chat())

        # ==========================================
        # 2. TOP TOOLBAR: Chọn cửa sổ cần chụp + Nút Bật/Tắt Giọng đọc
        # ==========================================
        sel_frame = tk.Frame(self.root, bg="#181825")
        sel_frame.pack(fill=tk.X, padx=12, pady=(6, 4))

        tk.Label(sel_frame, text="Mục tiêu:", bg="#181825", fg="#a6adc8",
                 font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))

        self.win_combobox = ttk.Combobox(sel_frame, state="readonly", font=("Segoe UI", 8))
        self.win_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.win_combobox.bind("<Button-1>", lambda e: self.refresh_windows_list())

        refresh_btn = tk.Button(sel_frame, text="🔄", bg="#313244", fg="#cdd6f4",
                                font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2",
                                command=self.refresh_windows_list)
        refresh_btn.pack(side=tk.LEFT, padx=(4, 6))

        # NÚT BẬT/TẮT ĐỌC CÂU TRẢ LỜI (TTS)
        self.tts_btn = tk.Button(sel_frame, text="🔊 Đọc: BẬT", bg="#a6e3a1", fg="#11111b",
                                 font=("Segoe UI", 8, "bold"), relief=tk.FLAT, cursor="hand2",
                                 padx=6, command=self.toggle_tts)
        self.tts_btn.pack(side=tk.RIGHT)

        # ==========================================
        # 3. KHUNG DƯỚI CÙNG (DOCK DƯỚI): Status + Sóng âm Mic + Input Bar + Góc Resize
        # ==========================================
        bottom_container = tk.Frame(self.root, bg="#181825")
        bottom_container.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 4))

        status_bar_frame = tk.Frame(bottom_container, bg="#181825")
        status_bar_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(2, 0))

        self.status_lbl = tk.Label(status_bar_frame, 
                                   text="💡 Đang ở chế độ Đàm thoại 1:1 (Nói là tự chụp & đọc trả lời)!", 
                                   bg="#181825", fg="#a6e3a1", font=("Segoe UI", 8))
        self.status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.resize_grip = tk.Label(status_bar_frame, text="⋰", bg="#181825", fg="#9399b2", 
                                    font=("Segoe UI", 12, "bold"), cursor="size_nw_se")
        self.resize_grip.pack(side=tk.RIGHT, padx=(2, 0))
        self.resize_grip.bind("<ButtonPress-1>", self._start_resize)
        self.resize_grip.bind("<B1-Motion>", self._on_resize)

        input_bar = tk.Frame(bottom_container, bg="#313244", relief=tk.FLAT, bd=0)
        input_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))

        self.live_btn = tk.Button(input_bar, text="🟢 Live 1:1 (BẬT)", bg="#a6e3a1", fg="#11111b",
                                  activebackground="#94e2d5", activeforeground="#11111b",
                                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, cursor="hand2",
                                  padx=6, command=self.toggle_live_voice)
        self.live_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.wave_canvas = tk.Canvas(input_bar, width=65, height=26, bg="#313244", highlightthickness=0)
        self.wave_canvas.pack(side=tk.LEFT, padx=(2, 4), pady=5)

        self.prompt_entry = tk.Entry(input_bar, bg="#313244", fg="#cdd6f4", 
                                     insertbackground="#cdd6f4", font=("Segoe UI", 10),
                                     relief=tk.FLAT)
        self.prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=4)
        self.prompt_entry.insert(0, "Cứ nói vào mic, hoặc gõ phím rồi bấm Enter...")
        self.prompt_entry.bind("<FocusIn>", self._clear_placeholder)
        self.prompt_entry.bind("<Return>", lambda e: self.on_text_submit())

        # ==========================================
        # 4. CHAT MESSAGE AREA (Toàn bộ phần giữa)
        # ==========================================
        chat_frame = tk.Frame(self.root, bg="#181825")
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 4))

        self.scrollbar = tk.Scrollbar(chat_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.chat_display = tk.Text(chat_frame, wrap=tk.WORD, yscrollcommand=self.scrollbar.set,
                                    bg="#11111b", fg="#cdd6f4", font=("Segoe UI", 10),
                                    relief=tk.FLAT, padx=12, pady=10)
        self.chat_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.chat_display.yview)

        # Cấu hình styles Markdown
        self.chat_display.tag_config("user_sender", foreground="#89b4fa", font=("Segoe UI", 10, "bold"), spacing1=8)
        self.chat_display.tag_config("ai_sender", foreground="#a6e3a1", font=("Segoe UI", 10, "bold"), spacing1=8)
        self.chat_display.tag_config("system_sender", foreground="#fab387", font=("Segoe UI", 9, "italic"), spacing1=4)
        
        self.chat_display.tag_config("md_h1", foreground="#f9e2af", font=("Segoe UI", 13, "bold"), spacing1=6, spacing3=4)
        self.chat_display.tag_config("md_h2", foreground="#f9e2af", font=("Segoe UI", 11, "bold"), spacing1=5, spacing3=3)
        self.chat_display.tag_config("md_h3", foreground="#fab387", font=("Segoe UI", 10, "bold"), spacing1=4, spacing3=2)
        self.chat_display.tag_config("md_bold", foreground="#f5c2e7", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_config("md_italic", foreground="#cdd6f4", font=("Segoe UI", 10, "italic"))
        self.chat_display.tag_config("md_code", foreground="#f38ba8", background="#313244", font=("Consolas", 9))
        self.chat_display.tag_config("md_code_block", foreground="#a6adc8", background="#181825", font=("Consolas", 9), lmargin1=15, lmargin2=15)
        self.chat_display.tag_config("md_bullet", foreground="#89dceb", font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_config("md_normal", foreground="#cdd6f4", font=("Segoe UI", 10))

        self.render_saved_history()
        self.refresh_windows_list()
        self.show()

        self.animate_wave()

        t_live = threading.Thread(target=self.live_voice_loop, daemon=True)
        t_live.start()

    def _start_resize(self, event):
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._orig_w = self.root.winfo_width()
        self._orig_h = self.root.winfo_height()

    def _on_resize(self, event):
        delta_w = event.x_root - self._resize_start_x
        delta_h = event.y_root - self._resize_start_y
        new_w = max(380, self._orig_w + delta_w)
        new_h = max(420, self._orig_h + delta_h)
        self.root.geometry(f"{new_w}x{new_h}")

    def toggle_tts(self):
        self.tts_enabled = not self.tts_enabled
        if self.tts_enabled:
            self.tts_btn.config(text="🔊 Đọc: BẬT", bg="#a6e3a1", fg="#11111b")
            self.set_status("Đã BẬT giọng đọc câu trả lời.")
        else:
            self.stop_speaking()
            self.tts_btn.config(text="🔇 Đọc: TẮT", bg="#45475a", fg="#cdd6f4")
            self.set_status("Đã TẮT giọng đọc câu trả lời.")

    def stop_speaking(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self.is_speaking_tts = False

    def clean_text_for_speech(self, text):
        """Trích xuất 1-2 câu trọng tâm, ngắn gọn để AI phát âm thanh ngay lập tức mà không bị delay"""
        # Bỏ khối code và bảng
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        lines = [l.strip() for l in text.split('\n') if l.strip() and not l.strip().startswith('|')]
        
        clean_lines = []
        for l in lines:
            c = re.sub(r'[*_~>`#]', ' ', l).strip()
            # Bỏ các câu rườm rà như 'Dưới đây là...', 'Bảng sau...'
            if any(w in c.lower() for w in ['dưới đây', 'bảng sau', 'chi tiết', 'tóm tắt:']):
                continue
            if len(c) > 5:
                clean_lines.append(c)

        full_text = ' '.join(clean_lines)
        # Tách câu theo dấu chấm hoặc xuống dòng
        sentences = [s.strip() for s in re.split(r'[.!?\n]+', full_text) if len(s.strip()) > 8]

        # Chỉ lấy 1 đến tối đa 2 câu trọng tâm đầu tiên (< 130 ký tự) để tốc độ phát âm thanh tức thì (<0.6s)
        speech = ''
        for s in sentences:
            if len(speech) + len(s) < 130:
                speech += s + '. '
            else:
                break

        if not speech and sentences:
            speech = sentences[0] + '.'

        return speech.strip()

    def speak_text_async(self, text):
        if not self.tts_enabled:
            return
        
        speech_text = self.clean_text_for_speech(text)
        if not speech_text:
            return

        def _tts_worker():
            self.is_speaking_tts = True
            try:
                # Dùng trực tiếp bộ nhớ RAM (BytesIO) thay vì ghi/đọc ổ cứng tempfile
                bio = io.BytesIO()
                async def _generate():
                    communicate = edge_tts.Communicate(speech_text, VOICE_NAME, rate="+10%")
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            bio.write(chunk["data"])

                asyncio.run(_generate())

                if not self.tts_enabled or bio.tell() == 0:
                    return

                bio.seek(0)
                if not pygame.mixer.get_init():
                    pygame.mixer.init()

                pygame.mixer.music.load(bio)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and self.tts_enabled:
                    pygame.time.Clock().tick(10)

            except Exception as e:
                print("TTS Playback Error:", e)
            finally:
                self.is_speaking_tts = False

        threading.Thread(target=_tts_worker, daemon=True).start()

    def animate_wave(self):
        if not self.root:
            return
        
        self.wave_canvas.delete("all")
        bar_count = 6
        c_w = 65
        c_h = 26
        bar_w = 4
        spacing = 5
        start_x = (c_w - (bar_count * bar_w + (bar_count - 1) * spacing)) // 2
        mid_y = c_h / 2

        vol = self.current_volume if self.live_voice_enabled else 0.0
        is_active = vol > 0.05 or self.is_user_speaking or self.is_speaking_tts

        t = time.time() * 12

        for i in range(bar_count):
            x = start_x + i * (bar_w + spacing)
            if is_active:
                factor = 0.4 + 0.6 * math.sin(t + i * 1.1)
                effective_vol = max(vol, 0.65 if (self.is_user_speaking or self.is_speaking_tts) else 0.0)
                h = max(4, int(effective_vol * c_h * factor * 1.4))
                h = min(h, c_h - 4)
                color = "#fab387" if self.is_speaking_tts else ("#a6e3a1" if i % 2 == 0 else "#89b4fa")
            else:
                h = 3
                color = "#585b70"

            y1 = mid_y - h / 2
            y2 = mid_y + h / 2
            self.wave_canvas.create_rectangle(x, y1, x + bar_w, y2, fill=color, outline="")

        self.root.after(35, self.animate_wave)

    def render_saved_history(self):
        if self.chat_history:
            self.append_chat("Hệ thống", "--- Đã nạp lịch sử hội thoại gần nhất ---", "system_sender")
            for msg in self.chat_history:
                role = msg.get("role")
                content = msg.get("content", "")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            content = part.get("text", "")
                            break
                if role == "user":
                    self.append_chat("Bạn", content, "user_sender")
                elif role == "assistant":
                    self.append_chat("AI Copilot", content, "ai_sender")
        else:
            self.append_chat("AI Copilot", "Chế độ **Đàm thoại 1:1 Realtime** đang BẬT! Bạn chỉ cần nói vào mic, tool sẽ tự chụp game, trả lời bảng Markdown và đọc câu trả lời bằng giọng nói tiếng Việt.", "ai_sender")

    def _start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_start_x)
        y = self.root.winfo_y() + (event.y - self._drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def _clear_placeholder(self, event):
        if "Cứ nói vào mic" in self.prompt_entry.get():
            self.prompt_entry.delete(0, tk.END)

    def refresh_windows_list(self):
        try:
            titles = ["🖥️ Toàn màn hình (Toàn bộ Desktop)"]
            self.window_map = {}
            for w in gw.getAllWindows():
                if w.title.strip() and w.visible and w.width > 150 and w.height > 150:
                    t = w.title.strip()
                    if "Game AI Assistant" in t:
                        continue
                    titles.append(t)
                    self.window_map[t] = w

            self.win_combobox['values'] = titles
            maple_title = next((t for t in titles if "MapleStory" in t), None)
            if maple_title:
                self.win_combobox.set(maple_title)
            elif not self.win_combobox.get() or self.win_combobox.get() not in titles:
                self.win_combobox.set(titles[0])
        except Exception as e:
            print("Refresh error:", e)

    def clear_chat(self):
        self.stop_speaking()
        self.chat_history = []
        if os.path.exists(HISTORY_FILE):
            try:
                os.remove(HISTORY_FILE)
            except Exception:
                pass
        self.chat_display.delete("1.0", tk.END)
        self.append_chat("Hệ thống", "Đã xóa toàn bộ lịch sử trò chuyện.", "system_sender")
        self.set_status("Đã làm mới đoạn chat.")

    def show(self):
        if self.root:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.is_active = True

    def hide(self):
        if self.root:
            self.root.withdraw()
            self.is_active = False

    def toggle(self):
        if self.is_active:
            self.hide()
        else:
            self.show()

    def toggle_live_voice(self):
        self.live_voice_enabled = not self.live_voice_enabled
        if self.live_voice_enabled:
            self.live_btn.config(text="🟢 Live 1:1 (BẬT)", bg="#a6e3a1", fg="#11111b")
            self.set_status("🎙️ Đã BẬT đàm thoại 1:1. Đang lắng nghe liên tục...")
        else:
            self.live_btn.config(text="⚪ Live 1:1 (TẮT)", bg="#45475a", fg="#cdd6f4")
            self.current_volume = 0.0
            self.is_user_speaking = False
            self.set_status("Đã TẮT đàm thoại realtime. Bạn có thể gõ phím để hỏi.")

    # ==========================================
    # RENDER BẢNG MARKDOWN DẠNG TABLE FRAME NATIVE
    # ==========================================
    def render_table_block(self, header_line, row_lines):
        def split_cells(line):
            cells = [c.strip() for c in line.strip().split('|')]
            if cells and cells[0] == '':
                cells.pop(0)
            if cells and cells[-1] == '':
                cells.pop()
            return cells

        headers = split_cells(header_line)
        rows = [split_cells(r) for r in row_lines]
        if not headers:
            return

        table_container = tk.Frame(self.chat_display, bg="#45475a", bd=1, relief=tk.SOLID)

        for col_idx, h in enumerate(headers):
            table_container.grid_columnconfigure(col_idx, weight=1)
            lbl = tk.Label(table_container, text=h, bg="#313244", fg="#f9e2af",
                           font=("Segoe UI", 9, "bold"), padx=10, pady=6, relief=tk.FLAT, anchor="w")
            lbl.grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=1)

        for r_idx, row in enumerate(rows):
            bg_color = "#1e1e2e" if r_idx % 2 == 0 else "#181825"
            for col_idx in range(len(headers)):
                val = row[col_idx] if col_idx < len(row) else ""
                lbl = tk.Label(table_container, text=val, bg=bg_color, fg="#cdd6f4",
                               font=("Segoe UI", 9), padx=10, pady=5, relief=tk.FLAT, anchor="w")
                lbl.grid(row=r_idx + 1, column=col_idx, sticky="nsew", padx=1, pady=1)

        self.chat_display.insert(tk.END, "\n")
        self.chat_display.window_create(tk.END, window=table_container)
        self.chat_display.insert(tk.END, "\n\n")

    def render_markdown_line(self, line):
        if line.startswith("# "):
            self.chat_display.insert(tk.END, line[2:] + "\n", "md_h1")
            return
        if line.startswith("## "):
            self.chat_display.insert(tk.END, line[3:] + "\n", "md_h2")
            return
        if line.startswith("### "):
            self.chat_display.insert(tk.END, line[4:] + "\n", "md_h3")
            return

        bullet_match = re.match(r"^(\s*[-*+]\s+|\s*\d+\.\s+)(.*)$", line)
        if bullet_match:
            bullet_prefix = bullet_match.group(1)
            content = bullet_match.group(2)
            self.chat_display.insert(tk.END, "  " + bullet_prefix, "md_bullet")
            self._render_inline_markdown(content)
            self.chat_display.insert(tk.END, "\n")
            return

        if line.startswith("> "):
            self.chat_display.insert(tk.END, "┃ ", "ai_sender")
            self._render_inline_markdown(line[2:])
            self.chat_display.insert(tk.END, "\n")
            return

        self._render_inline_markdown(line)
        self.chat_display.insert(tk.END, "\n")

    def _render_inline_markdown(self, text):
        pattern = re.compile(r'(\*\*.*?\*\*|`.*?`|\*.*?\*)')
        tokens = pattern.split(text)

        for token in tokens:
            if not token:
                continue
            if token.startswith("**") and token.endswith("**") and len(token) >= 4:
                self.chat_display.insert(tk.END, token[2:-2], "md_bold")
            elif token.startswith("`") and token.endswith("`") and len(token) >= 2:
                self.chat_display.insert(tk.END, f" {token[1:-1]} ", "md_code")
            elif token.startswith("*") and token.endswith("*") and len(token) >= 2:
                self.chat_display.insert(tk.END, token[1:-1], "md_italic")
            else:
                self.chat_display.insert(tk.END, token, "md_normal")

    def append_chat(self, sender, text, tag="user_sender"):
        def _append():
            self.chat_display.insert(tk.END, f"{sender}:\n", tag)
            lines = text.split("\n")
            n = len(lines)
            i = 0
            in_code_block = False

            while i < n:
                line = lines[i]

                # 1. Khối Code Block
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    i += 1
                    continue
                if in_code_block:
                    self.chat_display.insert(tk.END, "  " + line + "\n", "md_code_block")
                    i += 1
                    continue

                # 2. Bảng Markdown Table (| col1 | col2 |)
                if (line.strip().startswith("|") and line.strip().endswith("|") and 
                    i + 1 < n and re.match(r'^\s*\|(?:\s*:?-+:?\s*\|)+\s*$', lines[i + 1])):
                    header_line = line
                    i += 2
                    row_lines = []
                    while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                        row_lines.append(lines[i])
                        i += 1
                    self.render_table_block(header_line, row_lines)
                    continue

                # 3. Dòng Markdown thông thường
                self.render_markdown_line(line)
                i += 1

            self.chat_display.insert(tk.END, "\n")
            self.chat_display.see(tk.END)

        self.root.after(0, _append)

    def set_status(self, text):
        if not self.root:
            return
        self.root.after(0, lambda: self.status_lbl.config(text=text))

    def capture_screen_base64(self):
        selected = self.win_combobox.get()
        target_window = self.window_map.get(selected)
        with mss.mss() as sct:
            if target_window and "Toàn màn hình" not in selected:
                bbox = {
                    "top": max(0, target_window.top),
                    "left": max(0, target_window.left),
                    "width": max(100, target_window.width),
                    "height": max(100, target_window.height)
                }
                sct_img = sct.grab(bbox)
            else:
                sct_img = sct.grab(sct.monitors[1])

            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # Nén chuẩn WebP chất lượng 72 siêu nhẹ (~73 KB)
        img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=72, method=4)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def on_text_submit(self):
        user_text = self.prompt_entry.get().strip()
        if not user_text or "Cứ nói vào mic" in user_text:
            return
        self.prompt_entry.delete(0, tk.END)
        self.process_question(user_text)

    def process_question(self, prompt):
        if self.is_processing:
            return
        self.is_processing = True
        self.stop_speaking()

        self.append_chat("Bạn", prompt, "user_sender")
        self.set_status("📸 Đang tự chụp màn hình game...")

        self.root.withdraw()
        self.root.update()
        time.sleep(0.12)

        def _worker():
            try:
                img_b64 = self.capture_screen_base64()
                self.root.after(0, self.show)
                self.set_status("⚡ AI đang phân tích và trả lời...")

                api_key = get_api_key()
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json; charset=utf-8"
                }

                user_msg_with_img = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{img_b64}"}}
                    ]
                }

                system_msg = {"role": "system", "content": SYSTEM_INSTRUCTION}
                
                clean_history = []
                for m in self.chat_history[-6:]:
                    c = m.get("content", "")
                    if isinstance(c, list):
                        for p in c:
                            if isinstance(p, dict) and p.get("type") == "text":
                                c = p.get("text", "")
                                break
                    clean_history.append({"role": m["role"], "content": c})

                payload_messages = [system_msg] + clean_history + [user_msg_with_img]

                payload = {
                    "model": MODEL,
                    "messages": payload_messages
                }

                r = requests.post(API_URL, headers=headers, json=payload, timeout=45)
                if r.status_code != 200:
                    err_msg = r.content.decode("utf-8", errors="replace")
                    self.append_chat("Lỗi", f"Server ({r.status_code}): {err_msg}", "system_sender")
                    self.set_status("Lỗi phản hồi.")
                    self.is_processing = False
                    return

                response_text = r.content.decode("utf-8", errors="replace")
                lines = response_text.strip().split("\n")
                ai_reply = ""
                for line in lines:
                    line = line.strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            data = json.loads(line[6:])
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                ai_reply += content
                        except Exception:
                            pass

                if not ai_reply:
                    try:
                        res_json = json.loads(response_text)
                        ai_reply = res_json["choices"][0]["message"]["content"]
                    except Exception:
                        pass

                if ai_reply:
                    self.chat_history.append({"role": "user", "content": prompt})
                    self.chat_history.append({"role": "assistant", "content": ai_reply})
                    self.save_history()

                    self.append_chat("AI Copilot", ai_reply, "ai_sender")
                    
                    # Phát giọng nói đọc câu trả lời (TTS) nếu tính năng đang bật
                    self.speak_text_async(ai_reply)

                self.set_status("🟢 Đang lắng nghe... Hãy tiếp tục nói để hỏi câu tiếp theo!")

            except Exception as e:
                self.root.after(0, self.show)
                self.append_chat("Lỗi", str(e), "system_sender")
                self.set_status("Đã xảy ra lỗi.")
            finally:
                self.is_processing = False

        threading.Thread(target=_worker, daemon=True).start()

    def live_voice_loop(self):
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
                
                while True:
                    # Nếu đang nói trả lời bằng giọng nói (TTS) hoặc đang xử lý -> tạm ngưng nghe để không bị vọng âm
                    if not self.live_voice_enabled or self.is_processing or self.is_speaking_tts:
                        time.sleep(0.3)
                        continue

                    try:
                        audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=12)
                        
                        if not self.live_voice_enabled or self.is_processing or self.is_speaking_tts:
                            continue

                        self.is_user_speaking = True
                        self.set_status("🎙️ Đã nhận giọng nói, đang nhận dạng...")
                        
                        spoken_text = self.recognizer.recognize_google(audio, language="vi-VN")
                        self.is_user_speaking = False
                        
                        if spoken_text and len(spoken_text.strip()) > 1:
                            self.process_question(spoken_text.strip())
                    except sr.WaitTimeoutError:
                        self.is_user_speaking = False
                    except sr.UnknownValueError:
                        self.is_user_speaking = False
                    except Exception:
                        self.is_user_speaking = False
                        time.sleep(0.5)
        except Exception as e:
            print("Mic loop error:", e)

overlay = OverlayApp()

def hotkey_polling_loop():
    was_q_pressed = False
    while True:
        alt_down = (user32.GetAsyncKeyState(VK_MENU) & 0x8000) != 0
        q_down = (user32.GetAsyncKeyState(VK_Q) & 0x8000) != 0

        if alt_down and q_down:
            if not was_q_pressed:
                was_q_pressed = True
                overlay.toggle()
        else:
            was_q_pressed = False
            
        time.sleep(0.035)

def run_gui():
    overlay.create_window()
    t = threading.Thread(target=hotkey_polling_loop, daemon=True)
    t.start()
    overlay.root.mainloop()

if __name__ == "__main__":
    run_gui()
