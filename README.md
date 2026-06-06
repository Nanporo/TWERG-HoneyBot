# TWERG-HoneyBot (Discord 蜜罐防護機器人)

TWERG-HoneyBot 是一個專為 地牛記錄小組(TWERG) 設計的蜜罐機器人。

---

## 功能

### 1. 蜜罐頻道防護
- **機制**：任何人只要在蜜罐頻道發言，BOT 將立即發送圖文警告，並將該用戶**永久封鎖 (Ban)**。
- **豁免**：自動忽略伺服器管理員、身份組層級高於 BOT 的身份組，以及在白名單設定內的身份組。

### 2. 陷阱身份組防禦
- **機制**：可設定多個「誘餌身份組」（例如假的管理員標籤）。一旦惡意用戶或掃描腳本在伺服器內 `@提及` 這些身份組，將被視為惡意行為並立即封鎖。

### 3. 控制台日誌轉發
- **機制**：支援 console output，每 3 秒轉發至指定的 console 頻道。
- **監控項目**：所有斜線指令使用、私訊 (DM)、以及 BOT 被 at 都會被記錄 console 輸出。

### 4. 設定面板
- **機制**：無須修改程式碼，伺服器管理員可直接在 Discord 中使用 `/設定` 指令叫出圖形化面板，動態設定：
  - 排除防護的白名單身份組 (可複選)
  - 陷阱身份組 (可複選)
  - Console 系統日誌輸出頻道
  - 開關「封鎖時是否連帶刪除近 30 分鐘內的訊息」

---

## 部署與安裝教學

### 系統需求
- Python 3.12
- `git`
- `discord.py`

### 步驟 1：安裝
在終端機中執行以下指令安裝：
```bash
git clone https://github.com/Nanporo/TWERG-HoneyBot.git
cd TWERG-HoneyBot
pip install discord.py
```

### 步驟 2：設定設定檔 (config.json)
在專案根目錄建立一個 `config.json` 檔案，並填入以下內容：
```json
{
    "TOKEN": "DISCORD_TOKEN_HERE",
    "OWNER_ID": [OWNER_ID_HERE],
    "HONEYPOT_ID": 1512064831912411246,
    "CONSOLE_ID": 填入用來接收日誌的頻道ID_沒有可先填null
}
```
- `OWNER_ID`：必須為陣列 `[]` 格式，填入擁有者的 Discord ID，只有這些人可以使用危險的系統指令 (如 `/restart`)。
- `HONEYPOT_ID`：蜜罐頻道的 ID (數字)。

### 步驟 3：啟動機器人
```bash
python bot.py
```
看到 `登入成功！` 字樣即代表啟動完成。

---

## 使用方法與指令清單

### 伺服器權限設定
為了讓機器人能正常發揮功能，請確保機器人在伺服器中擁有以下權限，且**機器人的身份組層級必須高於一般成員**：
- 封鎖成員 (Ban Members)
- 管理訊息 (Manage Messages)
- 檢視頻道與發送訊息 (針對 console 日誌頻道)

### 管理員指令
僅限擁有「伺服器管理員 (Administrator)」權限的使用者可操作。

- **`/設定`**
  呼叫互動式設定面板。包含白名單、陷阱身份組、日誌頻道等所有防護功能的設定。*(面板停留 5 分鐘後會自動刪除以保持頻道整潔)*

---

## 專案架構

```text
TWERG-HoneyBot/
├── bot.py                     # 主程式入口，負責掛載 Cogs 與初始化
├── config.json                # (需手動建立) 環境設定檔
├── honeypot_settings.json     # (自動生成) 伺服器自訂的動態設定檔
├── README.md                  # 說明文件
└── cogs/                      # 模組化功能資料夾
    ├── console_output.py      # Console 日誌攔截與轉發模組
    ├── honeypot.py            # 蜜罐頻道防禦模組
    ├── owner.py               # 擁有者專屬指令模組
    ├── settings.py            # 控制台 UI 與設定讀寫模組
    └── trap_roles.py          # 陷阱身份組防禦模組
```
