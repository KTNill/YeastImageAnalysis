import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import datetime
import cv2
import pandas as pd
import shutil
from core.analyzer import YeastAnalyzer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    """
    メインGUIクラス。チェックボックスの状態に応じて出力を動的に切り替える。
    """

    def __init__(self):
        super().__init__()
        self.analyzer = None
        self.config_data = None
        self.target_path = ""

        self.title("酵母・油脂 画像解析システム")
        self.geometry("900x700")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="操作パネル", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.select_button = ctk.CTkButton(self.sidebar_frame, text="画像フォルダを選択", command=self.select_folder)
        self.select_button.grid(row=1, column=0, padx=20, pady=10)

        # チェックボックス連動ロジック
        self.run_cell_var = ctk.BooleanVar(value=True)
        self.cell_check = ctk.CTkCheckBox(self.sidebar_frame, text="細胞解析 (BF)", variable=self.run_cell_var,
                                          command=self.on_cell_check_changed)
        self.cell_check.grid(row=2, column=0, padx=20, pady=10, sticky="w")

        self.run_lipid_var = ctk.BooleanVar(value=True)
        self.lipid_check = ctk.CTkCheckBox(self.sidebar_frame, text="油脂解析 (FL)", variable=self.run_lipid_var,
                                           command=self.on_lipid_check_changed)
        self.lipid_check.grid(row=3, column=0, padx=20, pady=10, sticky="w")

        self.start_button = ctk.CTkButton(self.sidebar_frame, text="解析開始", command=self.start_analysis_thread,
                                          fg_color="green", hover_color="darkgreen")
        self.start_button.grid(row=4, column=0, padx=20, pady=20)

        self.log_text = ctk.CTkTextbox(self, width=600, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_text.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")

        self.progressbar = ctk.CTkProgressBar(self)
        self.progressbar.grid(row=2, column=1, padx=20, pady=(0, 20), sticky="ew")
        self.progressbar.set(0)

    def on_cell_check_changed(self):
        if not self.run_cell_var.get(): self.run_lipid_var.set(False)

    def on_lipid_check_changed(self):
        if self.run_lipid_var.get(): self.run_cell_var.set(True)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.target_path = path
            self.update_log(f"解析フォルダ設定完了: {path}")

    def update_log(self, message):
        self.log_text.insert("end", f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see("end")

    def start_analysis_thread(self):
        if not self.target_path or not os.path.exists(self.target_path):
            messagebox.showinfo("お知らせ", "画像フォルダが選択されていません。\nフォルダ選択ダイアログを表示します。")
            self.select_folder()
            if not self.target_path: return
        threading.Thread(target=self.run_analysis, daemon=True).start()

    def run_analysis(self):
        try:
            self.start_button.configure(state="disabled", fg_color="gray")
            self.update_log(f"設定ファイルを読み込み中: {self.config_data.config_path}")
            self.config_data.load_config()
            self.analyzer = YeastAnalyzer(self.config_data)

            run_cell = self.run_cell_var.get()
            run_lipid = self.run_lipid_var.get()

            bf_sfx = self.config_data.get("bf_suffix")
            fl_sfx = self.config_data.get("fl_suffix")

            files = [f for f in os.listdir(self.target_path) if
                     f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))]
            bf_files = [f for f in files if bf_sfx in f]

            if not bf_files:
                self.update_log(f"エラー: 画像が見つかりません。")
                return

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(self.target_path, f"result_{timestamp}")
            os.makedirs(output_dir, exist_ok=True)
            shutil.copy(self.config_data.config_path, os.path.join(output_dir, "used_settings.csv"))

            summary_rows = []
            sum_occ, sum_prod, sum_cells, sum_in_pct = 0.0, 0.0, 0, 0.0
            processed_count = 0
            total_files = len(bf_files)
            PREFIX_MAP = {"cell": "01_", "lipid": "02_", "combined": "03_"}

            self.update_log("=" * 55)
            self.update_log(f"解析開始: {total_files} セット")
            if run_lipid:
                self.update_log("定義確認:")
                self.update_log(" 1. 占有率 (蓄積度) = 細胞内の油脂面積 / 細胞の総面積")
                self.update_log(" 2. 総生産率 (効率) = 全油脂面積 / 細胞の総面積")
                self.update_log(" 3. 油脂分布 (分布) = (細胞内の油脂面積 / 全油脂面積) × 100")
            self.update_log("=" * 55)

            for i, bf_name in enumerate(bf_files):
                p_base, p_step = i / total_files, 1.0 / total_files
                fl_name = bf_name.replace(bf_sfx, fl_sfx)

                img_bf = cv2.imread(os.path.join(self.target_path, bf_name), cv2.IMREAD_UNCHANGED)
                img_fl = None
                if run_lipid:
                    fl_p = os.path.join(self.target_path, fl_name)
                    if os.path.exists(fl_p):
                        img_fl = cv2.imread(fl_p, cv2.IMREAD_UNCHANGED)

                def cb(ratio):
                    self.progressbar.set(p_base + (p_step * ratio))

                stats, vis = self.analyzer.analyze(img_bf, img_fl, run_cell=run_cell, run_lipid=run_lipid,
                                                   progress_callback=cb)

                for key, img_o in vis.items():
                    cv2.imwrite(os.path.join(output_dir, f"{PREFIX_MAP.get(key, '')}{key}_{bf_name}"), img_o)

                # 個別ログ出力とCSV行作成の分岐
                row = {"ファイル名": bf_name}
                self.update_log(f"[{i + 1}/{total_files}] {bf_name}")

                if run_cell:
                    cells = stats.get("cell_count", 0)
                    area = stats.get("total_cell_px", 0)
                    self.update_log(f"   >>> 細胞数: {cells} 個 / 細胞面積: {area} px")
                    row.update({"細胞数": cells, "細胞面積(px)": area})
                    sum_cells += cells

                if run_lipid:
                    occ = stats.get("lipid_cell_ratio", 0.0)
                    prod = stats.get("total_production_ratio", 0.0)
                    in_pct = stats.get("intracellular_lipid_percent", 0.0)
                    self.update_log(f"   >>> 占有率: {occ:.4f} / 生産率: {prod:.4f}")
                    self.update_log(f"   >>> 分布比: 細胞内 {in_pct * 100:.1f}%")
                    row.update({"油脂占有率": occ, "総生産率": prod, "細胞内油脂割合(%)": in_pct * 100})
                    sum_occ += occ
                    sum_prod += prod
                    sum_in_pct += in_pct

                summary_rows.append(row)
                processed_count += 1

            # 全体統計の分岐出力
            if processed_count > 0:
                self.update_log("-" * 40)
                self.update_log("【 全画像 統計サマリー 】")
                if run_cell:
                    self.update_log(f"   平均 細胞数    : {sum_cells / processed_count:.1f} 個")
                if run_lipid:
                    self.update_log(f"   平均 油脂占有率 : {sum_occ / processed_count:.4f}")
                    self.update_log(f"   平均 総生産率  : {sum_prod / processed_count:.4f}")
                    self.update_log(f"   平均 油脂分布  : 細胞内 {(sum_in_pct / processed_count) * 100:.1f}%")
                self.update_log("-" * 40)

                pd.DataFrame(summary_rows).to_csv(os.path.join(output_dir, "analysis_summary.csv"), index=False,
                                                  encoding='utf-8-sig')

            self.progressbar.set(1.0)
            self.update_log(f"全解析完了。結果保存先: {output_dir}")

        except Exception as e:
            self.update_log(f"エラー: {e}")
            messagebox.showerror("エラー", str(e))
        finally:
            self.start_button.configure(state="normal", fg_color="green")