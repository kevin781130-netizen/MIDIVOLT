"""Model subprocess tests using a tiny fake generator, not pretrained weights."""
import sys
import pretty_midi
import pytest

from midivolt.io import read_midi, write_midi
from midivolt.model_adapters import append_generated_tracks, generate_candidate
from midivolt.review_engine import check_proposal, apply_proposal


def song(path, bpm=70, program=73, start=0.5):
    midi = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    track = pretty_midi.Instrument(program=program, name="Original melody")
    track.notes.append(pretty_midi.Note(78, 65, start, start + .5))
    track.control_changes.append(
        pretty_midi.ControlChange(number=1, value=40, time=start))
    midi.instruments.append(track)
    write_midi(midi, path)
    return path


def upstream(tmp_path, name):
    root = tmp_path / "upstream"
    root.mkdir()
    if name == "text2midi":
        d = root / "model"
        d.mkdir()
        (d / "transformer_model.py").write_text("# dummy upstream")
        ckpt = tmp_path / "weights.bin"
        ckpt.write_bytes(b"weights")
        vocab = tmp_path / "vocab.pkl"
        vocab.write_bytes(b"vocab")
        tokenizer = tmp_path / "t5"
        tokenizer.mkdir()
    else:
        d = root / "anticipation"
        d.mkdir()
        (d / "sample.py").write_text("# dummy upstream")
        ckpt = tmp_path / "model"
        ckpt.mkdir()
        vocab = tokenizer = None
    return root, ckpt, vocab, tokenizer


def dummy_runner(path):
    path.write_text(
        'import argparse,pretty_midi\n'
        'p=argparse.ArgumentParser()\n'
        'p.add_argument("--out",required=True)\n'
        'a,_=p.parse_known_args()\n'
        'm=pretty_midi.PrettyMIDI(initial_tempo=120)\n'
        'i=pretty_midi.Instrument(program=0,name="AI piano")\n'
        'i.notes.append(pretty_midi.Note(80,60,0.5,1.0))\n'
        'm.instruments.append(i)\n'
        'm.write(a.out)\n')
    return path


def test_beat_alignment_does_not_edit_original(tmp_path):
    original_path = song(tmp_path / "original.mid", bpm=70)
    new_path = song(tmp_path / "new.mid", bpm=120, program=0)
    base, generated = read_midi(original_path), read_midi(new_path)
    result = append_generated_tracks(base, generated)
    assert len(result.instruments) == 2
    assert result.instruments[0].notes[0].start == base.instruments[0].notes[0].start
    assert result.instruments[0].control_changes[0].value == 40
    assert result.instruments[1].notes[0].start == pytest.approx(
        base.tick_to_time(base.resolution), abs=1e-7)
    assert result.get_tempo_changes()[1].tolist() == base.get_tempo_changes()[1].tolist()


@pytest.mark.parametrize("model", ["text2midi", "anticipation"])
def test_real_child_process_to_guarded_approval(tmp_path, monkeypatch, model):
    source = song(tmp_path / "source.mid")
    root, ckpt, vocab, t5 = upstream(tmp_path, model)
    fake = dummy_runner(tmp_path / "fake_runner.py")
    monkeypatch.setattr("midivolt.model_adapters._runner_script", lambda _: fake)
    params = dict(
        model=model, python_executable=sys.executable,
        checkout=root, checkpoint=ckpt,
        output_path=tmp_path / "candidate.mid",
        source_path=source, manifest_path=tmp_path / "plan.json",
        locked_tracks=[0],
    )
    if model == "text2midi":
        params.update(prompt="romantic synth flute", vocab_path=vocab, t5_dir=t5)
    else:
        params.update(melody_program=73, seconds=4)
    report = generate_candidate(**params)
    assert report.tracks == 2
    _, review = check_proposal(report.manifest)
    assert review["notes_added"] == 1
    assert review["locked_tracks"] == [0]
    applied = apply_proposal(report.manifest, tmp_path / "approved.mid", approved=True)
    assert len(read_midi(applied["output"]).instruments) == 2
    assert len(read_midi(source).instruments) == 1
    with pytest.raises(FileExistsError):
        generate_candidate(**params)


def test_text_requires_explicit_prompt_and_assets(tmp_path):
    root, ckpt, vocab, t5 = upstream(tmp_path, "text2midi")
    with pytest.raises(ValueError, match="--prompt"):
        generate_candidate(
            model="text2midi", python_executable=sys.executable, checkout=root,
            checkpoint=ckpt, vocab_path=vocab, t5_dir=t5,
            output_path=tmp_path / "candidate.mid", prompt="")
    assert not (tmp_path / "candidate.mid").exists()


def test_ant_model_requires_valid_program_and_source(tmp_path):
    root, ckpt, _, _ = upstream(tmp_path, "anticipation")
    source = song(tmp_path / "source.mid")
    params = dict(
        model="anticipation", python_executable=sys.executable,
        checkout=root, checkpoint=ckpt, source_path=source,
        output_path=tmp_path / "candidate.mid", seconds=3)
    with pytest.raises(ValueError, match="--melody-program"):
        generate_candidate(**params, melody_program=128)
    with pytest.raises(ValueError, match="--lock"):
        generate_candidate(**params, melody_program=73, locked_tracks=[0])


def test_runner_failure_never_publishes_candidate(tmp_path, monkeypatch):
    root, ckpt, vocab, t5 = upstream(tmp_path, "text2midi")
    runner = tmp_path / "fail.py"
    runner.write_text("raise RuntimeError('bad checkpoint')\n")
    monkeypatch.setattr("midivolt.model_adapters._runner_script", lambda _: runner)
    target = tmp_path / "candidate.mid"
    with pytest.raises(RuntimeError, match="inference failed"):
        generate_candidate(
            model="text2midi", python_executable=sys.executable, checkout=root,
            checkpoint=ckpt, vocab_path=vocab, t5_dir=t5,
            output_path=target, prompt="cool ambient beat")
    assert not target.exists()


def test_empty_model_output_rejected(tmp_path):
    original = song(tmp_path / "original.mid")
    with pytest.raises(ValueError, match="no notes"):
        append_generated_tracks(read_midi(original), pretty_midi.PrettyMIDI())
