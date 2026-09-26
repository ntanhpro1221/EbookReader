package vn.ebookreader.player

import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Lõi phát - sống trong tiến trình app, dùng chung giữa PlaybackService (thông báo, màn hình khoá, nút tai nghe)
 * và PlayerPlugin (giao diện). Mọi thao tác trên ExoPlayer chạy ở luồng chính.
 *
 * Vì sao hàng đợi, lưu vị trí, hẹn giờ đều ở ĐÂY chứ không ở JavaScript: tắt màn hình thì WebView bị treo, nên
 * tự sang chương kế hay tắt nhạc lúc ngủ mà nằm trong JS thì sẽ không bao giờ chạy.
 */
object Playback {
    data class Chapter(val id: Int, val title: String, val file: String, val duration: Double)

    private val main = Handler(Looper.getMainLooper())
    var player: ExoPlayer? = null
        internal set
    lateinit var appContext: Context
        private set

    var bookId: String = ""
        private set
    var bookTitle: String = ""
        private set
    var narrator: String = ""
        private set
    var chapters: List<Chapter> = emptyList()
        private set
    private var pausedAtMs = 0L
    private var autoRewindAfterMs = 5 * 60_000L
    private var autoRewindSeconds = 5.0
    private val listeners = mutableSetOf<(JSONObject) -> Unit>()
    private var ticking = false

    fun init(context: Context) {
        appContext = context.applicationContext
        Store.init(appContext)
    }

    fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else main.post(block)
    }

    fun addListener(listener: (JSONObject) -> Unit) { listeners += listener }
    fun removeListener(listener: (JSONObject) -> Unit) { listeners -= listener }

    fun emit(kind: String) {
        val event = state().put("kind", kind)
        listeners.toList().forEach { runCatching { it(event) } }
        if (::appContext.isInitialized) runCatching { PlayerWidget.refresh(appContext, tick = kind == "tick") }
    }

    /** Cuốn nghe gần nhất trên máy: (book.json, mốc "last") - cho widget và cho tiếp tục phát sau khi khởi động lại. */
    fun lastListened(): Pair<JSONObject, JSONObject>? =
        Store.books().mapNotNull { manifest ->
            val last = Store.state(manifest.getString("id")).optJSONObject("last") ?: return@mapNotNull null
            manifest to last
        }.maxByOrNull { it.second.optDouble("at") }

    fun chaptersOf(manifest: JSONObject): List<Chapter> {
        val array = manifest.optJSONArray("chapters") ?: return emptyList()
        return (0 until array.length()).map { array.getJSONObject(it) }
            .filter { it.optBoolean("available") && it.optString("file").isNotBlank() && it.optString("file") != "null" }
            .map { Chapter(it.getInt("id"), it.optString("fullTitle"), it.getString("file"), it.optDouble("duration", 0.0)) }
    }

    /** Nạp lại cuốn nghe gần nhất đúng chỗ đang dở rồi phát (bấm phát trên widget khi app không chạy). */
    fun resumeLast(): Boolean {
        val (manifest, last) = lastListened() ?: return false
        val id = manifest.getString("id")
        val items = chaptersOf(manifest)
        if (items.isEmpty()) return false
        val rate = Store.state(id).optDouble("rate", 1.0)
        load(id, manifest.optString("title"), manifest.optString("narrator"), items, last.optInt("chapterId"), last.optDouble("seconds"), rate)
        return true
    }

    val currentChapter: Chapter?
        get() = player?.currentMediaItem?.mediaId?.toIntOrNull()?.let { id -> chapters.firstOrNull { it.id == id } }

    val positionSeconds: Double
        get() = (player?.currentPosition ?: 0L) / 1000.0

    fun state(): JSONObject {
        val chapter = currentChapter
        val exo = player
        return JSONObject()
            .put("bookId", bookId)
            .put("bookTitle", bookTitle)
            .put("chapterId", chapter?.id ?: JSONObject.NULL)
            .put("chapterTitle", chapter?.title ?: "")
            .put("position", positionSeconds)
            .put("duration", exo?.duration?.takeIf { it > 0 }?.div(1000.0) ?: chapter?.duration ?: 0.0)
            .put("playing", exo?.isPlaying == true)
            .put("buffering", exo?.playbackState == Player.STATE_BUFFERING)
            .put("rate", exo?.playbackParameters?.speed?.toDouble() ?: 1.0)
            .put("sleep", SleepTimer.describe())
    }

    /** Nạp một cuốn: cả danh sách chương vào hàng đợi, bắt đầu ở chương/giây đã chọn. */
    fun load(id: String, title: String, narratorName: String, items: List<Chapter>, startChapterId: Int, startSeconds: Double, rate: Double, autoplay: Boolean = true) {
        val exo = player ?: return
        saveNow()
        bookId = id
        bookTitle = title
        narrator = narratorName
        chapters = items
        val media = items.map { chapter ->
            MediaItem.Builder()
                .setMediaId(chapter.id.toString())
                .setUri(Uri.fromFile(Store.file(id, chapter.file)))
                .setMediaMetadata(
                    MediaMetadata.Builder()
                        .setTitle(chapter.title)
                        .setArtist(narratorName.ifBlank { null })
                        .setAlbumTitle(title)
                        .setDisplayTitle(chapter.title)
                        .setSubtitle(title)
                        .setArtworkData(Artwork.cover(title), MediaMetadata.PICTURE_TYPE_FRONT_COVER)
                        .build(),
                )
                .build()
        }
        val index = items.indexOfFirst { it.id == startChapterId }.coerceAtLeast(0)
        exo.setMediaItems(media, index, (startSeconds * 1000).toLong())
        exo.playbackParameters = PlaybackParameters(rate.toFloat())
        exo.prepare()
        // Mở lại app: nạp sẵn đúng chỗ đang nghe dở ở trạng thái dừng, người nghe bấm phát khi sẵn sàng.
        if (autoplay) {
            exo.play()
            startTicking()
        }
        emit("load")
    }

    fun play() {
        val exo = player ?: return
        if (pausedAtMs > 0 && System.currentTimeMillis() - pausedAtMs > autoRewindAfterMs) {
            exo.seekTo((exo.currentPosition - (autoRewindSeconds * 1000).toLong()).coerceAtLeast(0))
        }
        exo.play()
        Bedtime.interaction("play")
    }

    fun pause() {
        player?.pause()
        Bedtime.interaction("pause")
    }

    fun toggle() = if (player?.isPlaying == true) pause() else play()

    fun seekTo(seconds: Double) {
        player?.seekTo((seconds * 1000).toLong().coerceAtLeast(0))
        Bedtime.interaction("seek")
        emit("seek")
    }

    fun skip(deltaSeconds: Double) = seekTo(positionSeconds + deltaSeconds)

    fun jumpTo(chapterId: Int, seconds: Double) {
        val exo = player ?: return
        val index = chapters.indexOfFirst { it.id == chapterId }
        if (index < 0) return
        saveNow()
        exo.seekTo(index, (seconds * 1000).toLong())
        exo.play()
        Bedtime.interaction("chapter")
        emit("chapter")
    }

    fun next() {
        val exo = player ?: return
        if (exo.hasNextMediaItem()) {
            saveNow()
            exo.seekToNextMediaItem()
            Bedtime.interaction("next")
        }
    }

    fun previous() {
        val exo = player ?: return
        saveNow()
        if (exo.currentPosition > 5000 || !exo.hasPreviousMediaItem()) exo.seekTo(0) else exo.seekToPreviousMediaItem()
        Bedtime.interaction("previous")
    }

    fun setRate(rate: Double) {
        player?.playbackParameters = PlaybackParameters(rate.toFloat())
        if (bookId.isNotEmpty()) Store.setRate(bookId, rate)
        emit("rate")
    }

    fun addBookmark(note: String): JSONObject? {
        val chapter = currentChapter ?: return null
        val mark = Store.addBookmark(bookId, chapter.id, positionSeconds, note)
        Bedtime.interaction("bookmark")
        emit("bookmark")
        return mark
    }

    fun configure(rewindAfterMinutes: Double, rewindSeconds: Double) {
        autoRewindAfterMs = (rewindAfterMinutes * 60_000).toLong()
        autoRewindSeconds = rewindSeconds
    }

    // ---- sự kiện từ ExoPlayer ------------------------------------------------------------------------------

    fun onPlayingChanged(playing: Boolean) {
        if (!playing) {
            pausedAtMs = System.currentTimeMillis()
            saveNow()
        } else {
            pausedAtMs = 0
            startTicking()
        }
        emit(if (playing) "play" else "pause")
    }

    fun onChapterChanged() {
        SleepTimer.onChapterChanged()
        emit("chapter")
    }

    fun onEnded() {
        saveNow()
        emit("ended")
    }

    /** Lưu vị trí: mỗi 5 giây khi đang phát, và ngay khi dừng/đổi chương. Cùng nhịp đó nhật ký đêm ghi mốc. */
    private fun startTicking() {
        if (ticking) return
        ticking = true
        main.post(object : Runnable {
            var beats = 0
            override fun run() {
                val exo = player
                if (exo == null || !exo.isPlaying) {
                    ticking = false
                    return
                }
                beats += 1
                if (beats % 10 == 0) saveNow()
                Bedtime.checkpoint()
                emit("tick")
                main.postDelayed(this, 500)
            }
        })
    }

    fun saveNow() {
        val chapter = currentChapter ?: return
        if (bookId.isEmpty()) return
        val duration = player?.duration?.takeIf { it > 0 }?.div(1000.0) ?: chapter.duration
        Store.progress(bookId, chapter.id, positionSeconds, duration)
    }

    fun chaptersJson(): JSONArray = JSONArray().also { array ->
        chapters.forEach { array.put(JSONObject().put("id", it.id).put("title", it.title).put("duration", it.duration)) }
    }

    fun localFile(relative: String): File = Store.file(bookId, relative)
}
