package id.codingserver.android.ui.editor

import android.annotation.SuppressLint
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import id.codingserver.android.data.api.ApiJson
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.Serializable
import kotlin.coroutines.resume

sealed interface EditorEvent {
    data class Changed(val tabId: String, val dirty: Boolean) : EditorEvent
    data class SaveRequested(val tabId: String) : EditorEvent
    /** Go-to-definition (LSP) menunjuk file lain di proyek. */
    data class OpenFile(val path: String, val line: Int, val column: Int) : EditorEvent
    data class RunRequested(val tabId: String) : EditorEvent
    data class References(val result: ReferenceResult) : EditorEvent
    data class RenameDone(val result: RenameResult) : EditorEvent
    data class Outline(val items: List<OutlineItem>) : EditorEvent
}

@Serializable data class OutlineItem(val name: String, val kind: String = "", val detail: String = "", val depth: Int = 0,
                                     val line: Int = 1)
@Serializable data class SnippetItem(val label: String, val detail: String = "", val preview: String = "")

@Serializable data class Problem(val line: Int, val column: Int = 1, val severity: String = "error", val message: String = "")
@Serializable data class ReferenceItem(val path: String? = null, val uri: String = "", val line: Int = 1, val column: Int = 1,
                                       val text: String = "")
@Serializable data class ReferenceResult(val symbol: String = "", val items: List<ReferenceItem> = emptyList())
/** Satu TextEdit LSP (0-based, offset UTF-16 = indeks String Kotlin). */
@Serializable data class TextEditItem(val startLine: Int, val startChar: Int, val endLine: Int, val endChar: Int, val newText: String)
@Serializable data class RenameResult(val newName: String = "", val files: Int = 0, val edits: Int = 0, val local: Int = 0,
                                      val remote: Map<String, List<TextEditItem>> = emptyMap())
@Serializable data class PreloadFile(val path: String, val text: String, val lang: String)

/** Terapkan TextEdit LSP ke teks (untuk file yang tidak terbuka di editor saat rename). */
object TextEdits {
    fun apply(text: String, edits: List<TextEditItem>): String {
        val starts = mutableListOf(0)
        text.forEachIndexed { i, ch -> if (ch == '\n') starts += i + 1 }
        fun off(line: Int, ch: Int): Int {
            if (line >= starts.size) return text.length
            val lineEnd = if (line + 1 < starts.size) starts[line + 1] - 1 else text.length
            return (starts[line] + ch).coerceAtMost(lineEnd)
        }
        val sb = StringBuilder(text)
        edits.map { Triple(off(it.startLine, it.startChar), off(it.endLine, it.endChar), it.newText) }
            .sortedByDescending { it.first }
            .forEach { (a, b, t) -> sb.replace(a, maxOf(a, b), t) }
        return sb.toString()
    }
}

@Serializable data class Symbol(val name: String, val line: Int, val text: String = "")
@Serializable data class Diagnostic(val line: Int, val column: Int? = null, val severity: String = "error", val message: String)

/** Jembatan JS -> Kotlin. Dipanggil dari thread WebView, diteruskan lewat flow. */
class EditorBridge(private val c: EditorController) {
    @JavascriptInterface fun onReady() { c.ready.complete(Unit) }
    @JavascriptInterface fun onChange(tabId: String?, dirty: Boolean) { tabId?.let { c.events.tryEmit(EditorEvent.Changed(it, dirty)) } }
    @JavascriptInterface fun onSave(tabId: String?) { tabId?.let { c.events.tryEmit(EditorEvent.SaveRequested(it)) } }
    @JavascriptInterface fun onRun(tabId: String?) { tabId?.let { c.events.tryEmit(EditorEvent.RunRequested(it)) } }
    @JavascriptInterface fun onCursor(line: Int, col: Int) { c.cursor.value = line to col }
    /** Konfigurasi LSP dibaca JS setiap membuka koneksi (token selalu yang terbaru). */
    @JavascriptInterface fun lspConfig(): String = runCatching { c.lspConfig() }.getOrDefault("")
    @JavascriptInterface fun onLspStatus(text: String?) { c.lspStatus.value = text.orEmpty() }
    @JavascriptInterface fun onOpenFile(path: String?, line: Int, col: Int) {
        path?.let { c.events.tryEmit(EditorEvent.OpenFile(it, line, col)) }
    }
    @JavascriptInterface fun onProblems(errors: Int, warnings: Int) { c.problems.value = errors to warnings }
    @JavascriptInterface fun onBreadcrumb(text: String?) { c.breadcrumb.value = text.orEmpty() }
    @JavascriptInterface fun onOutline(json: String?) {
        json?.let { runCatching { ApiJson.decodeFromString(ListSerializer(OutlineItem.serializer()), it) }.getOrNull() }
            ?.let { c.events.tryEmit(EditorEvent.Outline(it)) }
    }
    @JavascriptInterface fun onReferences(json: String?) {
        json?.let { runCatching { ApiJson.decodeFromString(ReferenceResult.serializer(), it) }.getOrNull() }
            ?.let { c.events.tryEmit(EditorEvent.References(it)) }
    }
    @JavascriptInterface fun onRenameEdits(json: String?) {
        json?.let { runCatching { ApiJson.decodeFromString(RenameResult.serializer(), it) }.getOrNull() }
            ?.let { c.events.tryEmit(EditorEvent.RenameDone(it)) }
    }
}

/**
 * Satu WebView CodeMirror 6 yang hidup selama Activity (tab & riwayat undo tetap ada saat
 * berpindah layar). Semua pemanggilan JS lewat thread utama.
 */
@SuppressLint("SetJavaScriptEnabled")
class EditorController(context: Context) {
    val ready = CompletableDeferred<Unit>()
    val events = MutableSharedFlow<EditorEvent>(extraBufferCapacity = 64)
    val eventsFlow: SharedFlow<EditorEvent> get() = events
    val cursor = MutableStateFlow(1 to 1)
    val cursorFlow: StateFlow<Pair<Int, Int>> get() = cursor
    /** JSON {wsBase, token, projectId, enabled} untuk klien LSP di WebView; diisi MainActivity. */
    @Volatile var lspConfig: () -> String = { "" }
    val lspStatus = MutableStateFlow("")
    /** (jumlah error, jumlah peringatan) file aktif — dari LSP atau output build. */
    val problems = MutableStateFlow(0 to 0)
    /** Fungsi/kelas tempat kursor berada (mis. "Kalkulator › tambah"). */
    val breadcrumb = MutableStateFlow("")
    private val main = Handler(Looper.getMainLooper())

    // Pakai context Activity (bukan applicationContext): koneksi keyboard (IME) WebView lebih andal.
    val webView: WebView = WebView(context).apply {
        isFocusable = true
        isFocusableInTouchMode = true
        // Pastikan WebView mendapat fokus saat disentuh supaya keyboard muncul & ketikan masuk ke editor.
        setOnTouchListener { v, ev ->
            if (ev.action == android.view.MotionEvent.ACTION_UP) {
                v.requestFocus()
                post {
                    val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
                    imm.showSoftInput(v, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
                }
            }
            false
        }
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.builtInZoomControls = false
        webChromeClient = WebChromeClient()
        webViewClient = object : WebViewClient() {
            // Editor tidak boleh membuka halaman lain.
            override fun shouldOverrideUrlLoading(view: WebView?, request: android.webkit.WebResourceRequest?) = true

            // Paksa teks editor terlihat walau CSS bundel gagal termuat (mencegah editor putih/kosong).
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                view?.evaluateJavascript("""
                    (function() {
                      if (document.getElementById('cs-editor-visibility-fix')) return;
                      var style = document.createElement('style');
                      style.id = 'cs-editor-visibility-fix';
                      style.textContent = [
                        'html,body,#editor,.cm-editor,.cm-scroller { visibility: visible !important; opacity: 1 !important; }',
                        '.cm-content,.cm-line,.cm-content span { opacity: 1 !important; visibility: visible !important; }',
                        '.cm-content { font-size: inherit !important; }'
                      ].join('');
                      document.head.appendChild(style);
                    })();
                """.trimIndent(), null)
            }
        }
        addJavascriptInterface(EditorBridge(this@EditorController), "AndroidBridge")
        loadUrl("file:///android_asset/web/editor.html")
    }

    fun detach() { (webView.parent as? ViewGroup)?.removeView(webView) }

    suspend fun eval(js: String): String? {
        ready.await()
        return suspendCancellableCoroutine { cont ->
            main.post { webView.evaluateJavascript(js) { r -> if (cont.isActive) cont.resume(r) } }
        }
    }

    private fun q(s: String) = ApiJson.encodeToString(String.serializer(), s)
    private fun decodeString(raw: String?): String? =
        if (raw == null || raw == "null") null else runCatching { ApiJson.decodeFromString(String.serializer(), raw) }.getOrNull()

    suspend fun hasTab(id: String) = eval("CS.hasTab(${q(id)})") == "true"
    suspend fun openTab(id: String, text: String, filename: String) { eval("CS.openTab(${q(id)}, ${q(text)}, ${q(filename)})") }
    suspend fun switchTab(id: String) = eval("CS.switchTab(${q(id)})") == "true"
    suspend fun closeTab(id: String) { eval("CS.closeTab(${q(id)})") }
    suspend fun renameTab(old: String, new: String, filename: String) { eval("CS.renameTab(${q(old)}, ${q(new)}, ${q(filename)})") }
    suspend fun getDoc(id: String): String? = decodeString(eval("CS.getDoc(${q(id)})"))
    suspend fun setDoc(id: String, text: String, markSaved: Boolean) { eval("CS.setDoc(${q(id)}, ${q(text)}, $markSaved)") }
    suspend fun markSaved(id: String) { eval("CS.markSaved(${q(id)})") }
    suspend fun isDirty(id: String) = eval("CS.isDirty(${q(id)})") == "true"
    suspend fun undo() { eval("CS.undo()") }
    suspend fun redo() { eval("CS.redo()") }
    suspend fun openSearch() { eval("CS.openSearch()") }
    suspend fun gotoLine(line: Int, column: Int = 1) { eval("CS.gotoLine($line, $column)") }
    /** Info simbol di kursor (hover LSP), tampil sebagai panel di editor. */
    suspend fun hover() { eval("CS.hover()") }
    /** Sambung ulang language server (proyek/token/pengaturan berubah). */
    suspend fun lspReset() { eval("CS.lspReset()") }
    suspend fun gotoDefinition() = eval("CS.gotoDefinition()") == "true"
    suspend fun foldAll() { eval("CS.foldAll()") }
    suspend fun unfoldAll() { eval("CS.unfoldAll()") }
    suspend fun insert(text: String) { eval("CS.insert(${q(text)})") }
    /** Baris tombol ekstra: ketik teks (kurung berpasangan otomatis) / jalankan perintah editor (left, tab, comment, …). */
    suspend fun typeText(text: String) { eval("CS.typeText(${q(text)})") }
    suspend fun key(name: String) { eval("CS.key(${q(name)})") }
    suspend fun applyPrefs(dark: Boolean, font: Int, wrap: Boolean, tab: Int, textColor: String = "", backgroundColor: String = "") {
        eval("CS.configure({theme:${q(if (dark) "dark" else "light")},fontSize:$font,wordWrap:$wrap,tabSize:$tab,textColor:${q(textColor)},backgroundColor:${q(backgroundColor)}})")
    }
    suspend fun symbols(): List<Symbol> {
        val raw = decodeString(eval("CS.symbols()")) ?: return emptyList()
        return runCatching { ApiJson.decodeFromString(ListSerializer(Symbol.serializer()), raw) }.getOrDefault(emptyList())
    }
    suspend fun setDiagnostics(d: List<Diagnostic>) {
        eval("CS.setDiagnostics(${q(ApiJson.encodeToString(ListSerializer(Diagnostic.serializer()), d))})")
    }
    suspend fun clearDiagnostics() { eval("CS.clearDiagnostics()") }
    suspend fun problemList(): List<Problem> {
        val raw = decodeString(eval("CS.problems()")) ?: return emptyList()
        return runCatching { ApiJson.decodeFromString(ListSerializer(Problem.serializer()), raw) }.getOrDefault(emptyList())
    }
    suspend fun applyFormatted(id: String, text: String) = eval("CS.applyFormatted(${q(id)}, ${q(text)})") == "true"
    suspend fun currentWord(): String = decodeString(eval("CS.currentWord()")).orEmpty()
    suspend fun lspServer(): String = decodeString(eval("CS.lspServer()")).orEmpty()
    private fun preloadJson(files: List<PreloadFile>?) =
        if (files.isNullOrEmpty()) "null" else q(ApiJson.encodeToString(ListSerializer(PreloadFile.serializer()), files))
    suspend fun setGitBase(id: String, text: String?) { eval("CS.setGitBase(${q(id)}, ${text?.let { q(it) } ?: "null"})") }
    suspend fun outline() { eval("CS.outline()") }
    suspend fun snippets(): List<SnippetItem> {
        val raw = decodeString(eval("CS.snippets()")) ?: return emptyList()
        return runCatching { ApiJson.decodeFromString(ListSerializer(SnippetItem.serializer()), raw) }.getOrDefault(emptyList())
    }
    suspend fun insertSnippet(label: String) { eval("CS.insertSnippet(${q(label)})") }
    suspend fun findReferences(preload: List<PreloadFile>? = null) { eval("CS.findReferences(${preloadJson(preload)})") }
    suspend fun renameSymbol(newName: String, preload: List<PreloadFile>? = null) {
        eval("CS.renameSymbol(${q(newName)}, ${preloadJson(preload)})")
    }
}

/** Ambil error kompilasi/runtime dari output sebagai diagnostics untuk file tertentu. */
object DiagnosticParser {
    private val gccLike = Regex("""^(.+?):(\d+):(?:(\d+):)?\s*(fatal error|error|warning|note)?:?\s*(.*)$""")
    private val pyTrace = Regex("""File "(.+?)", line (\d+)""")
    private val javac = Regex("""^(.+?\.java):(\d+):\s*(error|warning):\s*(.*)$""")
    private val csharp = Regex("""^(.+?\.cs)\((\d+),(\d+)\):\s*(error|warning)\s+\w+:\s*(.*?)(?:\s*\[.*\])?$""")
    private val php = Regex("""(?:PHP )?(Parse error|Fatal error|Warning):\s*(.*) in (.+?) on line (\d+)""")

    fun parse(output: String, file: String): List<Diagnostic> {
        val name = file.substringAfterLast('/')
        val out = mutableListOf<Diagnostic>()
        val lines = output.lines()
        for ((i, raw) in lines.withIndex()) {
            val line = raw.trim()
            val cs = csharp.find(line)
            if (cs != null) {
                if (cs.groupValues[1].endsWith(name)) out += Diagnostic(cs.groupValues[2].toInt(), cs.groupValues[3].toInt(),
                    cs.groupValues[4], cs.groupValues[5])
                continue
            }
            val jv = javac.find(line)
            if (jv != null) {
                if (jv.groupValues[1].endsWith(name)) out += Diagnostic(jv.groupValues[2].toInt(), null, jv.groupValues[3], jv.groupValues[4])
                continue
            }
            val ph = php.find(line)
            if (ph != null) {
                if (ph.groupValues[3].endsWith(name)) out += Diagnostic(ph.groupValues[4].toInt(), null,
                    if (ph.groupValues[1] == "Warning") "warning" else "error", ph.groupValues[2])
                continue
            }
            val py = pyTrace.find(line)
            if (py != null) {
                if (py.groupValues[1].endsWith(name)) {
                    val msg = lines.drop(i + 1).firstOrNull { l -> l.isNotBlank() && !l.startsWith("  ") }
                        ?: lines.lastOrNull { it.isNotBlank() } ?: "error"
                    out += Diagnostic(py.groupValues[2].toInt(), null, "error", msg.trim())
                }
                continue
            }
            val g = gccLike.find(line)
            if (g != null && g.groupValues[1].endsWith(name) && !g.groupValues[1].contains(' ')) {
                val sev = when (g.groupValues[4]) { "warning" -> "warning"; "note" -> "info"; else -> "error" }
                out += Diagnostic(g.groupValues[2].toInt(), g.groupValues[3].toIntOrNull(), sev, g.groupValues[5])
            }
        }
        // Python: hanya frame terakhir yang relevan
        return out.distinctBy { Triple(it.line, it.column, it.message) }
    }
}
