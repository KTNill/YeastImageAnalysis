import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import cv2
import datetime
import pandas as pd

# 見た目の設定
ctk.set_appearance_mode("dark")  # "light" も可能
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ウィンドウ設定
        self.title("酵母画像解析システム - Yeast Analysis App")
        self.geometry("900x700")

        # グリッド構成
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- サイドバー (設定・フォルダ選択) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="解析設定", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.select_button = ctk.CTkButton(self.sidebar_frame, text="画像フォルダを選択", command=self.browse_folder)
        self.select_button.grid(row=1, column=0, padx=20, pady=10)

        self.folder_label = ctk.CTkLabel(self.sidebar_frame, text="フォルダ未選択", wraplength=160, text_color="gray")
        self.folder_label.grid(row=2, column=0, padx=20, pady=5)

        # --- メインエリア (上部：モード選択) ---
        self.mode_frame = ctk.CTkFrame(self, corner_radius=10)
        self.mode_frame.grid(row=0, column=1, padx=20, pady=(20, 10), sticky="nsew")

        self.mode_label = ctk.CTkLabel(self.mode_frame, text="解析モードを選択してください", font=ctk.CTkFont(size=14))
        self.mode_label.pack(pady=10)

        self.button_frame = ctk.CTkFrame(self.mode_frame, fg_color="transparent")
        self.button_frame.pack(pady=10)

        self.bf_btn = ctk.CTkButton(self.button_frame, text="透過光 (BF)", width=150, height=50,
                                     command=lambda: self.start_analysis("透過光"))
        self.bf_btn.pack(side="left", padx=10)

        self.fda_btn = ctk.CTkButton(self.button_frame, text="FDA (生死)", width=150, height=50,
                                      command=lambda: self.start_analysis("FDA"))
        self.fda_btn.pack(side="left", padx=10)

        self.nr_btn = ctk.CTkButton(self.button_frame, text="ナイルレッド (油脂)", width=150, height=50,
                                     command=lambda: self.start_analysis("ナイルレッド"), fg_color="#E91E63", hover_color="#C2185B")
        self.nr_btn.pack(side="left", padx=10)

        # --- メインエリア (中央：ログ表示) ---
        self.log_textbox = ctk.CTkTextbox(self, width=600, corner_radius=10)
        self.log_textbox.grid(row=1, column=1, padx=20, pady=10, sticky="nsew")
        self.log_textbox.insert("0.0", "--- 解析ログ ---\nフォルダを選択して解析モードをクリックしてください。\n")

        # --- 下部 (プログレスバー) ---
        self.status_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.status_frame.grid(row=2, column=1, sticky="ew")

        self.progressbar = ctk.CTkProgressBar(self.status_frame, width=500)
        self.progressbar.grid(row=0, column=0, padx=20, pady=15)
        self.progressbar.set(0)

        self.status_label = ctk.CTkLabel(self.status_frame, text="待機中")
        self.status_label.grid(row=0, column=1, padx=20)

        # 内部変数
        self.target_path = ""
        self.config_data = {"cell_diameter": 30} # 解析用の設定値
        self.analyzer = None # 実際の解析クラスをここに割り当てる想定

    def browse_folder(self):
        """フォルダ選択ダイアログを開く"""
        # parent=self を指定することで、メインウィンドウに関連付けます
        path = filedialog.askdirectory(
            parent=self,
            title="解析対象の画像フォルダを選択してください"
        )

        if path:
            # パスが選択された場合、ウィンドウを一度前面に持ってくる
            self.focus_force()
            self.target_path = path
            self.folder_label.configure(text=f"選択中:\n{os.path.basename(path)}", text_color="white")
            self.update_log(f"フォルダを選択しました: {path}")
        else:
            # キャンセルされた場合もフォーカスを戻す
            self.focus_force()

    def update_log(self, message):
        """ログにメッセージを追加"""
        self.log_textbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_textbox.see("end")

    def show_error(self, message):
        """日本語のエラーポップアップを表示"""
        messagebox.showerror("エラー", message)

    def start_analysis(self, mode):
        """解析開始（マルチスレッドで実行してGUIをフリーズさせない）"""
        if not self.target_path:
            self.show_error("解析対象の画像フォルダが選択されていません。")
            return

        self.update_log(f"モード【{mode}】で解析を開始します...")

        # 解析処理を別スレッドで実行
        thread = threading.Thread(target=self.run_analysis_process, args=(mode,), daemon=True)
        thread.start()

    def run_analysis_process(self, mode):
        """実際の解析ロジックを実行し、CSVを出力します"""
        try:
            self.status_label.configure(text="解析中...")

            # 1. 画像ファイルのリストを取得
            extensions = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
            image_files = [f for f in os.listdir(self.target_path) if f.lower().endswith(extensions)]
            if not image_files:
                self.show_error("選択されたフォルダに画像ファイルが見つかりません。")
                return

            all_results = []
            total = len(image_files)

            for i, filename in enumerate(image_files):
                self.update_log(f"解析中 ({i+1}/{total}): {filename}")

                # 画像の読み込み
                img_path = os.path.join(self.target_path, filename)
                img = cv2.imread(img_path)

                if img is None:
                    self.update_log(f"失敗: {filename} を読み込めませんでした。")
                    continue

                # analyzer.py の実行 (透過光とナイルレッドが同じ画像、または同じフォルダにある前提)
                # 本来はモードに合わせてペアを探すロジックが必要ですが、ここでは単一画像でテスト
                # 注意: self.analyzer が事前に定義されている必要があります
                if self.analyzer is not None:
                    df = self.analyzer.run_analysis(img, img, diameter=self.config_data.get("cell_diameter"))
                else:
                    # analyzerが未設定の場合のダミー処理（デバッグ用）
                    time.sleep(0.1)
                    df = pd.DataFrame()

                if not df.empty:
                    df['filename'] = filename
                    all_results.append(df)

                # 進捗更新
                self.progressbar.set((i + 1) / total)

            # 2. 結果をまとめてCSV出力
            if all_results:
                final_df = pd.concat(all_results, ignore_index=True)

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"data/output/analysis_result_{timestamp}.csv"

                # data/output フォルダがなければ作成
                os.makedirs("data/output", exist_ok=True)

                final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
                self.update_log(f"--- 解析完了 ---")
                self.update_log(f"保存先: {output_path}")
                self.status_label.configure(text="完了")
                messagebox.showinfo("成功", f"解析が完了しました。\n{len(image_files)}枚の画像を処理し、CSVを保存しました。")
            else:
                self.update_log("解析結果が空でした。細胞が検出できなかった可能性があります。")
                self.status_label.configure(text="終了（データなし）")

        except Exception as e:
            self.show_error(f"解析中にエラーが発生しました:\n{str(e)}")
            self.status_label.configure(text="エラー")

if __name__ == "__main__":
    app = App()
    app.mainloop()
