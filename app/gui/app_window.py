import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import datetime
import cv2
import pandas as pd
import numpy as np
import shutil

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

        self.title("酵母・油脂 画像解析システム")
        self.geometry("900x700")

        # Configure grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Sidebar frame
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="操作パネル", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.select_button = ctk.CTkButton(self.sidebar_frame, text="画像フォルダを選択", command=self.select_folder)
        self.select_button.grid(row=1, column=0, padx=20, pady=10)

        # チェックボックス連動ロジック
        self.run_cell_var = ctk.BooleanVar(value=True)
        self.cell_check = ctk.CTkCheckBox(self.sidebar_frame, text="細胞解析 (BF)",
                                          variable=self.run_cell_var, command=self.on_cell_check_changed)
        self.cell_check.grid(row=2, column=0, padx=20, pady=10, sticky="w")

        self.run_lipid_var = ctk.BooleanVar(value=True)
        self.lipid_check = ctk.CTkCheckBox(self.sidebar_frame, text="油脂解析 (FL)",
                                           variable=self.run_lipid_var, command=self.on_lipid_check_changed)
        self.lipid_check.grid(row=3, column=0, padx=20, pady=10, sticky="w")

        self.start_button = ctk.CTkButton(self.sidebar_frame, text="解析開始", command=self.start_analysis_thread,
                                          fg_color="green", hover_color="darkgreen")
        self.start_button.grid(row=4, column=0, padx=20, pady=20)

        # ログエリア
        self.log_text = ctk.CTkTextbox(
            self,
            width=600,
            # Mac, Windows 両方の等幅フォントを網羅
            font=ctk.CTkFont(family="MS Gothic", size=12)
        )
        self.log_text.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")
        self.log_text.tag_config("filename", foreground="#4DA3FF")
        self.log_text.tag_config("summary_title", foreground="#FFD166")

        # 進捗バー
        self.progressbar = ctk.CTkProgressBar(self)
        self.progressbar.grid(row=2, column=1, padx=20, pady=(0, 20), sticky="ew")
        self.progressbar.set(0)

    def on_cell_check_changed(self):
        if not self.run_cell_var.get():
            self.run_lipid_var.set(False)

    def on_lipid_check_changed(self):
        if self.run_lipid_var.get():
            self.run_cell_var.set(True)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.target_path = path
            self.update_log(f"解析フォルダ設定完了: {path}")

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

        self.log_text.see("end")

    def update_status(self, message=None, progress=None, highlight_text=None, enable_start_button=None):
        self.after(0, self._update_status, message, progress, highlight_text, enable_start_button)

    def _update_status(self, message=None, progress=None, highlight_text=None, enable_start_button=None):
        if message is not None:
            self._append_log(message, highlight_text)

        if progress is not None:
            self.progressbar.set(progress)

        if enable_start_button is not None:
            self.is_running = not enable_start_button
            state = "normal" if enable_start_button else "disabled"
            color = "green" if enable_start_button else "gray"
            self.start_button.configure(state=state, fg_color=color)

    def set_start_button_enabled_now(self, enabled):
        state = "normal" if enabled else "disabled"
        color = "green" if enabled else "gray"
        self.start_button.configure(state=state, fg_color=color)

    def show_error(self, title, message):
        self.after(0, messagebox.showerror, title, message)

    def start_analysis_thread(self):
        if self.is_running:
            return

        if not self.target_path or not os.path.exists(self.target_path):
            self.select_folder()
            if not self.target_path:
                return

        self.is_running = True
        self.set_start_button_enabled_now(False)

        threading.Thread(target=self.run_analysis, daemon=True).start()

    def run_analysis(self):
        """解析ループ：各画像の比率算出と、統計情報の出力を行う"""
        try:
            self.update_log(f"設定ファイルを読み込み中: {self.config_data.config_path}")
            if not self.config_data.load_config():
                self.update_log("警告: 設定CSVの読み込みに失敗したため、前回またはデフォルト設定を使用します。")
            self.prepare_analyzer()

            run_cell = self.run_cell_var.get()
            run_lipid = self.run_lipid_var.get()

            bf_sfx = str(self.config_data.get("bf_suffix", "")).strip()
            fl_sfx = str(self.config_data.get("fl_suffix", "")).strip()

            files = [
                f for f in os.listdir(self.target_path)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff"))
            ]

            bf_sfx_lower = bf_sfx.lower()
            bf_files = sorted([f for f in files if bf_sfx_lower in f.lower()])

            if not bf_files:
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
                    f"   BF識別子: {bf_sfx}\n"
                    f"   検出した画像数: {len(files)}\n"
                    f"   画像ファイル例:\n{sample_files}",
                    1.0,
                    highlight_text=highlight_files,
                    enable_start_button=True
                )
                return

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(self.target_path, f"result_{timestamp}")
            os.makedirs(output_dir, exist_ok=True)
            shutil.copy(self.config_data.config_path, os.path.join(output_dir, "used_settings.csv"))

            summary_rows = []
            cell_counts = []  # 細胞数標準偏差算出用
            lipid_occupancies = []  # 油脂占有率標準偏差算出用

            sum_occ, sum_prod, sum_cells, sum_in_pct = 0.0, 0.0, 0, 0.0
            processed_count = 0
            total_files = len(bf_files)
            prefix_map = {"cell": "01_", "lipid": "02_", "combined": "03_"}

            start_log_lines = [
                f"【解析開始: {total_files} セット】"
            ]
            if run_lipid:
                start_log_lines.extend([
                    "=" * 55,
                    "定義確認:",
                    " 1. 油脂占有率 (蓄積度)   = 細胞内の油脂面積 / 細胞の総面積",
                    " 2. 油脂生産率 (効率)     = 全油脂面積 / 細胞の総面積",
                    " 3. 細胞内油脂割合 (分布) = (細胞内の油脂面積 / 全油脂面積) × 100",
                    "=" * 55
                ])

            self.update_log("\n".join(start_log_lines))

            for i, bf_name in enumerate(bf_files):
                progress_value = (i + 1) / total_files

                stem, ext = os.path.splitext(bf_name)
                if stem.lower().endswith(bf_sfx_lower):
                    fl_name = f"{stem[:-len(bf_sfx)]}{fl_sfx}{ext}"
                else:
                    self.update_status(
                        f"スキップ: BF識別子が末尾にありません: {bf_name}",
                        progress_value,
                        highlight_text=bf_name
                    )
                    continue

                img_bf = cv2.imdecode(np.fromfile(os.path.join(self.target_path, bf_name), dtype=np.uint8),
                                      cv2.IMREAD_UNCHANGED)
                img_fl = None
                if run_lipid:
                    fl_p = os.path.join(self.target_path, fl_name)
                    if os.path.exists(fl_p):
                        img_fl = cv2.imdecode(np.fromfile(fl_p, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

                if img_bf is None:
                    self.update_status(
                        f"警告: BF画像の読み込みに失敗しました。スキップします: {bf_name}",
                        progress_value,
                        highlight_text=bf_name
                    )
                    continue

                if run_lipid and img_fl is None:
                    self.update_status(
                        f"警告: 対応する蛍光画像が見つかりません。スキップします: {fl_name}",
                        progress_value,
                        highlight_text=fl_name
                    )
                    continue

                try:
                    stats, visuals = self.analyzer.analyze(
                        img_bf,
                        img_fl,
                        run_cell=run_cell,
                        run_lipid=run_lipid,
                        progress_callback=None
                    )
                except Exception as e:
                    self.update_status(
                        f"警告: 解析に失敗しました。スキップします: {bf_name}\n   理由: {e}",
                        progress_value,
                        highlight_text=bf_name
                    )
                    continue

                    # 個別ログ出力とCSV行作成
                row = {"ファイル名": bf_name}
                log_lines = [f"[{i + 1}/{total_files}] {bf_name}"]

                if run_cell:
                    cells = stats.get("cell_count", 0)
                    area = stats.get("total_cell_px", 0)
                    log_lines.append(f"   >>> 細胞数   : {cells} 個")
                    log_lines.append(f"   >>> 細胞面積 : {area} px")
                    row.update({"細胞数": cells, "細胞面積(px)": area})
                    sum_cells += cells
                    cell_counts.append(cells)

                if run_lipid:
                    occ = stats.get("lipid_cell_ratio", 0.0)
                    prod = stats.get("total_production_ratio", 0.0)
                    in_pct = stats.get("intracellular_lipid_percent", 0.0)
                    log_lines.append(f"   >>> 油脂占有率     : {occ:.4f}")
                    log_lines.append(f"   >>> 総生産率       : {prod:.4f}")
                    log_lines.append(f"   >>> 細胞内油脂割合 : {in_pct * 100:.1f}%")
                    row.update({"油脂占有率": occ, "総生産率": prod, "細胞内油脂割合(%)": in_pct * 100})
                    sum_occ += occ
                    sum_prod += prod
                    sum_in_pct += in_pct
                    lipid_occupancies.append(occ)

                self.update_status(
                    "\n".join(log_lines),
                    progress_value,
                    highlight_text=bf_name
                )

                for key, img_o in visuals.items():
                    output_path = os.path.join(output_dir, f"{prefix_map.get(key, '')}{key}_{bf_name}")
                    ext = os.path.splitext(output_path)[1]
                    success, encoded = cv2.imencode(ext, img_o)
                    if success:
                        encoded.tofile(output_path)
                    else:
                        self.update_log(
                            f"警告: 結果画像の保存に失敗しました: {output_path}",
                            highlight_text=bf_name
                        )

                summary_rows.append(row)
                processed_count += 1

            # 全体統計の出力
            if processed_count > 0:
                summary_log_lines = [
                    "",
                    "-" * 40,
                    "【 全画像 統計サマリー 】"
                ]

                summary_stat_row = {"ファイル名": "--- 全体統計平均 ---"}

                if run_cell:
                    avg_cells = sum_cells / processed_count
                    sd_cells = float(np.std(cell_counts, ddof=1)) if len(cell_counts) > 1 else 0.0
                    summary_log_lines.append(f"   [平均]     細胞数 : {avg_cells:.1f} 個")
                    summary_log_lines.append(f"   [標準偏差] 細胞数 : {sd_cells:.2f}")
                    summary_stat_row.update({
                        "細胞数": avg_cells,
                        "細胞数標準偏差": sd_cells
                    })

                if run_lipid:
                    avg_occ = sum_occ / processed_count
                    avg_prod = sum_prod / processed_count
                    avg_dist = (sum_in_pct / processed_count) * 100
                    sd_occ = float(np.std(lipid_occupancies, ddof=1)) if len(lipid_occupancies) > 1 else 0.0

                    summary_log_lines.append(f"   [平均]     油脂占有率 : {avg_occ:.4f}")
                    summary_log_lines.append(f"   [標準偏差] 油脂占有率 : {sd_occ:.4f}")
                    summary_log_lines.append(f"   [平均] 総生産率       : {avg_prod:.4f}")
                    summary_log_lines.append(f"   [平均] 細胞内油脂割合 : {avg_dist:.1f}%")

                    summary_stat_row.update({
                        "油脂占有率": avg_occ,
                        "油脂占有率標準偏差": sd_occ,
                        "総生産率": avg_prod,
                        "細胞内油脂割合(%)": avg_dist
                    })

                summary_log_lines.append("-" * 40)
                summary_log_lines.append(f"解析結果保存先: {output_dir}")

                summary_rows.append(summary_stat_row)

                pd.DataFrame(summary_rows).to_csv(
                    os.path.join(output_dir, "analysis_summary.csv"),
                    index=False,
                    encoding='utf-8-sig'
                )

                self.update_status(
                    "\n".join(summary_log_lines),
                    1.0,
                    highlight_text=output_dir,
                    enable_start_button=True
                )
            else:
                self.update_status(
                    "処理対象の画像がありませんでした。",
                    1.0,
                    enable_start_button=True
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
            self.config_data.get("use_gpu"),
        )

    def prepare_analyzer(self):
        from app.core.analyzer import YeastAnalyzer

        signature = self.get_analyzer_signature()

        if self.analyzer is None or self.analyzer_signature != signature:
            self.update_log_sync("解析モデルを初期化しています。")
            try:
                analyzer = YeastAnalyzer(self.config_data)
            except Exception as e:
                raise RuntimeError(f"解析モデルの初期化に失敗しました: {e}") from e

            self.analyzer = analyzer
            self.analyzer_signature = signature
            self.update_log("解析モデルの初期化が完了しました。")
        else:
            self.update_log("既存の解析モデルを再利用します。")
            self.analyzer.cfg = self.config_data

    @staticmethod
    def _normalize_path_signature(path):
        if not path:
            return ""
        return os.path.abspath(os.path.normpath(str(path)))
