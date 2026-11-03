# MIDIVOLT 0.1.0rc1 — 實機測試前最終收斂（2026-11-03）

**狀態：`READY_FOR_REAL_MACHINE_TEST`（僅限本 repo 實際存在的核心 MIDI CLI 範圍）**

- Tested SHA：`d318e2d22ae5613369858d6040499b1d67cf53da`（證據 commit 僅新增 `docs/`，`src/ scripts/ tests/ packaging/` 無差異）
- 起點：遠端 `fix/midivolt-rc-closeout-python313-gates-20261102` @ `b801cc2`（含獨立審計者的 4 個 Cubase 審計修復，已一併重驗）
- 工作分支：`work/midivolt-ready-real-machine-20261103`；未動 main、未用 Actions

## 範圍不符（必讀）
任務提到的 **Verovio 渲染、MusicXML 輸出/讀回、七組 Golden E2E、鋼琴雙譜表測試、Codex 審核結果** 在本 repo 任何分支皆不存在
（README 明載 "no MusicXML export"；`beta_gate.py` 僅存在於舊譜系 PR #9 線，且只是 wheel 發行審計，無 Verovio/MusicXML）。
這些項目 **NOT_APPLICABLE（無對應程式碼）**：未新增功能、未以 mock 冒充。若它們屬於另一個 repo／分支，需提供來源後再收斂。

## 本次修復
| 嚴重度 | 問題 | 修復 |
|---|---|---|
| P1 | 非 Latin-1 軌名（中文、emoji）經 `write_midi` 以 `UnicodeEncodeError` 崩潰 | `io.py` 非 Latin-1 名稱改以 UTF-8 位元組寫入，不改動呼叫者物件；Latin-1 名稱與讀回往返行為不變；有回歸測試（無修復時失敗） |

## 結果
| Gate | 3.11 | 3.12 | 3.13 |
|---|---|---|---|
| 完整 pytest（pass/skip/fail） | 337/4/0 | 332/9/0 | 332/9/0 |
| 七階段 release gate | **PASS_PRE_MACHINE**（官方 bootstrap） | 七階段 PASS（無 expected-head 故整體 BLOCKED，設計如此） | 本輪未重跑；前一輪於 `94081bd` 七階段 PASS |
| 最終 wheel 非 editable 乾淨安裝 + 13/13 CLI + 真 music21 + 工作流探針 + Unicode 軌名實測 | PASS | PASS | PASS |
- 乾淨安裝同時確認 music21 為真實載入（`PASS_REAL_MUSIC21_ACCEPTANCE`，9.9.2）。
- MIDI roundtrip（探針，PPQ 192/480/960，中文＋空白路徑）：tempo／拍號／調號／PPQ／鎖定軌 note、velocity、CC、pitch bend、program、同 tick 次序皆一致；來源雜湊不變；既有輸出不覆寫。
- 已知限制（既有、已載明）：review→approve 輸出不保留 SysEx／文字標記／conductor 軌名；SysEx 僅由 `midivolt-cubase prepare` 路徑保證。
- Verovio／MusicXML／Golden E2E：NOT_APPLICABLE（見上）。Windows 安裝/smoke、Cubase GUI：**NOT_RUN_DEVICE**。`Verify-MIDIVOLT-RC.ps1` 未執行且未經 PowerShell 解析器驗證。

## 產物（`docs/evidence/ready-20261103/`，雜湊見 `SHA256SUMS-evidence.txt`）
- wheel `e19e8530c2c9fd820e5e593478dfe4125b68f5a13f2dd4bb655be8404f63521d`
- Windows ZIP（Python zipfile 建立，非 Compress-Archive）`511b79981a8df25fcd67b5d93c6c96b82c968877f9b30861758af2182b087229`
- `cubase-testkit/`：PPQ 480/960 測試素材與操作說明

## 實機指令
Windows（Python 3.11 x64 + py.exe；解壓 ZIP，先 `Get-FileHash` 核對上表）：
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-MIDIVOLT-RC.ps1 -AllowNetwork
```
Cubase：匯入 `cubase-testkit/03-IMPORT-TO-CUBASE-ppq480.mid`，匯出 `returned-ppq480.mid` 後：
```
midivolt-cubase compare --reference 03-IMPORT-TO-CUBASE-ppq480.mid --returned returned-ppq480.mid --strict
```
