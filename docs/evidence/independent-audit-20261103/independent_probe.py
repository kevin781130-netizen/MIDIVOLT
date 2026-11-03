import os, sys, json, subprocess, hashlib
from pathlib import Path
import mido, midivolt, importlib.metadata as md
root=Path('/workspace/audit-results/中文 MIDI fixtures');root.mkdir(exist_ok=True)
bin=Path(sys.executable).parent
report={'python':sys.version,'import':midivolt.__file__,'version':md.version('midivolt'),'entry_points':[e.name for e in md.distribution('midivolt').entry_points], 'cases':[]}
def run(*args):
 r=subprocess.run([str(bin/'midivolt-cubase'),*map(str,args)],capture_output=True,text=True)
 return {'args':list(map(str,args)),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
def events(p):
 m=mido.MidiFile(p);return [[(sum(x.time for x in t[:i+1]), x.copy(time=0).dict()) for i,x in enumerate(t) if x.type!='end_of_track'] for t in m.tracks]
for typ in (0,1):
 p=root/f'type{typ}.mid';out=root/f'prepared{typ}.mid'
 m=mido.MidiFile(type=typ,ticks_per_beat=480); t=mido.MidiTrack();m.tracks.append(t)
 t.extend([mido.MetaMessage('set_tempo',tempo=500000),mido.MetaMessage('set_tempo',tempo=400000),mido.Message('sysex',data=[125,1]),mido.Message('program_change',channel=2,program=10),mido.Message('control_change',channel=2,control=64,value=127),mido.Message('pitchwheel',channel=2,pitch=100),mido.Message('note_on',channel=2,note=60,velocity=90),mido.Message('note_off',channel=2,note=60,time=480),mido.Message('note_on',channel=2,note=60,velocity=70),mido.Message('note_off',channel=2,note=60,time=480),mido.Message('note_on',channel=9,note=36,velocity=90),mido.Message('note_off',channel=9,note=36,time=120),mido.MetaMessage('end_of_track',time=480)])
 m.save(p);h=hashlib.sha256(p.read_bytes()).hexdigest()
 a=run('prepare','--input',p,'--out',out,'--ppq',480); assert a['exit']==0,a
 # Independent readback: every non-EOT event in exact absolute tick multiset.
 from collections import Counter
 canonical=lambda p:Counter((tick,json.dumps(msg,sort_keys=True)) for tr in events(p) for tick,msg in tr)
 assert canonical(p)==canonical(out)
 b=run('compare','--reference',p,'--returned',out,'--strict');assert b['exit']==0,b
 altered=mido.MidiFile(out);tr=altered.tracks[0]; tempos=[i for i,x in enumerate(tr) if x.type=='set_tempo'];tr[tempos[0]],tr[tempos[1]]=tr[tempos[1]],tr[tempos[0]];bad=root/f'bad{typ}.mid';altered.save(bad)
 c=run('compare','--reference',p,'--returned',bad,'--strict');assert c['exit']==3,c
 conflict=run('prepare','--input',p,'--out',out,'--ppq',480);assert conflict['exit']!=0
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h
 report['cases'].append({'type':typ,'prepare':a,'compare':b,'order_rejection':c,'conflict':conflict,'source_sha256':h,'independent_events_equal':True})
Path('/workspace/audit-results/installed-probe.json').write_text(json.dumps(report,indent=2))
print('PASS installed CLI independent MIDI readback and order rejection')
