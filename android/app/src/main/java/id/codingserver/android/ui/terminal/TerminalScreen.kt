package id.codingserver.android.ui.terminal

import android.annotation.SuppressLint
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.view.inputmethod.InputMethodManager
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.DisposableEffect
import id.codingserver.android.data.settings.TerminalPrefs
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import id.codingserver.android.data.api.ApiJson
import id.codingserver.android.data.api.TerminalCreate
import id.codingserver.android.data.api.TerminalSession
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.serializer

class TerminalBridge(private val c: TerminalController) {
    @JavascriptInterface fun onStatus(s: String?) { c.status.value = s ?: "" }
    @JavascriptInterface fun onReady() { c.ready.value = true }
    /** Terminal diketuk: munculkan keyboard (bila diaktifkan di pengaturan). */
    @JavascriptInterface fun onTap() { if (c.tapKeyboard) c.showKeyboard() }
    /** Ukuran huruf diubah dengan cubit dua jari: simpan ke pengaturan. */
    @JavascriptInterface fun onFontSize(px: Int) { c.onFontSizeChanged?.invoke(px) }
}

/** WebView xterm.js yang bertahan selama Activity; terhubung ke /ws/terminal/{id}. */
@SuppressLint("SetJavaScriptEnabled")
class TerminalController(context: Context) {
    val status = MutableStateFlow("disconnected")
    val ready = MutableStateFlow(false)
    var sessionId: String? = null
        private set
    @Volatile var tapKeyboard: Boolean = true
    var onFontSizeChanged: ((Int) -> Unit)? = null
    private val main = Handler(Looper.getMainLooper())

    val webView: WebView = WebView(context).apply {
        isFocusable = true
        isFocusableInTouchMode = true
        setOnTouchListener { v, ev ->
            if (ev.action == android.view.MotionEvent.ACTION_UP && !v.hasFocus()) v.requestFocus()
            false
        }
        settings.javaScriptEnabled = true
        settings.allowFileAccess = false
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: android.webkit.WebResourceRequest?) = true
        }
        addJavascriptInterface(TerminalBridge(this@TerminalController), "AndroidBridge")
        loadUrl("file:///android_asset/web/terminal.html")
    }

    fun detach() { (webView.parent as? ViewGroup)?.removeView(webView) }
    private fun js(code: String) = main.post { webView.evaluateJavascript(code, null) }
    private fun q(s: String) = ApiJson.encodeToString(String.serializer(), s)

    fun connect(sessionId: String, wsUrl: String) { this.sessionId = sessionId; js("CS_TERM.connect(${q(wsUrl)})") }
    fun disconnect() { sessionId = null; js("CS_TERM.disconnect()") }
    fun key(k: String) = js("CS_TERM.sendKey(${q(k)})")
    fun text(t: String) = js("CS_TERM.sendText(${q(t)})")
    fun fontSize(px: Int) = js("CS_TERM.setFontSize($px)")

    /** Terapkan pengaturan tampilan ke xterm.js. */
    fun apply(p: TerminalPrefs) {
        tapKeyboard = p.tapKeyboard
        js("CS_TERM.setOptions({fontSize:${p.fontSize},lineHeight:${p.lineHeight},theme:${q(p.theme)}," +
           "cursorStyle:${q(p.cursorStyle)},cursorBlink:${p.cursorBlink},fontFamily:${q(p.fontFamily)}})")
    }
    fun focus() = js("CS_TERM.focus()")
    /** Hitung ulang kolom/baris (dipanggil saat ukuran WebView berubah, mis. keyboard muncul/hilang). */
    fun fit() = js("CS_TERM.fit()")

    private val imm get() = webView.context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager

    /** Fokus ke terminal dan tampilkan keyboard (WebView tidak selalu memunculkannya sendiri). */
    fun showKeyboard() = main.post {
        webView.requestFocus()
        webView.evaluateJavascript("CS_TERM.focus()", null)
        main.postDelayed({ imm.showSoftInput(webView, InputMethodManager.SHOW_IMPLICIT) }, 80)
    }

    fun hideKeyboard() = main.post { imm.hideSoftInputFromWindow(webView.windowToken, 0) }
}

/** Terminal interaktif: banyak sesi, input perintah, output real-time, Ctrl-C, tutup sesi. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TerminalScreen(vm: AppViewModel, term: TerminalController, onMenu: () -> Unit = {}) {
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    val status by term.status.collectAsState()
    val ready by term.ready.collectAsState()
    var sessions by remember { mutableStateOf<List<TerminalSession>>(emptyList()) }
    var reload by remember { mutableIntStateOf(0) }
    var current by remember { mutableStateOf(term.sessionId) }
    val scope = rememberCoroutineScope()
    val imeVisible = WindowInsets.isImeVisible
    val prefs by vm.terminalPrefs.collectAsState()
    var showSettings by remember { mutableStateOf(false) }

    // Pengaturan tampilan diterapkan saat halaman terminal siap dan setiap kali diubah.
    LaunchedEffect(ready, prefs) { if (ready) term.apply(prefs) }
    DisposableEffect(prefs) {
        term.onFontSizeChanged = { px -> vm.setTerminalPrefs(vm.terminalPrefs.value.copy(fontSize = px)) }
        onDispose { term.onFontSizeChanged = null }
    }

    LaunchedEffect(client, reload) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.terminals() }.onSuccess { sessions = it.filter { s -> s.status == "running" } }
            .onFailure { vm.toast(it.message ?: "") }
    }

    fun connect(s: TerminalSession) {
        val c = client ?: return
        scope.launch {
            c.ensureFreshToken()
            term.connect(s.session_id, c.wsUrl("ws/terminal/${s.session_id}"))
            current = s.session_id
        }
    }

    fun newSession(cwd: String = "") {
        val c = client ?: return
        val p = project ?: run { vm.toast("Buka proyek dulu"); return }
        scope.launch {
            apiCall { c.api.createTerminal(TerminalCreate(p.id, cwd, 80, 24)) }
                .onSuccess { s -> reload++; connect(s) }
                .onFailure { vm.toast(it.message ?: "Gagal membuka terminal") }
        }
    }

    // Dibuka dari Project Explorer ("Buka di terminal"): sesi baru di folder itu.
    val openAt by vm.terminalAt.collectAsState()
    LaunchedEffect(ready, openAt) {
        val at = openAt ?: return@LaunchedEffect
        if (ready) { vm.consumeTerminalAt(); newSession(at) }
    }
    LaunchedEffect(ready, sessions) {
        if (ready && current == null && sessions.isNotEmpty() && openAt == null) connect(sessions.first())
    }
    // Keyboard muncul/hilang mengubah tinggi terminal -> hitung ulang baris.
    LaunchedEffect(imeVisible) { term.fit() }

    Column(Modifier.fillMaxSize()) {
        // ---- baris atas ringkas: menu + tab sesi + tambah + status ----
        Row(Modifier.fillMaxWidth().height(40.dp).padding(horizontal = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onMenu, modifier = Modifier.size(36.dp)) { Icon(Icons.Default.Menu, "Menu", Modifier.size(20.dp)) }
            Row(Modifier.weight(1f).horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically) {
                sessions.forEachIndexed { i, s ->
                    val folder = s.working_directory.trimEnd('/').substringAfterLast('/')
                    val atRoot = project?.let { p -> s.working_directory.trimEnd('/').endsWith("/" + p.id) } ?: true
                    SessionTab(if (atRoot) "Sesi ${i + 1}" else "Sesi ${i + 1} · $folder", selected = s.session_id == current, onClick = { connect(s) }, onClose = {
                        val c = client ?: return@SessionTab
                        scope.launch {
                            apiCall { c.api.closeTerminal(s.session_id) }
                            if (current == s.session_id) { term.disconnect(); current = null }
                            reload++
                        }
                    })
                }
                IconButton(onClick = { newSession() }, modifier = Modifier.size(32.dp)) { Icon(Icons.Default.Add, "Sesi baru", Modifier.size(20.dp)) }
            }
            val (dot, label) = when (status) {
                "connected" -> Color(0xFF43A047) to "terhubung"
                "connecting" -> Color(0xFFFFA000) to "menghubungkan"
                "exited" -> Color.Gray to "selesai"
                "error" -> Color(0xFFE53935) to "error"
                else -> Color.Gray to "terputus"
            }
            Box(Modifier.size(8.dp).clip(RoundedCornerShape(50)).background(dot))
            Text(label, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(start = 4.dp))
            IconButton(onClick = { showSettings = true }, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Default.Settings, "Pengaturan tampilan terminal", Modifier.size(20.dp))
            }
        }
        if (sessions.isEmpty()) Text("Tidak ada sesi. Tekan + untuk membuka terminal di folder proyek (${project?.name ?: "-"}).",
                                     Modifier.padding(horizontal = 8.dp, vertical = 4.dp), style = MaterialTheme.typography.bodySmall)
        Box(Modifier.weight(1f).fillMaxWidth().onSizeChanged { term.fit() }) {
            AndroidView(factory = { term.detach(); term.webView }, modifier = Modifier.fillMaxSize())
        }
        // ---- baris tombol khusus (ringkas) ----
        if (prefs.extraKeys) Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant)
                .horizontalScroll(rememberScrollState()).padding(start = 4.dp, end = 4.dp, top = 3.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            listOf("CTRL_A" to "^A", "CTRL_E" to "^E", "CTRL_R" to "^R", "CTRL_U" to "^U", "CTRL_W" to "^W",
                   "PGUP" to "PgUp", "PGDN" to "PgDn").forEach { (k, l) -> KeyButton(l) { term.key(k); term.focus() } }
            listOf("$", "*", "'", "\"", ";", ":", "=", "_").forEach { t -> KeyButton(t) { term.text(t); term.focus() } }
        }
        if (prefs.showKeys) Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant)
                .horizontalScroll(rememberScrollState()).padding(horizontal = 4.dp, vertical = 3.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            KeyButton(if (imeVisible) "⌨ ▼" else "⌨ ▲", highlight = true) {
                if (imeVisible) term.hideKeyboard() else term.showKeyboard()
            }
            listOf("ESC" to "ESC", "TAB" to "TAB", "CTRL_C" to "^C", "CTRL_D" to "^D", "CTRL_Z" to "^Z", "CTRL_L" to "^L",
                   "UP" to "↑", "DOWN" to "↓", "LEFT" to "←", "RIGHT" to "→", "HOME" to "HOME", "END" to "END").forEach { (k, l) ->
                KeyButton(l) { term.key(k); term.focus() }
            }
            listOf("|", "/", "-", "~", "&&", ">").forEach { t -> KeyButton(t) { term.text(t); term.focus() } }
        }
    }
    if (showSettings) TerminalSettingsDialog(prefs, onChange = { vm.setTerminalPrefs(it) }, onDismiss = { showSettings = false })
}

@Composable
private fun SessionTab(label: String, selected: Boolean, onClick: () -> Unit, onClose: () -> Unit) {
    val bg = if (selected) MaterialTheme.colorScheme.primaryContainer else Color.Transparent
    Row(Modifier.padding(end = 4.dp).height(30.dp).clip(RoundedCornerShape(8.dp)).background(bg)
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick).padding(start = 10.dp, end = 2.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.labelLarge)
        IconButton(onClick = onClose, modifier = Modifier.size(26.dp)) { Icon(Icons.Default.Close, "Tutup $label", Modifier.size(14.dp)) }
    }
}

@Composable
private fun KeyButton(label: String, highlight: Boolean = false, onClick: () -> Unit) {
    Box(Modifier.height(34.dp).widthIn(min = 40.dp).clip(RoundedCornerShape(6.dp))
            .background(if (highlight) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface)
            .clickable(onClick = onClick).padding(horizontal = 10.dp),
        contentAlignment = Alignment.Center) {
        Text(label, style = MaterialTheme.typography.labelLarge,
             color = if (highlight) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface)
    }
}
