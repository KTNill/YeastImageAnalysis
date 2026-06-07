import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import datetime
import cv2
import pandas as pd
import numpy as np
import shutil
import platform
import subprocess
import re

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    """
    メインGUIクラス。チェックボックスの状態に応じて出力を動的に切り替える。
    """

    def __init__(self):
        super().__init__()
        self.analyzer = None
        self.analyzer_signature = None
        self.config_data = None
        self.target_path = ""
        self.is_running = False
        self.cancel_requested = False

        self.title("酵母・油脂 画像解析システム")
        self.geometry("960x750")

        # Configure grid layout
        self.grid_columnconfigure(0, weight=0, minsize=260)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Sidebar frame
        self.sidebar_frame = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="操作パネル", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.select_button = ctk.CTkButton(self.sidebar_frame, text="画像フォルダを選択", command=self.select_folder)
        self.select_button.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        # 実験メモ
        self.memo_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="実験メモ (フォルダ名用)")
        self.memo_entry.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="ew")

        # チェックボックス連動ロジック
        self.run_cell_var = ctk.BooleanVar(value=True)
        self.cell_check = ctk.CTkCheckBox(self.sidebar_frame, text="細胞解析 (BF)",
                                          variable=self.run_cell_var, command=self.on_cell_check_changed)
        self.cell_check.grid(row=3, column=0, padx=20, pady=10, sticky="w")

        self.run_lipid_var = ctk.BooleanVar(value=True)
        self.lipid_check = ctk.CTkCheckBox(self.sidebar_frame, text="油脂解析 (FL)",
                                           variable=self.run_lipid_var, command=self.on_lipid_check_changed)
        self.lipid_check.grid(row=4, column=0, padx=20, pady=10, sticky="w")

        self.run_necrosis_var = ctk.BooleanVar(value=False)
        self.necrosis_check = ctk.CTkCheckBox(self.sidebar_frame, text="壊死解析 (PI)",
                                              variable=self.run_necrosis_var, command=self.on_necrosis_check_changed)
        self.necrosis_check.grid(row=5, column=0, padx=20, pady=10, sticky="w")

        # プレビュー設定フレーム
        self.preview_frame = ctk.CTkFrame(self.sidebar_frame)
        self.preview_frame.grid(row=6, column=0, padx=20, pady=10, sticky="ew")

        self.preview_label = ctk.CTkLabel(self.preview_frame, text="プレビュー表示対象:", anchor="w")
        self.preview_label.pack(padx=10, pady=(5, 0), fill="x")

        self.preview_target_var = ctk.StringVar(value="combined")

        self.radio_clean = ctk.CTkRadioButton(self.preview_frame, text="前処理後画像", variable=self.preview_target_var, value="clean")
        self.radio_clean.pack(padx=10, pady=5, anchor="w")

        self.radio_mask = ctk.CTkRadioButton(self.preview_frame, text="マスク画像", variable=self.preview_target_var, value="mask")
        self.radio_mask.pack(padx=10, pady=5, anchor="w")

        self.radio_combined = ctk.CTkRadioButton(self.preview_frame, text="マージ画像", variable=self.preview_target_var, value="combined")
        self.radio_combined.pack(padx=10, pady=(5, 10), anchor="w")

        # プレビューボタン
        self.preview_button = ctk.CTkButton(self.sidebar_frame, text="1枚テストプレビュー", command=self.run_preview_thread)
        self.preview_button.grid(row=7, column=0, padx=20, pady=(10, 10), sticky="ew")

        # 解析開始・中止ボタン
        self.start_button = ctk.CTkButton(self.sidebar_frame, text="解析開始", command=self.toggle_analysis,
                                          fg_color="green", hover_color="darkgreen")
        self.start_button.grid(row=8, column=0, padx=20, pady=(0, 20), sticky="ew")

        # ログエリア
        self.log_text = ctk.CTkTextbox(
            self,
            width=600,
            font=ctk.CTkFont(family="MS Gothic", size=12)
        )
        self.log_text.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")
        self.log_text.tag_config("log_line_spacing", spacing3=5)
        self.log_text.tag_config("filename", foreground="#4DA3FF")
        self.log_text.tag_config("summary_title", foreground="#FFD166")
        self.log_text.tag_config("warning", foreground="#FF6B6B")  # 警告表示用の明るい赤色を追加

        # 進捗バー
        self.progressbar = ctk.CTkProgressBar(self)
        self.progressbar.grid(row=2, column=1, padx=20, pady=(0, 20), sticky="ew")
        self.progressbar.set(0)

        # 初期状態の反映
        self.update_radio_state()

    def update_radio_state(self):
        """油脂または壊死解析がONのときのみラジオボタンを有効化する"""
        if not self.run_lipid_var.get() and not self.run_necrosis_var.get():
            self.radio_clean.configure(state="disabled")
            self.radio_mask.configure(state="disabled")
            self.radio_combined.configure(state="disabled")
        else:
            self.radio_clean.configure(state="normal")
            self.radio_mask.configure(state="normal")
            self.radio_combined.configure(state="normal")

    def on_cell_check_changed(self):
        if not self.run_cell_var.get():
            self.run_lipid_var.set(False)
            self.run_necrosis_var.set(False)
        self.update_radio_state()

    def on_lipid_check_changed(self):
        if self.run_lipid_var.get():
            self.run_cell_var.set(True)
            self.run_necrosis_var.set(False)
        self.update_radio_state()

    def on_necrosis_check_changed(self):
        if self.run_necrosis_var.get():
            self.run_cell_var.set(True)
            self.run_lipid_var.set(False)
        self.update_radio_state()

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.target_path = path
            self.update_log(f"解析フォルダ設定完了: {path}")

    def _set_ui_state_running_main(self, is_preview=False):
        self.preview_button.configure(state="disabled")
        # 実行中はラジオボタンを操作不可にする
        self.radio_clean.configure(state="disabled")
        self.radio_mask.configure(state="disabled")
        self.radio_combined.configure(state="disabled")

        if is_preview:
            self.start_button.configure(state="disabled", fg_color="gray")
        else:
            self.start_button.configure(text="解析中止", fg_color="#cc0000", hover_color="#990000", state="normal")

    def _set_ui_state_stopped_main(self):
        self.preview_button.configure(state="normal")
        # 停止時にチェック状態に合わせてラジオボタンの有効/無効を復元する
        self.update_radio_state()

        self.start_button.configure(text="解析開始", state="normal", fg_color="green", hover_color="darkgreen")
        self.cancel_requested = False
        self.is_running = False

    def update_log(self, message, highlight_text=None):
        self.after(0, self._append_log, message, highlight_text)

    def update_log_sync(self, message, highlight_text=None):
        if threading.current_thread() is threading.main_thread():
            self._append_log(message, highlight_text)
            return

        completed = threading.Event()

        def append_and_notify():
            try:
                self._append_log(message, highlight_text)
            finally:
                completed.set()

        try:
            self.after(0, append_and_notify)
            completed.wait(timeout=2.0)
        except Exception:
            completed.set()

    def _append_log(self, message, highlight_text=None):
        timestamp = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
        start_index = self.log_text.index("end-1c")

        self.log_text.insert("end", f"{timestamp}{message}\n")

        if highlight_text:
            highlight_texts = highlight_text if isinstance(highlight_text, list) else [highlight_text]

            for text in highlight_texts:
                search_start = start_index
                while True:
                    found_index = self.log_text.search(text, search_start, stopindex="end")
                    if not found_index:
                        break

                    found_end = f"{found_index}+{len(text)}c"
                    self.log_text.tag_add("filename", found_index, found_end)
                    search_start = found_end

        # 警告マーク（⚠）のある箇所を行末まで警告色（赤色）に設定する
        search_start = start_index
        while True:
            found_index = self.log_text.search("⚠", search_start, stopindex="end")
            if not found_index:
                break
            found_end = f"{found_index} lineend"
            self.log_text.tag_add("warning", found_index, found_end)
            search_start = f"{found_index}+1c"

        highlighted_titles = [
            "【 全画像 統計サマリー 】",
            "【解析開始:"
        ]

        for title in highlighted_titles:
            search_start = start_index
            while True:
                found_index = self.log_text.search(title, search_start, stopindex="end")
                if not found_index:
                    break

                if title == "【解析開始:":
                    line_end = self.log_text.search("】", found_index, stopindex="end")
                    if not line_end:
                        break
                    found_end = f"{line_end}+1c"
                else:
                    found_end = f"{found_index}+{len(title)}c"

                self.log_text.tag_add("summary_title", found_index, found_end)
                search_start = found_end

        self.log_text.tag_add("log_line_spacing", start_index, "end")
        self.log_text.see("end")
        # --- 描画の遅延を防ぐため、強制的にUIを再描画（アップデート）する ---
        self.update_idletasks()

    def update_status(self, message=None, progress=None, highlight_text=None, enable_start_button=None):
        self.after(0, self._update_status, message, progress, highlight_text, enable_start_button)

    def _update_status(self, message=None, progress=None, highlight_text=None, enable_start_button=None):
        if message is not None:
            self._append_log(message, highlight_text)

        if progress is not None:
            self.progressbar.set(progress)

        if enable_start_button is not None:
            if enable_start_button:
                self._set_ui_state_stopped_main()
            else:
                self.is_running = True

        # ステータス更新時も強制的にUIを再描画する
        self.update_idletasks()

    def show_error(self, title, message):
        self.after(0, messagebox.showerror, title, message)

    def toggle_analysis(self):
        """解析開始・中止ボタンの制御"""
        if self.is_running and not self.cancel_requested:
            self.cancel_requested = True
            self.start_button.configure(text="中止処理中...", state="disabled", fg_color="gray")
            self.update_log("⚠ 解析の中止を要求しました。現在の処理が終わるまでお待ちください...")
        elif not self.is_running:
            self.start_analysis_thread()

    def start_analysis_thread(self):
        if self.is_running:
            return

        if not self.target_path or not os.path.exists(self.target_path):
            self.select_folder()
            if not self.target_path:
                return

        # エラーを防ぐため、GUIウィジェットからの値取得はメインスレッドで事前に行う
        run_cell = self.run_cell_var.get()
        run_lipid = self.run_lipid_var.get()
        run_necrosis = self.run_necrosis_var.get()
        memo_text = self.memo_entry.get().strip()

        self.is_running = True
        self.cancel_requested = False
        self.after(0, lambda: self._set_ui_state_running_main(is_preview=False))

        # 重い処理（モデルロード等）はバックグラウンドスレッドで実行
        threading.Thread(
            target=self.run_analysis,
            args=(run_cell, run_lipid, run_necrosis, memo_text),
            daemon=True
        ).start()

    def run_preview_thread(self):
        """プレビュー処理の開始スレッド"""
        if self.is_running:
            return

        if not self.target_path or not os.path.exists(self.target_path):
            self.select_folder()
            if not self.target_path:
                return

        # エラーを防ぐため、GUIウィジェットからの値取得はメインスレッドで事前に行う
        run_cell = self.run_cell_var.get()
        run_lipid = self.run_lipid_var.get()
        run_necrosis = self.run_necrosis_var.get()
        preview_type = self.preview_target_var.get()

        self.is_running = True
        self.cancel_requested = False
        self.after(0, lambda: self._set_ui_state_running_main(is_preview=True))

        # 重い処理（モデルロード等）はバックグラウンドスレッドで実行
        threading.Thread(
            target=self.run_preview,
            args=(run_cell, run_lipid, run_necrosis, preview_type),
            daemon=True
        ).start()

    def run_preview(self, run_cell, run_lipid, run_necrosis, preview_type):
        """1枚テストプレビューを実行する処理"""
        try:
            self.update_log(f"設定ファイルを読み込み中: {self.config_data.config_dir}")
            if not self.config_data.load_config():
                self.update_log("警告: 設定CSVの読み込みに失敗したため、前回またはデフォルト設定を使用します。")

            self.prepare_analyzer()

            # 解析開始直後に、必要なモデルが未ロードであればGUIログで進捗を表示しながらロードを実行する
            if run_cell:
                # analyzer._get_cell_model() 内で self.log_callback を通じて完了ログが表示される
                self.analyzer._get_cell_model()

            if run_lipid:
                self.analyzer._get_lipid_model()

            if run_necrosis:
                self.analyzer._get_necrosis_model()

            bf_suffix = str(self.config_data.get("bf_suffix", "")).strip()
            fl_suffix = str(self.config_data.get("fl_suffix", "")).strip()
            pi_suffix = str(self.config_data.get("pi_suffix", "")).strip()

            files, bf_files, bf_suffix_lower = self.collect_image_files(bf_suffix)

            if not bf_files:
                self.handle_no_bf_images(files, bf_suffix)
                return

            bf_name = bf_files[0]
            self.update_log(f"【プレビュー実行】先頭の1枚を解析中: {bf_name}")

            preview_dir = os.path.join(self.target_path, "preview_temp")
            os.makedirs(preview_dir, exist_ok=True)

            prefix_map = {
                "cell": "01_",
                "lipid_clean": "00_clean_",
                "lipid": "02_",
                "combined": "03_",
                "necrosis_clean": "00_clean_",
                "necrosis": "02_",
                "combined_necrosis": "03_"
            }

            # ダミーのtotalsディクショナリ
            dummy_totals = {
                "sum_occ": 0.0, "sum_prod": 0.0, "sum_cells": 0, "sum_in_pct": 0.0,
                "sum_lipid_positive_cells": 0, "sum_lipid_positive_cell_ratio": 0.0,
                "sum_necrosis_positive_cells": 0, "sum_necrosis_positive_cell_ratio": 0.0,
                "cell_counts": [], "cell_area_means": [], "lipid_occupancies": [],
                "total_production_ratios": [], "intracellular_lipid_percents": [],
                "lipid_positive_cells": [], "lipid_positive_cell_ratios": [],
                "necrosis_positive_cells": [], "necrosis_positive_cell_ratios": []
            }

            row = self.analyze_single_image(
                0, 1, bf_name, bf_suffix, bf_suffix_lower, fl_suffix, pi_suffix,
                run_cell, run_lipid, run_necrosis, preview_dir, prefix_map, dummy_totals
            )

            if row is not None:
                self.update_log("プレビュー画像の生成が完了しました。画像を開きます。")

                target_key = "cell"
                if run_necrosis:
                    if preview_type == "clean":
                        target_key = "necrosis_clean"
                    elif preview_type == "mask":
                        target_key = "necrosis"
                    else:
                        target_key = "combined_necrosis"
                elif run_lipid:
                    if preview_type == "clean":
                        target_key = "lipid_clean"
                    elif preview_type == "mask":
                        target_key = "lipid"
                    else:
                        target_key = "combined"

                filepath = os.path.join(preview_dir, f"{prefix_map.get(target_key, '')}{target_key}_{bf_name}")
                if os.path.exists(filepath):
                    self.open_file_in_os(filepath)
                else:
                    self.update_log(f"指定されたプレビュー画像が見つかりません: {filepath}")

        except Exception as e:
            self.update_status(f"エラー: {e}", enable_start_button=True)
            self.show_error("エラー", str(e))
        finally:
            self.update_status(progress=1.0, enable_start_button=True)

    def open_file_in_os(self, filepath):
        """OSの標準アプリケーションでファイルを開く"""
        try:
            if platform.system() == 'Windows':
                os.startfile(filepath)
            elif platform.system() == 'Darwin':
                subprocess.call(('open', filepath))
            else:
                subprocess.call(('xdg-open', filepath))
        except Exception as e:
            self.update_log(f"プレビュー画像の表示に失敗しました: {e}")

    def prepare_analysis_context(self):
        self.update_log(f"設定ファイルを読み込み中: {self.config_data.config_dir}")
        if not self.config_data.load_config():
            self.update_log("警告: 設定CSVの読み込みに失敗したため、前回またはデフォルト設定を使用します。")

        self.prepare_analyzer()

        run_cell = self.run_cell_var.get()
        run_lipid = self.run_lipid_var.get()
        run_necrosis = self.run_necrosis_var.get()
        bf_suffix = str(self.config_data.get("bf_suffix", "")).strip()
        fl_suffix = str(self.config_data.get("fl_suffix", "")).strip()
        pi_suffix = str(self.config_data.get("pi_suffix", "")).strip()

        return run_cell, run_lipid, run_necrosis, bf_suffix, fl_suffix, pi_suffix

    def collect_image_files(self, bf_suffix):
        image_extensions = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
        files = [
            file_name for file_name in os.listdir(self.target_path)
            if file_name.lower().endswith(image_extensions)
        ]

        bf_suffix_lower = bf_suffix.lower()
        bf_files = sorted([file_name for file_name in files if bf_suffix_lower in file_name.lower()])

        return files, bf_files, bf_suffix_lower

    def handle_no_bf_images(self, files, bf_suffix):
        sample_file_names = files[:10]
        if sample_file_names:
            sample_files = "\n".join(f"      - {file_name}" for file_name in sample_file_names)
            highlight_files = sample_file_names
        else:
            sample_files = "      画像ファイル自体が見つかりません。"
            highlight_files = None

        self.update_status(
            "エラー: 画像が見つかりません。\n"
            f"   対象フォルダ: {self.target_path}\n"
            f"   BF識別子: {bf_suffix}\n"
            f"   検出した画像数: {len(files)}\n"
            f"   画像ファイル例:\n{sample_files}",
            1.0,
            highlight_text=highlight_files,
            enable_start_button=True
        )

    def create_output_directory(self, memo):
        """出力フォルダの作成。メモが入力されていればフォルダ名に付与する"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        if memo:
            # フォルダ名に使えない文字をアンダースコアに置換
            memo_clean = re.sub(r'[\\/:*?"<>|]+', '_', memo)
            folder_name = f"result_{memo_clean}_{timestamp}"
        else:
            folder_name = f"result_{timestamp}"

        output_dir = os.path.join(self.target_path, folder_name)
        os.makedirs(output_dir, exist_ok=True)

        # 設定ファイルを全てコピーする
        config_files = ["config_common.csv", "config_cell.csv", "config_lipid.csv", "config_necrosis.csv"]
        for f_name in config_files:
            src = os.path.join(self.config_data.config_dir, f_name)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(output_dir, f"used_{f_name}"))

        return output_dir

    def build_start_log(self, total_files, run_lipid, run_necrosis):
        start_log_lines = [
            f"【解析開始: {total_files} セット】"
        ]

        if run_lipid:
            start_log_lines.extend([
                "=" * 70,
                "定義確認:",
                " 1. 油脂占有率 (蓄積度)   = 細胞内の油脂面積 / 細胞の総面積",
                " 2. 油脂生産率 (効率)     = 全油脂面積 / 細胞の総面積",
                " 3. 細胞内油脂割合 (分布) = (細胞内の油脂面積 / 全油脂面積) × 100",
                " 4. 油脂保有細胞割合     = 油脂を含む細胞数 / 全体の細胞数",
                "=" * 70
            ])
        elif run_necrosis:
            start_log_lines.extend([
                "=" * 70,
                "定義確認:",
                " 1. 壊死細胞割合 = 壊死細胞数 / 全体の細胞数",
                "=" * 70
            ])

        return "\n".join(start_log_lines)

    def read_image(self, file_name):
        image_path = os.path.join(self.target_path, file_name)
        return cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

    def save_visuals(self, visuals, output_dir, bf_name, prefix_map):
        for key, image in visuals.items():
            output_path = os.path.join(output_dir, f"{prefix_map.get(key, '')}{key}_{bf_name}")
            ext = os.path.splitext(output_path)[1]
            success, encoded = cv2.imencode(ext, image)

            if success:
                encoded.tofile(output_path)
            else:
                self.update_log(
                    f"警告: 結果画像の保存に失敗しました: {output_path}",
                    highlight_text=bf_name
                )

    def build_result_row_and_log(self, bf_name, index, total_files, stats, run_cell, run_lipid, run_necrosis, totals):
        row = {"ファイル名": bf_name}
        log_lines = [f"[{index + 1}/{total_files}] {bf_name}"]

        cells = stats.get("cell_count", 0) if run_cell else 0

        if run_cell:
            area = stats.get("total_cell_px", 0)

            log_lines.append(f"   >>> 細胞数   : {cells} 個")
            log_lines.append(f"   >>> 細胞面積 : {area} px")

            row.update({
                "細胞数": cells,
                "細胞面積(px)": area
            })

            totals["sum_cells"] += cells
            totals["cell_counts"].append(cells)

            if cells > 0:
                totals["cell_area_means"].append(area / cells)
            else:
                log_lines.append("   ⚠ 細胞数が0のため、本画像の平均・比率データは全体統計の計算から除外されます。")

        if run_lipid:
            occ = stats.get("lipid_cell_ratio", 0.0)
            prod = stats.get("total_production_ratio", 0.0)
            in_pct = stats.get("intracellular_lipid_percent", 0.0)
            lipid_positive_cell_count = stats.get("lipid_positive_cell_count", 0)
            lipid_positive_cell_ratio = stats.get("lipid_positive_cell_ratio", 0.0)

            log_lines.append(f"   >>> 油脂占有率       : {occ:.4f}")
            log_lines.append(f"   >>> 総生産率         : {prod:.4f}")
            log_lines.append(f"   >>> 細胞内油脂割合   : {in_pct * 100:.1f}%")
            log_lines.append(f"   >>> 油脂保有細胞数   : {lipid_positive_cell_count} 個")
            log_lines.append(f"   >>> 油脂保有細胞割合 : {lipid_positive_cell_ratio * 100:.1f}%")

            row.update({
                "油脂占有率": occ,
                "総生産率": prod,
                "細胞内油脂割合(%)": in_pct * 100,
                "油脂保有細胞数": lipid_positive_cell_count,
                "油脂保有細胞割合(%)": lipid_positive_cell_ratio * 100
            })

            totals["sum_occ"] += occ
            totals["sum_prod"] += prod
            totals["sum_in_pct"] += in_pct
            totals["sum_lipid_positive_cells"] += lipid_positive_cell_count
            totals["sum_lipid_positive_cell_ratio"] += lipid_positive_cell_ratio

            totals["lipid_positive_cells"].append(lipid_positive_cell_count)
            if cells > 0:
                totals["lipid_occupancies"].append(occ)
                totals["total_production_ratios"].append(prod)
                totals["lipid_positive_cell_ratios"].append(lipid_positive_cell_ratio)
            if stats.get("total_lipid_px", 0) > 0:
                totals["intracellular_lipid_percents"].append(in_pct)

        if run_necrosis:
            necrosis_positive_cell_count = stats.get("necrosis_positive_cell_count", 0)
            necrosis_positive_cell_ratio = stats.get("necrosis_positive_cell_ratio", 0.0)

            log_lines.append(f"   >>> 壊死細胞数       : {necrosis_positive_cell_count} 個")
            log_lines.append(f"   >>> 壊死細胞割合     : {necrosis_positive_cell_ratio * 100:.1f}%")

            row.update({
                "壊死細胞数": necrosis_positive_cell_count,
                "壊死細胞割合(%)": necrosis_positive_cell_ratio * 100
            })

            totals["sum_necrosis_positive_cells"] += necrosis_positive_cell_count
            totals["sum_necrosis_positive_cell_ratio"] += necrosis_positive_cell_ratio

            totals["necrosis_positive_cells"].append(necrosis_positive_cell_count)
            if cells > 0:
                totals["necrosis_positive_cell_ratios"].append(necrosis_positive_cell_ratio)

        return row, "\n".join(log_lines)

    def analyze_single_image(
            self,
            index,
            total_files,
            bf_name,
            bf_suffix,
            bf_suffix_lower,
            fl_suffix,
            pi_suffix,
            run_cell,
            run_lipid,
            run_necrosis,
            output_dir,
            prefix_map,
            totals
    ):
        progress_value = (index + 1) / total_files

        stem, ext = os.path.splitext(bf_name)
        if not stem.lower().endswith(bf_suffix_lower):
            self.update_status(
                f"スキップ: BF識別子が末尾にありません: {bf_name}",
                progress_value,
                highlight_text=bf_name
            )
            return None

        img_bf = self.read_image(bf_name)
        img_fl = None
        img_pi = None
        fl_name = None
        pi_name = None

        if run_lipid:
            fl_name = f"{stem[:-len(bf_suffix)]}{fl_suffix}{ext}"
            fl_path = os.path.join(self.target_path, fl_name)
            if os.path.exists(fl_path):
                img_fl = self.read_image(fl_name)

        if run_necrosis:
            pi_name = f"{stem[:-len(bf_suffix)]}{pi_suffix}{ext}"
            pi_path = os.path.join(self.target_path, pi_name)
            if os.path.exists(pi_path):
                img_pi = self.read_image(pi_name)

        if img_bf is None:
            self.update_status(
                f"警告: BF画像の読み込みに失敗しました。スキップします: {bf_name}",
                progress_value,
                highlight_text=bf_name
            )
            return None

        if run_lipid and img_fl is None:
            self.update_status(
                f"警告: 対応する蛍光画像が見つかりません。スキップします: {fl_name}",
                progress_value,
                highlight_text=fl_name if fl_name else ""
            )
            return None

        if run_necrosis and img_pi is None:
            self.update_status(
                f"警告: 対応するPI蛍光画像が見つかりません。スキップします: {pi_name}",
                progress_value,
                highlight_text=pi_name if pi_name else ""
            )
            return None

        try:
            stats, visuals = self.analyzer.analyze(
                bf_image=img_bf,
                fl_image=img_fl,
                pi_image=img_pi,
                run_cell=run_cell,
                run_lipid=run_lipid,
                run_necrosis=run_necrosis,
                progress_callback=None
            )
        except Exception as e:
            self.update_status(
                f"警告: 解析に失敗しました。スキップします: {bf_name}\n   理由: {e}",
                progress_value,
                highlight_text=bf_name
            )
            return None

        row, log_message = self.build_result_row_and_log(
            bf_name,
            index,
            total_files,
            stats,
            run_cell,
            run_lipid,
            run_necrosis,
            totals
        )

        self.update_status(
            log_message,
            progress_value,
            highlight_text=bf_name
        )

        self.save_visuals(visuals, output_dir, bf_name, prefix_map)

        return row

    def write_summary(self, summary_rows, totals, processed_count, run_cell, run_lipid, run_necrosis, output_dir):
        if processed_count <= 0:
            self.update_status(
                "処理対象の画像がありませんでした。",
                1.0,
                enable_start_button=True
            )
            return

        summary_log_lines = [
            "",
            "-" * 40,
            "【 全画像 統計サマリー 】"
        ]

        summary_stat_row = {"ファイル名": "--- 全体統計平均 ---"}

        if run_cell:
            avg_cells = float(np.mean(totals["cell_counts"])) if totals["cell_counts"] else 0.0
            sd_cells = float(np.std(totals["cell_counts"], ddof=1)) if len(totals["cell_counts"]) > 1 else 0.0
            avg_cell_area = float(np.mean(totals["cell_area_means"])) if totals["cell_area_means"] else 0.0
            sd_cell_area = float(np.std(totals["cell_area_means"], ddof=1)) if len(totals["cell_area_means"]) > 1 else 0.0

            summary_log_lines.append(f"   [平均]     細胞数 : {avg_cells:.1f} 個")
            summary_log_lines.append(f"   [標準偏差] 細胞数 : {sd_cells:.2f}")
            summary_log_lines.append(f"   [平均]     細胞平均面積 : {avg_cell_area:.2f} px")
            summary_log_lines.append(f"   [標準偏差] 細胞平均面積 : {sd_cell_area:.2f}")

            summary_stat_row.update({
                "細胞数": avg_cells,
                "細胞数標準偏差": sd_cells,
                "細胞平均面積(px)": avg_cell_area,
                "細胞平均面積標準偏差": sd_cell_area
            })

        if run_lipid:
            avg_occ = float(np.mean(totals["lipid_occupancies"])) if totals["lipid_occupancies"] else 0.0
            sd_occ = float(np.std(totals["lipid_occupancies"], ddof=1)) if len(totals["lipid_occupancies"]) > 1 else 0.0
            avg_prod = float(np.mean(totals["total_production_ratios"])) if totals["total_production_ratios"] else 0.0
            avg_dist = float(np.mean(totals["intracellular_lipid_percents"])) * 100 if totals["intracellular_lipid_percents"] else 0.0
            avg_lipid_positive_cell_count = float(np.mean(totals["lipid_positive_cells"])) if totals["lipid_positive_cells"] else 0.0
            avg_lipid_positive_cell_ratio = float(np.mean(totals["lipid_positive_cell_ratios"])) * 100 if totals["lipid_positive_cell_ratios"] else 0.0
            sd_lipid_positive_cell_ratio = (
                float(np.std(totals["lipid_positive_cell_ratios"], ddof=1)) * 100
                if len(totals["lipid_positive_cell_ratios"]) > 1 else 0.0
            )

            summary_log_lines.append(f"   [平均]     油脂占有率 : {avg_occ:.4f}")
            summary_log_lines.append(f"   [標準偏差] 油脂占有率 : {sd_occ:.4f}")
            summary_log_lines.append(f"   [平均] 総生産率       : {avg_prod:.4f}")
            summary_log_lines.append(f"   [平均] 細胞内油脂割合 : {avg_dist:.1f}%")
            summary_log_lines.append(f"   [平均] 油脂保有細胞数 : {avg_lipid_positive_cell_count:.1f} 個")
            summary_log_lines.append(f"   [平均] 油脂保有細胞割合 : {avg_lipid_positive_cell_ratio:.1f}%")
            summary_log_lines.append(f"   [標準偏差] 油脂保有細胞割合 : {sd_lipid_positive_cell_ratio:.2f}")

            summary_stat_row.update({
                "油脂占有率": avg_occ,
                "油脂占有率標準偏差": sd_occ,
                "総生産率": avg_prod,
                "細胞内油脂割合(%)": avg_dist,
                "油脂保有細胞数": avg_lipid_positive_cell_count,
                "油脂保有細胞割合(%)": avg_lipid_positive_cell_ratio,
                "油脂保有細胞割合標準偏差": sd_lipid_positive_cell_ratio
            })

        if run_necrosis:
            avg_necrosis_positive_cell_count = float(np.mean(totals["necrosis_positive_cells"])) if totals["necrosis_positive_cells"] else 0.0
            avg_necrosis_positive_cell_ratio = float(np.mean(totals["necrosis_positive_cell_ratios"])) * 100 if totals["necrosis_positive_cell_ratios"] else 0.0
            sd_necrosis_positive_cell_ratio = (
                float(np.std(totals["necrosis_positive_cell_ratios"], ddof=1)) * 100
                if len(totals["necrosis_positive_cell_ratios"]) > 1 else 0.0
            )

            summary_log_lines.append(f"   [平均] 壊死細胞数 : {avg_necrosis_positive_cell_count:.1f} 個")
            summary_log_lines.append(f"   [平均] 壊死細胞割合 : {avg_necrosis_positive_cell_ratio:.1f}%")
            summary_log_lines.append(f"   [標準偏差] 壊死細胞割合 : {sd_necrosis_positive_cell_ratio:.2f}")

            summary_stat_row.update({
                "壊死細胞数": avg_necrosis_positive_cell_count,
                "壊死細胞割合(%)": avg_necrosis_positive_cell_ratio,
                "壊死細胞割合標準偏差": sd_necrosis_positive_cell_ratio
            })

        summary_log_lines.append("-" * 40)
        summary_log_lines.append(f"解析結果保存先: {output_dir}")

        summary_rows.append(summary_stat_row)

        pd.DataFrame(summary_rows).to_csv(
            os.path.join(output_dir, "analysis_summary.csv"),
            index=False,
            encoding="utf-8-sig"
        )

        self.update_status(
            "\n".join(summary_log_lines),
            1.0,
            highlight_text=output_dir,
            enable_start_button=True
        )

    def run_analysis(self, run_cell, run_lipid, run_necrosis, memo_text):
        try:
            self.update_log(f"設定ファイルを読み込み中: {self.config_data.config_dir}")
            if not self.config_data.load_config():
                self.update_log("警告: 設定CSVの読み込みに失敗したため、前回またはデフォルト設定を使用します。")

            self.prepare_analyzer()

            # 解析開始直後に、必要なモデルが未ロードであればGUIログで進捗を表示しながらロードを実行する
            # analyzer._get_...model() 内の self._info() を通じてGUIに開始・完了ログが流れます
            if run_cell:
                self.analyzer._get_cell_model()

            if run_lipid:
                self.analyzer._get_lipid_model()

            if run_necrosis:
                self.analyzer._get_necrosis_model()

            bf_suffix = str(self.config_data.get("bf_suffix", "")).strip()
            fl_suffix = str(self.config_data.get("fl_suffix", "")).strip()
            pi_suffix = str(self.config_data.get("pi_suffix", "")).strip()

            files, bf_files, bf_suffix_lower = self.collect_image_files(bf_suffix)

            if not bf_files:
                self.handle_no_bf_images(files, bf_suffix)
                return

            output_dir = self.create_output_directory(memo_text)
            total_files = len(bf_files)

            prefix_map = {
                "cell": "01_",
                "lipid_clean": "00_clean_",
                "lipid": "02_",
                "combined": "03_",
                "necrosis_clean": "00_clean_",
                "necrosis": "02_",
                "combined_necrosis": "03_"
            }

            summary_rows = []
            totals = {
                "sum_occ": 0.0,
                "sum_prod": 0.0,
                "sum_cells": 0,
                "sum_in_pct": 0.0,
                "sum_lipid_positive_cells": 0,
                "sum_lipid_positive_cell_ratio": 0.0,
                "sum_necrosis_positive_cells": 0,
                "sum_necrosis_positive_cell_ratio": 0.0,
                "cell_counts": [],
                "cell_area_means": [],
                "lipid_occupancies": [],
                "total_production_ratios": [],
                "intracellular_lipid_percents": [],
                "lipid_positive_cells": [],
                "lipid_positive_cell_ratios": [],
                "necrosis_positive_cells": [],
                "necrosis_positive_cell_ratios": []
            }
            processed_count = 0

            self.update_log(self.build_start_log(total_files, run_lipid, run_necrosis))

            for index, bf_name in enumerate(bf_files):
                if self.cancel_requested:
                    self.update_log("⚠ ユーザー操作により解析が中止されました。")
                    break

                row = self.analyze_single_image(
                    index,
                    total_files,
                    bf_name,
                    bf_suffix,
                    bf_suffix_lower,
                    fl_suffix,
                    pi_suffix,
                    run_cell,
                    run_lipid,
                    run_necrosis,
                    output_dir,
                    prefix_map,
                    totals
                )

                if row is None:
                    continue

                summary_rows.append(row)
                processed_count += 1

            self.write_summary(
                summary_rows,
                totals,
                processed_count,
                run_cell,
                run_lipid,
                run_necrosis,
                output_dir
            )

        except Exception as e:
            self.update_status(
                f"エラー: {e}",
                enable_start_button=True
            )
            self.show_error("エラー", str(e))

    def get_analyzer_signature(self):
        return (
            self._normalize_path_signature(self.config_data.get("cell_model_path")),
            self._normalize_path_signature(self.config_data.get("lipid_model_path")),
            self._normalize_path_signature(self.config_data.get("necrosis_model_path")),
            self.config_data.get("use_gpu"),
        )

    def prepare_analyzer(self):
        from app.core.analyzer import YeastAnalyzer

        signature = self.get_analyzer_signature()

        if self.analyzer is None or self.analyzer_signature != signature:
            self.update_log_sync("解析エンジンの準備を完了しました。（解析開始時に必要なモデルを自動ロードします）")
            try:
                # ログ・コールバック（update_log）を渡してインスタンス化
                analyzer = YeastAnalyzer(self.config_data, log_callback=self.update_log)
            except Exception as e:
                raise RuntimeError(f"解析エンジンのセットアップに失敗しました: {e}") from e

            self.analyzer = analyzer
            self.analyzer_signature = signature
        else:
            self.analyzer.cfg = self.config_data

    @staticmethod
    def _normalize_path_signature(path):
        if not path:
            return ""
        return os.path.abspath(os.path.normpath(str(path)))
