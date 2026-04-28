import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import datetime
import cv2
import pandas as pd
from core.analyzer import YeastAnalyzer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    """
    アプリケーションのGUIクラス。画像フォルダの読み込みと解析実行。
    """

    def __init__(self):
        super().__init__()
        self.analyzer = None
        self.config_data = None
        self.target_path = ""

        self.title("酵母・油脂 解析システム")
        self.geometry("900x700")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # UIコンポーネント配置
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="操作メニュー",
                                       font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.select_button = ctk.CTkButton(self.sidebar_frame, text="フォルダを選択", command=self.select_folder)
        self.select_button.grid(row=1, column=0, padx=20, pady=10)

        self.run_cell_var = ctk.BooleanVar(value=True)
        self.cell_check = ctk.CTkCheckBox(self.sidebar_frame, text="細胞解析 (BF)", variable=self.run_cell_var)
        self.cell_check.grid(row=2, column=0, padx=20, pady=10, sticky="w")

        self.run_lipid_var = ctk.BooleanVar(value=True)
        self.lipid_check = ctk.CTkCheckBox(self.sidebar_frame, text="油脂解析 (FL)", variable=self.run_lipid_var)
        self.lipid_check.grid(row=3, column=0, padx=20, pady=10, sticky="w")

        self.start_button = ctk.CTkButton(self.sidebar_frame, text="解析開始", command=self.start_analysis_thread,
                                          fg_color="green", hover_color="darkgreen")
        self.start_button.grid(row=4, column=0, padx=20, pady=20)

        self.log_text = ctk.CTkTextbox(self, width=600)
        self.log_text.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")

        self.progressbar = ctk.CTkProgressBar(self)
        self.progressbar.grid(row=2, column=1, padx=20, pady=(0, 20), sticky="ew")
        self.progressbar.set(0)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.target_path = path
            self.update_log(f"フォルダ選択: {path}")

    def update_log(self, message):
        self.log_text.insert("end", f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see("end")

    def start_analysis_thread(self):
        if not self.target_path:
            messagebox.showwarning("警告", "フォルダを選択してください。")
            return
        threading.Thread(target=self.run_analysis, daemon=True).start()

    def run_analysis(self):
        """解析本体。透過光と蛍光のペアリングを行い、CSVに集計結果を出力する。"""
        try:
            bf_suffix = self.config_data.get("bf_suffix")
            fl_suffix = self.config_data.get("fl_suffix")

            files = [f for f in os.listdir(self.target_path) if
                     f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))]
            bf_files = [f for f in files if bf_suffix in f]

            if not bf_files:
                self.update_log(f"エラー: 接尾辞 '{bf_suffix}' が付いた画像が見つかりません。")
                return

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(self.target_path, f"result_{timestamp}")
            os.makedirs(output_dir, exist_ok=True)

            summary_data = []
            total = len(bf_files)

            for i, bf_filename in enumerate(bf_files):
                p_base = i / total
                p_step = 1.0 / total

                # 自動ペアリング
                fl_filename = bf_filename.replace(bf_suffix, fl_suffix)
                self.update_log(f"解析中 ({i + 1}/{total}): {bf_filename}")

                img_bf = cv2.imread(os.path.join(self.target_path, bf_filename), cv2.IMREAD_UNCHANGED)
                img_fl = None
                fl_path = os.path.join(self.target_path, fl_filename)
                if os.path.exists(fl_path):
                    img_fl = cv2.imread(fl_path, cv2.IMREAD_UNCHANGED)

                def cb(ratio):
                    self.progressbar.set(p_base + (p_step * ratio))

                # 解析実行
                stats, vis = self.analyzer.analyze(
                    img_bf, img_fl,
                    run_cell=self.run_cell_var.get(),
                    run_lipid=self.run_lipid_var.get() and img_fl is not None,
                    progress_callback=cb
                )

                # 可視化画像の書き出し
                for key, img_out in vis.items():
                    cv2.imwrite(os.path.join(output_dir, f"{key}_{bf_filename}"), img_out)

                # CSV行データの作成（比率項目を追加）
                row = {
                    "ファイル名": bf_filename,
                    "細胞数": stats.get("cell_count", 0),
                    "細胞面積(px)": stats.get("total_cell_px", 0),
                    "油脂数": stats.get("lipid_count", 0),
                    "総油脂面積(px)": stats.get("total_lipid_px", 0),
                    "細胞内油脂面積(px)": stats.get("integrated_lipid_px", 0),
                    "油脂面積/細胞面積": stats.get("lipid_cell_ratio", 0)
                }
                summary_data.append(row)

            # CSV保存
            if summary_data:
                csv_path = os.path.join(output_dir, "analysis_summary.csv")
                pd.DataFrame(summary_data).to_csv(csv_path, index=False, encoding='utf-8-sig')

            self.update_log(f"全工程完了。保存先:\n{output_dir}")

        except Exception as e:
            self.update_log(f"エラー発生: {e}")
            messagebox.showerror("エラー", str(e))