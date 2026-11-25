# SoundWeavers 音樂科技播報 (Music Tech News)

自動搜尋近期音樂科技新聞、最新產品與製作教學，透過 **Gemini API** 產出繁體中文重點整理與技術分析，使用本機 **GPT-SoVITS v5turbo（隔壁女孩音檔）** 合成口播語音，並以程式化手繪白板引擎生成 **30 秒 9:16 手繪動畫短影片**，最後自動推送至 `https://github.com/soundweavers-musicnews`（可直接掛載於 `https://soundweavers-music.github.io/news/`）。

## 快速開始

### 1. 設定 Gemini API Key
在專案根目錄建立 `.env` 檔案（此檔案已加入 `.gitignore`，不會上傳到 GitHub）：
```env
GEMINI_API_KEY=你的_GEMINI_API_KEY
```

### 2. 手動執行一次完整流程
```powershell
# 完整執行（含 GPT-SoVITS 語音 + 30 秒手繪動畫短影片）
python pipeline/run_daily.py

# 快速測試（跳過 GPT-SoVITS，使用內建氛圍音墊測試影片與網站）
python pipeline/run_daily.py --skip-tts --max-articles 3
```

### 3. 本機預覽網站
```powershell
python -m http.server 8080 --directory site
# 瀏覽器開啟 http://127.0.0.1:8080
```

### 4. 安裝 Git 並推送到 GitHub
若尚未安裝 Git：
```powershell
winget install --id Git.Git -e --source winget
```
接著執行：
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_and_deploy.ps1
```

### 5. 設定每日自動更新（Windows 工作排程器）
```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 -RunTime "08:30"
```

## 整合至 `https://soundweavers-music.github.io/news/`
網站內所有資源皆使用相對路徑（`./data/news.json`、`./media/*.mp4`），因此只要將 `site/` 內容部署至 GitHub Pages 的 `/news` 子路徑（或直接將 `soundweavers-musicnews` 設為子模組/獨立 repo 的 GitHub Pages），即可無縫運作。
