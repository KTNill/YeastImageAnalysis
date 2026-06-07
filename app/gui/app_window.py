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
import queue
from app.core.analyzer import YeastAnalyzer, LogCategory

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    """
    最終安定版GUI。
    エラーの原因となるtag_configのfont指定を排除し、配色とリアルタイム描画を最適化。
    """

    IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")

    def __init__(self):
        super().__init__()
        self.analyzer = None
        self.config_data = None
        self.target_path = ""
        self.is_running = False
        self.cancel_requested = False
        self.msg_queue = queue.Queue()

        self.title("酵母・油脂 画像解析システム (Refactored)")
        self.geometry("1100x750")

        # サイドバー幅を320pxに固定して見切れを防止
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._setup_sidebar()
        self._setup_main_area()
        self.after(100, self.process_msg_queue)

    def _setup_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=320, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="操作パネル", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # 現在の状況を示すステータステキスト
        self.status_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="< 待機中 >",
            font=ctk.CTkFont(family="MS Gothic", size=16, weight="bold"),
            text_color="#757575"
        )
        self.status_label.grid(row=1, column=0, padx=20, pady=(0, 15))

        self.select_button = ctk.CTkButton(self.sidebar_frame, text="画像フォルダを選択", command=self.select_folder)
        self.select_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.memo_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="実験メモ (フォルダ名用)")
        self.memo_entry.grid(row=3, column=0, padx=20, pady=(5, 10), sticky="ew")

        self.run_cell_var = ctk.BooleanVar(value=True)
        self.cell_check = ctk.CTkCheckBox(self.sidebar_frame, text="細胞解析 (BF)", variable=self.run_cell_var, command=self.on_cell_check_changed)
        self.cell_check.grid(row=4, column=0, padx=30, pady=8, sticky="w")

        self.run_lipid_var = ctk.BooleanVar(value=True)
        self.lipid_check = ctk.CTkCheckBox(self.sidebar_frame, text="油脂解析 (FL)", variable=self.run_lipid_var, command=self.on_lipid_check_changed)
        self.lipid_check.grid(row=5, column=0, padx=30, pady=8, sticky="w")

        self.run_necrosis_var = ctk.BooleanVar(value=False)
        self.necrosis_check = ctk.CTkCheckBox(self.sidebar_frame, text="壊死解析 (PI)", variable=self.run_necrosis_var, command=self.on_necrosis_check_changed)
        self.necrosis_check.grid(row=6, column=0, padx=30, pady=8, sticky="w")

        self.preview_frame = ctk.CTkFrame(self.sidebar_frame)
        self.preview_frame.grid(row=7, column=0, padx=20, pady=10, sticky="ew")
        self.preview_label = ctk.CTkLabel(self.preview_frame, text="プレビュー表示対象:", font=ctk.CTkFont(size=13, weight="bold"))
        self.preview_label.pack(padx=10, pady=(5, 2), anchor="w")

        self.preview_target_var = ctk.StringVar(value="combined")
        self.radio_clean = ctk.CTkRadioButton(self.preview_frame, text="前処理後画像", variable=self.preview_target_var, value="clean")
        self.radio_clean.pack(padx=15, pady=4, anchor="w")
        self.radio_mask = ctk.CTkRadioButton(self.preview_frame, text="マスク画像", variable=self.preview_target_var, value="mask")
        self.radio_mask.pack(padx=15, pady=4, anchor="w")
        self.radio_combined = ctk.CTkRadioButton(self.preview_frame, text="マージ画像", variable=self.preview_target_var, value="combined")
        self.radio_combined.pack(padx=15, pady=(4, 10), anchor="w")

        self.preview_button = ctk.CTkButton(self.sidebar_frame, text="1枚テストプレビュー", command=self.run_preview_thread)
        self.preview_button.grid(row=8, column=0, padx=20, pady=(15, 10), sticky="ew")

        self.start_button = ctk.CTkButton(self.sidebar_frame, text="解析開始", command=self.toggle_analysis, fg_color="green", hover_color="darkgreen")
        self.start_button.grid(row=9, column=0, padx=20, pady=(0, 20), sticky="ew")

        self.input_widgets = [
            self.select_button, self.memo_entry,
            self.cell_check, self.lipid_check, self.necrosis_check,
            self.preview_button, self.radio_clean, self.radio_mask, self.radio_combined
        ]
        self.update_radio_state()

    def _setup_main_area(self):
        self.log_text = ctk.CTkTextbox(self, width=600, font=ctk.CTkFont(family="MS Gothic", size=13))
        self.log_text.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")
        self.log_text.tag_config("log_line_spacing", spacing3=5)

        # 配色設計 (fontオプションを排除)
        self.log_text.tag_config(LogCategory.NORMAL.name, foreground="#E0E0E0")
        self.log_text.tag_config(LogCategory.EVENT_START.name, foreground="#FFFFFF")  # 開始：白
        self.log_text.tag_config(LogCategory.EVENT_END.name, foreground="#00E676")  # 完了：緑
        self.log_text.tag_config(LogCategory.WARNING.name, foreground="#FF6D00")  # 警告：オレンジ
        self.log_text.tag_config(LogCategory.ERROR.name, foreground="#FF1744")  # エラー：赤

        self.log_text.tag_config("highlight_path", foreground="#40C4FF")  # パス：水色
        self.log_text.tag_raise("highlight_path")

        self.progressbar = ctk.CTkProgressBar(self)
        self.progressbar.grid(row=2, column=1, padx=20, pady=(0, 20), sticky="ew")
        self.progressbar.set(0)

    def process_msg_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                msg_type = msg.get("type")
                if msg_type == "log":
                    self._append_log_to_widget(msg["text"], msg["category"], msg.get("metadata"))
                elif msg_type == "progress":
                    self.progressbar.set(msg["value"])
                elif msg_type == "ui_state":
                    self._set_ui_state(msg["state"], msg.get("mode"))

                self.msg_queue.task_done()
                self.update_idletasks()  # 再描画を強制
        except queue.Empty:
            pass
        finally:
            self.after(50, self.process_msg_queue)

    def _append_log_to_widget(self, message, category, metadata=None):
        timestamp = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
        start_idx = self.log_text.index("end-1c")

        prefix = ""
        if category == LogCategory.WARNING:
            prefix = "⚠ "
        elif category == LogCategory.ERROR:
            prefix = "❌ "

        self.log_text.insert("end", f"{timestamp}{prefix}{message}\n")
        end_idx = self.log_text.index("end-1c")
        self.log_text.tag_add(category.name, start_idx, end_idx)
        self.log_text.tag_add("log_line_spacing", start_idx, end_idx)

        h_targets = []
        if metadata:
            if "path" in metadata: h_targets.append(metadata["path"])
            if "filename" in metadata: h_targets.append(metadata["filename"])
        if "解析結果保存先:" in message:
            h_targets.append(message.split("解析結果保存先:", 1)[1].strip())

        for t in h_targets:
            if not t: continue
            cur = start_idx
            while True:
                found = self.log_text.search(t, cur, stopindex=end_idx)
                if not found: break
                self.log_text.tag_add("highlight_path", found, f"{found}+{len(t)}c")
                cur = f"{found}+1c"
        self.log_text.see("end")

    def queue_log(self, msg, category=LogCategory.NORMAL, metadata=None):
        self.msg_queue.put({"type": "log", "text": msg, "category": category, "metadata": metadata})

    def _set_ui_state(self, is_running, mode=None):
        """解析中/待機中のUI表示。ステータス色をログと完全に分離。"""
        self.is_running = is_running
        state = "disabled" if is_running else "normal"
        for w in self.input_widgets: w.configure(state=state)

        if is_running:
            if mode == "preview":
                self.status_label.configure(text="< プレビュー中... >", text_color="#FFD740")  # アンバー
                self.start_button.configure(state="disabled", fg_color="gray")
            else:
                self.status_label.configure(text="< 解析中... >", text_color="#FF4081")  # マゼンタピンク
                self.start_button.configure(text="解析中止", fg_color="#cc0000", hover_color="#990000", state="normal")
        else:
            self.status_label.configure(text="< 待機中 >", text_color="#757575")
            self.update_radio_state()
            self.start_button.configure(text="解析開始", state="normal", fg_color="green", hover_color="darkgreen")
            self.cancel_requested = False

    def update_radio_state(self):
        if not self.is_running:
            st = "normal" if self.run_lipid_var.get() or self.run_necrosis_var.get() else "disabled"
            for r in [self.radio_clean, self.radio_mask, self.radio_combined]: r.configure(state=st)

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
        p = filedialog.askdirectory()
        if p: self.target_path = p; self.queue_log(f"解析フォルダ設定完了: {p}", metadata={"path": p})

    def toggle_analysis(self):
        if self.is_running and not self.cancel_requested:
            self.cancel_requested = True
            self.status_label.configure(text="< 中止処理中... >", text_color="#FF1744")
            self.start_button.configure(text="中止処理中...", state="disabled", fg_color="gray")
            self.queue_log("解析の中止を要求しました。現在の処理が終わるまでお待ちください...", LogCategory.WARNING)
        elif not self.is_running:
            if not self.target_path: self.select_folder()
            if not self.target_path: return
            self.msg_queue.put({"type": "ui_state", "state": True, "mode": "analysis"})
            threading.Thread(target=self.run_analysis_logic, args=(self.run_cell_var.get(), self.run_lipid_var.get(), self.run_necrosis_var.get(), self.memo_entry.get().strip()), daemon=True).start()

    def run_preview_thread(self):
        if self.is_running: return
        if not self.target_path: self.select_folder()
        if not self.target_path: return
        self.msg_queue.put({"type": "ui_state", "state": True, "mode": "preview"})
        threading.Thread(target=self.run_preview_logic, args=(self.run_cell_var.get(), self.run_lipid_var.get(), self.run_necrosis_var.get(), self.preview_target_var.get()), daemon=True).start()

    def run_analysis_logic(self, run_cell, run_lipid, run_necrosis, memo):
        try:
            self.prepare_analyzer()
            if run_cell: self.analyzer.get_cell_model()
            if run_lipid: self.analyzer.get_lipid_model()
            if run_necrosis: self.analyzer.get_necrosis_model()

            bf_s, fl_s, pi_s = [str(self.config_data.get(k, "")).strip() for k in ["bf_suffix", "fl_suffix", "pi_suffix"]]
            bf_files = sorted([f for f in os.listdir(self.target_path) if bf_s.lower() in f.lower() and f.lower().endswith(self.IMAGE_EXTS)])

            if not bf_files:
                self.queue_log(f"エラー: 画像が見つかりません (識別子: {bf_s})", LogCategory.ERROR);
                return

            out_dir = self._create_out_dir(memo)
            self.queue_log(f"【解析開始: {len(bf_files)} セット】", LogCategory.EVENT_START)

            if run_lipid or run_necrosis:
                def_msg = "\n" + "=" * 70 + "\n定義確認:\n"
                if run_lipid:
                    def_msg += " 1. 油脂占有率 (蓄積度)   = 細胞内の油脂面積 / 細胞の総面積\n" \
                               " 2. 油脂生産率 (効率)     = 全油脂面積 / 細胞の総面積\n" \
                               " 3. 細胞内油脂割合 (分布) = (細胞内の油脂面積 / 全油脂面積) × 100\n" \
                               " 4. 油脂保有細胞割合     = 油脂を含む細胞数 / 全体の細胞数\n"
                if run_necrosis:
                    def_msg += " 1. 壊死細胞割合 = 壊死細胞数 / 全体の細胞数\n"
                def_msg += "=" * 70
                self.queue_log(def_msg, LogCategory.EVENT_START)

            rows, totals = [], self._init_totals()
            total_count = len(bf_files)
            for idx, name in enumerate(bf_files):
                if self.cancel_requested:
                    self.queue_log("ユーザー操作により解析が中止されました。", LogCategory.WARNING)
                    break

                # 進捗修正：処理開始時に (idx / total) を表示（2枚なら1枚目開始で0%）
                self.msg_queue.put({"type": "progress", "value": idx / total_count})
                row = self._proc_img(idx, total_count, name, bf_s, fl_s, pi_s, run_cell, run_lipid, run_necrosis, out_dir, totals)
                if row: rows.append(row)

            if rows:
                self._write_summary(rows, totals, len(rows), run_cell, run_lipid, run_necrosis, out_dir)
                self.queue_log("✨ 全ての解析工程が完了しました", LogCategory.EVENT_END)

        except Exception as e:
            self.queue_log(f"解析致命的エラー: {e}", LogCategory.ERROR)
        finally:
            self.msg_queue.put({"type": "progress", "value": 1.0})
            self.msg_queue.put({"type": "ui_state", "state": False})

    def run_preview_logic(self, run_cell, run_lipid, run_necrosis, p_type):
        try:
            self.prepare_analyzer()
            bf_s, fl_s, pi_s = [str(self.config_data.get(k, "")).strip() for k in ["bf_suffix", "fl_suffix", "pi_suffix"]]
            bf_files = sorted([f for f in os.listdir(self.target_path) if bf_s.lower() in f.lower() and f.lower().endswith(self.IMAGE_EXTS)])
            if not bf_files: return

            self.msg_queue.put({"type": "progress", "value": 0.2})
            out = os.path.join(self.target_path, "preview_temp");
            os.makedirs(out, exist_ok=True)
            self.queue_log(f"【プレビュー実行】先頭の1枚を解析中: {bf_files[0]}", LogCategory.EVENT_START, metadata={"filename": bf_files[0]})

            row = self._proc_img(0, 1, bf_files[0], bf_s, fl_s, pi_s, run_cell, run_lipid, run_necrosis, out, self._init_totals())
            if row:
                self.queue_log("✨ プレビュー画像の生成が完了しました。", LogCategory.EVENT_END)
                target = self._get_preview_key(run_lipid, run_necrosis, p_type)
                pref = {"cell": "01_", "lipid_clean": "00_clean_", "lipid": "02_", "combined": "03_", "necrosis_clean": "00_clean_", "necrosis": "02_", "combined_necrosis": "03_"}
                path = os.path.join(out, f"{pref.get(target, '')}{target}_{bf_files[0]}")
                if os.path.exists(path):
                    if platform.system() == 'Windows':
                        os.startfile(path)
                    else:
                        subprocess.call(('open' if platform.system() == 'Darwin' else 'xdg-open', path))
        except Exception as e:
            self.queue_log(f"エラー: {e}", LogCategory.ERROR)
        finally:
            self.msg_queue.put({"type": "progress", "value": 1.0})
            self.msg_queue.put({"type": "ui_state", "state": False})

    def _proc_img(self, idx, total, bf_name, bf_s, fl_s, pi_s, run_c, run_l, run_n, out_dir, totals):
        stem, ext = os.path.splitext(bf_name);
        img_bf = self._read_img(bf_name)
        img_fl, img_pi = None, None
        if run_l:
            fl_n = f"{stem[:-len(bf_s)]}{fl_s}{ext}";
            img_fl = self._read_img(fl_n)
            if img_fl is None:
                self.queue_log(f"警告: 油脂用画像が見つかりません。スキップします: {fl_n}", LogCategory.WARNING, metadata={"filename": fl_n});
                return None
        if run_n:
            pi_n = f"{stem[:-len(bf_s)]}{pi_s}{ext}";
            img_pi = self._read_img(pi_n)
            if img_pi is None:
                self.queue_log(f"警告: 壊死用画像が見つかりません。スキップします: {pi_n}", LogCategory.WARNING, metadata={"filename": pi_n});
                return None
        if img_bf is None: return None

        stats, visuals = self.analyzer.analyze(img_bf, img_fl, img_pi, run_c, run_l, run_n)
        prefixes = {"cell": "01_", "lipid_clean": "00_clean_", "lipid": "02_", "combined": "03_", "necrosis_clean": "00_clean_", "necrosis": "02_", "combined_necrosis": "03_"}
        for k, v in visuals.items():
            p = os.path.join(out_dir, f"{prefixes.get(k, '')}{k}_{bf_name}");
            cv2.imencode(os.path.splitext(p)[1], v)[1].tofile(p)
        return self._build_row_and_log(bf_name, idx, total, stats, run_c, run_l, run_n, totals)

    def _build_row_and_log(self, name, idx, total, stats, run_c, run_l, run_n, totals):
        row, log = {"ファイル名": name}, [f"[{idx + 1}/{total}] {name}"]
        cells = stats.get("cell_count", 0) if run_c else 0
        if run_c:
            a = stats.get("total_cell_px", 0);
            log.append(f"   >>> 細胞数   : {cells} 個\n   >>> 細胞面積 : {a} px")
            row.update({"細胞数": cells, "細胞面積(px)": a});
            totals["cell_counts"].append(cells)
            if cells > 0:
                totals["cell_area_means"].append(a / cells)
            else:
                log.append("⚠ 細胞数が0のため、本画像の平均データは除外されます。")
        if run_l:
            occ, prd, inp, lpcc, lpcr = [stats.get(k, 0.0) for k in ["lipid_cell_ratio", "total_production_ratio", "intracellular_lipid_percent", "lipid_positive_cell_count", "lipid_positive_cell_ratio"]]
            log.append(f"   >>> 油脂占有率       : {occ:.4f}\n   >>> 総生産率         : {prd:.4f}\n   >>> 細胞内油脂割合   : {inp * 100:.1f}%\n   >>> 油脂保有細胞数   : {lpcc} 個\n   >>> 油脂保有細胞割合 : {lpcr * 100:.1f}%")
            row.update({"油脂占有率": occ, "総生産率": prd, "細胞内油脂割合(%)": inp * 100, "油脂保有細胞数": lpcc, "油脂保有細胞割合(%)": lpcr * 100})
            totals["lipid_positive_cells"].append(lpcc)
            if cells > 0: totals["lipid_occupancies"].append(occ); totals["total_production_ratios"].append(prd); totals["lipid_positive_cell_ratios"].append(lpcr)
            if stats.get("total_lipid_px", 0) > 0: totals["intracellular_lipid_percents"].append(inp)
        if run_n:
            npcc, npcr = stats.get("necrosis_positive_cell_count", 0), stats.get("necrosis_positive_cell_ratio", 0.0)
            log.append(f"   >>> 壊死細胞数       : {npcc} 個\n   >>> 壊死細胞割合     : {npcr * 100:.1f}%")
            row.update({"壊死細胞数": npcc, "壊死細胞割合(%)": npcr * 100});
            totals["necrosis_positive_cells"].append(npcc)
            if cells > 0: totals["necrosis_positive_cell_ratios"].append(npcr)
        self.queue_log("\n".join(log), LogCategory.NORMAL, metadata={"filename": name});
        return row

    def _write_summary(self, rows, totals, count, run_c, run_l, run_n, out_dir):
        sum_log, stat_row = ["", "-" * 40, "【 全画像 統計サマリー 】"], {"ファイル名": "--- 全体統計平均 ---"}
        if run_c and totals["cell_counts"]:
            avg_c, sd_c = np.mean(totals["cell_counts"]), (np.std(totals["cell_counts"], ddof=1) if len(totals["cell_counts"]) > 1 else 0.0)
            avg_a, sd_a = np.mean(totals["cell_area_means"]), (np.std(totals["cell_area_means"], ddof=1) if len(totals["cell_area_means"]) > 1 else 0.0)
            sum_log.extend([f"   [平均]     細胞数 : {avg_c:.1f} 個", f"   [標準偏差] 細胞数 : {sd_c:.2f}", f"   [平均]     細胞平均面積 : {avg_a:.2f} px", f"   [標準偏差] 細胞平均面積 : {sd_a:.2f}"])
            stat_row.update({"細胞数": avg_c, "細胞数標準偏差": sd_c, "細胞平均面積(px)": avg_a, "細胞平均面積標準偏差": sd_a})
        if run_l and totals["lipid_occupancies"]:
            avg_o, sd_o = np.mean(totals["lipid_occupancies"]), (np.std(totals["lipid_occupancies"], ddof=1) if len(totals["lipid_occupancies"]) > 1 else 0.0)
            avg_p, avg_i, avg_lpcc = np.mean(totals["total_production_ratios"]), np.mean(totals["intracellular_lipid_percents"]) * 100, np.mean(totals["lipid_positive_cells"])
            avg_lpcr, sd_lpcr = np.mean(totals["lipid_positive_cell_ratios"]) * 100, (np.std(totals["lipid_positive_cell_ratios"], ddof=1) * 100 if len(totals["lipid_positive_cell_ratios"]) > 1 else 0.0)
            sum_log.extend(
                [f"   [平均]     油脂占有率 : {avg_o:.4f}", f"   [標準偏差] 油脂占有率 : {sd_o:.4f}", f"   [平均] 総生産率       : {avg_p:.4f}", f"   [平均] 細胞内油脂割合 : {avg_i:.1f}%", f"   [平均] 油脂保有細胞数 : {avg_lpcc:.1f} 個",
                 f"   [平均] 油脂保有細胞割合 : {avg_lpcr:.1f}%", f"   [標準偏差] 油脂保有細胞割合 : {sd_lpcr:.2f}"])
            stat_row.update({"油脂占有率": avg_o, "油脂占有率標準偏差": sd_o, "総生産率": avg_p, "細胞内油脂割合(%)": avg_i, "油脂保有細胞数": avg_lpcc, "油脂保有細胞割合(%)": avg_lpcr, "油脂保有細胞割合標準偏差": sd_lpcr})
        if run_n and totals["necrosis_positive_cells"]:
            avg_n, avg_nr, sd_nr = np.mean(totals["necrosis_positive_cells"]), np.mean(totals["necrosis_positive_cell_ratios"]) * 100, (
                np.std(totals["necrosis_positive_cell_ratios"], ddof=1) * 100 if len(totals["necrosis_positive_cell_ratios"]) > 1 else 0.0)
            sum_log.extend([f"   [平均] 壊死細胞数 : {avg_n:.1f} 個", f"   [平均] 壊死細胞割合 : {avg_nr:.1f}%", f"   [標準偏差] 壊死細胞割合 : {sd_nr:.2f}"])
            stat_row.update({"壊死細胞数": avg_n, "壊死細胞割合(%)": avg_nr, "壊死細胞割合標準偏差": sd_nr})

        sum_log.append("-" * 40);
        self.queue_log("\n".join(sum_log), LogCategory.EVENT_END)
        self.queue_log(f"解析結果保存先: {out_dir}", LogCategory.NORMAL);
        rows.append(stat_row)
        pd.DataFrame(rows).to_csv(os.path.join(out_dir, "analysis_summary.csv"), index=False, encoding="utf-8-sig")

    def _create_out_dir(self, memo):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        f = f"result_{re.sub(r'[\\/:*?\"<>|]+', '_', memo)}_{ts}" if memo else f"result_{ts}"
        p = os.path.join(self.target_path, f);
        os.makedirs(p, exist_ok=True);
        return p

    def _init_totals(self):
        return {"cell_counts": [], "cell_area_means": [], "lipid_occupancies": [], "total_production_ratios": [], "intracellular_lipid_percents": [], "lipid_positive_cell_ratios": [], "lipid_positive_cells": [],
                "necrosis_positive_cells": [], "necrosis_positive_cell_ratios": []}

    def _read_img(self, n):
        p = os.path.join(self.target_path, n)
        return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_UNCHANGED) if os.path.exists(p) else None

    def _get_preview_key(self, run_l, run_n, p_type):
        if run_n: return {"clean": "necrosis_clean", "mask": "necrosis"}.get(p_type, "combined_necrosis")
        if run_l: return {"clean": "lipid_clean", "mask": "lipid"}.get(p_type, "combined")
        return "cell"

    def prepare_analyzer(self):
        self.config_data.load_config()
        if not self.analyzer: self.analyzer = YeastAnalyzer(self.config_data, log_callback=self.queue_log)
