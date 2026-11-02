"""Actual installed MIDIVOLT core property regression, not a substitute for release certification."""
from pathlib import Path
from io import BytesIO
import hashlib, random, copy
import pretty_midi
from midivolt.prompt_music import parse_prompt, generate_sketch, report,PARTS

def canonical(m):
    return [(i.name,i.is_drum,i.program,tuple((n.pitch,n.velocity,round(n.start,6),round(n.end,6)) for n in i.notes)) for i in m.instruments]


def test_full_midi_matrix():
    rng = random.Random(20261102)
    examples=0; complete=0; extended=0
    for key in ('C','C#','Db','D','Eb','E','F','F#','Gb','G','Ab','A','Bb','B'):
     for mode in ('major','minor'):
      for i in range(20):
        bars=rng.choice([1,2,3,4,8,16,32]);bpm=rng.choice([40,41,70,90,110,120,138,171,200,239,240]);parts=tuple(p for p in PARTS if rng.randrange(2)) or ('melody',)
        text=f'full song {bars} bars {key} {mode} {bpm} bpm '+rng.choice(['sparse','rising','syncopated','normal','build tension'])
        seed=rng.randrange(2**32)
        spec=parse_prompt(text,key=key,mode=mode,bars=bars,bpm=bpm,parts=parts,seed=seed)
        one=generate_sketch(spec)
        two=generate_sketch(spec)
        assert canonical(one)==canonical(two),(key,mode,i,'non-deterministic')
        assert len(one.instruments)==len(parts),(key,mode,i,'incorrect tracks')
        assert all(len(x.notes)>0 for x in one.instruments)
        assert all(0<=n.pitch<=127 and 0<n.velocity<=127 and 0<=n.start<n.end for t in one.instruments for n in t.notes)
        buf=BytesIO();one.write(buf);buf.seek(0)
        back=pretty_midi.PrettyMIDI(buf)
        assert len(back.instruments)==len(one.instruments)
        assert [(x.name,x.is_drum,len(x.notes)) for x in back.instruments]==[(x.name,x.is_drum,len(x.notes)) for x in one.instruments]
        assert all(n.end<=bars*(60/bpm)*4+.002 for t in one.instruments for n in t.notes)
        examples+=1
        if i%4==0:
            source=pretty_midi.PrettyMIDI(initial_tempo=bpm)
            inst=pretty_midi.Instrument(program=73,name='Original')
            inst.notes=[pretty_midi.Note(pitch=60,velocity=100,start=0.25,end=0.7)]
            source.instruments.append(inst)
            old=canonical(source)
            ext=generate_sketch(spec,source=source)
            assert canonical(source)==old
            assert canonical(ext)[:len(old)]==old
            assert len(ext.instruments)==len(parts)+len(old)
            assert min(n.start for t in ext.instruments[1:] for n in t.notes)>=source.get_end_time()-1e-6
            extended+=1
        complete+=1
    assert examples == 560 and extended == 140
