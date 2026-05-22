import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import asyncio
import edge_tts
import threading
import os
import json
import random
import tempfile
import string
import sys
import subprocess
import time
import re
import unicodedata
import traceback
import gc
import shutil
from pathlib import Path
from pydub import AudioSegment

# BUG FIX: 'import audioop' removed — deprecated in Python 3.11 and removed in
# Python 3.13, causing ImportError on modern installs. It was unused anyway.

from TTS.api import TTS
import torch

# ==========================================
# XTTS VOICE CLONING MODEL
# ==========================================

# Global variable for TTS model to avoid reloading
tts_model = None
xtts_available = False


def init_xtts_model():
    """Initialize XTTS model only once"""
    global tts_model, xtts_available
    try:
        if tts_model is None:
            print("[XTTS] Initializing model...")
            tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=torch.cuda.is_available())
            xtts_available = True
            print("[XTTS] Model loaded successfully")
        return True
    except Exception as e:
        print(f"[XTTS] Failed to initialize: {e}")
        xtts_available = False
        return False


# ==========================================
# AUDIO PLAYBACK USING MULTIPLE METHODS
# ==========================================
try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    from playsound import playsound

    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False

try:
    import simpleaudio as sa

    SIMPLEAUDIO_AVAILABLE = True
except ImportError:
    SIMPLEAUDIO_AVAILABLE = False

# Use system default player as fallback
import platform


# ==========================================
# HISTORY MANAGER CLASS
# ==========================================
class HistoryManager:
    def __init__(self, max_items=10):
        self.history = []
        self.max_items = max_items

    def add(self, text, audio_path):
        self.history.insert(0, {
            "text": text[:100] + "..." if len(text) > 100 else text,
            "audio": audio_path,
            "time": time.time()
        })
        self.history = self.history[:self.max_items]

    def get_all(self):
        return self.history

    def clear(self):
        self.history = []


# ==========================================
# SIMPLE AUDIO PLAYER CLASS
# ==========================================
class SimpleAudioPlayer:
    def __init__(self):
        self.current_play_thread = None
        self.stop_playback = False
        self.is_playing = False
        self.play_lock = threading.Lock()

    def play(self, filepath):
        """Play audio file using available method"""
        with self.play_lock:
            if self.is_playing:
                self.stop()
            self.stop_playback = False
            self.is_playing = True

        def play_in_thread():
            try:
                if PLAYSOUND_AVAILABLE:
                    playsound(filepath)
                elif SIMPLEAUDIO_AVAILABLE:
                    wave_obj = sa.WaveObject.from_wave_file(self.convert_to_wav(filepath))
                    play_obj = wave_obj.play()
                    while play_obj.is_playing() and not self.stop_playback:
                        time.sleep(0.1)
                elif PYGAME_AVAILABLE:
                    if not pygame.mixer.get_init():
                        pygame.mixer.init()
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
                    pygame.mixer.music.load(filepath)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        if self.stop_playback:
                            pygame.mixer.music.stop()
                            break
                        time.sleep(0.1)
                    pygame.mixer.music.stop()
                else:
                    self.play_with_system_player(filepath)
            except Exception as e:
                print(f"Playback error: {e}")
            finally:
                with self.play_lock:
                    self.is_playing = False

        self.current_play_thread = threading.Thread(target=play_in_thread, daemon=True)
        self.current_play_thread.start()

    def stop(self):
        """Stop audio playback"""
        with self.play_lock:
            self.stop_playback = True
        try:
            if PYGAME_AVAILABLE and pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
        except:
            pass
        with self.play_lock:
            self.is_playing = False

    def convert_to_wav(self, mp3_path):
        """Convert MP3 to WAV for simpleaudio"""
        wav_path = mp3_path.replace('.mp3', '_temp.wav')
        try:
            audio = AudioSegment.from_mp3(mp3_path)
            audio.export(wav_path, format="wav")
            return wav_path
        except:
            return mp3_path

    def play_with_system_player(self, filepath):
        """Use system default player"""
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(filepath)
            elif system == "Darwin":
                subprocess.call(['afplay', filepath])
            else:
                subprocess.call(['xdg-open', filepath])
        except:
            pass


# ==========================================
# AVAILABLE VOICES (ULTRA HD STUDIO QUALITY)
# ==========================================
VOICES = {
    "Urdu Female (Studio HD)": "ur-PK-UzmaNeural",
    "Urdu Male (Studio HD)": "ur-PK-AsadNeural",
    "English Female (Jenny HD)": "en-US-JennyNeural",
    "English Male (Guy HD)": "en-US-GuyNeural",
    "English Female (Aria HD)": "en-US-AriaNeural",
    "English Male (Davis HD)": "en-US-DavisNeural",
    "English Female (Emotional)": "en-US-JennyNeural",
    "English Male (Emotional)": "en-US-GuyNeural",
    "Hindi Female": "hi-IN-SwaraNeural",
    "Hindi Male": "hi-IN-MadhurNeural",
}

# ==========================================
# SUPPORTED LANGUAGES DICTIONARY
# ==========================================
SUPPORTED_LANGUAGES = {
    "Auto Detect": "auto",
    "Urdu": "ur",
    "English": "en",
    "Hindi": "hi",
    "Arabic": "ar",
    "French": "fr",
    "German": "de",
    "Spanish": "es",
    "Turkish": "tr",
    "Russian": "ru"
}


# ==========================================
# SUBTITLE GENERATION
# ==========================================
class SubtitleGenerator:
    def __init__(self):
        self.subtitles = []

    def generate_subtitles(self, text, duration_seconds=30):
        words = text.split()
        if len(words) == 0:
            return []
        words_per_subtitle = 10
        time_per_word = duration_seconds / len(words)
        subtitles = []
        for i in range(0, len(words), words_per_subtitle):
            chunk = " ".join(words[i:i + words_per_subtitle])
            start_time = i * time_per_word
            end_time = min((i + words_per_subtitle) * time_per_word, duration_seconds)
            subtitles.append({
                "text": chunk,
                "start": start_time,
                "end": end_time
            })
        return subtitles

    def export_srt(self, subtitles, filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles, 1):
                start = self._format_time(sub['start'])
                end = self._format_time(sub['end'])
                f.write(f"{i}\n{start} --> {end}\n{sub['text']}\n\n")

    def export_vtt(self, subtitles, filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            for i, sub in enumerate(subtitles, 1):
                start = self._format_time_vtt(sub['start'])
                end = self._format_time_vtt(sub['end'])
                f.write(f"{start} --> {end}\n{sub['text']}\n\n")

    def _format_time(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _format_time_vtt(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


# ==========================================
# WAV CONVERTER
# ==========================================
class AudioConverter:
    @staticmethod
    def mp3_to_wav(mp3_path, wav_path):
        try:
            audio = AudioSegment.from_mp3(mp3_path)
            audio.export(wav_path, format="wav")
            return True
        except ImportError:
            try:
                result = subprocess.run(['ffmpeg', '-i', mp3_path, wav_path],
                                        capture_output=True, text=True)
                return result.returncode == 0
            except:
                return False
        except:
            return False


# ==========================================
# PROFESSIONAL KEYBOARD-STYLE BUTTON CLASS
# ==========================================
class KeyboardButton(tk.Button):
    """Professional keyboard-style button with 3D effect, hover, and press animations"""

    def __init__(self, parent, **kwargs):
        self.bg_color = kwargs.pop('bg', '#2563eb')
        self.hover_color = kwargs.pop('hovercolor', '#3b82f6')
        self.press_color = kwargs.pop('presscolor', '#1d4ed8')
        self.border_radius = kwargs.pop('border_radius', 8)
        self.text_color = kwargs.pop('fg', 'white')
        self.is_pressed = False

        kwargs['relief'] = 'flat'
        kwargs['borderwidth'] = 0
        kwargs['highlightthickness'] = 0
        kwargs['fg'] = self.text_color
        kwargs['bg'] = self.bg_color
        kwargs['activebackground'] = self.hover_color
        kwargs['activeforeground'] = self.text_color
        kwargs['cursor'] = 'hand2'

        if 'font' not in kwargs:
            kwargs['font'] = ('Arial', 10, 'bold')

        # BUG FIX: Remove 'command' from kwargs before passing to super().__init__
        # so the native tk.Button command binding does NOT fire on its own.
        # We handle command execution manually via on_press to avoid double-firing.
        self._user_command = kwargs.pop('command', None)

        super().__init__(parent, **kwargs)

        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        self.bind('<ButtonPress-1>', self.on_press)
        self.bind('<ButtonRelease-1>', self.on_release)

        self._apply_style(self.bg_color, raised=True)

    def _apply_style(self, color, raised=True):
        self.config(bg=color, activebackground=self.hover_color)
        if raised:
            self.config(highlightbackground=color, highlightcolor=color)
            self.config(highlightthickness=1)
        else:
            self.config(highlightthickness=1, highlightbackground=self.press_color)

    def on_enter(self, event):
        if not self.is_pressed:
            self.config(bg=self.hover_color, activebackground=self.hover_color)
            self.config(highlightbackground=self.hover_color)

    def on_leave(self, event):
        if not self.is_pressed:
            self.config(bg=self.bg_color, activebackground=self.hover_color)
            self.config(highlightbackground=self.bg_color)

    def on_press(self, event):
        self.is_pressed = True
        self.config(bg=self.press_color, activebackground=self.press_color)
        self.config(highlightbackground=self.press_color)
        self.config(relief='sunken', borderwidth=1)
        # BUG FIX: Use self._user_command (stored separately) instead of
        # self['command']. The original code used self['command']() which
        # would double-fire because tk.Button also invokes 'command' on click.
        # By storing and removing the command from the widget, we control
        # exactly when it fires (once, after 50ms for visual feedback).
        if self._user_command:
            self.after(50, self._trigger_command)

    def _trigger_command(self):
        if self._user_command:
            self._user_command()

    def on_release(self, event):
        self.is_pressed = False
        self.config(relief='flat', borderwidth=0)
        self.config(bg=self.bg_color, activebackground=self.hover_color)
        self.config(highlightbackground=self.bg_color)


# ==========================================
# MAIN APPLICATION CLASS
# ==========================================
class TextToSpeechApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Text To Speech Studio - Ultimate Edition - www.urdujahaan.com")

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        window_width = min(1300, screen_width - 50)
        window_height = min(680, screen_height - 80)

        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(1100, 650)
        self.root.configure(bg="#0f172a")

        # Variables
        self.current_theme = "dark"
        self.generated_file = os.path.join(
            tempfile.gettempdir(),
            "output.mp3")
        self.current_audio_file = None
        self.audio_player = SimpleAudioPlayer()
        self.subtitle_gen = SubtitleGenerator()
        self.emotion_mode = tk.BooleanVar(value=False)
        self.live_preview = tk.BooleanVar(value=True)

        # Voice cloning
        self.use_clone_voice = tk.BooleanVar(value=False)
        self.voice_sample_path = ""
        self.is_generating = False  # Track generation state

        # History Manager
        self.history_manager = HistoryManager(max_items=10)

        # Setup UI
        self.setup_ui()
        self.apply_theme()

        # Setup keyboard shortcuts
        self.setup_shortcuts()

        # Initialize with sample text
        self.set_sample_text()

        # Setup window close handler for cleanup
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Initialize XTTS model in background if needed
        self.xtts_ready = False
        threading.Thread(target=self._init_xtts_background, daemon=True).start()

    def _init_xtts_background(self):
        """Initialize XTTS in background"""
        self.xtts_ready = init_xtts_model()

    # ==========================================
    # CLEANUP FUNCTIONS
    # ==========================================

    def cleanup_temp_files(self):
        """Clean up temporary TTS files"""
        temp_dir = tempfile.gettempdir()
        for file in os.listdir(temp_dir):
            if file.startswith("tts_"):
                try:
                    os.remove(os.path.join(temp_dir, file))
                except:
                    pass

    def on_close(self):
        """Handle window close event"""
        try:
            self.cleanup_temp_files()
            self.stop_audio()
        except:
            pass
        self.root.destroy()

    # ==========================================
    # URDU TEXT PROCESSING FUNCTIONS
    # ==========================================

    def preprocess_text(self, text):
        """Better Unicode safe text processing"""
        if not text:
            return ""

        # UTF-8 safe conversion
        text = text.encode("utf-8", errors="ignore").decode("utf-8")

        # Unicode normalization
        text = unicodedata.normalize("NFKC", text)

        # Remove hidden unicode marks
        text = re.sub(r'[\u200B-\u200F\u202A-\u202E]', '', text)

        # Normalize spaces
        text = re.sub(r'\s+', ' ', text)

        # Replace Urdu punctuation
        text = text.replace("۔", ".")
        text = text.replace("،", ",")

        return text.strip()

    def normalize_urdu_text(self, text):
        """Normalize Urdu text for better TTS processing"""
        if not text:
            return ""

        # Unicode normalize
        text = unicodedata.normalize("NFKC", text)

        # Remove hidden RTL/LTR marks
        text = re.sub(r'[\u200B-\u200F\u202A-\u202E]', '', text)

        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text)

        # Replace newlines with spaces for better flow
        text = text.replace("\n", " ")

        # Urdu punctuation normalize
        text = text.replace("۔", ".")
        text = text.replace("،", ",")

        return text.strip()

    def detect_language(self, text):
        """Improved auto language detection logic"""
        text = self.preprocess_text(text)

        urdu_chars = 0
        english_chars = 0
        arabic_chars = 0

        for char in text:
            if '\u0600' <= char <= '\u06FF':
                urdu_chars += 1
            elif char.isascii() and char.isalpha():
                english_chars += 1
            if '\u0750' <= char <= '\u077F':
                arabic_chars += 1

        if urdu_chars > english_chars:
            return "ur"
        if arabic_chars > 10:
            return "ar"
        return "en"

    def get_selected_language(self, text):
        """Get language based on user selection or auto detect"""
        selected = self.language_var.get()

        # Manual language selected
        if selected != "Auto Detect":
            return SUPPORTED_LANGUAGES[selected]

        # Auto detect fallback
        detected = self.detect_language(text)

        if detected not in SUPPORTED_LANGUAGES.values():
            return "en"

        return detected

    def validate_xtts_language(self, lang_code):
        """Validate if language is supported by XTTS"""
        xtts_supported = [
            "en", "ur", "hi", "ar", "fr", "de", "es", "tr", "ru"
        ]
        return lang_code in xtts_supported

    def preprocess_voice_sample(self, input_path):
        """Preprocess voice sample for better XTTS performance"""
        try:
            temp_wav = os.path.join(
                tempfile.gettempdir(),
                "clean_voice_sample.wav"
            )

            audio = AudioSegment.from_file(input_path)

            # Convert to mono
            audio = audio.set_channels(1)

            # Set standard sample rate for XTTS
            audio = audio.set_frame_rate(22050)

            # Normalize volume
            from pydub.effects import normalize
            audio = normalize(audio)

            # Export cleaned audio
            audio.export(temp_wav, format="wav")

            return temp_wav
        except Exception as e:
            print(f"Preprocessing warning: {e}")
            return input_path

    # ==========================================
    # UI SETUP METHODS
    # ==========================================

    def setup_ui(self):
        # Main container
        main_container = tk.Frame(self.root, bg="#0f172a")
        main_container.pack(fill="both", expand=True)

        # Title
        title = tk.Label(
            main_container,
            text="🎙️ Text To Speech Studio",
            font=("Arial", 14, "bold"),
            bg="#0f172a",
            fg="white"
        )
        title.pack(pady=(5, 8))

        # Main content frame
        main_frame = tk.Frame(main_container, bg="#0f172a")
        main_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Left panel - Text Input
        self.setup_text_panel(main_frame)

        # Right panel - Controls
        self.setup_controls_panel(main_frame)

        # Bottom buttons
        self.setup_bottom_buttons(main_container)

        # Status bar
        self.setup_status_bar(main_container)

    def setup_text_panel(self, parent):
        text_frame = tk.LabelFrame(
            parent,
            text="📝 Text Input Area",
            font=("Arial", 11, "bold"),
            bg="#0f172a",
            fg="white",
            padx=8,
            pady=6
        )
        text_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        # TEXT TOOLBAR WITH PASTE BUTTON
        text_toolbar = tk.Frame(text_frame, bg="#0f172a")
        text_toolbar.pack(fill="x", pady=(0, 4))

        paste_btn = tk.Button(
            text_toolbar,
            text="📋 Paste",
            command=self.paste_text,
            bg="#1e293b",
            fg="white",
            relief="flat",
            cursor="hand2",
            font=("Arial", 8)
        )
        paste_btn.pack(side="right", padx=4)

        text_widget_frame = tk.Frame(text_frame, bg="#0f172a")
        text_widget_frame.pack(fill="both", expand=True)

        scrollbar_y = tk.Scrollbar(text_widget_frame)
        scrollbar_y.pack(side="right", fill="y")

        scrollbar_x = tk.Scrollbar(text_widget_frame, orient="horizontal")
        scrollbar_x.pack(side="bottom", fill="x")

        self.text_box = tk.Text(
            text_widget_frame,
            font=("Arial", 11),
            wrap="word",
            bg="#1e293b",
            fg="white",
            insertbackground="white",
            relief="flat",
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set,
            height=10
        )
        self.text_box.pack(fill="both", expand=True)
        self.text_box.bind('<KeyRelease>', self.update_text_stats)

        # Paste event binding — updates stats after paste
        self.text_box.bind("<<Paste>>", lambda e: self.update_text_stats())

        # TEXT AREA CONTEXT MENU
        self.text_menu = tk.Menu(self.root, tearoff=0)

        self.text_menu.add_command(
            label="Paste",
            command=self.paste_text
        )

        self.text_menu.add_command(
            label="Copy",
            command=lambda: self.text_box.event_generate("<<Copy>>")
        )

        self.text_menu.add_command(
            label="Cut",
            command=lambda: self.text_box.event_generate("<<Cut>>")
        )

        self.text_menu.add_separator()

        self.text_menu.add_command(
            label="Select All",
            command=self.select_all_text
        )

        # Right click binding
        self.text_box.bind("<Button-3>", self.show_text_context_menu)

        # Linux compatibility
        self.text_box.bind("<Button-2>", self.show_text_context_menu)

        # Focus on click
        self.text_box.bind(
            "<Button-1>",
            lambda e: self.text_box.focus_force()
        )

        scrollbar_y.config(command=self.text_box.yview)
        scrollbar_x.config(command=self.text_box.xview)

        info_bar = tk.Frame(text_frame, bg="#0f172a")
        info_bar.pack(fill="x", pady=(5, 0))

        self.char_count_label = tk.Label(
            info_bar,
            text="Characters: 0 | Words: 0",
            font=("Arial", 8),
            bg="#0f172a",
            fg="#94a3b8"
        )
        self.char_count_label.pack(side="left")

        drop_frame = tk.Frame(text_frame, bg="#1e293b", height=26)
        drop_frame.pack(fill="x", pady=(5, 0))

        drop_label = tk.Label(
            drop_frame,
            text="📁 Drag & Drop Text Files Here or Click to Load",
            font=("Arial", 8),
            bg="#1e293b",
            fg="#38bdf8",
            cursor="hand2"
        )
        drop_label.pack(expand=True, fill="both", padx=6, pady=2)
        drop_label.bind("<Button-1>", lambda e: self.load_text_file())

        button_row = tk.Frame(text_frame, bg="#0f172a")
        button_row.pack(fill="x", pady=(5, 0))

        batch_btn = KeyboardButton(
            button_row,
            text="📂 Batch Convert",
            command=self.batch_convert,
            bg="#7c3aed",
            hovercolor="#8b5cf6",
            presscolor="#6d28d9",
            fg="white",
            font=("Arial", 8, "bold")
        )
        batch_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))

        history_btn = KeyboardButton(
            button_row,
            text="🕐 History",
            command=self.show_history,
            bg="#f59e0b",
            hovercolor="#fbbf24",
            presscolor="#d97706",
            fg="white",
            font=("Arial", 8, "bold")
        )
        history_btn.pack(side="right", fill="x", expand=True, padx=(3, 0))

    def setup_controls_panel(self, parent):
        controls_frame = tk.LabelFrame(
            parent,
            text="🎮 Control Panel",
            font=("Arial", 11, "bold"),
            bg="#0f172a",
            fg="white",
            padx=8,
            pady=6
        )
        controls_frame.pack(side="right", fill="both", padx=(8, 0))

        voice_frame = tk.LabelFrame(controls_frame, text="Voice Settings",
                                    font=("Arial", 9, "bold"), bg="#0f172a", fg="white")
        voice_frame.pack(fill="x", pady=(0, 6))

        tk.Label(voice_frame, text="Select Voice:", bg="#0f172a", fg="white", font=("Arial", 8)).pack(anchor="w",
                                                                                                      padx=6,
                                                                                                      pady=(2, 0))
        self.voice_var = tk.StringVar(value="English Female (Jenny HD)")
        self.voice_combo = ttk.Combobox(
            voice_frame,
            textvariable=self.voice_var,
            values=list(VOICES.keys()),
            state="readonly",
            width=28
        )
        self.voice_combo.pack(padx=6, pady=2)

        gender_frame = tk.Frame(voice_frame, bg="#0f172a")
        gender_frame.pack(fill="x", padx=6, pady=2)
        tk.Label(gender_frame, text="Filter by Gender:", bg="#0f172a", fg="white", font=("Arial", 8)).pack(side="left")
        self.gender_var = tk.StringVar(value="All")
        gender_combo = ttk.Combobox(
            gender_frame,
            textvariable=self.gender_var,
            values=["All", "Female", "Male"],
            state="readonly",
            width=10
        )
        gender_combo.pack(side="right")
        gender_combo.bind("<<ComboboxSelected>>", self.filter_voices)

        # LANGUAGE SELECTION
        lang_frame = tk.LabelFrame(
            controls_frame,
            text="Language Settings",
            font=("Arial", 9, "bold"),
            bg="#0f172a",
            fg="white"
        )
        lang_frame.pack(fill="x", pady=(0, 6))

        tk.Label(
            lang_frame,
            text="Select Language:",
            bg="#0f172a",
            fg="white",
            font=("Arial", 8)
        ).pack(anchor="w", padx=6, pady=(2, 0))

        self.language_var = tk.StringVar(value="Auto Detect")

        self.language_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.language_var,
            values=list(SUPPORTED_LANGUAGES.keys()),
            state="readonly",
            width=28
        )
        self.language_combo.pack(padx=6, pady=4)

        settings_row = tk.Frame(controls_frame, bg="#0f172a")
        settings_row.pack(fill="x", pady=(0, 6))

        emotion_frame = tk.LabelFrame(settings_row, text="Emotion",
                                      font=("Arial", 9, "bold"), bg="#0f172a", fg="white")
        emotion_frame.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.emotion_check = tk.Checkbutton(
            emotion_frame,
            text="💖 Real Human Emotion",
            variable=self.emotion_mode,
            bg="#0f172a",
            fg="white",
            selectcolor="#0f172a",
            font=("Arial", 8)
        )
        self.emotion_check.pack(anchor="w", padx=6, pady=3)

        speed_frame = tk.LabelFrame(settings_row, text="Speed",
                                    font=("Arial", 9, "bold"), bg="#0f172a", fg="white")
        speed_frame.pack(side="right", fill="x", expand=True, padx=(3, 0))

        self.speed_var = tk.IntVar(value=0)
        speed_slider = tk.Scale(
            speed_frame,
            from_=-100,
            to=100,
            orient="horizontal",
            variable=self.speed_var,
            bg="#0f172a",
            fg="white",
            highlightthickness=0,
            length=100,
            troughcolor="#1e293b"
        )
        speed_slider.pack(padx=6, pady=2)
        self.speed_label = tk.Label(speed_frame, text="Speed: 0%",
                                    bg="#0f172a", fg="#38bdf8", font=("Arial", 7))
        self.speed_label.pack()
        speed_slider.config(command=self.update_speed_label)

        ssml_frame = tk.LabelFrame(controls_frame, text="SSML Settings",
                                   font=("Arial", 9, "bold"), bg="#0f172a", fg="white")
        ssml_frame.pack(fill="x", pady=(0, 6))

        self.use_ssml = tk.BooleanVar(value=False)
        ssml_check = tk.Checkbutton(
            ssml_frame,
            text="🎚️ Enable SSML",
            variable=self.use_ssml,
            bg="#0f172a",
            fg="white",
            selectcolor="#0f172a",
            font=("Arial", 8)
        )
        ssml_check.pack(anchor="w", padx=6, pady=2)

        ssml_row = tk.Frame(ssml_frame, bg="#0f172a")
        ssml_row.pack(fill="x", padx=6, pady=2)

        tk.Label(ssml_row, text="Rate:", bg="#0f172a", fg="white", font=("Arial", 7)).pack(side="left")
        self.ssml_rate = ttk.Combobox(ssml_row, values=["x-slow", "slow", "medium", "fast", "x-fast"],
                                      state="readonly", width=7)
        self.ssml_rate.set("medium")
        self.ssml_rate.pack(side="left", padx=(5, 10))

        tk.Label(ssml_row, text="Pitch:", bg="#0f172a", fg="white", font=("Arial", 7)).pack(side="left")
        self.ssml_pitch = ttk.Combobox(ssml_row, values=["x-low", "low", "medium", "high", "x-high"],
                                       state="readonly", width=7)
        self.ssml_pitch.set("medium")
        self.ssml_pitch.pack(side="left", padx=(5, 0))

        options_row = tk.Frame(controls_frame, bg="#0f172a")
        options_row.pack(fill="x", pady=(0, 6))

        format_frame = tk.LabelFrame(options_row, text="Export Format",
                                     font=("Arial", 9, "bold"), bg="#0f172a", fg="white")
        format_frame.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.format_var = tk.StringVar(value="MP3")
        mp3_radio = tk.Radiobutton(format_frame, text="MP3", variable=self.format_var,
                                   value="MP3", bg="#0f172a", fg="white", selectcolor="#0f172a", font=("Arial", 8))
        mp3_radio.pack(anchor="w", padx=6, pady=1)

        wav_radio = tk.Radiobutton(format_frame, text="WAV", variable=self.format_var,
                                   value="WAV", bg="#0f172a", fg="white", selectcolor="#0f172a", font=("Arial", 8))
        wav_radio.pack(anchor="w", padx=6, pady=1)

        preview_frame = tk.LabelFrame(options_row, text="Preview",
                                      font=("Arial", 9, "bold"), bg="#0f172a", fg="white")
        preview_frame.pack(side="right", fill="x", expand=True, padx=(3, 0))

        self.live_preview_check = tk.Checkbutton(
            preview_frame,
            text="🔊 Live Preview",
            variable=self.live_preview,
            bg="#0f172a",
            fg="white",
            selectcolor="#0f172a",
            font=("Arial", 8)
        )
        self.live_preview_check.pack(anchor="w", padx=6, pady=6)

        clone_frame = tk.LabelFrame(
            controls_frame,
            text="Voice Cloning",
            font=("Arial", 9, "bold"),
            bg="#0f172a",
            fg="white"
        )
        clone_frame.pack(fill="x", pady=(0, 4))

        clone_check = tk.Checkbutton(
            clone_frame,
            text="🧠 Use My Voice",
            variable=self.use_clone_voice,
            bg="#0f172a",
            fg="white",
            selectcolor="#0f172a",
            font=("Arial", 8)
        )
        clone_check.pack(anchor="w", padx=6, pady=2)

        upload_btn = KeyboardButton(
            clone_frame,
            text="🎤 Upload Voice Sample",
            command=self.load_voice_sample,
            bg="#2563eb",
            hovercolor="#3b82f6",
            presscolor="#1d4ed8",
            fg="white",
            font=("Arial", 8, "bold")
        )
        upload_btn.pack(fill="x", padx=6, pady=2)

        self.voice_sample_label = tk.Label(
            clone_frame,
            text="No voice sample selected",
            bg="#0f172a",
            fg="#94a3b8",
            font=("Arial", 7)
        )
        self.voice_sample_label.pack(pady=(0, 2))

    def setup_bottom_buttons(self, parent):
        button_frame = tk.Frame(parent, bg="#0f172a")
        button_frame.pack(pady=(0, 8))

        buttons = [
            ("🎙️ Convert", self.convert_to_speech, "#2563eb", "#3b82f6", "#1d4ed8"),
            ("▶️ Play", self.play_audio, "#16a34a", "#22c55e", "#15803d"),
            ("⏹️ Stop", self.stop_audio, "#dc2626", "#ef4444", "#b91c1c"),
            ("💾 Save", self.save_audio, "#7c3aed", "#8b5cf6", "#6d28d9"),
            ("📝 Subtitles", self.export_subtitles, "#f59e0b", "#fbbf24", "#d97706"),
            ("🗑️ Clear", self.clear_text, "#ef4444", "#f87171", "#dc2626"),
            ("🌙 Theme", self.toggle_theme, "#8b5cf6", "#a78bfa", "#7c3aed"),
        ]

        for text, command, bg_color, hover_color, press_color in buttons:
            btn = KeyboardButton(
                button_frame,
                text=text,
                command=command,
                bg=bg_color,
                hovercolor=hover_color,
                presscolor=press_color,
                fg="white",
                font=("Arial", 10, "bold"),
                border_radius=8
            )
            btn.pack(side="left", padx=4)

    def setup_status_bar(self, parent):
        status_frame = tk.Frame(parent, bg="#1e293b", height=28)
        status_frame.pack(fill="x", side="bottom")

        self.status_label = tk.Label(
            status_frame,
            text="✅ Ready | AI Voice Studio Pro Created by Urdu Jahaan",
            font=("Arial", 8),
            bg="#1e293b",
            fg="#38bdf8",
            anchor="w"
        )
        self.status_label.pack(side="left", padx=8, pady=4)

        self.progress = ttk.Progressbar(status_frame, mode='indeterminate', length=100)
        self.progress.pack(side="right", padx=8, pady=4)

    def setup_shortcuts(self):
        self.root.bind('<F5>', lambda e: self.convert_to_speech())
        self.root.bind('<Control-p>', lambda e: self.play_audio())
        self.root.bind('<Control-s>', lambda e: self.stop_audio())
        self.root.bind('<Control-o>', lambda e: self.load_text_file())

    def apply_theme(self):
        """Apply theme to all widgets properly"""
        if self.current_theme == "dark":
            bg_color = "#0f172a"
            fg_color = "white"
            text_bg = "#1e293b"
            frame_bg = "#0f172a"
            label_frame_bg = "#0f172a"
            button_bg = "#1e293b"
        else:  # light theme
            bg_color = "#f0f4f8"
            fg_color = "#1e293b"
            text_bg = "#ffffff"
            frame_bg = "#f0f4f8"
            label_frame_bg = "#e2e8f0"
            button_bg = "#e2e8f0"

        self.root.configure(bg=bg_color)
        self.update_widget_colors(self.root, bg_color, fg_color, text_bg, frame_bg, label_frame_bg, button_bg)

    def update_widget_colors(self, widget, bg_color, fg_color, text_bg, frame_bg, label_frame_bg, button_bg):
        """Recursively update colors for all widgets"""
        try:
            if isinstance(widget, tk.Frame):
                widget.configure(bg=frame_bg)
            elif isinstance(widget, tk.LabelFrame):
                widget.configure(bg=label_frame_bg, fg=fg_color)
                for child in widget.winfo_children():
                    self.update_widget_colors(child, bg_color, fg_color, text_bg, frame_bg, label_frame_bg, button_bg)
            elif isinstance(widget, tk.Label):
                if widget.winfo_parent():
                    current_bg = widget.cget('bg')
                    if current_bg not in ['#2563eb', '#16a34a', '#dc2626', '#7c3aed', '#f59e0b', '#ef4444', '#8b5cf6']:
                        widget.configure(bg=bg_color, fg=fg_color)
            elif isinstance(widget, tk.Button):
                if not isinstance(widget, KeyboardButton):
                    widget.configure(bg=button_bg, fg=fg_color, activebackground=button_bg)
            elif isinstance(widget, tk.Text):
                widget.configure(bg=text_bg, fg=fg_color, insertbackground=fg_color)
            elif isinstance(widget, tk.Listbox):
                widget.configure(bg=text_bg, fg=fg_color)
            elif isinstance(widget, ttk.Combobox):
                style = ttk.Style()
                style.configure('TCombobox', fieldbackground=text_bg, foreground=fg_color, background=bg_color)
            elif isinstance(widget, tk.Scale):
                widget.configure(bg=bg_color, fg=fg_color, troughcolor=text_bg)
            elif isinstance(widget, tk.Checkbutton):
                widget.configure(bg=bg_color, fg=fg_color, selectcolor=bg_color)
            elif isinstance(widget, tk.Radiobutton):
                widget.configure(bg=bg_color, fg=fg_color, selectcolor=bg_color)

            for child in widget.winfo_children():
                self.update_widget_colors(child, bg_color, fg_color, text_bg, frame_bg, label_frame_bg, button_bg)
        except Exception:
            pass

    def toggle_theme(self):
        """Toggle between dark and light themes"""
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme()
        self.status_label.config(text=f"✅ Theme changed to {self.current_theme} mode")

    def filter_voices(self, event=None):
        filter_val = self.gender_var.get()
        if filter_val == "All":
            filtered = list(VOICES.keys())
        else:
            filtered = [v for v in VOICES.keys() if filter_val in v]

        self.voice_combo['values'] = filtered
        if filtered:
            self.voice_var.set(filtered[0])

    def update_speed_label(self, value):
        self.speed_label.config(text=f"Speed: {value}%")

    def update_text_stats(self, event=None):
        text = self.text_box.get("1.0", tk.END).strip()
        char_count = len(text)
        word_count = len(text.split())
        self.char_count_label.config(text=f"Characters: {char_count} | Words: {word_count}")

    def set_sample_text(self):
        sample = """Assalam-o-Alaikum! Welcome to AI Text To Speech Studio.

This is a professional Text-to-Speech converter featuring ultra-HD neural voices,
created by Urdu Jahaan.
You can type or paste any Urdu or English text, and the AI will convert it into natural,
human-like speech with high-quality voice output.
This tool is completely free for everyone to use.
For more professional tools and custom software solutions,
visit www.urdujahaan.com or contact us info@urdujahaan.com for more information.

Features include:
• Real human emotion voice
• Multiple voice options
• Speed control
• Subtitle export
• MP3 and WAV support

Experience the power of AI voice technology today!"""
        self.text_box.insert("1.0", sample)
        self.update_text_stats()

    # ==========================================
    # FILE HANDLING METHODS
    # ==========================================

    def load_text_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.text_box.delete("1.0", tk.END)
                self.text_box.insert("1.0", content)
                self.status_label.config(text=f"✅ Loaded: {os.path.basename(file_path)}")
                self.update_text_stats()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {str(e)}")

    def on_file_drop(self, event):
        file_path = event.data.strip('{}')
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.text_box.delete("1.0", tk.END)
                self.text_box.insert("1.0", content)
                self.status_label.config(text=f"✅ Loaded: {os.path.basename(file_path)}")
                self.update_text_stats()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def load_voice_sample(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Audio Files", "*.wav *.mp3")]
        )
        if file_path:
            try:
                self.voice_sample_path = self.preprocess_voice_sample(file_path)
                self.voice_sample_label.config(text=os.path.basename(file_path))
                self.status_label.config(text="✅ Voice sample loaded and preprocessed successfully")
            except Exception as e:
                messagebox.showwarning("Warning", f"Could not preprocess sample: {e}\nUsing original file.")
                self.voice_sample_path = file_path
                self.voice_sample_label.config(text=os.path.basename(file_path))

    # ==========================================
    # CONTEXT MENU FUNCTIONS
    # ==========================================

    def show_text_context_menu(self, event):
        """Show context menu on right click"""
        try:
            self.text_box.focus_force()
            self.text_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.text_menu.grab_release()

    def paste_text(self):
        """Paste text from clipboard"""
        try:
            self.text_box.focus_force()
            try:
                clipboard_text = self.root.clipboard_get()
            except:
                clipboard_text = ""

            if clipboard_text:
                self.text_box.insert(tk.INSERT, clipboard_text)
                self.update_text_stats()
        except Exception as e:
            print(f"Paste Error: {e}")

    def select_all_text(self):
        """Select all text in text box"""
        self.text_box.tag_add("sel", "1.0", "end")
        return "break"

    # ==========================================
    # TTS GENERATION METHODS
    # ==========================================

    def generate_emotion_text(self, text):
        # BUG FIX: Removed '<emph>' which is not valid SSML/edge-tts markup
        # and would be passed as raw text or cause silent TTS failures.
        # Replaced with valid prosody adjustments only.
        emotions = {
            'great': '<prosody pitch="+10%">great</prosody>',
            'wonderful': '<prosody pitch="+15%">wonderful</prosody>',
            'amazing': '<prosody pitch="+15%" rate="+5%">amazing</prosody>',
            'sorry': '<prosody rate="-5%">sorry</prosody>',
            'wow': '<prosody pitch="+20%">wow</prosody>',
        }
        modified = text
        for word, replacement in emotions.items():
            modified = modified.replace(word, replacement)
        return modified

    def generate_ssml(self, text):
        rate = self.ssml_rate.get()
        pitch = self.ssml_pitch.get()
        return f"""<?xml version="1.0"?>
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <prosody rate="{rate}" pitch="{pitch}">
        {text}
    </prosody>
</speak>"""

    # ==========================================
    # VOICE CLONING - IMPROVED FOR URDU
    # ==========================================

    def generate_cloned_voice(self, text, output_file):
        """Improved voice cloning with better Urdu support and error handling"""
        global xtts_available, tts_model

        try:
            if not xtts_available:
                if not init_xtts_model():
                    raise Exception("XTTS model failed to initialize. Please check your installation.")

            if not self.voice_sample_path:
                raise Exception("Voice sample not selected. Please upload a voice sample first.")

            if not os.path.exists(self.voice_sample_path):
                raise Exception(f"Voice sample file not found: {self.voice_sample_path}")

            text = self.preprocess_text(text)

            if not text.strip():
                raise Exception("Text is empty")

            lang_code = self.get_selected_language(text)

            if lang_code == "ur":
                text = self.normalize_urdu_text(text)
                print(f"[XTTS] Processing Urdu text: {text[:50]}...")

            if not self.validate_xtts_language(lang_code):
                print(f"Warning: XTTS may not fully support '{lang_code}', falling back to English")
                lang_code = "en"

            print(f"[XTTS] Using language: {lang_code}")
            print(f"[XTTS] Text length: {len(text)} chars")

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # BUG FIX: XTTS tts_to_file always outputs a WAV file.
            # The caller may pass a .mp3 path, which causes a broken audio file.
            # We write to a guaranteed .wav temp path, then convert to the
            # requested output format (mp3 or wav) using pydub.
            wav_temp = os.path.join(tempfile.gettempdir(), "xtts_out_temp.wav")

            tts_model.tts_to_file(
                text=text,
                speaker_wav=self.voice_sample_path,
                language=lang_code,
                file_path=wav_temp
            )

            if not os.path.exists(wav_temp) or os.path.getsize(wav_temp) < 1000:
                raise Exception("Audio file was not generated properly (file too small)")

            # Convert to the desired output format
            if output_file.lower().endswith(".mp3"):
                audio = AudioSegment.from_wav(wav_temp)
                audio.export(output_file, format="mp3")
                try:
                    os.remove(wav_temp)
                except:
                    pass
            else:
                shutil.copy(wav_temp, output_file)
                try:
                    os.remove(wav_temp)
                except:
                    pass

            print(f"[XTTS] Successfully generated: {output_file} ({os.path.getsize(output_file)} bytes)")

        except Exception as e:
            print("\n========== XTTS ERROR DETAILS ==========")
            traceback.print_exc()
            print("=========================================\n")

            error_msg = str(e)

            if "No speaker" in error_msg or "speaker" in error_msg.lower():
                raise Exception(
                    "Voice sample could not be processed. Please use a clear WAV or MP3 file with a single voice (3-10 seconds).")
            elif "language" in error_msg.lower():
                raise Exception(
                    f"The selected language is not supported for voice cloning. Please use standard TTS mode for this language.")
            elif "memory" in error_msg.lower() or "cuda" in error_msg.lower():
                raise Exception("Not enough memory for voice cloning. Please close other applications and try again.")
            elif "file" in error_msg.lower():
                raise Exception(f"Voice sample file issue: {error_msg}")
            else:
                raise Exception(
                    f"Voice cloning failed: {error_msg}\n\nTips:\n- Use a 3-10 second clear audio sample\n- Avoid background noise\n- Try a WAV file for best results")

    async def generate_tts(self, text, voice, speed, progress_callback=None):
        """Generate TTS using edge-tts"""
        text = text.encode("utf-8", errors="ignore").decode("utf-8")
        raw_file = self.generated_file.replace(".mp3", "_raw.mp3")
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(raw_file)

        if progress_callback:
            progress_callback(50)

        sound = AudioSegment.from_file(raw_file)
        if speed != 0:
            playback_speed = 1.0 + (speed / 100.0)
            playback_speed = max(0.5, min(playback_speed, 2.0))
            modified_sound = sound._spawn(
                sound.raw_data,
                overrides={"frame_rate": int(sound.frame_rate * playback_speed)}
            ).set_frame_rate(sound.frame_rate)
            sound = modified_sound

        sound.export(self.generated_file, format="mp3")

        if progress_callback:
            progress_callback(100)

        try:
            os.remove(raw_file)
        except:
            pass

    # ==========================================
    # CONVERT METHOD - PROPER VOICE MAPPING
    # ==========================================

    def convert_to_speech(self):
        """Main conversion method with fixed Urdu voice mapping"""
        if self.is_generating:
            messagebox.showwarning("Warning", "Generation already in progress")
            return

        text = self.text_box.get("1.0", tk.END).strip()
        if not text:
            messagebox.showerror("Error", "Please enter text to convert")
            return

        if self.use_ssml.get():
            text = self.generate_ssml(text)

        if self.emotion_mode.get():
            if self.detect_language(text) == "en":
                text = self.generate_emotion_text(text)

        text = self.preprocess_text(text)

        lang = self.get_selected_language(text)

        print(f"[DEBUG] Text preview: {text[:100]}...")
        print(f"[DEBUG] Detected/Selected Language: {lang}")
        print(f"[DEBUG] Clone Voice Enabled: {self.use_clone_voice.get()}")

        selected_voice_display = self.voice_var.get()
        selected_voice = VOICES.get(selected_voice_display, "en-US-JennyNeural")

        print(f"[DEBUG] Selected Voice Display: {selected_voice_display}")
        print(f"[DEBUG] Selected Voice ID: {selected_voice}")

        speed = self.speed_var.get()

        random_name = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        self.generated_file = os.path.join(tempfile.gettempdir(), f"tts_{random_name}.mp3")

        self.is_generating = True
        self.status_label.config(text="🎙️ Generating Speech... Please wait")
        self.progress.start()

        def update_progress(value):
            self.root.after(0, lambda: self.status_label.config(text=f"🎙️ Generating... {value}%"))

        def run():
            loop = None
            try:
                self.audio_player.stop()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                if self.use_clone_voice.get():
                    if not self.voice_sample_path:
                        raise Exception("Please upload voice sample first")

                    self.root.after(0, lambda: self.status_label.config(
                        text="🎤 Cloning voice... This may take 10-15 seconds"))
                    self.generate_cloned_voice(text, self.generated_file)

                    if self.live_preview.get():
                        self.root.after(500, self.play_audio)
                else:
                    print(f"[DEBUG] Using voice ID: {selected_voice} for text language: {lang}")
                    loop.run_until_complete(self.generate_tts(text, selected_voice, speed, update_progress))

                self.history_manager.add(text, self.generated_file)

                self.root.after(0, lambda: self.status_label.config(text="✅ Speech Generated Successfully!"))
                self.root.after(0, lambda: self.progress.stop())
                self.root.after(0, lambda: setattr(self, 'is_generating', False))

                if self.live_preview.get() and not self.use_clone_voice.get():
                    self.root.after(500, self.play_audio)

            except Exception as e:
                print("\n========== FULL ERROR ==========")
                traceback.print_exc()
                print("================================\n")

                self.root.after(0, lambda: self.status_label.config(text="❌ Error generating speech"))
                self.root.after(0, lambda: self.progress.stop())
                self.root.after(0, lambda: setattr(self, 'is_generating', False))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                if loop:
                    try:
                        loop.stop()
                        loop.close()
                    except:
                        pass

        threading.Thread(target=run, daemon=True).start()

    # ==========================================
    # AUDIO CONTROL METHODS
    # ==========================================

    def play_audio(self):
        if not os.path.exists(self.generated_file):
            messagebox.showwarning("Warning", "Please generate speech first (Click 'Convert To Speech')")
            return
        self.status_label.config(text="▶️ Playing Audio...")
        self.audio_player.play(self.generated_file)

    def stop_audio(self):
        self.audio_player.stop()
        self.status_label.config(text="⏹️ Audio Stopped")

    def save_audio(self):
        if not os.path.exists(self.generated_file):
            messagebox.showwarning("Warning", "Please generate speech first")
            return

        if self.format_var.get() == "MP3":
            file_path = filedialog.asksaveasfilename(
                defaultextension=".mp3",
                filetypes=[("MP3 Files", "*.mp3")]
            )
            if file_path:
                with open(self.generated_file, "rb") as src:
                    with open(file_path, "wb") as dst:
                        dst.write(src.read())
                self.status_label.config(text=f"💾 Audio saved: {os.path.basename(file_path)}")
                messagebox.showinfo("Success", "MP3 saved successfully!")
        else:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".wav",
                filetypes=[("WAV Files", "*.wav")]
            )
            if file_path:
                success = AudioConverter.mp3_to_wav(self.generated_file, file_path)
                if success:
                    self.status_label.config(text=f"🎵 WAV saved: {os.path.basename(file_path)}")
                    messagebox.showinfo("Success", "WAV file saved successfully!")
                else:
                    messagebox.showerror("Error", "Failed to convert to WAV.\nInstall: pip install pydub")

    def export_subtitles(self):
        text = self.text_box.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter text first")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".srt",
            filetypes=[("Subtitle Files", "*.srt"), ("WebVTT Files", "*.vtt")]
        )

        if file_path:
            duration = max(5, len(text) / 8)
            subtitles = self.subtitle_gen.generate_subtitles(text, duration)
            if file_path.endswith('.vtt'):
                self.subtitle_gen.export_vtt(subtitles, file_path)
            else:
                self.subtitle_gen.export_srt(subtitles, file_path)
            self.status_label.config(text=f"📝 Subtitles exported: {os.path.basename(file_path)}")
            messagebox.showinfo("Success", "Subtitles exported successfully!")

    # ==========================================
    # CLEAR TEXT METHOD WITH LANGUAGE RESET
    # ==========================================

    def clear_text(self):
        """Clear text and reset all application state including language"""
        try:
            self.stop_audio()
            self.text_box.delete("1.0", tk.END)
            self.text_box.focus_force()
            self.root.update_idletasks()
            self.language_var.set("Auto Detect")
            self.update_text_stats()

            self.generated_file = os.path.join(
                tempfile.gettempdir(),
                f"tts_reset_{random.randint(1000, 9999)}.mp3"
            )

            self.is_generating = False
            self.cleanup_temp_files()
            gc.collect()

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            self.status_label.config(text="✅ Text and language state cleared successfully")

        except Exception as e:
            print(traceback.format_exc())
            messagebox.showerror("Error", f"Error during reset: {str(e)}")

    # ==========================================
    # BATCH CONVERSION METHOD
    # ==========================================

    def batch_convert(self):
        files = filedialog.askopenfilenames(
            title="Select Text Files for Batch Conversion",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )

        if not files:
            return

        output_dir = filedialog.askdirectory(title="Select Output Directory")
        if not output_dir:
            return

        self.status_label.config(text=f"📂 Batch converting {len(files)} files...")
        self.progress.start()

        def run_batch():
            total = len(files)
            selected_voice_display = self.voice_var.get()
            selected_voice = VOICES.get(selected_voice_display, "en-US-JennyNeural")
            speed = self.speed_var.get()

            for idx, file_path in enumerate(files):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()

                    if not text.strip():
                        continue

                    text = self.preprocess_text(text)

                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    output_file = os.path.join(output_dir, f"{base_name}.mp3")

                    # BUG FIX: Each batch iteration now uses its own unique temp file.
                    # The original code reused self.generated_file across iterations,
                    # meaning concurrent or sequential writes could overwrite each other.
                    # We assign a fresh temp path per file so no data is lost.
                    random_name = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                    self.generated_file = os.path.join(tempfile.gettempdir(), f"tts_{random_name}.mp3")

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.generate_tts(text, selected_voice, speed, None))
                    loop.close()

                    shutil.copy(self.generated_file, output_file)

                    percent = int((idx + 1) / total * 100)
                    self.root.after(0, lambda p=percent, i=idx: self.status_label.config(
                        text=f"📂 Batch: {i + 1}/{total} ({p}%)"))

                except Exception as e:
                    print(f"Error converting {file_path}: {e}")

            self.root.after(0, lambda: self.status_label.config(text=f"✅ Batch complete! {total} files converted"))
            self.root.after(0, lambda: self.progress.stop())
            self.root.after(0, lambda: messagebox.showinfo("Success",
                                                           f"Successfully converted {total} files to {output_dir}"))

        threading.Thread(target=run_batch, daemon=True).start()

    # ==========================================
    # HISTORY WINDOW METHOD
    # ==========================================

    def show_history(self):
        history_window = tk.Toplevel(self.root)
        history_window.title("Conversion History")
        history_window.geometry("500x400")
        history_window.configure(bg="#0f172a")

        tk.Label(
            history_window,
            text="🕐 Recent Conversions",
            font=("Arial", 14, "bold"),
            bg="#0f172a",
            fg="white"
        ).pack(pady=10)

        listbox = tk.Listbox(history_window, bg="#1e293b", fg="white", font=("Arial", 10), height=15)
        listbox.pack(fill="both", expand=True, padx=10, pady=5)

        history_items = self.history_manager.get_all()
        for item in history_items:
            listbox.insert(tk.END, f"{item['text']} [{time.strftime('%H:%M:%S', time.localtime(item['time']))}]")

        def clear_history():
            self.history_manager.clear()
            listbox.delete(0, tk.END)
            self.status_label.config(text="✅ History cleared")

        def replay_selected():
            selection = listbox.curselection()
            if selection:
                item = history_items[selection[0]]
                if os.path.exists(item['audio']):
                    self.generated_file = item['audio']
                    self.play_audio()
                else:
                    messagebox.showerror("Error", "Audio file not found")

        btn_frame = tk.Frame(history_window, bg="#0f172a")
        btn_frame.pack(fill="x", pady=10, padx=10)

        replay_btn = KeyboardButton(
            btn_frame,
            text="▶️ Replay",
            command=replay_selected,
            bg="#16a34a",
            hovercolor="#22c55e",
            presscolor="#15803d",
            fg="white",
            font=("Arial", 9, "bold")
        )
        replay_btn.pack(side="left", padx=5)

        clear_btn = KeyboardButton(
            btn_frame,
            text="🗑️ Clear History",
            command=clear_history,
            bg="#ef4444",
            hovercolor="#f87171",
            presscolor="#dc2626",
            fg="white",
            font=("Arial", 9, "bold")
        )
        clear_btn.pack(side="left", padx=5)

        close_btn = KeyboardButton(
            btn_frame,
            text="❌ Close",
            command=history_window.destroy,
            bg="#64748b",
            hovercolor="#94a3b8",
            presscolor="#475569",
            fg="white",
            font=("Arial", 9, "bold")
        )
        close_btn.pack(side="right", padx=5)


# ==========================================
# INSTALL AND RUN
# ==========================================
def check_and_install_dependencies():
    required = ['edge-tts', 'TTS']
    for package in required:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])


if __name__ == "__main__":
    check_and_install_dependencies()

    # BUG FIX: tkinterdnd2 startup — if the first import fails (not installed),
    # we install it and then attempt import again. However, pip installing a
    # package mid-process can sometimes fail on the immediate re-import if the
    # sys.path hasn't refreshed. We now wrap the second import in a try/except
    # and fall back gracefully to plain tk.Tk() so the app still launches even
    # if drag-and-drop is unavailable, rather than crashing with an ImportError.
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except ImportError:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "tkinterdnd2"])
            # Reload path so the freshly-installed package is visible
            import importlib
            import importlib.util
            spec = importlib.util.find_spec("tkinterdnd2")
            if spec:
                from tkinterdnd2 import TkinterDnD
                root = TkinterDnD.Tk()
            else:
                raise ImportError("tkinterdnd2 not found after install")
        except Exception:
            print("Warning: tkinterdnd2 not available — drag-and-drop disabled. Using standard Tk.")
            root = tk.Tk()

    app = TextToSpeechApp(root)
    root.mainloop()