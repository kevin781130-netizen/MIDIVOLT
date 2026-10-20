# MIDIVOLT Model Hub v0.1

**First milestone: local-first catalog, read-only HF discovery, version/size/license preview,
read-only Windows setup doctor, and opt-in verified asset download.**

This release does not install Python, PyTorch, model code, checkpoints,
tokenizers, or drivers automatically. It does not execute a downloaded file.
The existing Text2midi/Anticipatory runners stay in separate Python environments.

## How it works

```powershell
pip install -e ".[hub,dev]"

# Guaranteed offline, using the two curated models:
midivolt-hub catalog
midivolt-hub search midi
midivolt-hub inspect text2midi
midivolt-hub inspect anticipation

# Explicit opt-in internet read-only queries:
midivolt-hub inspect text2midi --online
midivolt-hub inspect anticipation --online
midivolt-hub search "symbolic music midi" --online --limit 10
```

`inspect --online` prints the remote model license, immutable **40-character
revision commit SHA**, file names, known sizes and digests. It also shows
whether the **model card currently says** Apache-2.0. This is a model-card claim,
not comprehensive legal verification. Third-party dependencies and source
dataset rights need separate audit.

`search --online` can display new HF models, **but cannot download arbitrary
search results**. The download allowlist remains limited to two specifically
reviewed repositories. Files outside that allowlist (such as Text2midi's
`soundfont.sf2`) are intentionally excluded.

## Deliberate single-file download

Copy the exact 40-character revision shown by `inspect --online`.
Choose an existing local assets folder:

```powershell
mkdir C:\MIDIVOLT\Models\anticipation
midivolt-hub download anticipation --file config.json --revision YOUR40CHARCOMMITSHA --dest "C:\MIDIVOLT\Models\anticipation" --accept-license apache-2.0 --confirm-download
```

The file is staged in the destination filesystem and checked against remote
file size and LFS SHA256 or Git object SHA1 before it is atomically published.
Existing files are never overwritten. A missing digest or unknown file size
**blocks** the download rather than skipping integrity verification.

Model `.bin` and `.pkl` files are **unsafe serialization formats**. They require
an additional opt-in **after** source/provenance review:

```powershell
midivolt-hub download anticipation --file pytorch_model.bin --revision YOUR40CHARCOMMITSHA --dest "C:\MIDIVOLT\Models\anticipation" --accept-license apache-2.0 --confirm-download --allow-unsafe-format
```

Default max single-file size: 2,000 MB, configurable via `--max-mb`.
No bulk/automatic weight installation; run one explicit command per file.
Official Hugging Face client is an **optional** dependency and may cache bytes
in the local temporary download area. This workflow is not a sandbox against
malicious upstream code. Do not execute untrusted checkpoints/pickle as admin.

## Read-only setup doctor

```powershell
midivolt-hub doctor text2midi --python "C:\models\text2midi\.venv\Scripts\python.exe" --checkout "C:\models\Text2midi" --checkpoint "C:\models\text2midi-assets\pytorch_model.bin" --vocab "C:\models\text2midi-assets\vocab_remi.pkl" --t5-dir "C:\models\flan-t5-tokenizer"
midivolt-hub doctor anticipation --python "C:\models\anticipation\.venv\Scripts\python.exe" --checkout "C:\models\anticipation" --checkpoint "C:\MIDIVOLT\Models\anticipation"
```

Doctor checks paths, the expected upstream source file and required
checkpoint assets; it **does not** execute an arbitrary supplied Python binary.
A green filesystem report is **not** proof of working CUDA/Windows drivers,
PyTorch, tokenizer compatibility, or valid trained weights.

After the doctor, run `midivolt-model ...` as documented in
[model-adapters.md](model-adapters.md), followed by
`midivolt-review preview` and `midivolt-review apply --approve`.

## Model catalog and rights boundary

- **AMAAI-Lab Text2midi**: [MIT source](https://github.com/AMAAI-Lab/Text2midi),
  [HF model card](https://huggingface.co/amaai-lab/text2midi) stating Apache-2.0.
  Allowlisted: `pytorch_model.bin`, `vocab_remi.pkl`, `README.md`.
  Also requires separate FLAN-T5 tokenizer and trusted local upstream checkout.
- **Stanford Anticipatory Music Transformer**:
  [Apache-2.0 source](https://github.com/jthickstun/anticipation),
  [HF model card](https://huggingface.co/stanford-crfm/music-medium-800k)
  stating Apache-2.0. Allowlisted: `config.json`, `pytorch_model.bin`,
  `README.md`. Requires separate upstream checkout and runtime.

Neither weights nor pretrained models have been installed or invoked by this PR.
Unit tests mock HF metadata/download operations; **live HF download, GPU
inference, MIDI quality, Cubase and Windows E2E acceptance remain unverified**.

Run `python -m pytest -q tests/test_model_hub.py` for offline checks. 
