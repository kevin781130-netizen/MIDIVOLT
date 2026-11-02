"""真實 CLI 工作流探針：生成→review→approve→Cubase prepare→strict compare，
並以 mido 逐事件（絕對 tick、含同 tick 順序）比對來源與輸出。
用法：<venv>/bin/python midi_workflow_probe.py <venv-bin-dir> <output-json>
只使用已安裝的 console scripts（不經 PYTHONPATH）。"""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
import mido

BIN = Path(sys.argv[1]); OUT = Path(sys.argv[2])
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(name, *a):
    r = subprocess.run([str(BIN / name), *map(str, a)], capture_output=True, text=True, encoding="utf-8")
    return {"cmd": f"{name} {' '.join(map(str, a))}", "exit": r.returncode,
            "stdout": r.stdout[-600:], "stderr": r.stderr[-600:]}

def build_source(path, ppq):
    mid = mido.MidiFile(type=1, ticks_per_beat=ppq, charset="utf-8")
    t0 = mido.MidiTrack(); mid.tracks.append(t0)
    t0 += [mido.MetaMessage("track_name", name="指揮 Conductor", time=0),
           mido.MetaMessage("time_signature", numerator=3, denominator=4, time=0),
           mido.MetaMessage("key_signature", key="Bb", time=0),
           mido.MetaMessage("set_tempo", tempo=500000, time=0),
           mido.Message("sysex", data=[0x7D, 0x01, 0x02], time=0),
           mido.MetaMessage("set_tempo", tempo=400000, time=4 * ppq),
           mido.MetaMessage("time_signature", numerator=7, denominator=8, time=ppq),
           mido.MetaMessage("end_of_track", time=0)]
    t1 = mido.MidiTrack(); mid.tracks.append(t1)
    t1 += [mido.MetaMessage("track_name", name="旋律 Lead", time=0),
           mido.Message("program_change", channel=0, program=73, time=0),
           mido.Message("control_change", channel=0, control=7, value=100, time=0),
           mido.Message("control_change", channel=0, control=64, value=127, time=0),
           mido.Message("pitchwheel", channel=0, pitch=2048, time=0),
           mido.Message("note_on", channel=0, note=60, velocity=90, time=0),
           # 同 tick：note_off 與下一個重複音 note_on
           mido.Message("note_off", channel=0, note=60, velocity=0, time=ppq),
           mido.Message("note_on", channel=0, note=60, velocity=80, time=0),
           mido.Message("pitchwheel", channel=0, pitch=-1024, time=ppq // 2),
           mido.Message("note_off", channel=0, note=60, velocity=0, time=ppq // 2),
           mido.Message("control_change", channel=0, control=64, value=0, time=0),
           mido.Message("note_on", channel=0, note=64, velocity=70, time=ppq),
           mido.Message("note_off", channel=0, note=64, velocity=0, time=ppq),
           mido.MetaMessage("end_of_track", time=0)]
    t2 = mido.MidiTrack(); mid.tracks.append(t2)
    t2 += [mido.MetaMessage("track_name", name="鼓組 Drums", time=0)]
    for i in range(4):
        t2 += [mido.Message("note_on", channel=9, note=36 if i % 2 == 0 else 38, velocity=100, time=0 if i == 0 else ppq // 2),
               mido.Message("note_off", channel=9, note=36 if i % 2 == 0 else 38, velocity=0, time=ppq // 4)]
    t2 += [mido.MetaMessage("end_of_track", time=0)]
    mid.save(path)

def events(path):
    mid = mido.MidiFile(path, charset="utf-8"); out = {}
    for i, tr in enumerate(mid.tracks):
        t = 0; name = None; ev = []
        for m in tr:
            t += m.time
            if m.type == "track_name": name = m.name
            if m.type == "end_of_track": continue
            ev.append((t, str(m.copy(time=0))))
        out[name or f"track{i}"] = ev
    return mid.ticks_per_beat, mid.type, out

report = {"cases": []}
for ppq in (480, 960, 192):
    with tempfile.TemporaryDirectory(prefix="中文 目錄 空白 ") as d:
        d = Path(d); case = {"ppq": ppq, "dir": str(d), "steps": []}
        src, cand, man, appr, cub = (d / n for n in ("來源 source.mid", "候選 candidate.mid", "plan 計畫.json", "核准 approved.mid", "cubase 輸出.mid"))
        build_source(src, ppq); src_hash = sha(src)
        steps = case["steps"]
        steps.append(run("midivolt-review", "propose", "--input", src, "--chords", "Bbmaj7 Ebm7 C7/Bb Bb7/Eb Dbm7b5",
                         "--candidate-out", cand, "--manifest", man, "--lock", 0, "--lock", 1))
        steps.append(run("midivolt-review", "preview", "--manifest", man))
        steps.append(run("midivolt-review", "apply", "--manifest", man, "--out", appr, "--approve"))
        # 既有輸出不覆寫、未核准不寫出
        steps.append({"expect_nonzero": True, **run("midivolt-review", "apply", "--manifest", man, "--out", appr, "--approve")})
        steps.append(run("midivolt-cubase", "check", "--input", appr))
        steps.append(run("midivolt-cubase", "prepare", "--input", appr, "--out", cub, "--ppq", ppq))
        steps.append(run("midivolt-cubase", "compare", "--reference", appr, "--returned", cub, "--strict"))
        # A) review 管線（pretty_midi 序列化）語意層比對：被鎖定軌道與全域事件必須一致
        import pretty_midi
        def sem(path):
            m = pretty_midi.PrettyMIDI(str(path)); out = {"res": m.resolution,
                "tempo": [(round(t, 6), round(q, 6)) for t, q in zip(*m.get_tempo_changes())],
                "ts": [(x.numerator, x.denominator, round(x.time, 6)) for x in m.time_signature_changes],
                "key": [(x.key_number, round(x.time, 6)) for x in m.key_signature_changes], "inst": {}}
            for i in m.instruments:
                out["inst"][i.name] = {"program": i.program, "drum": i.is_drum,
                    "notes": sorted((round(n.start, 6), round(n.end, 6), n.pitch, n.velocity) for n in i.notes),
                    "cc": sorted((round(c.time, 6), c.number, c.value) for c in i.control_changes),
                    "bend": sorted((round(b.time, 6), b.pitch) for b in i.pitch_bends)}
            return out
        a_sem, s_sem = sem(appr), sem(src)
        checks = {"source_hash_unchanged": sha(src) == src_hash,
                  "review_global_events_preserved": all(a_sem[k] == s_sem[k] for k in ("res", "tempo", "ts", "key"))}
        for name, info in s_sem["inst"].items():
            checks[f"review_locked_track_semantics[{name}]"] = a_sem["inst"].get(name) == info
        checks["review_added_tracks"] = sorted(set(a_sem["inst"]) - set(s_sem["inst"]))
        _, _, s_ev = events(src); _, _, a_ev = events(appr)
        # 已知（文件已載明）review 管線限制：SysEx 與 conductor 軌名不由 pretty_midi 保留
        checks["KNOWN_review_pipeline_sysex_kept"] = any("sysex" in e for ev in a_ev.values() for _, e in ev)
        checks["KNOWN_review_pipeline_conductor_name_kept"] = "指揮 Conductor" in a_ev
        # B) 直接對「來源」做 Cubase prepare：逐事件（絕對 tick、同 tick 次序、SysEx）嚴格比對
        cub2 = d / "cubase 來源直出.mid"
        steps.append(run("midivolt-cubase", "prepare", "--input", src, "--out", cub2, "--ppq", ppq))
        steps.append(run("midivolt-cubase", "compare", "--reference", src, "--returned", cub2, "--strict"))
        p_ppq, p_type, p_ev = events(cub2)
        flat = lambda evs: sorted(str((t, e)) for ev in evs.values() for t, e in ev)
        checks["cubase_prepare_source_raw_events_equal"] = flat(s_ev) == flat(p_ev)
        checks["cubase_prepare_source_sysex_kept"] = any("sysex" in e for ev in p_ev.values() for _, e in ev)
        lane = lambda evs, n: [x for x in evs.get(n, [])]
        checks["cubase_prepare_lead_lane_order_identical"] = lane(s_ev, "旋律 Lead") == lane(p_ev, "旋律 Lead")
        checks["cubase_prepare_ppq_type"] = [p_ppq, p_type]
        c_ppq, c_type, c_ev = events(cub)
        checks["approved_to_cubase_event_multiset_equal"] = flat(a_ev) == flat(c_ev)
        case["checks"] = checks
        case["hashes"] = {"source": src_hash, "approved": sha(appr), "cubase_prepared": sha(cub)}
        report["cases"].append(case)

def ok(c):
    st = c["steps"]
    good = all(x["exit"] == 0 for x in st if not x.get("expect_nonzero")) and st[3]["exit"] != 0
    k = c["checks"]
    must = [v for n, v in k.items() if n.startswith(("review_locked_track_semantics", "cubase_prepare_source_raw", "cubase_prepare_source_sysex",
            "cubase_prepare_lead", "approved_to_cubase")) or n in ("source_hash_unchanged", "review_global_events_preserved")]
    return good and all(must)
report["status"] = "PASS" if all(ok(c) for c in report["cases"]) else "FAIL"
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print(report["status"])
for c in report["cases"]:
    print(c["ppq"], [x["exit"] for x in c["steps"]], c["checks"])
