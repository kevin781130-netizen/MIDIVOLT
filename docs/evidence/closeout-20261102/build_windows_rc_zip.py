"""在無 Windows／無 GitHub Actions 的環境，依 .github/workflows/windows-rc.yml 的同一內容清單
建立 Windows RC ZIP（wheel + 安裝/smoke/驗收腳本 + 授權文件 + SHA256SUMS.txt），輸出可重現。
用法：python build_windows_rc_zip.py <wheel> <repo_root> <out_dir>
注意：此 ZIP 由 Python zipfile 建立（非 PowerShell Compress-Archive）；內容清單相同。"""
import hashlib, subprocess, sys, zipfile
from pathlib import Path

wheel, root, out = (Path(a).resolve() for a in sys.argv[1:4])
out.mkdir(parents=True, exist_ok=True)
epoch = int(subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct"], capture_output=True, text=True, check=True).stdout)
stamp = tuple(__import__("time").gmtime(epoch)[:6])
members = {wheel.name: wheel}
for name in ("Install-MIDIVOLT.ps1", "Smoke-MIDIVOLT.ps1", "Verify-MIDIVOLT-RC.ps1", "README-Windows.txt"):
    members[name] = root / "packaging/windows" / name
members["LICENSE"] = root / "LICENSE"
members["THIRD_PARTY_NOTICES.md"] = root / "THIRD_PARTY_NOTICES.md"
sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {n}\n" for n, p in sorted(members.items()))
zip_path = out / "MIDIVOLT-Windows-0.1.0rc1-py311.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for n, p in sorted(members.items()):
        info = zipfile.ZipInfo(n, stamp); info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o644 << 16
        z.writestr(info, p.read_bytes())
    info = zipfile.ZipInfo("SHA256SUMS.txt", stamp); info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o644 << 16
    z.writestr(info, sums)
digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
(out / (zip_path.name + ".sha256")).write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
print(digest, zip_path)
