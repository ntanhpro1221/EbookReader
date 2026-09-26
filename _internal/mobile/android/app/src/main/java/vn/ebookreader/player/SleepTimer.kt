package vn.ebookreader.player

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import org.json.JSONObject
import kotlin.math.sqrt

/**
 * Hẹn giờ ngủ: tắt sau N phút hoặc hết chương, tiếng nhỏ dần trước khi dừng, lắc máy để nghe thêm.
 *
 * Lắc được cả khi đang nhỏ dần và trong 2 phút sau khi đã tự dừng (người nghe vẫn còn thức, lắc để nghe tiếp).
 * Máy rung nhẹ để xác nhận mà không phải mở mắt nhìn màn hình.
 */
object SleepTimer {
    enum class Mode { OFF, MINUTES, CHAPTER }

    private val main = Handler(Looper.getMainLooper())
    var mode = Mode.OFF
        private set
    private var endsAtMs = 0L
    private var minutes = 0
    private var stoppedAtMs = 0L
    var fadeMs = 30_000L
    var extendMinutes = 10
    var shakeEnabled = true
    private var ticking = false

    fun describe(): JSONObject {
        val json = JSONObject().put("mode", mode.name.lowercase())
        when (mode) {
            Mode.MINUTES -> json.put("remaining", ((endsAtMs - System.currentTimeMillis()) / 1000.0).coerceAtLeast(0.0))
                .put("minutes", minutes)
            Mode.CHAPTER -> json.put("remaining", remainingInChapter())
            Mode.OFF -> if (stoppedAtMs > 0) json.put("stoppedAt", stoppedAtMs / 1000.0)
        }
        return json
    }

    private fun remainingInChapter(): Double {
        val exo = Playback.player ?: return 0.0
        return ((exo.duration - exo.currentPosition) / 1000.0).coerceAtLeast(0.0)
    }

    fun setMinutes(value: Int) {
        mode = Mode.MINUTES
        minutes = value
        endsAtMs = System.currentTimeMillis() + value * 60_000L
        stoppedAtMs = 0
        Playback.player?.pauseAtEndOfMediaItems = false
        restoreVolume()
        Bedtime.timerSet(value)
        Motion.start(Playback.appContext)
        tick()
        Playback.emit("sleep")
    }

    fun setEndOfChapter() {
        mode = Mode.CHAPTER
        stoppedAtMs = 0
        Playback.player?.pauseAtEndOfMediaItems = true
        restoreVolume()
        Bedtime.timerSet(-1)
        Motion.start(Playback.appContext)
        tick()
        Playback.emit("sleep")
    }

    fun cancel() {
        mode = Mode.OFF
        Playback.player?.pauseAtEndOfMediaItems = false
        restoreVolume()
        Motion.stop()
        Playback.emit("sleep")
    }

    /** Thêm giờ: đang hẹn phút thì cộng thêm; đang hẹn hết chương thì chuyển thành N phút kể từ bây giờ. */
    fun extend(extra: Int = extendMinutes) {
        val now = System.currentTimeMillis()
        if (mode == Mode.MINUTES) endsAtMs = maxOf(endsAtMs, now) + extra * 60_000L
        else {
            mode = Mode.MINUTES
            endsAtMs = now + extra * 60_000L
            Playback.player?.pauseAtEndOfMediaItems = false
        }
        minutes = ((endsAtMs - now) / 60_000L).toInt()
        restoreVolume()
        tick()
        Playback.emit("sleep")
    }

    /** Lắc máy: đang hẹn giờ thì nghe thêm; vừa tự dừng (< 2 phút) thì phát tiếp và hẹn lại. */
    fun onShake() {
        if (!shakeEnabled) return
        val now = System.currentTimeMillis()
        when {
            mode != Mode.OFF -> {
                extend()
                Bedtime.event("shake")
                buzz(longArrayOf(0, 60, 80, 60))
            }
            stoppedAtMs > 0 && now - stoppedAtMs < 120_000L -> {
                Playback.play()
                setMinutes(extendMinutes)
                Bedtime.event("shake")
                buzz(longArrayOf(0, 60, 80, 60))
            }
        }
    }

    fun onChapterChanged() {
        if (mode == Mode.CHAPTER) finish()
    }

    /** Gọi khi ExoPlayer dừng ở cuối chương (chế độ hết chương). */
    fun onPausedAtChapterEnd() {
        if (mode == Mode.CHAPTER) finish()
    }

    private fun finish() {
        Playback.player?.pause()
        Playback.player?.pauseAtEndOfMediaItems = false
        mode = Mode.OFF
        stoppedAtMs = System.currentTimeMillis()
        restoreVolume()
        Bedtime.stopped()
        buzz(longArrayOf(0, 40))
        // Cảm biến còn nghe thêm 2 phút để "lắc để nghe tiếp" vẫn chạy.
        main.postDelayed({ if (mode == Mode.OFF) Motion.stop() }, 125_000L)
        Playback.emit("sleep")
    }

    private fun tick() {
        if (ticking) return
        ticking = true
        main.post(object : Runnable {
            override fun run() {
                val exo = Playback.player
                if (mode == Mode.OFF || exo == null) {
                    ticking = false
                    return
                }
                val remaining = when (mode) {
                    Mode.MINUTES -> endsAtMs - System.currentTimeMillis()
                    Mode.CHAPTER -> exo.duration - exo.currentPosition
                    Mode.OFF -> 0L
                }
                if (mode == Mode.MINUTES && remaining <= 0) {
                    finish()
                    ticking = false
                    return
                }
                if (exo.isPlaying && remaining in 0 until fadeMs) {
                    exo.volume = (remaining.toFloat() / fadeMs).coerceIn(0.05f, 1f)
                } else if (exo.volume < 1f && remaining >= fadeMs) {
                    exo.volume = 1f
                }
                main.postDelayed(this, 250)
            }
        })
    }

    private fun restoreVolume() {
        Playback.player?.volume = 1f
    }

    private fun buzz(pattern: LongArray) {
        val context = Playback.appContext
        val vibrator = if (Build.VERSION.SDK_INT >= 31) {
            (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
        } else {
            @Suppress("DEPRECATION") context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }
        runCatching { vibrator.vibrate(VibrationEffect.createWaveform(pattern, -1)) }
    }
}

/**
 * Cảm biến gia tốc dùng chung cho hai việc: nhận ra cú lắc (thêm giờ ngủ) và nhận ra lúc điện thoại nằm yên
 * (nhật ký đêm đoán lúc người nghe thiếp đi). Chỉ bật khi đang hẹn giờ ngủ - không tốn pin lúc khác.
 */
object Motion : SensorEventListener {
    private var manager: SensorManager? = null
    private var running = false
    private val peaks = ArrayDeque<Long>()
    private var lastShakeMs = 0L
    // Cửa sổ 30 giây: độ lệch của độ lớn gia tốc - rất nhỏ nghĩa là máy nằm yên.
    private var windowStartMs = 0L
    private var count = 0
    private var sum = 0.0
    private var sumSquares = 0.0

    fun start(context: Context) {
        if (running) return
        manager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensor = manager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) ?: return
        manager?.registerListener(this, sensor, SensorManager.SENSOR_DELAY_GAME)
        running = true
        windowStartMs = System.currentTimeMillis()
    }

    fun stop() {
        if (!running) return
        manager?.unregisterListener(this)
        running = false
    }

    override fun onSensorChanged(event: SensorEvent) {
        val (x, y, z) = Triple(event.values[0], event.values[1], event.values[2])
        val magnitude = sqrt((x * x + y * y + z * z).toDouble())
        val now = System.currentTimeMillis()
        // Lắc: hai đỉnh > 2,2 g trong 800 ms, cách lần lắc trước > 2 giây.
        if (magnitude / SensorManager.GRAVITY_EARTH > 2.2) {
            peaks.addLast(now)
            while (peaks.isNotEmpty() && now - peaks.first() > 800) peaks.removeFirst()
            if (peaks.size >= 2 && now - lastShakeMs > 2000) {
                lastShakeMs = now
                peaks.clear()
                Playback.onMain { SleepTimer.onShake() }
            }
        }
        count += 1
        sum += magnitude
        sumSquares += magnitude * magnitude
        if (now - windowStartMs >= 30_000) {
            val mean = sum / count
            val deviation = sqrt((sumSquares / count - mean * mean).coerceAtLeast(0.0))
            val start = windowStartMs
            Playback.onMain { Bedtime.window(start, deviation) }
            windowStartMs = now
            count = 0
            sum = 0.0
            sumSquares = 0.0
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
}
