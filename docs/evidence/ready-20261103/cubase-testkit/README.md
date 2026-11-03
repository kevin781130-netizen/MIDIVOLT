# Cubase 實機 roundtrip 測試素材

素材皆由最終 wheel（非 editable）安裝後的 CLI 產生；含中文軌名、tempo 變化、3/4→7/8、Bb 調號、CC/pitch bend/program change、
conductor SysEx、同 tick 重複音、鼓軌（ch10）。PPQ 480 與 960 各一組。

| 檔案 | 用途 |
|---|---|
| `01-source-ppq*.mid` | 原始來源（不得被修改） |
| `02-approved-ppq*.mid` | review 核准輸出（pretty_midi 序列化；**不含 SysEx／conductor 軌名，為已知限制**） |
| `03-IMPORT-TO-CUBASE-ppq*.mid` | **匯入 Cubase 用**（Type 1，同 PPQ） |
| `03b-source-direct-sysex-ppq*.mid` | 由來源直接 prepare，保留 SysEx；用來單獨檢驗 Cubase 對 SysEx 的處理 |

## 操作（最少）
1. 新專案 → 匯入 `03-IMPORT-TO-CUBASE-ppq480.mid`（選「匯入 Tempo」；專案 PPQ 與檔案一致）→ 播放確認 → 檔案→匯出→MIDI（Type 1、同 PPQ）存成 `returned-ppq480.mid`。
2. 對 960 與 `03b-*` 重複一次（`returned-*.mid`）。
3. 比對（每組一條）：
```
midivolt-cubase compare --reference 03-IMPORT-TO-CUBASE-ppq480.mid --returned returned-ppq480.mid --strict
```
`--strict` 非 0：把差異分為「產品要求保留的事件遺失」（阻擋）與「Cubase 匯出自行改寫」（記錄於證據，不降低門檻）。
將 `returned-*.mid`、比對輸出與 Cubase 版本回傳，狀態才能由 `NOT_RUN_DEVICE` 改為 PASS/FAIL。
