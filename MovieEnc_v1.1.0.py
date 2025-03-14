import os
import json
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinterdnd2 import DND_FILES, TkinterDnD

# ==============================
# 設定ファイルの読み書き
# ==============================
CONFIG_FILE = "config.json"

def load_config():
    """ config.json を読み込み、辞書を返す。存在しなければ空の辞書を返す。 """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"設定ファイルの読み込みに失敗: {e}")
    return {}

def save_config(data):
    """ 辞書を config.json に書き込む """
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"設定ファイルの書き込みに失敗: {e}")

# ==============================
# FFmpeg関連の定数や関数
# ==============================
TARGET_SIZE_MB = 9.2          # ターゲットファイルサイズ（MB）
AUDIO_BITRATE = 128000        # オーディオビットレート (bps)

def get_video_duration(filename):
    """
    ffprobeを使って動画の再生時間（秒）を取得する
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filename
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        messagebox.showerror("エラー", f"動画の長さ取得に失敗しました:\n{e}")
        return None

def get_video_resolution(filename):
    """
    ffprobeを使って動画の解像度 (widthxheight) を取得する
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                filename
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        resolution = result.stdout.strip()
        return resolution
    except Exception as e:
        messagebox.showerror("エラー", f"動画の解像度取得に失敗しました:\n{e}")
        return "unknown"

# ==============================
# UI用の関数
# ==============================
def browse_file():
    """ 入力ファイルを選択する """
    filename = filedialog.askopenfilename(
        title="入力ファイルを選択",
        filetypes=[("Video Files", "*.mp4;*.avi;*.mkv;*")]
    )
    if filename:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, filename)

def drop(event):
    """ ドラッグ＆ドロップされたファイルを入力欄に反映する """
    file_path = event.data.strip('{}')
    input_entry.delete(0, tk.END)
    input_entry.insert(0, file_path)

def browse_output_dir():
    """ 出力先フォルダを選択する """
    directory = filedialog.askdirectory(title="出力先フォルダを選択")
    if directory:
        output_dir_entry.delete(0, tk.END)
        output_dir_entry.insert(0, directory)
        # 設定ファイルに保存
        config['last_output_dir'] = directory
        save_config(config)

def toggle_nvenc():
    """ NVENC使用チェックの状態を保存 """
    config['use_nvenc'] = use_nvenc_var.get()
    save_config(config)

def run_ffmpeg():
    """ FFmpegを実行して動画をエンコードする """
    input_file = input_entry.get().strip()
    if not input_file:
        messagebox.showerror("エラー", "入力ファイルを指定してください。")
        return
    if not os.path.exists(input_file):
        messagebox.showerror("エラー", "指定されたファイルが存在しません。")
        return

    # 動画の再生時間を取得
    duration = get_video_duration(input_file)
    if duration is None:
        return

    # NVENC使用の有無をチェック
    use_nvenc = use_nvenc_var.get()

    # ラジオボタンで選択されたモードを取得
    mode = mode_var.get()  # "360p", "480p", "720p" または "9.5MB"
    # 縦長かどうかを判定するため、元の解像度を取得
    orig_res = get_video_resolution(input_file)
    if orig_res != "unknown":
        orig_width, orig_height = map(int, orig_res.split("x"))
        vertical = orig_width < orig_height
    else:
        vertical = False

    if mode in ["360p", "480p", "720p"]:
        # 縦長の場合は高さ固定、横幅は自動調整（-1:固定値）
        if vertical:
            presets = {"360p": "360:-1", "480p": "480:-1", "720p": "720:-1"}
        else:
            # 横長の場合のプリセット例
            presets = {"360p": "640:360", "480p": "854:480", "720p": "1280:720"}
        scaling_filter = f"scale={presets[mode]}"
        resolution_str = mode
        use_bitrate = False  # 解像度指定モードはCRF（品質指定）でエンコード
    elif mode == "9.5MB":
        if vertical:
            scaling_filter =  f"scale=480:-1" # 解像度変更 480p
        else:
            scaling_filter =  f"scale=854:480"

        resolution_str = mode
        use_bitrate = True   # ビットレート指定モード
    else:
        scaling_filter = None
        resolution_str = "default"
        use_bitrate = False

    # 出力先フォルダを取得
    output_dir = output_dir_entry.get().strip()
    if not output_dir:
        output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.exists(output_dir):
        messagebox.showerror("エラー", f"指定された出力先フォルダが存在しません。\n{output_dir}")
        return

    # 出力ファイル名は「元ファイル名_解像度.mp4」
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(output_dir, f"{base_name}_{resolution_str}.mp4")

    # FFmpegコマンドの組み立て
    command = ["ffmpeg", "-i", input_file]
    if scaling_filter:
        command.extend(["-vf", scaling_filter])

    if use_bitrate:
        # ターゲットファイルサイズに合わせたビットレートの計算
        target_size_bits = TARGET_SIZE_MB * 1000 * 1000* 8 #1024から1000に変更
        audio_total_bits = AUDIO_BITRATE * duration
        video_total_bits = target_size_bits - audio_total_bits
        if video_total_bits <= 0:
            messagebox.showerror("エラー", "動画の長さが長すぎるか、ターゲットサイズが小さすぎます。")
            return
        video_bitrate_bps = video_total_bits / duration
        video_bitrate_kbps = int(video_bitrate_bps / 1000)
        if video_bitrate_kbps <= 0:
            messagebox.showerror("エラー", "計算されたビットレートが不正です。")
            return

        if use_nvenc:
            command.extend(["-b:v", f"{video_bitrate_kbps}k", "-c:v", "h264_nvenc", "-preset", "slow"])
        else:
            command.extend(["-b:v", f"{video_bitrate_kbps}k", "-c:v", "libx264", "-preset", "slow"])
    else:
        # CRF（品質指定）でエンコード
        if use_nvenc:
            # NVENCの場合、-cq を使用（値は例として23）
            command.extend(["-c:v", "h264_nvenc", "-preset", "slow", "-cq", "23"])
        else:
            command.extend(["-c:v", "libx264", "-preset", "slow", "-crf", "23"])

    # 共通のオーディオ設定
    command.extend([
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar" ,"44100",
        output_file
    ])

    try:
        subprocess.run(command, check=True)
        messagebox.showinfo("完了", f"動画の圧縮が完了しました。\n出力ファイル:\n{output_file}")
    except subprocess.CalledProcessError as e:
        messagebox.showerror("エラー", f"変換中にエラーが発生しました。\n{e}")

# ==============================
# メインウィンドウの構築
# ==============================
root = TkinterDnD.Tk()
root.title("FFmpeg MovieEncoder_v1.1.1")

# 設定ファイルを読み込み、前回の保存先とNVENC設定を取得
config = load_config()
last_output_dir = config.get('last_output_dir', "")  # なければ空文字列
default_nvenc = config.get('use_nvenc', False)

# 入力ファイルの選択エリア
tk.Label(root, text="入力ファイル:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
input_entry = tk.Entry(root, width=50)
input_entry.grid(row=0, column=1, padx=5, pady=5)
input_entry.drop_target_register(DND_FILES)
input_entry.dnd_bind('<<Drop>>', drop)
tk.Button(root, text="参照", command=browse_file).grid(row=0, column=2, padx=5, pady=5)

# 出力先フォルダの選択エリア
tk.Label(root, text="出力先フォルダ:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
output_dir_entry = tk.Entry(root, width=50)
output_dir_entry.grid(row=1, column=1, padx=5, pady=5)
output_dir_entry.insert(0, last_output_dir)  # 前回保存したフォルダをセット
tk.Button(root, text="出力先を選択", command=browse_output_dir).grid(row=1, column=2, padx=5, pady=5)

# 出力設定（ラジオボタン）
mode_var = tk.StringVar(value="360p")  # デフォルトは360p
frame = tk.LabelFrame(root, text="出力設定")
frame.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")
modes = [("360p", "360p"), ("480p", "480p"), ("720p", "720p"), ("9.5MB", "9.5MB")]
for i, (text, mode) in enumerate(modes):
    rb = tk.Radiobutton(frame, text=text, variable=mode_var, value=mode)
    rb.grid(row=0, column=i, padx=5, pady=5)

# NVENC使用チェックボックス
use_nvenc_var = tk.BooleanVar(value=default_nvenc)
nvenc_checkbox = tk.Checkbutton(root, text="NVENCを使用", variable=use_nvenc_var, command=toggle_nvenc)
nvenc_checkbox.grid(row=3, column=0, columnspan=3, padx=5, pady=5)

# 変換開始ボタン
tk.Button(root, text="エンコード開始", command=run_ffmpeg).grid(row=4, column=1, pady=10)

root.mainloop()
