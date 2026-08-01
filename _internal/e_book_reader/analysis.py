from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from typing import Any, Callable

import requests

from .database import ProjectDB


ALLOWED_KINDS = {"narration", "dialogue", "thought"}
ALLOWED_GENDERS = {"male", "female", "unknown"}
ALLOWED_AGES = {"child", "teen", "young", "adult", "elderly", "unknown"}
ALLOWED_EMOTIONS = {
    "neutral", "happy", "sad", "angry", "afraid", "surprised", "tender",
    "sarcastic", "excited", "tired", "whispering",
}
ALLOWED_PACES = {"slow", "normal", "fast"}
ALLOWED_VOLUMES = {"soft", "normal", "loud"}


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": sorted(ALLOWED_KINDS)},
                    "speaker": {"type": "string"},
                    "gender": {"type": "string", "enum": sorted(ALLOWED_GENDERS)},
                    "age": {"type": "string", "enum": sorted(ALLOWED_AGES)},
                    "emotion": {"type": "string", "enum": sorted(ALLOWED_EMOTIONS)},
                    "intensity": {"type": "integer", "minimum": 0, "maximum": 3},
                    "pace": {"type": "string", "enum": sorted(ALLOWED_PACES)},
                    "volume": {"type": "string", "enum": sorted(ALLOWED_VOLUMES)},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "personality_hint": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": [
                    "id", "kind", "speaker", "gender", "age", "emotion", "intensity",
                    "pace", "volume", "confidence", "personality_hint", "notes",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """Bạn là đạo diễn audiobook tiếng Việt và biên tập viên light novel.
Phân tích từng đoạn theo đúng ID. Không hỏi người dùng và không bỏ sót ID.

Quy tắc:
1. Lời kể dùng speaker=NARRATOR.
2. Hội thoại dùng tên nhân vật nhất quán với danh sách đã biết; nếu thực sự không chắc dùng UNKNOWN.
3. Độc thoại nội tâm dùng kind=thought và speaker là nhân vật đang nghĩ nếu suy ra được.
4. Không sửa văn bản. Không bịa nhân vật chỉ vì đại từ hắn/cô ấy/nàng.
5. Cảm xúc phải tiết chế; intensity=3 chỉ dùng ở cao trào rõ ràng.
6. gender/age mô tả người nói, NARRATOR dùng unknown.
7. Trả JSON đúng schema, không có văn bản bên ngoài JSON.
"""


RECONCILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["canonical", "aliases", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["groups"],
    "additionalProperties": False,
}


def _safe_choice(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _heuristic(row: Any) -> dict[str, Any]:
    text = str(row["text"])
    lowered = text.casefold()
    kind = str(row["kind_hint"])
    speaker = "NARRATOR" if kind == "narration" else "UNKNOWN"
    emotion, intensity, pace, volume = "neutral", 1, "normal", "normal"
    if any(word in lowered for word in ("khóc", "nước mắt", "đau lòng", "buồn", "tuyệt vọng")):
        emotion, pace, volume = "sad", "slow", "soft"
    elif any(word in lowered for word in ("giận", "tức", "quát", "gầm", "đồ khốn")):
        emotion, intensity, volume = "angry", 2, "loud"
    elif any(word in lowered for word in ("sợ", "run rẩy", "hoảng", "kinh hãi")):
        emotion, pace = "afraid", "fast"
    elif any(word in lowered for word in ("cười", "vui", "hạnh phúc", "mừng")):
        emotion = "happy"
    return {
        "id": row["stable_id"],
        "kind": kind,
        "speaker": speaker,
        "gender": "unknown",
        "age": "unknown",
        "emotion": emotion,
        "intensity": intensity,
        "pace": pace,
        "volume": volume,
        "confidence": 0.25,
        "personality_hint": "",
        "notes": "heuristic fallback",
    }


def _validate(group: list[Any], payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected = {str(row["stable_id"]) for row in group}
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("segments", []):
        seg_id = str(item.get("id", ""))
        if seg_id not in expected or seg_id in result:
            continue
        kind = _safe_choice(item.get("kind"), ALLOWED_KINDS, "narration")
        speaker = str(item.get("speaker") or "UNKNOWN").strip()[:120] or "UNKNOWN"
        if kind == "narration":
            speaker = "NARRATOR"
        result[seg_id] = {
            "kind": kind,
            "speaker": speaker,
            "gender": _safe_choice(item.get("gender"), ALLOWED_GENDERS, "unknown"),
            "age": _safe_choice(item.get("age"), ALLOWED_AGES, "unknown"),
            "emotion": _safe_choice(item.get("emotion"), ALLOWED_EMOTIONS, "neutral"),
            "intensity": max(0, min(3, int(item.get("intensity", 1)))),
            "pace": _safe_choice(item.get("pace"), ALLOWED_PACES, "normal"),
            "volume": _safe_choice(item.get("volume"), ALLOWED_VOLUMES, "normal"),
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
            "personality_hint": str(item.get("personality_hint", ""))[:300],
            "notes": str(item.get("notes", ""))[:500],
        }
    return result


class OllamaBookAnalyzer:
    def __init__(self, settings: dict[str, Any], db: ProjectDB, log: Callable[[str], None]) -> None:
        self.full_settings = settings
        self.settings = settings["analysis"]
        self.allow_downloads = bool(settings.get("safety", {}).get("allow_network_downloads_during_job", False))
        self.db = db
        self.log = log
        self.base_url = str(self.settings["base_url"]).rstrip("/")
        self.model = str(self.settings["model"])
        self.session = requests.Session()
        existing = self.db.list_segments(statuses=("analyzed", "warning", "signal_passed", "asr_passed", "verified"))
        self._speaker_counts = Counter(
            str(row["speaker"]) for row in existing if row["speaker"] not in {"NARRATOR", "UNKNOWN"}
        )
        self._chapter_titles = {
            int(row["id"]): str(row["title"]) for row in self.db.list_chapters()
        }

    def _available(self) -> bool:
        try:
            return self.session.get(f"{self.base_url}/api/tags", timeout=5).ok
        except requests.RequestException:
            return False

    def ensure_available(self) -> bool:
        if not self.settings.get("enabled", True):
            return False
        executable = shutil.which("ollama")
        if not self._available():
            if not executable:
                return False
            try:
                subprocess.Popen(
                    [executable, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
                )
            except OSError:
                return False
            for _ in range(30):
                if self._available():
                    break
                time.sleep(1)
            else:
                return False
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            names = {str(item.get("name", "")) for item in response.json().get("models", [])}
            if self.model in names or any(name.split(":", 1)[0] == self.model for name in names):
                return True
        except requests.RequestException:
            return False
        if not executable or not self.allow_downloads:
            self.log(
                f"Thiếu Ollama model {self.model}. Job không được tự tải model sau khi đã bắt đầu; "
                "hãy mở lại START.bat để kiểm tra/cài model."
            )
            return False
        self.log(f"Đang tải Ollama model {self.model} theo policy đã cho phép.")
        try:
            subprocess.run([executable, "pull", self.model], check=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False

    def _known_summary(self) -> str:
        if not self._speaker_counts:
            return "(Chưa có nhân vật đã biết)"
        return "\n".join(
            f"- {name}; số lần đã gặp={count}" for name, count in self._speaker_counts.most_common(80)
        )

    def _request(self, group: list[Any]) -> dict[str, Any]:
        chapter_titles: list[str] = []
        rows: list[dict[str, Any]] = []
        for row in group:
            chapter_title = self._chapter_titles.get(int(row["chapter_id"]), "")
            if chapter_title not in chapter_titles:
                chapter_titles.append(chapter_title)
            rows.append({"id": row["stable_id"], "hint": row["kind_hint"], "text": row["text"]})
        prompt = (
            f"Các chương hiện tại: {', '.join(chapter_titles)}\n\n"
            f"Nhân vật đã biết từ các phần trước:\n{self._known_summary()}\n\n"
            f"Các đoạn liên tiếp:\n{json.dumps(rows, ensure_ascii=False, indent=2)}"
        )
        request = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "format": OUTPUT_SCHEMA,
            "keep_alive": "30m",
            "options": {
                "temperature": float(self.settings.get("temperature", 0.1)),
                "num_ctx": int(self.settings.get("num_ctx", 16384)),
            },
        }
        response = self.session.post(
            f"{self.base_url}/api/generate",
            json=request,
            timeout=float(self.settings.get("timeout_seconds", 900)),
        )
        response.raise_for_status()
        content = response.json().get("response", "{}")
        return json.loads(content)

    def analyze_all(
        self,
        stop_requested: Callable[[], bool],
        progress: Callable[[int, int], None] | None = None,
        before_batch: Callable[[int], None] | None = None,
    ) -> None:
        all_rows = self.db.list_segments()
        pending = [row for row in all_rows if row["status"] == "pending"]
        if not pending:
            self.log("Toàn bộ segment đã có checkpoint phân tích.")
            return
        llm_ready = self.ensure_available()
        if not llm_ready:
            if self.settings.get("enabled", True) and self.settings.get("required", True):
                raise RuntimeError(
                    f"Ollama/Qwen model {self.model} không sẵn sàng. "
                    "Pipeline dừng an toàn thay vì âm thầm hạ chất lượng phân tích toàn book."
                )
            self.log("Phân tích AI bị tắt/không bắt buộc; dùng heuristic và đánh warning, không dừng hỏi người dùng.")
        max_segments = int(self.settings.get("batch_segments", 28))
        max_chars = int(self.settings.get("batch_chars", 6200))
        groups: list[list[Any]] = []
        current: list[Any] = []
        chars = 0
        for row in pending:
            text_len = len(str(row["text"]))
            if current and (len(current) >= max_segments or chars + text_len > max_chars):
                groups.append(current)
                current = []
                chars = 0
            current.append(row)
            chars += text_len
        if current:
            groups.append(current)

        done = len(all_rows) - len(pending)
        total = len(all_rows)
        required = bool(self.settings.get("enabled", True) and self.settings.get("required", True))
        confidence_threshold = float(self.settings.get("low_confidence_threshold", 0.58))
        for group_index, group in enumerate(groups, 1):
            if stop_requested():
                return
            if before_batch is not None:
                before_batch(group_index)
            validated: dict[str, dict[str, Any]] = {}
            last_error = "AI analysis is unavailable"
            if llm_ready:
                for attempt in range(int(self.settings.get("max_retries", 3))):
                    try:
                        validated = _validate(group, self._request(group))
                        if len(validated) == len(group):
                            break
                        last_error = f"LLM returned {len(validated)}/{len(group)} IDs"
                    except Exception as exc:  # noqa: BLE001
                        last_error = str(exc)
                    self.log(f"Phân tích batch {group_index} lỗi lần {attempt + 1}: {last_error}")
                    time.sleep(min(8, 2 ** attempt))
            if len(validated) != len(group) and required:
                message = (
                    f"Phân tích bắt buộc thất bại ở batch {group_index}: "
                    f"nhận {len(validated)}/{len(group)} segment; lỗi cuối: {last_error}"
                )
                self.db.event(
                    "critical",
                    "REQUIRED_ANALYSIS_BATCH_FAILED",
                    message,
                    {
                        "batch_index": group_index,
                        "expected_segments": len(group),
                        "validated_segments": len(validated),
                    },
                )
                raise RuntimeError(message)
            for row in group:
                data = validated.get(str(row["stable_id"])) or _heuristic(row)
                self.db.update_analysis(
                    int(row["id"]),
                    data,
                    low_confidence_threshold=confidence_threshold,
                )
                speaker = str(data.get("speaker", "UNKNOWN"))
                if speaker not in {"NARRATOR", "UNKNOWN", ""}:
                    self._speaker_counts[speaker] += 1
                done += 1
                if progress:
                    progress(done, total)
            self.log(f"Đã checkpoint phân tích {done:,}/{total:,} segment.")

    def reconcile_aliases(
        self,
        before_batch: Callable[[int], None] | None = None,
    ) -> dict[str, str]:
        """Conservative full-book reconciliation. It never merges low-confidence names automatically."""
        rows = [row for row in self.db.list_segments() if str(row["status"]) != "pending"]
        contexts: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            speaker = str(row["speaker"]).strip()
            if speaker in {"NARRATOR", "UNKNOWN", ""}:
                continue
            if len(contexts[speaker]) < 4:
                contexts[speaker].append(str(row["text"])[:260])
        if len(contexts) < 2 or not self._available():
            return {}
        items = [
            {"name": name, "examples": examples}
            for name, examples in sorted(contexts.items(), key=lambda item: item[0].casefold())
        ]
        alias_map: dict[str, str] = {}
        # Keep requests bounded. Only high-confidence merges are applied automatically.
        for batch_index, offset in enumerate(range(0, len(items), 50), 1):
            if before_batch is not None:
                before_batch(batch_index)
            batch = items[offset : offset + 50]
            prompt = (
                "Hợp nhất bí danh của cùng một nhân vật trong audiobook. Không gộp đại từ chung như hắn, nàng, cô ấy. "
                "Chỉ trả nhóm khi chắc chắn từ ngữ cảnh. Canonical phải là tên rõ nhất trong aliases.\n\n"
                + json.dumps(batch, ensure_ascii=False, indent=2)
            )
            request = {
                "model": self.model,
                "system": "Bạn là biên tập viên nhất quán nhân vật. Trả JSON đúng schema.",
                "prompt": prompt,
                "stream": False,
                "format": RECONCILE_SCHEMA,
                "keep_alive": "10m",
                "options": {"temperature": 0.0, "num_ctx": int(self.settings.get("num_ctx", 16384))},
            }
            try:
                response = self.session.post(
                    f"{self.base_url}/api/generate",
                    json=request,
                    timeout=float(self.settings.get("timeout_seconds", 900)),
                )
                response.raise_for_status()
                payload = json.loads(response.json().get("response", "{}"))
                for group in payload.get("groups", []):
                    confidence = float(group.get("confidence", 0))
                    aliases = [str(x).strip() for x in group.get("aliases", []) if str(x).strip()]
                    canonical = str(group.get("canonical", "")).strip()
                    if confidence < 0.86 or canonical not in aliases or len(aliases) < 2:
                        continue
                    for alias in aliases:
                        if alias != canonical:
                            alias_map[alias] = canonical
                    self.db.event(
                        "info",
                        "ALIAS_RECONCILIATION_APPLIED",
                        f"High-confidence alias group: {canonical}",
                        {"canonical": canonical, "aliases": aliases, "confidence": confidence},
                    )
            except Exception as exc:  # noqa: BLE001
                self.db.event("warning", "ALIAS_RECONCILIATION_FAILED", str(exc))
        # Resolve transitive mappings deterministically so A→B and B→C cannot leave A at B.
        resolved: dict[str, str] = {}
        for alias in sorted(alias_map, key=str.casefold):
            canonical = alias_map[alias]
            visited = {alias}
            while canonical in alias_map and canonical not in visited:
                visited.add(canonical)
                canonical = alias_map[canonical]
            if canonical not in visited:
                resolved[alias] = canonical
        return resolved

    def release_model(self) -> None:
        """Unload Qwen from Ollama VRAM while keeping the HTTP session reusable."""
        try:
            self.session.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": 0},
                timeout=20,
            )
        except requests.RequestException:
            pass

    def unload(self) -> None:
        self.release_model()
        self.session.close()
