# MIDIVOLT 0.1.0rc1 — 實機前封版收斂（2026-11-02）

**結論：`PRE_DEVICE_RC_READY`**（核心 MIDI CLI RC）。尚無 `DEVICE_ACCEPTED` / `RELEASE_READY` 證據。

- Tested source SHA（所有 Gate 的被測程式碼）：`94081bd55564720474565fb3c06a38fbdcb3c007`
- Evidence commit：本文件所在 commit（僅新增 `docs/` 下證據；相對 tested SHA 無任何 `src/`、`scripts/`、`tests/`、`packaging/` 差異）
- 平台：Linux 6.18 x86_64；Python 3.11.18 / 3.12.3 / 3.13.18；music21 9.9.2、pretty_midi 0.2.11.post0、mido 1.3.3
- 舊 SHA 的 PASS 一律不沿用；先前 `97bcad4` 的結果已在本 SHA 重跑。

## 來源說明
指定支線原 tip `6c40fa0` 是 `737d9a9` 的祖先（缺少 Cubase 同 tick 嚴格比對、真 music21 修復、正式 gate 腳本）。已對該支線做 fast-forward（無合併、無改寫歷史、未動 main），再疊上本次修復。無 `AGENTS.md`。無 PR。

## 本次修復（皆有回歸測試）
| # | 嚴重度 | 問題 | 修復 |
|---|---|---|---|
| 1 | P1 | 真 music21 9.9.2：`Bb7/Eb`（非和弦音低音）使和弦聲部混入低音音級，`accept_music21_core.py` FAIL | `theory.py` 和弦音程取自 slash 前本體，低音走 `bass_pc` |
| 2 | P1 | 缺拍號的來源 MIDI 被 `review propose` 誤判「改變 tempo/meter/key」而拒絕 | `review_engine._global_signature` 缺拍號視為 SMF 預設 4/4（真改拍號仍被拒） |
| 3 | P1 | 模型推論子行程把 venv `python` symlink `resolve()` 到系統 Python，失去 venv 套件 | `model_adapters._interpreter` 不解析 symlink |
| 4 | P1 | 乾淨安裝關卡繼承 `PYTHONPATH=src`，`src/*.egg-info` 讓 pip 略過安裝 | `verify_rc_wheel_install.py` 移除 `PYTHONPATH/PYTHONHOME` |
| 5 | P1 | bootstrap 外層 venv 為複製版，巢狀 venv 落到 PATH 上的 Python 3.13 | `bootstrap_pre_machine_rc.py` 外層 venv 用 symlink |
| 6 | P2(測試) | 3 個 fixture 仍為 `<3.12`；optional 模型環境測試在 3.12/3.13 失敗 | fixture 改 `<3.14`；模型環境測試在非 3.10/3.11 跳過並新增「明確拒絕」測試 |

## Gate 結果
| Gate | 3.11 | 3.12 | 3.13 |
|---|---|---|---|
| 完整 pytest（passed/skipped/failed） | 334 / 4 / 0 | 329 / 9 / 0 | 329 / 9 / 0 |
| Source Contract | PASS | PASS | PASS |
| AI Regression（離線） | PASS | PASS | PASS |
| 真 music21 `PASS_REAL_MUSIC21_ACCEPTANCE` | PASS | PASS | PASS |
| Wheel Build / Integrity / Clean Install（gate 內） | PASS | PASS | PASS |
| 官方 `bootstrap_pre_machine_rc.py --allow-network` | **PASS_PRE_MACHINE**（HEAD 釘住、clean tree） | 不適用※ | 不適用※ |
| 最終 wheel 於全新 venv 非 editable 安裝 + 13/13 CLI `--help` + 真 music21 + 工作流探針 | PASS | PASS | PASS |
| `pip check` / compileall | PASS | PASS | PASS |

※ 官方認證流程刻意只在 3.11 發證（完整產品套件含 optional 模型環境）。3.12/3.13 以同一 `verify_pre_machine_rc.py` 逐階段執行，七階段皆 PASS，整體狀態為 `BLOCKED: EXPECTED_HEAD_REQUIRED_FOR_RELEASE`（未帶 `--expected-head`，設計如此，非失敗）。
Skip 說明：3.11 的 4 個＝「僅非支援版本才跑」×3 + Basic Pitch 真模型 opt-in；3.12/3.13 的 9 個＝上述 + 6 個 optional 模型環境測試（僅 3.10/3.11）。xfail/xpass＝0。
repo 未設定 lint／type check（NOT_CONFIGURED）；以 `compileall` 與 `pip check` 代替並如實標註。

## MIDI 正確性（真實 CLI、乾淨安裝、PPQ 192/480/960、中文＋空白路徑）
`logs/probe-clean-*.json`：生成→review→approve→覆寫拒絕→`cubase check/prepare/compare --strict`。
- PASS：來源雜湊不變；鎖定軌 note/CC/pitch bend/program 語意逐項相同；tempo／拍號／調號／PPQ 保留；中文軌名位元組保留；重複音同 tick 的 note-off→note-on 次序保留；既有輸出不覆寫（exit 2）；Cubase prepare 對「來源」逐事件（含 SysEx、同 tick 次序）嚴格相等。
- 零長音、卡音（無 note_off）：`cubase check/prepare/compare --strict` 與 review propose 均通過（臨時驗證，見修復 #2 前後對照；回歸測試涵蓋缺拍號路徑）。
- **已知限制（文件已載明，非本次引入）**：review→approve 管線經 `pretty_midi` 重新序列化，**不保留 SysEx、文字／標記與 conductor 軌名**（探針 `KNOWN_review_pipeline_*` 為 false）。SysEx 保留僅由 `midivolt-cubase prepare` 路徑保證。若來源含 SysEx，請勿以 review 輸出當作 SysEx 保真檔。未新增功能去改變此行為。

## 正式包
| 檔案 | SHA256 |
|---|---|
| `artifacts/midivolt-0.1.0rc1-py3-none-any.whl`（86,788 B，由 tested SHA 的 `git archive` 建置） | `6e40c50ce6903881dab195baaec4b67f098e63cf3a1a5e07957ee1f49cdf014f` |
| `artifacts/MIDIVOLT-Windows-0.1.0rc1-py311.zip` | `d8b7dbe21a9aa02c423b6b858865fe194dc00d0b771a4405b38fa1cac22535f0` |
版本 0.1.0rc1、13 個 entry points、LICENSE／THIRD_PARTY_NOTICES 皆在 wheel 的 `licenses/`；ZIP 內含 `SHA256SUMS.txt`。ZIP 由 `build_windows_rc_zip.py`（Python zipfile，內容清單同 workflow）建立，**不是** PowerShell `Compress-Archive` 產物。全部證據檔雜湊見 `docs/evidence/closeout-20261102/SHA256SUMS-evidence.txt`。

## NOT_RUN / BLOCKED（誠實清單）
| 項目 | 狀態 | 原因 |
|---|---|---|
| Windows 安裝器與 smoke 實跑 | NOT_RUN | 無 Windows。`Verify-MIDIVOLT-RC.ps1` 為**未執行、未經 PowerShell 解析器驗證**的新腳本（下載官方 pwsh 後的執行被權限分類器拒絕，未繞過） |
| Windows 安裝器僅支援 Python 3.11 | 如實記錄 | `Install-MIDIVOLT.ps1` 寫死 `py -3.11`；套件本體支援 3.11–3.13，Windows 安裝器未擴充（不新增功能） |
| Cubase GUI roundtrip | NOT_RUN | 無 Cubase；mido 往返不代稱 Cubase PASS |
| Basic Pitch（音訊轉譜） | NOT_RUN | optional extra；3.11 限定，未下載權重 |
| 外部 AI Provider／Text2midi／Anticipation／GPU／音樂品質 | NOT_RUN | 無憑證、無權重；不阻塞核心 RC。規則引擎能產生 MIDI **不代表** AI 推論通過 |
| 授權終審、簽章、回滾演練 | NOT_RUN | `RELEASE_READY` 前置 |

## 實機驗收
Windows（Python 3.11 x64＋py.exe；解壓 ZIP，先以 `Get-FileHash` 對照上表）：
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-MIDIVOLT-RC.ps1 -AllowNetwork
```
結果寫入同目錄 `MIDIVOLT-windows-acceptance-result.json`（需 `status: PASS`）。

Cubase（最少操作）：
1. `midivolt-cubase prepare --input approved.mid --out prepared.mid --ppq <原PPQ>`
2. Cubase 匯入 `prepared.mid` → 播放確認 → 匯出 MIDI 為 `returned.mid`（Type 1，同 PPQ）。
3. 比對：
```powershell
midivolt-cubase compare --reference prepared.mid --returned returned.mid --strict
```
`--strict` 非 0 時，請把差異分類為「產品要求保留的事件遺失」（阻擋）與「Cubase 匯出自行改寫」（記錄）；不得降低門檻。
