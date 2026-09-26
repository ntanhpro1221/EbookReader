package vn.ebookreader.player

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Build
import android.util.SizeF
import android.widget.RemoteViews
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.MoreExecutors
import org.json.JSONObject

/**
 * Widget màn hình chính - trình phát thu nhỏ. Cỡ lớn: bìa, tên chương, tiến độ, lùi/phát/tới, hẹn giờ ngủ;
 * cỡ nhỏ: bìa + phát/dừng (Android 12+ tự chọn bố cục theo kích thước).
 *
 * Bấm phát khi app không chạy: dịch vụ phát được khởi động, cuốn nghe gần nhất được nạp đúng chỗ đang dở.
 */
class PlayerWidget : AppWidgetProvider() {
    companion object {
        private const val ACTION_TOGGLE = "vn.ebookreader.widget.TOGGLE"
        private const val ACTION_BACK = "vn.ebookreader.widget.BACK"
        private const val ACTION_FORWARD = "vn.ebookreader.widget.FORWARD"
        private const val ACTION_SLEEP = "vn.ebookreader.widget.SLEEP"
        private var lastRefreshMs = 0L

        /** Vẽ lại mọi widget. `tick` chỉ vẽ lại mỗi 30 giây (thanh tiến độ), còn lại vẽ ngay. */
        fun refresh(context: Context, tick: Boolean = false) {
            val now = System.currentTimeMillis()
            if (tick && now - lastRefreshMs < 30_000) return
            lastRefreshMs = now
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, PlayerWidget::class.java))
            if (ids.isNotEmpty()) render(context, manager, ids)
        }

        private fun intent(context: Context, action: String, code: Int): PendingIntent =
            PendingIntent.getBroadcast(
                context, code, Intent(context, PlayerWidget::class.java).setAction(action),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )

        private data class View(
            val book: String,
            val chapter: String,
            val progress: Double,
            val playing: Boolean,
            val sleep: String,
            val sleepOn: Boolean,
        )

        /** Trạng thái để vẽ: đang phát thì lấy từ lõi phát, không thì lấy cuốn nghe gần nhất trên máy. */
        private fun current(context: Context): View {
            Store.init(context)
            val exo = Playback.player
            if (exo != null && Playback.bookId.isNotEmpty()) {
                val state = Playback.state()
                val sleep = state.getJSONObject("sleep")
                val sleepText = when (sleep.optString("mode")) {
                    "minutes" -> "${Math.ceil(sleep.optDouble("remaining") / 60).toInt()}′"
                    "chapter" -> "hết chương"
                    else -> ""
                }
                val duration = state.optDouble("duration")
                return View(
                    Playback.bookTitle, state.optString("chapterTitle"),
                    if (duration > 0) state.optDouble("position") / duration else 0.0,
                    state.optBoolean("playing"), sleepText, sleep.optString("mode") != "off",
                )
            }
            val recent = Playback.lastListened() ?: return View("Ebook Reader", "Chưa nghe sách nào", 0.0, false, "", false)
            val (manifest, last) = recent
            val chapter = chapterOf(manifest, last.optInt("chapterId"))
            val duration = chapter?.optDouble("duration") ?: 0.0
            return View(
                manifest.optString("title"), chapter?.optString("fullTitle") ?: "",
                if (duration > 0) last.optDouble("seconds") / duration else 0.0, false, "", false,
            )
        }

        private fun chapterOf(manifest: JSONObject, chapterId: Int): JSONObject? {
            val chapters = manifest.optJSONArray("chapters") ?: return null
            for (index in 0 until chapters.length()) {
                val chapter = chapters.getJSONObject(index)
                if (chapter.optInt("id") == chapterId) return chapter
            }
            return null
        }

        private fun build(context: Context, layout: Int, view: View): RemoteViews {
            val views = RemoteViews(context.packageName, layout)
            val cover = Artwork.cover(view.book)
            views.setImageViewBitmap(R.id.widget_cover, BitmapFactory.decodeByteArray(cover, 0, cover.size))
            views.setTextViewText(R.id.widget_chapter, view.chapter.ifBlank { view.book })
            views.setImageViewResource(R.id.widget_toggle, if (view.playing) R.drawable.ic_widget_pause else R.drawable.ic_widget_play)
            views.setOnClickPendingIntent(R.id.widget_toggle, intent(context, ACTION_TOGGLE, 1))
            val open = PendingIntent.getActivity(
                context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE,
            )
            views.setOnClickPendingIntent(R.id.widget_cover, open)
            if (layout == R.layout.widget_player) {
                views.setTextViewText(R.id.widget_book, view.book)
                views.setProgressBar(R.id.widget_progress, 1000, (view.progress * 1000).toInt().coerceIn(0, 1000), false)
                views.setOnClickPendingIntent(R.id.widget_back, intent(context, ACTION_BACK, 2))
                views.setOnClickPendingIntent(R.id.widget_forward, intent(context, ACTION_FORWARD, 3))
                views.setOnClickPendingIntent(R.id.widget_sleep, intent(context, ACTION_SLEEP, 4))
                views.setImageViewResource(R.id.widget_sleep_icon, if (view.sleepOn) R.drawable.ic_widget_moon_on else R.drawable.ic_widget_moon)
                views.setTextViewText(R.id.widget_sleep_text, view.sleep)
                views.setOnClickPendingIntent(R.id.widget_book, open)
                views.setOnClickPendingIntent(R.id.widget_chapter, open)
            }
            return views
        }

        fun render(context: Context, manager: AppWidgetManager, ids: IntArray) {
            val view = current(context)
            val views = if (Build.VERSION.SDK_INT >= 31) {
                RemoteViews(
                    mapOf(
                        SizeF(110f, 40f) to build(context, R.layout.widget_player_small, view),
                        SizeF(220f, 96f) to build(context, R.layout.widget_player, view),
                    ),
                )
            } else {
                build(context, R.layout.widget_player, view)
            }
            ids.forEach { manager.updateAppWidget(it, views) }
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) = render(context, manager, ids)

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        val action = intent.action ?: return
        if (action !in setOf(ACTION_TOGGLE, ACTION_BACK, ACTION_FORWARD, ACTION_SLEEP)) return
        Playback.init(context)
        val pending = goAsync()
        // Kết nối tới dịch vụ phát (khởi động nó nếu chưa chạy) rồi mới ra lệnh.
        val future = MediaController.Builder(
            context, SessionToken(context, ComponentName(context, PlaybackService::class.java)),
        ).buildAsync()
        future.addListener({
            Playback.onMain {
                if (Playback.bookId.isEmpty() && action == ACTION_TOGGLE) {
                    Playback.resumeLast()
                } else {
                    when (action) {
                        ACTION_TOGGLE -> Playback.toggle()
                        ACTION_BACK -> Playback.skip(-15.0)
                        ACTION_FORWARD -> Playback.skip(15.0)
                        ACTION_SLEEP -> if (SleepTimer.mode == SleepTimer.Mode.OFF) SleepTimer.setMinutes(30) else SleepTimer.cancel()
                    }
                }
                refresh(context)
                MediaController.releaseFuture(future)
                pending.finish()
            }
        }, MoreExecutors.directExecutor())
    }
}
