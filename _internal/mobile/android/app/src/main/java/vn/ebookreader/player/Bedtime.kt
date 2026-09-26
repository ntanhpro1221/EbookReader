package vn.ebookreader.player

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Nhật ký đêm - cho "Tối qua bạn nghe tới đâu?".
 *
 * Không ai biết chính xác lúc người nghe thiếp đi, nhưng có những mốc chắc chắn:
 *  - lúc hẹn giờ ngủ: chắc chắn còn thức;
 *  - lần cuối chạm máy / bấm nút / lắc máy: chắc chắn còn thức;
 *  - lúc điện thoại bắt đầu nằm yên (cảm biến): rất có thể là lúc thiếp đi;
 *  - lúc tự dừng.
 * Mỗi mốc ghi kèm chương + giây đang phát, và cứ 30 giây một mốc vị trí để suy ra "lúc X đang nghe tới đâu".
 * Sáng hôm sau giao diện hiện các mốc kèm câu văn đang đọc lúc đó để người nghe nhận ra đoạn cuối mình còn nhớ.
 */
object Bedtime {
    private const val STILL_DEVIATION = 0.06   // m/s² - máy nằm yên trên đệm
    private const val STILL_WINDOWS = 4        // 4 cửa sổ 30 giây liền = 2 phút nằm yên
    private var session: JSONObject? = null
    private var lastCheckpointMs = 0L
    private var stillRun = 0
    private var stillSince = 0L
    private var stillRecorded = false

    private fun file() = File(Store.root, "bedtime/latest.json")

    private fun position(): JSONObject {
        val chapter = Playback.currentChapter
        return JSONObject()
            .put("chapterId", chapter?.id ?: JSONObject.NULL)
            .put("chapterTitle", chapter?.title ?: "")
            .put("seconds", Playback.positionSeconds)
    }

    private fun nowSeconds() = System.currentTimeMillis() / 1000.0

    /** Hẹn giờ mở (hoặc nối tiếp) một đêm: hẹn lại trong vòng 90 phút vẫn là cùng một đêm. */
    fun timerSet(minutes: Int, reason: String? = null) {
        val current = session
        val continuing = current != null && current.optString("bookId") == Playback.bookId &&
            nowSeconds() - current.optDouble("lastAt", 0.0) < 90 * 60
        if (!continuing) {
            session = JSONObject()
                .put("bookId", Playback.bookId)
                .put("bookTitle", Playback.bookTitle)
                .put("startedAt", nowSeconds())
                .put("events", JSONArray())
                .put("timeline", JSONArray())
            stillRun = 0
            stillRecorded = false
        }
        add("timer", JSONObject().put("minutes", minutes).also { if (reason != null) it.put("action", reason) })
    }

    /** Mốc "còn thức" đã biết từ trước (lần chạm máy cuối cùng trước khi lưới an toàn bật). */
    fun touchAt(atMs: Long, chapterId: Int?, seconds: Double) {
        val current = session ?: return
        val chapter = Playback.chapters.firstOrNull { it.id == chapterId }
        val position = JSONObject()
            .put("chapterId", chapterId ?: JSONObject.NULL)
            .put("chapterTitle", chapter?.title ?: "")
            .put("seconds", seconds)
        current.getJSONArray("events").put(
            JSONObject().put("type", "touch").put("action", "last-activity").put("at", atMs / 1000.0).put("position", position),
        )
        save()
    }

    fun interaction(kind: String) {
        if (session == null) return
        add("touch", JSONObject().put("action", kind))
    }

    fun event(kind: String) {
        if (session == null) return
        add(kind, JSONObject())
    }

    fun stopped() {
        if (session == null) return
        add("stopped", JSONObject())
        session?.put("endedAt", nowSeconds())
        save()
    }

    fun checkpoint() {
        val current = session ?: return
        val now = System.currentTimeMillis()
        if (now - lastCheckpointMs < 30_000) return
        lastCheckpointMs = now
        val timeline = current.getJSONArray("timeline")
        timeline.put(position().put("at", nowSeconds()))
        while (timeline.length() > 480) timeline.remove(0)   // 4 giờ
        save()
    }

    /** Một cửa sổ 30 giây của cảm biến: đủ 2 phút liền nằm yên thì ghi mốc "nằm yên" tại lúc bắt đầu yên. */
    fun window(startMs: Long, deviation: Double) {
        val current = session ?: return
        if (deviation < STILL_DEVIATION) {
            if (stillRun == 0) stillSince = startMs
            stillRun += 1
            if (stillRun >= STILL_WINDOWS && !stillRecorded) {
                stillRecorded = true
                val at = stillSince / 1000.0
                val events = current.getJSONArray("events")
                events.put(JSONObject().put("type", "still").put("at", at).put("position", positionAt(at)))
                save()
            }
        } else {
            if (stillRecorded) add("moved", JSONObject())
            stillRun = 0
            stillRecorded = false
        }
    }

    /** Vị trí đang phát ở một thời điểm đã qua, suy từ mốc 30 giây gần nhất trước đó. */
    private fun positionAt(at: Double): JSONObject {
        val timeline = session?.optJSONArray("timeline") ?: return position()
        var best: JSONObject? = null
        for (index in 0 until timeline.length()) {
            val point = timeline.getJSONObject(index)
            if (point.optDouble("at") <= at) best = point else break
        }
        return best ?: position()
    }

    private fun add(type: String, extra: JSONObject) {
        val current = session ?: return
        val at = nowSeconds()
        extra.put("type", type).put("at", at).put("position", position())
        current.getJSONArray("events").put(extra)
        current.put("lastAt", at)
        save()
    }

    private fun save() {
        val current = session ?: return
        Store.writeAtomic(file(), current.toString())
    }

    fun latest(): JSONObject? {
        val file = file()
        return if (file.isFile) runCatching { JSONObject(file.readText()) }.getOrNull() else null
    }

    fun dismiss() {
        val latest = latest() ?: return
        latest.put("dismissed", true)
        Store.writeAtomic(file(), latest.toString())
        if (session?.optDouble("startedAt") == latest.optDouble("startedAt")) session = null
    }
}
