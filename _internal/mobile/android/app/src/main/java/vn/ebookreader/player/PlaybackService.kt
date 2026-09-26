package vn.ebookreader.player

import android.app.PendingIntent
import android.content.Intent
import android.os.Bundle
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.CommandButton
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionResult
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture

/**
 * Dịch vụ phát nền: giữ ExoPlayer sống khi tắt màn hình, hiện điều khiển ở thanh thông báo và màn hình khoá,
 * nhận nút tai nghe/Bluetooth, tự dừng khi rút tai nghe hoặc có cuộc gọi (audio focus).
 *
 * Thanh thông báo: lùi 15 giây · phát/dừng · tới 15 giây, cộng "dấu trang" và - khi đang hẹn giờ ngủ - "+10 phút".
 */
class PlaybackService : MediaSessionService() {
    private var session: MediaSession? = null

    companion object {
        val BOOKMARK = SessionCommand("vn.ebookreader.BOOKMARK", Bundle.EMPTY)
        val SLEEP_PLUS = SessionCommand("vn.ebookreader.SLEEP_PLUS", Bundle.EMPTY)
        var instance: PlaybackService? = null
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        Playback.init(this)
        val player = ExoPlayer.Builder(this)
            .setAudioAttributes(
                AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build(),
                true,
            )
            .setHandleAudioBecomingNoisy(true)
            .setWakeMode(C.WAKE_MODE_LOCAL)
            .setSeekBackIncrementMs(15_000)
            .setSeekForwardIncrementMs(15_000)
            .build()
        player.addListener(object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                if (!isPlaying && player.playbackState == Player.STATE_READY && player.pauseAtEndOfMediaItems &&
                    player.duration - player.currentPosition < 1500
                ) {
                    SleepTimer.onPausedAtChapterEnd()
                }
                Playback.onPlayingChanged(isPlaying)
            }

            override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) = Playback.onChapterChanged()

            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) Playback.onEnded()
                Playback.emit("state")
            }
        })
        Playback.player = player
        val openApp = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        session = MediaSession.Builder(this, player)
            .setSessionActivity(openApp)
            .setCallback(Callback())
            .setMediaButtonPreferences(buttons())
            .build()
    }

    /** Nút trên thông báo; đổi theo trạng thái hẹn giờ (có "+10 phút" chỉ khi đang hẹn). */
    fun buttons(): List<CommandButton> {
        val list = mutableListOf(
            CommandButton.Builder(CommandButton.ICON_SKIP_BACK_15)
                .setPlayerCommand(Player.COMMAND_SEEK_BACK).setDisplayName("Lùi 15 giây").build(),
            CommandButton.Builder(CommandButton.ICON_SKIP_FORWARD_15)
                .setPlayerCommand(Player.COMMAND_SEEK_FORWARD).setDisplayName("Tới 15 giây").build(),
            CommandButton.Builder(CommandButton.ICON_BOOKMARK_UNFILLED)
                .setSessionCommand(BOOKMARK).setDisplayName("Thêm dấu trang").build(),
        )
        if (SleepTimer.mode != SleepTimer.Mode.OFF) {
            list += CommandButton.Builder(CommandButton.ICON_PLUS)
                .setSessionCommand(SLEEP_PLUS).setDisplayName("Nghe thêm ${SleepTimer.extendMinutes} phút").build()
        }
        return list
    }

    fun refreshButtons() {
        session?.setMediaButtonPreferences(buttons())
    }

    private inner class Callback : MediaSession.Callback {
        override fun onConnect(session: MediaSession, controller: MediaSession.ControllerInfo): MediaSession.ConnectionResult {
            val commands = MediaSession.ConnectionResult.DEFAULT_SESSION_COMMANDS.buildUpon()
                .add(BOOKMARK).add(SLEEP_PLUS).build()
            return MediaSession.ConnectionResult.AcceptedResultBuilder(session)
                .setAvailableSessionCommands(commands)
                .setMediaButtonPreferences(buttons())
                .build()
        }

        /** Tiếp tục phát từ điều khiển media của hệ thống / tai nghe Bluetooth sau khi app đã bị tắt hay máy khởi
         *  động lại: nạp lại cuốn nghe gần nhất đúng chỗ đang dở. */
        override fun onPlaybackResumption(
            mediaSession: MediaSession,
            controller: MediaSession.ControllerInfo,
            isForPlayback: Boolean,
        ): ListenableFuture<MediaSession.MediaItemsWithStartPosition> {
            val recent = Playback.lastListened()
                ?: return Futures.immediateFailedFuture(UnsupportedOperationException("chưa nghe sách nào"))
            val (manifest, last) = recent
            val chapters = Playback.chaptersOf(manifest)
            Playback.onMain { Playback.resumeLast() }
            val index = chapters.indexOfFirst { it.id == last.optInt("chapterId") }.coerceAtLeast(0)
            val items = chapters.map { MediaItem.Builder().setMediaId(it.id.toString()).setUri(android.net.Uri.fromFile(Store.file(manifest.getString("id"), it.file))).build() }
            return Futures.immediateFuture(
                MediaSession.MediaItemsWithStartPosition(items, index, (last.optDouble("seconds") * 1000).toLong()),
            )
        }

        override fun onCustomCommand(
            session: MediaSession,
            controller: MediaSession.ControllerInfo,
            customCommand: SessionCommand,
            args: Bundle,
        ): ListenableFuture<SessionResult> {
            when (customCommand.customAction) {
                BOOKMARK.customAction -> Playback.addBookmark("")
                SLEEP_PLUS.customAction -> SleepTimer.extend()
            }
            return Futures.immediateFuture(SessionResult(SessionResult.RESULT_SUCCESS))
        }
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    override fun onTaskRemoved(rootIntent: Intent?) {
        val player = session?.player
        if (player == null || !player.playWhenReady || player.mediaItemCount == 0) stopSelf()
    }

    override fun onDestroy() {
        Playback.saveNow()
        session?.run {
            player.release()
            release()
        }
        session = null
        Playback.player = null
        instance = null
        super.onDestroy()
    }
}
