"""Va analysis.py: danh sach 'nhan vat da biet' doc ca bang characters, khong chi segments."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''        self._chapter_titles = {
            int(row["id"]): str(row["title"]) for row in self.db.list_chapters()
        }'''

NEW = '''        # A batch that starts at chapter 307 has no analysed segments yet, so everything
        # above finds nothing and the prompt opens with "(Chưa có nhân vật đã biết)" - the
        # model re-guesses a cast the previous batch already worked out. Measured on this
        # book's own text: from the second batch onward, 80% of the proper nouns in a batch
        # have already appeared in an earlier one, and by the ninth it is 95%. An empty list
        # at a seam is not a small loss; it is most of the cast.
        #
        # port_casting.py carries those characters into the new project before `run`, the
        # same way pronunciations and voices are carried. This is where they are picked up.
        # Segments win where both exist: a count this project measured is worth more than a
        # count it was told, and adding them would double-count the overlap.
        for row in self.db.list_characters():
            name = str(row["canonical_name"])
            gender = str(row["gender"])
            mentions = int(row["mention_count"] or 0)
            if (
                mentions <= 0
                or gender not in {"male", "female"}
                or name.casefold() in RESERVED_SPEAKERS
                or is_local_speaker(name)
                or name in self._speaker_counts
            ):
                continue
            self._speaker_counts[name] = mentions
            self._speaker_genders[name][gender] = mentions

        self._chapter_titles = {
            int(row["id"]): str(row["title"]) for row in self.db.list_chapters()
        }'''

assert OLD in s, "khong khop cho seed"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
