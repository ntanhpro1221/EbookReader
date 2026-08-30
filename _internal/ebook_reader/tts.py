from __future__ import annotations

import gc
import hashlib
import random
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyworld

from .audio_io import (
    AudioQualityError,
    SegmentDurationPolicy,
    atomic_write_wav,
    is_short_utterance,
    segment_duration_policy,
    vieneu_generation_reached_frame_ceiling,
)
from .database import (
    GENERATION_DELIVERY_CLARITY as DELIVERY_CLARITY,
    GENERATION_DELIVERY_MODES as DELIVERY_MODES,
    GENERATION_DELIVERY_PRIMARY as DELIVERY_PRIMARY,
    PRONUNCIATION_DELIVERY_LOCKED,
    PRONUNCIATION_DELIVERY_SOURCE,
    PRONUNCIATION_DELIVERY_VARIANTS,
    ProjectDB,
)
from .io_utils import stable_int
from .models import (
    CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
    ENGLISH_NAME_PRONUNCIATION_SOURCE,
)
from .resource_manager import trim_process_working_set
from .text_processing import is_standalone_ha_gasp, normalize_vocalizations_for_tts
from .tts_contract import (
    HA_VOCALIZATION_DELIVERY_PROFILE,
    HA_VOCALIZATION_FINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_MAX_NEW_FRAMES,
    HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD,
    HA_VOCALIZATION_MAX_TEMPERATURE,
    HA_VOCALIZATION_MAX_TOP_P,
    HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD,
    HA_VOCALIZATION_PADDING_SAMPLES_FIELD,
    HA_VOCALIZATION_PROFILE_FIELD,
    HA_VOCALIZATION_SAMPLE_RATE_FIELD,
    HA_VOCALIZATION_TARGET_SAMPLES_FIELD,
    HA_VOCALIZATION_TEMPERATURE_FIELD,
    HA_VOCALIZATION_TOP_P_FIELD,
)


FATAL_TTS_MARKERS = (
    "cuda driver",
    "cublas",
    "cudnn",
    "no module named",
    "out of memory",
    "not enough memory",
    "defaultcpuallocator",
    "alloc_cpu.cpp",
    "thiếu vieneu",
    "locked vieneu preset",
    "only vieneu profiles",
)

EMOTION_TEMPERATURE = {
    "neutral": 0.74,
    "happy": 0.84,
    "sad": 0.70,
    "angry": 0.86,
    "afraid": 0.84,
    "surprised": 0.86,
    "tender": 0.70,
    "sarcastic": 0.80,
    "excited": 0.88,
    "tired": 0.68,
    "whispering": 0.66,
}
PACE_TEMPERATURE_OFFSETS = {"slow": -0.03, "normal": 0.0, "fast": 0.04}
PACE_SILENCE_PROPORTIONS = {"slow": 0.20, "normal": 0.15, "fast": 0.08}
WORLD_FRAME_PERIOD_MS = 5.0
WORLD_F0_FLOOR_HZ = 55.0
WORLD_F0_CEIL_HZ = 600.0
WORLD_MIN_VOICED_FRAMES = 3
SHORT_UTTERANCE_MAX_TEMPERATURE = 0.72
SHORT_UTTERANCE_MAX_TOP_P = 0.90
SHORT_UTTERANCE_REPAIR_MAX_FRAMES = 12
MICRO_UTTERANCE_REPAIR_MAX_FRAMES = 6
MICRO_UTTERANCE_MAX_SPEAKABLE_CHARS = 1
GENERATION_CEILING_WARNING = "TTS_GENERATION_CEILING_REACHED"
GENERATION_CEILING_METRIC = "generation_ceiling_hit"
GENERATION_ENDPOINT_ACTIVE_METRIC = "generation_endpoint_active"
GENERATION_FRAME_CAP_FIELD = "generation_frame_cap"
DEFAULT_SEGMENT_ACTIVE_FLOOR_DBFS = -45.0
CLARITY_MAX_TEMPERATURE = 0.78
CLARITY_MAX_TOP_P = 0.90
LOCKED_ENGLISH_NAME_PRONUNCIATION_SOURCES = frozenset(
    {
        ENGLISH_NAME_PRONUNCIATION_SOURCE,
        CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE,
    }
)


def is_fatal_tts_error(error: BaseException) -> bool:
    message = str(error).casefold()
    return any(marker in message for marker in FATAL_TTS_MARKERS)


def _set_generation_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32))
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _row_value(row: Any, key: str, default: Any) -> Any:
    try:
        value = row[key]
    except (IndexError, KeyError, TypeError):
        return default
    return default if value is None else value


def apply_pitch_variant(
    audio: Any,
    sample_rate: int,
    pitch_semitones: int,
    *,
    allow_padding: bool = True,
) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    steps = int(pitch_semitones)
    if steps == 0 or array.size == 0:
        return array
    if sample_rate < 8_000:
        raise ValueError(f"WORLD pitch shifting requires at least 8000 Hz, got {sample_rate}")
    waveform = np.asarray(array, dtype=np.float64)
    f0, time_axis = pyworld.harvest(
        waveform,
        sample_rate,
        f0_floor=WORLD_F0_FLOOR_HZ,
        f0_ceil=WORLD_F0_CEIL_HZ,
        frame_period=WORLD_FRAME_PERIOD_MS,
    )
    f0 = pyworld.stonemask(waveform, f0, time_axis, sample_rate)
    voiced = f0 > 0.0
    if int(np.count_nonzero(voiced)) < WORLD_MIN_VOICED_FRAMES:
        raise ValueError("WORLD could not find enough voiced frames for formant-preserving pitch shift")
    spectral_envelope = pyworld.cheaptrick(waveform, f0, time_axis, sample_rate)
    aperiodicity = pyworld.d4c(waveform, f0, time_axis, sample_rate)
    shifted_f0 = f0.copy()
    shifted_f0[voiced] *= 2.0 ** (float(steps) / 12.0)
    shifted = pyworld.synthesize(
        shifted_f0,
        spectral_envelope,
        aperiodicity,
        sample_rate,
        frame_period=WORLD_FRAME_PERIOD_MS,
    ).astype(np.float32, copy=False)
    if shifted.size >= array.size:
        return shifted[: array.size]
    if not allow_padding:
        raise ValueError(
            "WORLD pitch shift shortened a strict no-padding waveform"
        )
    return np.pad(shifted, (0, array.size - shifted.size)).astype(np.float32, copy=False)


def short_utterance_repair_frame_cap(text: str) -> int | None:
    if not is_short_utterance(text):
        return None
    speakable_chars = sum(char.isalnum() for char in text)
    return (
        MICRO_UTTERANCE_REPAIR_MAX_FRAMES
        if speakable_chars <= MICRO_UTTERANCE_MAX_SPEAKABLE_CHARS
        else SHORT_UTTERANCE_REPAIR_MAX_FRAMES
    )


def _max_new_frames(row: Any, settings: dict[str, Any] | None) -> int:
    policy_frames = segment_duration_policy(
        str(_row_value(row, "text", "")),
        settings,
        row,
    ).generation_max_frames
    persisted_cap = int(_row_value(row, GENERATION_FRAME_CAP_FIELD, 0) or 0)
    return min(policy_frames, persisted_cap) if persisted_cap > 0 else policy_frames


def vieneu_sampling_for_segment(
    row: Any,
    settings: dict[str, Any] | None = None,
    *,
    repair_short_utterance: bool = False,
    delivery_mode: str = DELIVERY_PRIMARY,
    vocalization_delivery_profile: str | None = None,
) -> dict[str, float | int]:
    normalized_delivery = str(delivery_mode).strip().casefold()
    if normalized_delivery not in DELIVERY_MODES:
        raise ValueError(f"Unsupported TTS delivery mode: {delivery_mode}")
    normalized_vocalization_profile = (
        str(vocalization_delivery_profile).strip().casefold()
        if vocalization_delivery_profile is not None
        else None
    )
    if normalized_vocalization_profile not in {
        None,
        HA_VOCALIZATION_DELIVERY_PROFILE,
    }:
        raise ValueError(
            f"Unsupported TTS vocalization delivery profile: {vocalization_delivery_profile}"
        )
    text = str(_row_value(row, "text", ""))
    emotion = str(_row_value(row, "emotion", "neutral"))
    pace = str(_row_value(row, "pace", "normal"))
    intensity = max(0, min(3, int(_row_value(row, "intensity", 0))))
    base_temperature = EMOTION_TEMPERATURE.get(emotion, EMOTION_TEMPERATURE["neutral"])
    temperature = min(
        0.92,
        base_temperature + PACE_TEMPERATURE_OFFSETS.get(pace, 0.0) + 0.015 * intensity,
    )
    top_p = min(0.98, 0.92 + 0.015 * intensity)
    if normalized_delivery == DELIVERY_CLARITY:
        temperature = min(temperature, CLARITY_MAX_TEMPERATURE)
        top_p = min(top_p, CLARITY_MAX_TOP_P)
    max_new_frames = _max_new_frames(row, settings)
    if is_short_utterance(text):
        temperature = min(temperature, SHORT_UTTERANCE_MAX_TEMPERATURE)
        top_p = min(top_p, SHORT_UTTERANCE_MAX_TOP_P)
        warning_codes = str(_row_value(row, "warning_code", "")).split("|")
        if repair_short_utterance and GENERATION_CEILING_WARNING in warning_codes:
            repair_frames = (
                HA_VOCALIZATION_MAX_NEW_FRAMES
                if normalized_vocalization_profile
                == HA_VOCALIZATION_DELIVERY_PROFILE
                else short_utterance_repair_frame_cap(text)
            )
            if repair_frames is not None:
                max_new_frames = min(max_new_frames, repair_frames)
    if normalized_vocalization_profile == HA_VOCALIZATION_DELIVERY_PROFILE:
        temperature = min(temperature, HA_VOCALIZATION_MAX_TEMPERATURE)
        top_p = min(top_p, HA_VOCALIZATION_MAX_TOP_P)
        max_new_frames = min(max_new_frames, HA_VOCALIZATION_MAX_NEW_FRAMES)
    return {
        "temperature": temperature,
        "top_k": 25,
        "top_p": top_p,
        "repetition_penalty": 1.2,
        "silence_p": PACE_SILENCE_PROPORTIONS.get(pace, PACE_SILENCE_PROPORTIONS["normal"]),
        "max_new_frames": max_new_frames,
    }


class VieNeuEngine:
    def __init__(self, settings: dict[str, Any], log: Callable[[str], None]) -> None:
        self.settings = settings
        self.log = log
        self.tts = None
        self.sample_rate = int(settings["tts"]["sample_rate"])
        self.voices: list[str] = []

    def load(self) -> None:
        if self.tts is not None:
            return
        try:
            from vieneu import Vieneu
        except ImportError as exc:
            raise RuntimeError("Thiếu VieNeu; hãy chạy Ebook Reader") from exc
        self.log("Nạp VieNeu-TTS.")
        self.tts = Vieneu(max_batch_size=max(1, int(self.settings["tts"]["batch_size"])))
        raw = list(self.tts.list_preset_voices())
        self.voices = []
        for item in raw:
            if isinstance(item, (tuple, list)) and item:
                voice_id = str((item[1] if len(item) > 1 else item[0]) or item[0]).strip()
            else:
                voice_id = str(item).strip()
            if voice_id and voice_id not in self.voices:
                self.voices.append(voice_id)
        if not self.voices:
            raise RuntimeError("VieNeu không cung cấp preset voice nào")
        self.sample_rate = int(getattr(self.tts, "sample_rate", self.sample_rate))

    def unload(self) -> None:
        had_model = self.tts is not None
        self.tts = None
        self.voices = []
        if not had_model:
            return
        self.release_inference_cache()
        trim_process_working_set()

    @staticmethod
    def release_inference_cache() -> None:
        """Release temporary Python/CUDA allocations after a completed inference unit."""
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def voice_for_profile(self, profile: Any) -> str:
        self.load()
        if str(profile["engine"]) != "vieneu":
            raise AudioQualityError(
                f"Only VieNeu profiles are supported; found {profile['engine']!r} for {profile['voice_key']}"
            )
        preset = str(profile["preset_name"] or "").strip()
        if not preset or preset not in self.voices:
            raise AudioQualityError(
                f"Locked VieNeu preset {preset!r} is unavailable; refusing to change voice silently"
            )
        return preset

    def generate_one(
        self,
        row: Any,
        profile: Any,
        seed: int,
        *,
        sampling: dict[str, float | int] | None = None,
    ) -> np.ndarray:
        self.load()
        _set_generation_seed(seed)
        voice = self.voice_for_profile(profile)
        style = "doc_truyen" if str(row["speaker"]) == "NARRATOR" else "tu_nhien"
        effective_sampling = (
            sampling
            if sampling is not None
            else vieneu_sampling_for_segment(row, self.settings)
        )
        try:
            return np.asarray(
                self.tts.infer(
                    str(row["text"]),
                    voice=voice,
                    style=style,
                    **effective_sampling,
                ),
                dtype=np.float32,
            ).reshape(-1)
        except Exception as exc:  # noqa: BLE001
            raise AudioQualityError(str(exc)) from exc


class TTSCoordinator:
    def __init__(self, settings: dict[str, Any], db: ProjectDB, log: Callable[[str], None]) -> None:
        self.settings = settings
        self.db = db
        self.log = log
        self.vieneu = VieNeuEngine(settings, log)
        self._pronunciation_pattern: re.Pattern[str] | None = None
        self._pronunciation_map: dict[str, str] = {}
        self._pronunciation_metadata: dict[str, Any] = {}
        self._exact_pronunciation_pattern: re.Pattern[str] | None = None
        self._exact_pronunciation_map: dict[str, str] = {}
        self._exact_pronunciation_metadata: dict[str, Any] = {}

    def unload_all(self) -> None:
        self.vieneu.unload()

    def release_inference_cache(self) -> None:
        self.vieneu.release_inference_cache()

    def unload_idle_models(self, keep_engine: str | None = None) -> None:
        if keep_engine != "vieneu":
            self.vieneu.unload()

    def generation_seed(self, row: Any, seed_salt: str = "") -> int:
        profile = self._voice_profile_for_row(row)
        return stable_int(f"segment::{row['stable_id']}::{profile['voice_key']}::{seed_salt}")

    def _voice_profile_for_row(self, row: Any) -> Any:
        if str(_row_value(row, "kind", "narration")) == "thought":
            return self.db.voice_profile_by_key("narrator")
        return self.db.voice_profile(int(row["voice_profile_id"]))

    def locked_voice_provenance(self, row: Any) -> dict[str, int]:
        profile = self._voice_profile_for_row(row)
        return {
            "voice_profile_id": int(profile["id"]),
            "pitch_semitones": int(profile["pitch_semitones"] or 0),
        }

    def _load_pronunciations(self) -> None:
        if self._pronunciation_pattern is None:
            minimum = float(self.settings["analysis"].get("low_confidence_threshold", 0.58))
            pronunciations = self.db.list_pronunciations(minimum)
            exact_pronunciations = [
                item
                for item in pronunciations
                if str(item["source"]) == CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
            ]
            pronunciations = [
                item
                for item in pronunciations
                if str(item["source"]) != CONTEXTUAL_ENGLISH_NAME_PRONUNCIATION_SOURCE
            ]
            self._pronunciation_map = {
                " ".join(str(item["surface"]).casefold().split()): str(item["spoken_form"])
                for item in pronunciations
            }
            self._pronunciation_metadata = {
                " ".join(str(item["surface"]).casefold().split()): item
                for item in pronunciations
            }
            surfaces = [str(item["surface"]) for item in pronunciations]
            self._pronunciation_pattern = (
                re.compile(
                    r"(?<!\w)(?:" + "|".join(re.escape(value) for value in surfaces) + r")(?!\w)",
                    re.IGNORECASE,
                )
                if surfaces
                else re.compile(r"(?!x)x")
            )
            self._exact_pronunciation_map = {
                str(item["surface"]): str(item["spoken_form"])
                for item in exact_pronunciations
            }
            self._exact_pronunciation_metadata = {
                str(item["surface"]): item for item in exact_pronunciations
            }
            exact_surfaces = [str(item["surface"]) for item in exact_pronunciations]
            self._exact_pronunciation_pattern = (
                re.compile(r"(?<!\w)(?:" + "|".join(re.escape(value) for value in exact_surfaces) + r")(?!\w)")
                if exact_surfaces
                else re.compile(r"(?!x)x")
            )

    @staticmethod
    def _source_span(
        origins: list[tuple[int, int]],
        start: int,
        end: int,
    ) -> tuple[int, int]:
        matched_origins = origins[start:end]
        if not matched_origins:
            return start, end
        return min(origin[0] for origin in matched_origins), max(
            origin[1] for origin in matched_origins
        )

    def _substitute_pronunciations(
        self,
        text: str,
        origins: list[tuple[int, int]],
        anchor_tags: list[frozenset[int]],
        pattern: re.Pattern[str],
        pronunciation_map: dict[str, str],
        metadata_map: dict[str, Any],
        *,
        case_sensitive: bool,
        source_text: str,
        anchors: list[dict[str, Any]],
        pronunciation_delivery_variant: str,
    ) -> tuple[str, list[tuple[int, int]], list[frozenset[int]]]:
        output_parts: list[str] = []
        output_origins: list[tuple[int, int]] = []
        output_anchor_tags: list[frozenset[int]] = []
        cursor = 0
        for match in pattern.finditer(text):
            output_parts.append(text[cursor : match.start()])
            output_origins.extend(origins[cursor : match.start()])
            output_anchor_tags.extend(anchor_tags[cursor : match.start()])
            matched_text = match.group(0)
            key = (
                matched_text
                if case_sensitive
                else " ".join(matched_text.casefold().split())
            )
            canonical_replacement = pronunciation_map.get(key, matched_text)
            metadata = metadata_map.get(key)
            locked_english_pronunciation = bool(
                metadata is not None
                and int(_row_value(metadata, "locked", 0)) == 1
                and str(_row_value(metadata, "source", ""))
                in LOCKED_ENGLISH_NAME_PRONUNCIATION_SOURCES
            )
            replacement = (
                matched_text
                if pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_SOURCE
                and locked_english_pronunciation
                else canonical_replacement
            )
            source_start, source_end = self._source_span(
                origins,
                match.start(),
                match.end(),
            )
            replacement_anchor_tags = set().union(*anchor_tags[match.start() : match.end()])
            if (
                not replacement_anchor_tags
                and locked_english_pronunciation
                and (
                    canonical_replacement != matched_text
                    or pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_SOURCE
                )
            ):
                anchor_index = len(anchors)
                replacement_anchor_tags.add(anchor_index)
                anchors.append(
                    {
                        "pronunciation_id": int(metadata["id"]),
                        "surface": str(metadata["surface"]),
                        "normalized_surface": str(metadata["normalized_surface"]),
                        "matched_surface": source_text[source_start:source_end],
                        "spoken_form": replacement,
                        "canonical_spoken_form": str(metadata["spoken_form"]),
                        "pronunciation_delivery_variant": pronunciation_delivery_variant,
                        "source": str(metadata["source"]),
                        "source_start": source_start,
                        "source_end": source_end,
                        "_anchor_index": anchor_index,
                        "_execution_order": len(anchors),
                    }
                )
            output_parts.append(replacement)
            output_origins.extend([(source_start, source_end)] * len(replacement))
            output_anchor_tags.extend(
                [frozenset(replacement_anchor_tags)] * len(replacement)
            )
            cursor = match.end()
        output_parts.append(text[cursor:])
        output_origins.extend(origins[cursor:])
        output_anchor_tags.extend(anchor_tags[cursor:])
        return "".join(output_parts), output_origins, output_anchor_tags

    @staticmethod
    def _private_use_markers(text: str, count: int) -> list[str]:
        occupied = set(text)
        markers: list[str] = []
        for start, end in ((0xF0000, 0xFFFFE), (0x100000, 0x10FFFE)):
            for codepoint in range(start, end):
                marker = chr(codepoint)
                if marker in occupied:
                    continue
                markers.append(marker)
                occupied.add(marker)
                if len(markers) == count:
                    return markers
        raise RuntimeError("Unable to allocate pronunciation anchor markers")

    def _normalize_with_anchor_spans(
        self,
        text: str,
        anchor_tags: list[frozenset[int]],
        anchors: list[dict[str, Any]],
    ) -> str:
        normalized_text = normalize_vocalizations_for_tts(text)
        if not anchors:
            return normalized_text
        positions: dict[int, list[int]] = {
            int(anchor["_anchor_index"]): [] for anchor in anchors
        }
        for position, tags in enumerate(anchor_tags):
            for anchor_index in tags:
                positions[anchor_index].append(position)
        markers = self._private_use_markers(text, len(anchors) * 2)
        marker_events: dict[str, tuple[dict[str, Any], str]] = {}
        boundary_markers: dict[int, list[str]] = {}
        for anchor, start_marker, end_marker in zip(
            anchors,
            markers[::2],
            markers[1::2],
            strict=True,
        ):
            anchor_positions = positions[int(anchor["_anchor_index"])]
            if not anchor_positions:
                raise RuntimeError("Applied pronunciation anchor has no spoken text span")
            start = min(anchor_positions)
            end = max(anchor_positions) + 1
            boundary_markers.setdefault(start, []).append(start_marker)
            boundary_markers.setdefault(end, []).append(end_marker)
            marker_events[start_marker] = (anchor, "start")
            marker_events[end_marker] = (anchor, "end")
        marked_parts: list[str] = []
        for boundary in range(len(text) + 1):
            marked_parts.extend(boundary_markers.get(boundary, ()))
            if boundary < len(text):
                marked_parts.append(text[boundary])
        normalized_marked_text = normalize_vocalizations_for_tts("".join(marked_parts))
        visible_characters: list[str] = []
        for character in normalized_marked_text:
            marker_event = marker_events.get(character)
            if marker_event is None:
                visible_characters.append(character)
                continue
            anchor, boundary = marker_event
            anchor[f"spoken_{boundary}"] = len(visible_characters)
        if "".join(visible_characters) != normalized_text:
            raise RuntimeError("Pronunciation anchor markers changed spoken-text normalization")
        for anchor in anchors:
            if "spoken_start" not in anchor or "spoken_end" not in anchor:
                raise RuntimeError("Pronunciation anchor marker was lost during normalization")
        return normalized_text

    def spoken_text_with_anchors(
        self,
        row: Any,
        *,
        pronunciation_delivery_variant: str = PRONUNCIATION_DELIVERY_LOCKED,
    ) -> tuple[str, list[dict[str, Any]]]:
        normalized_variant = str(pronunciation_delivery_variant).strip().casefold()
        if normalized_variant not in PRONUNCIATION_DELIVERY_VARIANTS:
            raise ValueError("Unsupported pronunciation delivery variant")
        self._load_pronunciations()
        source_text = str(row["text"])
        origins = [(index, index + 1) for index in range(len(source_text))]
        anchor_tags = [frozenset() for _character in source_text]
        anchors: list[dict[str, Any]] = []
        text, origins, anchor_tags = self._substitute_pronunciations(
            source_text,
            origins,
            anchor_tags,
            self._exact_pronunciation_pattern,
            self._exact_pronunciation_map,
            self._exact_pronunciation_metadata,
            case_sensitive=True,
            source_text=source_text,
            anchors=anchors,
            pronunciation_delivery_variant=normalized_variant,
        )
        text, _origins, anchor_tags = self._substitute_pronunciations(
            text,
            origins,
            anchor_tags,
            self._pronunciation_pattern,
            self._pronunciation_map,
            self._pronunciation_metadata,
            case_sensitive=False,
            source_text=source_text,
            anchors=anchors,
            pronunciation_delivery_variant=normalized_variant,
        )
        text = self._normalize_with_anchor_spans(text, anchor_tags, anchors)
        anchors.sort(
            key=lambda item: (
                int(item["source_start"]),
                int(item["source_end"]),
                int(item["_execution_order"]),
            )
        )
        occurrences: dict[int, int] = {}
        for order, anchor in enumerate(anchors, start=1):
            pronunciation_id = int(anchor["pronunciation_id"])
            occurrence = occurrences.get(pronunciation_id, 0) + 1
            occurrences[pronunciation_id] = occurrence
            anchor["occurrence"] = occurrence
            anchor["order"] = order
            del anchor["_anchor_index"]
            del anchor["_execution_order"]
        return text, anchors

    def spoken_text(
        self,
        row: Any,
        *,
        pronunciation_delivery_variant: str = PRONUNCIATION_DELIVERY_LOCKED,
    ) -> str:
        text, _anchors = self.spoken_text_with_anchors(
            row,
            pronunciation_delivery_variant=pronunciation_delivery_variant,
        )
        return text

    def _spoken_row(
        self,
        row: Any,
        *,
        pronunciation_delivery_variant: str = PRONUNCIATION_DELIVERY_LOCKED,
    ) -> dict[str, Any]:
        result = dict(row)
        result["text"] = self.spoken_text(
            row,
            pronunciation_delivery_variant=pronunciation_delivery_variant,
        )
        if str(_row_value(row, "kind", "narration")) == "thought":
            narrator_profile = self.db.voice_profile_by_key("narrator")
            result["speaker"] = "NARRATOR"
            result["voice_profile_id"] = int(narrator_profile["id"])
        return result

    def prepare_voice_presets(self) -> None:
        self.vieneu.load()
        profiles = self.db.list_voice_profiles()
        for profile in profiles:
            self.vieneu.voice_for_profile(profile)
        self.log(f"Đã xác minh {len(profiles)} voice profile VieNeu đã khóa.")

    def synthesize_atomic(
        self,
        row: Any,
        output: Path,
        seed_salt: str = "",
        *,
        repair_short_utterance: bool = False,
        delivery_mode: str = DELIVERY_PRIMARY,
        pronunciation_delivery_variant: str = PRONUNCIATION_DELIVERY_LOCKED,
    ) -> tuple[str, dict[str, Any], int]:
        try:
            profile = self._voice_profile_for_row(row)
            seed = self.generation_seed(row, seed_salt)
            normalized_pronunciation_variant = str(
                pronunciation_delivery_variant
            ).strip().casefold()
            if normalized_pronunciation_variant not in PRONUNCIATION_DELIVERY_VARIANTS:
                raise ValueError("Unsupported pronunciation delivery variant")
            spoken_row = self._spoken_row(
                row,
                pronunciation_delivery_variant=normalized_pronunciation_variant,
            )
            vocalization_delivery_profile = (
                HA_VOCALIZATION_DELIVERY_PROFILE
                if is_standalone_ha_gasp(str(row["text"]))
                else None
            )
            sampling = vieneu_sampling_for_segment(
                spoken_row,
                self.settings,
                repair_short_utterance=repair_short_utterance,
                delivery_mode=delivery_mode,
                vocalization_delivery_profile=vocalization_delivery_profile,
            )
            audio = self.vieneu.generate_one(
                spoken_row,
                profile,
                seed,
                sampling=sampling,
            )
            raw_vocalization_samples = (
                int(np.asarray(audio).reshape(-1).size)
                if vocalization_delivery_profile
                == HA_VOCALIZATION_DELIVERY_PROFILE
                else None
            )
            duration_policy = segment_duration_policy(
                str(spoken_row["text"]),
                self.settings,
                spoken_row,
            )
            effective_generation_policy = SegmentDurationPolicy(
                generation_max_frames=int(sampling["max_new_frames"]),
                validation_max_seconds=duration_policy.validation_max_seconds,
            )
            generation_ceiling_hit = (
                is_short_utterance(str(spoken_row["text"]))
                and vieneu_generation_reached_frame_ceiling(audio, effective_generation_policy)
            )
            pitch_steps = int(_row_value(profile, "pitch_semitones", 0))
            pitch_variant_skipped = False
            try:
                if (
                    vocalization_delivery_profile
                    == HA_VOCALIZATION_DELIVERY_PROFILE
                ):
                    pitched_audio = apply_pitch_variant(
                        audio,
                        self.vieneu.sample_rate,
                        pitch_steps,
                        allow_padding=False,
                    )
                    if (
                        int(np.asarray(pitched_audio).reshape(-1).size)
                        != raw_vocalization_samples
                    ):
                        raise ValueError(
                            "Ha vocalization pitch variant changed the raw sample count"
                        )
                else:
                    pitched_audio = apply_pitch_variant(
                        audio,
                        self.vieneu.sample_rate,
                        pitch_steps,
                    )
                audio = pitched_audio
            except Exception as exc:  # noqa: BLE001
                # Pitch is optional voice diversification. The original waveform still contains
                # every spoken word, so preserve it instead of failing or retrying the whole TTS.
                pitch_variant_skipped = True
                self.log(
                    f"Bỏ biến thể cao độ {pitch_steps:+d} cho segment {row['stable_id']} "
                    f"vì xử lý pitch lỗi: {exc}"
                )
            vocalization_provenance: dict[str, Any] = {}
            if vocalization_delivery_profile == HA_VOCALIZATION_DELIVERY_PROFILE:
                audio_array = np.asarray(audio, dtype=np.float32).reshape(-1)
                audio = audio_array
                sample_rate = int(self.vieneu.sample_rate)
                original_samples = int(raw_vocalization_samples or 0)
                final_samples = int(audio_array.size)
                if original_samples <= 0 or final_samples != original_samples:
                    raise AudioQualityError(
                        "Ha vocalization must preserve its raw no-padding sample count"
                    )
                vocalization_provenance.update(
                    {
                        HA_VOCALIZATION_PROFILE_FIELD: HA_VOCALIZATION_DELIVERY_PROFILE,
                        HA_VOCALIZATION_TEMPERATURE_FIELD: float(
                            sampling["temperature"]
                        ),
                        HA_VOCALIZATION_TOP_P_FIELD: float(sampling["top_p"]),
                        HA_VOCALIZATION_MAX_NEW_FRAMES_FIELD: int(
                            sampling["max_new_frames"]
                        ),
                        HA_VOCALIZATION_SAMPLE_RATE_FIELD: sample_rate,
                        HA_VOCALIZATION_ORIGINAL_SAMPLES_FIELD: original_samples,
                        HA_VOCALIZATION_TARGET_SAMPLES_FIELD: original_samples,
                        HA_VOCALIZATION_PADDING_SAMPLES_FIELD: 0,
                        HA_VOCALIZATION_FINAL_SAMPLES_FIELD: final_samples,
                    }
                )
            checksum, metrics = atomic_write_wav(
                output,
                audio,
                self.vieneu.sample_rate,
                str(spoken_row["text"]),
                self.settings,
                segment=spoken_row,
            )
            metrics["pitch_variant_skipped"] = float(pitch_variant_skipped)
            metrics["pitch_variant_mixed"] = 0.0
            metrics["tts_delivery_mode"] = str(delivery_mode).strip().casefold()
            metrics["pronunciation_delivery_variant"] = normalized_pronunciation_variant
            metrics["spoken_text_sha256"] = hashlib.sha256(
                str(spoken_row["text"]).encode("utf-8")
            ).hexdigest()
            metrics["voice_profile_id"] = int(profile["id"])
            metrics["pitch_semitones"] = pitch_steps
            metrics["effective_pitch_semitones"] = (
                0 if pitch_variant_skipped else pitch_steps
            )
            metrics.update(vocalization_provenance)
            if generation_ceiling_hit or (
                vocalization_delivery_profile == HA_VOCALIZATION_DELIVERY_PROFILE
            ):
                # This compares the trailing RMS of the levelled WAV, so it must use
                # the endpoint floor that tracks the loudness anchors, not the active
                # floor, which is measured on the raw waveform before any gain.
                audio_settings = self.settings.get("audio", {})
                endpoint_floor_dbfs = float(
                    audio_settings.get(
                        "segment_endpoint_floor_dbfs",
                        audio_settings.get(
                            "segment_active_floor_dbfs",
                            DEFAULT_SEGMENT_ACTIVE_FLOOR_DBFS,
                        ),
                    )
                )
                endpoint_floor = 10.0 ** (endpoint_floor_dbfs / 20.0)
                endpoint_active = float(
                    float(metrics.get("trailing_rms", 0.0)) > endpoint_floor
                )
                metrics[GENERATION_ENDPOINT_ACTIVE_METRIC] = endpoint_active
                metrics["generation_endpoint_floor_dbfs"] = endpoint_floor_dbfs
            if generation_ceiling_hit:
                metrics[GENERATION_CEILING_METRIC] = 1.0
            return checksum, metrics, seed
        finally:
            # VieNeu's PyTorch backend may retain allocator cache after returning a NumPy waveform.
            # The WAV is already committed (or the attempt has failed), so this is a safe boundary.
            self.release_inference_cache()
