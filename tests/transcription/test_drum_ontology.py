"""Frozen upstream drum taxonomy: no WAV/model downloads, no score tuning."""
from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace

import pretty_midi

from midivolt.drum_ontology import (
    GM_TO_VENDOR, VENDOR_CLASS_NAMES, ONTOLOGY_ID,
    evaluate_common_ontology, mapping_sha256, project_events,
    require_custom_checkpoint, summarize_ontology,
)


def midi(*notes, drums=True):
    result = pretty_midi.PrettyMIDI(initial_tempo=120)
    track = pretty_midi.Instrument(program=0, is_drum=drums)
    for pitch, start in notes:
        track.notes.append(pretty_midi.Note(
            pitch=pitch, start=start, end=start + 0.1, velocity=90
        ))
    result.instruments.append(track)
    return result


class OntologyTests(unittest.TestCase):
    def test_exact_source_table_has_47_gm_entries_and_26_classes(self):
        self.assertEqual(set(GM_TO_VENDOR), set(range(35, 82)))
        self.assertEqual(set(VENDOR_CLASS_NAMES), set(range(35, 61)))
        self.assertEqual(len(mapping_sha256()), 64)

    def test_vendor_58_is_claves_not_gm_58_vibraslap(self):
        self.assertEqual(GM_TO_VENDOR[75], 58)
        self.assertEqual(GM_TO_VENDOR[58], 53)
        self.assertEqual(VENDOR_CLASS_NAMES[58], "Claves")
        self.assertEqual(VENDOR_CLASS_NAMES[53], "Vibraslap")

    def test_vendor_43_is_pedal_hihat_not_gm_43_floor_tom(self):
        self.assertEqual(GM_TO_VENDOR[44], 43)
        self.assertEqual(GM_TO_VENDOR[43], 41)
        self.assertEqual(VENDOR_CLASS_NAMES[43], "Pedal Hi-hat")

    def test_crash_and_ride_have_distinct_shared_classes(self):
        self.assertEqual(GM_TO_VENDOR[49], 46)
        self.assertEqual(GM_TO_VENDOR[57], 46)
        self.assertEqual(GM_TO_VENDOR[51], 48)
        self.assertEqual(GM_TO_VENDOR[53], 48)
        self.assertNotEqual(GM_TO_VENDOR[49], GM_TO_VENDOR[51])

    def test_same_performance_can_be_scored_fairly_under_both_namespaces(self):
        ref = midi((36, 0.2), (44, 0.5), (49, 0.8), (51, 1.1), (75, 1.4))
        dsp = midi((36, 0.2), (44, 0.5), (49, 0.8), (51, 1.1), (75, 1.4))
        vendor = midi((36, 0.2), (43, 0.5), (46, 0.8), (48, 1.1), (58, 1.4))
        first = evaluate_common_ontology(ref, dsp, prediction_namespace="gm")
        second = evaluate_common_ontology(ref, vendor, prediction_namespace="adt_str_custom")
        self.assertEqual(first["micro"]["f1"], 1.0)
        self.assertEqual(first["micro"], second["micro"])
        self.assertEqual(first["mapping_sha256"], second["mapping_sha256"])
        self.assertEqual(first["ontology_id"], ONTOLOGY_ID)

    def test_distinct_gm_kick_classes_not_silently_combined(self):
        ref = midi((36, 0.2))
        prediction = midi((35, 0.2))
        result = evaluate_common_ontology(ref, prediction, prediction_namespace="adt_str_custom")
        self.assertEqual(result["micro"]["tp"], 0)
        self.assertEqual(result["micro"]["fp"], 1)
        self.assertEqual(result["micro"]["fn"], 1)

    def test_simultaneous_merged_notes_are_still_one_to_one(self):
        ref = midi((43, 0.2), (45, 0.2))  # Both map to custom Floor Tom
        predicted = midi((41, 0.2))
        result = evaluate_common_ontology(ref, predicted, prediction_namespace="adt_str_custom")
        self.assertEqual(result["micro"]["tp"], 1)
        self.assertEqual(result["micro"]["fn"], 1)
        self.assertEqual(result["per_class"]["41"]["reference_count"], 2)

    def test_prediction_midi_is_not_mutated_or_relabelled(self):
        raw = midi((58, 0.2), (43, 0.4))
        before = [(x.pitch, x.start) for x in raw.instruments[0].notes]
        evaluate_common_ontology(midi((75, 0.2), (44, 0.4)), raw,
                                 prediction_namespace="adt_str_custom")
        after = [(x.pitch, x.start) for x in raw.instruments[0].notes]
        self.assertEqual(before, after)

    def test_unknown_vendor_pitch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "outside pinned"):
            project_events(midi((99, 0.2)), source_namespace="adt_str_custom")

    def test_unmapped_gm_pitch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no published"):
            project_events(midi((22, 0.2)), source_namespace="gm")

    def test_invalid_or_pitched_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unknown drum pitch namespace"):
            project_events(midi((36, 0.2)), source_namespace="guess")
        with self.assertRaisesRegex(ValueError, "percussion"):
            project_events(midi((36, 0.2), drums=False), source_namespace="gm")

    def test_checkpoint_tokenizer_must_be_verified_at_runtime(self):
        model = SimpleNamespace(tokenizer=SimpleNamespace(ADTOF_mapping=False))
        confirmation = require_custom_checkpoint(model)
        self.assertEqual(confirmation["output_namespace"], "adt_str_custom")
        for invalid in (None, True, "false"):
            with self.assertRaisesRegex(RuntimeError, "tokenizer"):
                require_custom_checkpoint(
                    SimpleNamespace(tokenizer=SimpleNamespace(ADTOF_mapping=invalid))
                )

    def test_song_macro_preserves_independence_from_event_micro(self):
        a = evaluate_common_ontology(
            midi((36, 0.2)), midi((36, 0.2)),
            prediction_namespace="adt_str_custom",
        )
        b = evaluate_common_ontology(
            midi((36, 0.2), (38, 0.4), (42, 0.6)),
            midi((36, 0.2), (35, 0.4), (35, 0.6)),
            prediction_namespace="adt_str_custom",
        )
        result = summarize_ontology([
            {"song_id": "song-a", "ontology_scores": a},
            {"song_id": "song-b", "ontology_scores": b},
        ])
        self.assertEqual(result["song_count"], 2)
        self.assertGreater(result["song_macro_f1"], result["event_micro"]["f1"])
        self.assertEqual(result["event_micro"]["tp"], 2)
        self.assertEqual(result["event_micro"]["fn"], 2)
        self.assertEqual(result["event_micro"]["fp"], 2)

    def test_incompatible_mapping_digest_refuses_aggregation(self):
        a = evaluate_common_ontology(
            midi((36, 0.2)), midi((36, 0.2)), prediction_namespace="gm"
        )
        a["mapping_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Inconsistent ontology"):
            summarize_ontology([{"song_id": "one", "ontology_scores": a}])


if __name__ == "__main__":
    unittest.main()
