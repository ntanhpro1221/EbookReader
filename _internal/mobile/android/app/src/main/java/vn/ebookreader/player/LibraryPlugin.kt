package vn.ebookreader.player

import android.content.Context
import android.os.Build
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL
import java.util.concurrent.Executors

/**
 * Thư viện trên điện thoại + đồng bộ với máy tính qua Wi-Fi (ebook_reader/webui/sync.py).
 *
 * Mọi mạng đi qua đây (native) chứ không qua fetch của WebView: trang chạy ở https://localhost, gọi http://<máy
 * tính> sẽ bị chặn vì mixed content, và tải hàng trăm MB audio thì nên làm ở luồng nền, ghi thẳng ra file.
 */
@CapacitorPlugin(name = "EbookLibrary")
class LibraryPlugin : Plugin() {
    private val io = Executors.newSingleThreadExecutor()
    private val downloads = Executors.newSingleThreadExecutor()
    private val prefs by lazy { context.getSharedPreferences("sync", Context.MODE_PRIVATE) }

    override fun load() {
        Playback.init(context)
    }

    private fun background(call: PluginCall, block: () -> Unit) = io.execute {
        try {
            block()
        } catch (error: Exception) {
            call.reject(error.message ?: error.javaClass.simpleName)
        }
    }

    @PluginMethod
    fun info(call: PluginCall) = call.resolve(JSObject().put("root", Store.root.absolutePath))

    // ---- ghép nối --------------------------------------------------------------------------------------------

    private fun base(): String = "http://${prefs.getString("host", "")}:${prefs.getInt("port", 47630)}"

    private fun request(method: String, path: String, body: JSONObject? = null, auth: Boolean = true, root: String = base()): String {
        val connection = URL(root + path).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 5000
        connection.readTimeout = 20000
        if (auth) connection.setRequestProperty("Authorization", "Bearer ${prefs.getString("token", "")}")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.outputStream.use { it.write(body.toString().toByteArray()) }
        }
        val code = connection.responseCode
        val text = (if (code < 400) connection.inputStream else connection.errorStream)?.bufferedReader()?.use { it.readText() } ?: ""
        connection.disconnect()
        if (code >= 400) {
            val message = runCatching { JSONObject(text).optString("error") }.getOrNull()
            throw IllegalStateException(message?.ifBlank { null } ?: "Máy tính trả lỗi $code")
        }
        return text
    }

    /** Tìm máy tính đang bật đồng bộ trong cùng mạng Wi-Fi (UDP broadcast). */
    @PluginMethod
    fun discover(call: PluginCall) = background(call) {
        val found = JSArray()
        val seen = mutableSetOf<String>()
        DatagramSocket().use { socket ->
            socket.broadcast = true
            socket.soTimeout = 400
            val probe = "EBOOKREADER_DISCOVER".toByteArray()
            val deadline = System.currentTimeMillis() + (call.getInt("timeoutMs") ?: 2500)
            var sent = 0
            while (System.currentTimeMillis() < deadline) {
                if (sent < 3) {
                    runCatching { socket.send(DatagramPacket(probe, probe.size, InetAddress.getByName("255.255.255.255"), 47631)) }
                    sent += 1
                }
                val buffer = ByteArray(512)
                val packet = DatagramPacket(buffer, buffer.size)
                try {
                    socket.receive(packet)
                    val reply = JSONObject(String(packet.data, 0, packet.length))
                    val host = packet.address.hostAddress ?: continue
                    if (reply.optString("app") == "ebook-reader" && seen.add(host)) {
                        found.put(JSObject().put("host", host).put("port", reply.optInt("port", 47630)).put("name", reply.optString("name")))
                    }
                } catch (_: SocketTimeoutException) {
                }
            }
        }
        call.resolve(JSObject().put("computers", found))
    }

    @PluginMethod
    fun pair(call: PluginCall) = background(call) {
        val host = call.getString("host") ?: throw IllegalArgumentException("thiếu địa chỉ máy tính")
        val port = call.getInt("port") ?: 47630
        val device = call.getString("device") ?: "${Build.MANUFACTURER} ${Build.MODEL}"
        val body = JSONObject().put("code", call.getString("code") ?: "").put("device", device)
        val reply = JSONObject(request("POST", "/sync/v1/pair", body, auth = false, root = "http://$host:$port"))
        prefs.edit().putString("host", host).putInt("port", port).putString("token", reply.getString("token"))
            .putString("name", reply.optString("name")).apply()
        call.resolve(JSObject().put("name", reply.optString("name")))
    }

    @PluginMethod
    fun connection(call: PluginCall) {
        val paired = !prefs.getString("token", "").isNullOrBlank()
        call.resolve(
            JSObject().put("paired", paired).put("host", prefs.getString("host", "")).put("port", prefs.getInt("port", 47630))
                .put("name", prefs.getString("name", "")),
        )
    }

    @PluginMethod
    fun unpair(call: PluginCall) {
        prefs.edit().clear().apply()
        call.resolve()
    }

    @PluginMethod
    fun remoteLibrary(call: PluginCall) = background(call) {
        val reply = JSONObject(request("GET", "/sync/v1/library"))
        val books = reply.getJSONArray("books")
        for (index in 0 until books.length()) {
            val book = books.getJSONObject(index)
            val local = Store.manifest(book.getString("id"))
            book.put("downloaded", local != null)
            book.put("localChapters", local?.optInt("chaptersAvailable") ?: 0)
        }
        call.resolve(JSObject().put("name", reply.optString("name")).put("books", books))
    }

    // ---- tải sách --------------------------------------------------------------------------------------------

    private fun fetchFile(id: String, relative: String, expectedSize: Long): Long {
        val target = Store.file(id, relative)
        if (expectedSize > 0 && target.isFile && target.length() == expectedSize) return 0
        target.parentFile?.mkdirs()
        val partial = File(target.path + ".part")
        val connection = URL("${base()}/sync/v1/books/$id/files/$relative").openConnection() as HttpURLConnection
        connection.connectTimeout = 5000
        connection.readTimeout = 30000
        connection.setRequestProperty("Authorization", "Bearer ${prefs.getString("token", "")}")
        val resumeFrom = if (partial.isFile) partial.length() else 0L
        if (resumeFrom > 0) connection.setRequestProperty("Range", "bytes=$resumeFrom-")
        val code = connection.responseCode
        if (code >= 400) throw IllegalStateException("Không tải được $relative (mã $code)")
        val append = code == 206
        java.io.FileOutputStream(partial, append).use { output -> connection.inputStream.use { it.copyTo(output, 256 * 1024) } }
        connection.disconnect()
        if (!partial.renameTo(target)) {
            target.delete()
            partial.renameTo(target)
        }
        return target.length()
    }

    /** Tải (hoặc cập nhật) một cuốn: chỉ tải file mới/đổi; book.json ghi CUỐI để sách chỉ hiện khi đã đủ file. */
    @PluginMethod
    fun download(call: PluginCall) {
        val id = call.getString("bookId") ?: return call.reject("thiếu bookId")
        call.setKeepAlive(true)
        downloads.execute {
            try {
                val manifest = JSONObject(request("GET", "/sync/v1/books/$id/manifest"))
                val chapters = manifest.getJSONArray("chapters")
                val files = mutableListOf<Pair<String, Long>>()
                for (index in 0 until chapters.length()) {
                    val chapter = chapters.getJSONObject(index)
                    if (!chapter.optBoolean("available")) continue
                    files += chapter.getString("file") to chapter.optLong("size")
                    files += chapter.getString("script") to 0L
                }
                files += "cast.json" to 0L
                val samples = manifest.optJSONArray("samples") ?: JSONArray()
                for (index in 0 until samples.length()) files += samples.getString(index) to 0L
                val total = files.sumOf { it.second }
                var done = 0L
                files.forEachIndexed { index, (relative, size) ->
                    fetchFile(id, relative, size)
                    done += size
                    notifyListeners("download", JSObject().put("bookId", id).put("done", done).put("total", total)
                        .put("files", index + 1).put("filesTotal", files.size))
                }
                Store.writeAtomic(File(Store.bookDir(id), "book.json"), manifest.toString())
                pushState(id)
                notifyListeners("download", JSObject().put("bookId", id).put("finished", true))
                call.resolve(JSObject().put("bookId", id))
            } catch (error: Exception) {
                notifyListeners("download", JSObject().put("bookId", id).put("error", error.message ?: "lỗi tải"))
                call.reject(error.message ?: "lỗi tải")
            } finally {
                call.setKeepAlive(false)
            }
        }
    }

    // ---- sách trên máy ---------------------------------------------------------------------------------------

    @PluginMethod
    fun localBooks(call: PluginCall) = background(call) {
        val books = JSArray()
        Store.books().forEach { manifest ->
            val id = manifest.getString("id")
            books.put(JSObject.fromJSONObject(manifest).put("state", JSObject.fromJSONObject(Store.state(id)))
                .put("bytes", Store.sizeOf(Store.bookDir(id))))
        }
        call.resolve(JSObject().put("books", books))
    }

    @PluginMethod
    fun book(call: PluginCall) = background(call) {
        val id = call.getString("id") ?: throw IllegalArgumentException("thiếu id")
        val manifest = Store.manifest(id) ?: throw IllegalStateException("Sách chưa được tải về máy")
        call.resolve(JSObject.fromJSONObject(manifest).put("state", JSObject.fromJSONObject(Store.state(id))))
    }

    @PluginMethod
    fun readText(call: PluginCall) = background(call) {
        val file = Store.file(call.getString("id") ?: "", call.getString("path") ?: "")
        call.resolve(JSObject().put("text", if (file.isFile) file.readText() else ""))
    }

    @PluginMethod
    fun path(call: PluginCall) {
        val file = Store.file(call.getString("id") ?: "", call.getString("path") ?: "")
        call.resolve(JSObject().put("path", file.absolutePath).put("exists", file.isFile))
    }

    @PluginMethod
    fun deleteBook(call: PluginCall) = background(call) {
        Store.deleteBook(call.getString("id") ?: "")
        call.resolve()
    }

    @PluginMethod
    fun storage(call: PluginCall) = background(call) {
        call.resolve(JSObject().put("bytes", Store.sizeOf(File(Store.root, "books"))).put("free", Store.root.usableSpace))
    }

    // ---- trạng thái nghe -------------------------------------------------------------------------------------

    private fun resolveState(call: PluginCall, state: JSONObject) {
        call.resolve(JSObject.fromJSONObject(state))
        val id = call.getString("id") ?: return
        io.execute { runCatching { pushState(id) } }
    }

    @PluginMethod
    fun progress(call: PluginCall) = background(call) {
        resolveState(call, Store.progress(call.getString("id")!!, call.getInt("chapterId")!!, call.getDouble("seconds")!!, call.getDouble("duration") ?: 0.0))
    }

    @PluginMethod
    fun setChapterDone(call: PluginCall) = background(call) {
        resolveState(call, Store.setChapterDone(call.getString("id")!!, call.getInt("chapterId")!!, call.getBoolean("done") ?: true))
    }

    @PluginMethod
    fun setFinished(call: PluginCall) = background(call) {
        resolveState(call, Store.setFinished(call.getString("id")!!, call.getBoolean("finished") ?: true))
    }

    @PluginMethod
    fun setRate(call: PluginCall) = background(call) {
        Store.setRate(call.getString("id")!!, call.getDouble("rate") ?: 1.0)
        call.resolve()
    }

    @PluginMethod
    fun addBookmark(call: PluginCall) = background(call) {
        val mark = Store.addBookmark(call.getString("id")!!, call.getInt("chapterId")!!, call.getDouble("seconds") ?: 0.0, call.getString("note") ?: "")
        call.resolve(JSObject.fromJSONObject(mark))
    }

    @PluginMethod
    fun updateBookmark(call: PluginCall) = background(call) {
        Store.updateBookmark(call.getString("id")!!, call.getString("markId")!!, call.getString("note") ?: "")
        call.resolve()
    }

    @PluginMethod
    fun deleteBookmark(call: PluginCall) = background(call) {
        Store.deleteBookmark(call.getString("id")!!, call.getString("markId")!!)
        call.resolve()
    }

    /** Gửi trạng thái nghe lên máy tính, nhận bản đã gộp (mới-hơn-thắng) - im lặng nếu không có mạng. */
    private fun pushState(id: String) {
        if (prefs.getString("token", "").isNullOrBlank()) return
        val merged = runCatching { JSONObject(request("POST", "/sync/v1/books/$id/state", Store.state(id))) }.getOrNull() ?: return
        Store.replaceState(id, merged)
    }

    @PluginMethod
    fun syncState(call: PluginCall) = background(call) {
        val id = call.getString("id") ?: throw IllegalArgumentException("thiếu id")
        pushState(id)
        call.resolve(JSObject.fromJSONObject(Store.state(id)))
    }
}
