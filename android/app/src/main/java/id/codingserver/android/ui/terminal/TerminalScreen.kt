package id.codingserver.android.ui.terminal

import android.annotation.SuppressLint
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
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
import androidx.compose.material3.AssistChip
import androidx.compose.material3.FilterChip
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
}

/** WebView xterm.js yang bertahan selama Activity; terhubung ke /ws/terminal/{id}. */
@SuppressLint("SetJavaScriptEnabled")
class TerminalController(context: Context) {
    val status = MutableStateFlow("disconnected")
    val ready = MutableStateFlow(false)
    var sessionId: String? = null
        private set
    private val main = Handler(Looper.getMainLooper())

    val webView: WebView = WebView(context.applicationContext).apply {
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
    fun focus() = js("CS_TERM.focus()")
}

/** Terminal interaktif: banyak sesi, input perintah, output real-time, Ctrl-C, tutup sesi. */
@Composable
fun TerminalScreen(vm: AppViewModel, term: TerminalController) {
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    val status by term.status.collectAsState()
    val ready by term.ready.collectAsState()
    var sessions by remember { mutableStateOf<List<TerminalSession>>(emptyList()) }
    var reload by remember { mutableIntStateOf(0) }
    var current by remember { mutableStateOf(term.sessionId) }
    val scope = rememberCoroutineScope()

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

    fun newSession() {
        val c = client ?: return
        val p = project ?: run { vm.toast("Buka proyek dulu"); return }
        scope.launch {
            apiCall { c.api.createTerminal(TerminalCreate(p.id, "", 80, 24)) }
                .onSuccess { s -> reload++; connect(s) }
                .onFailure { vm.toast(it.message ?: "Gagal membuka terminal") }
        }
    }

    LaunchedEffect(ready, sessions) {
        if (ready && current == null && sessions.isNotEmpty()) connect(sessions.first())
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(4.dp), verticalAlignment = Alignment.CenterVertically) {
            sessions.forEachIndexed { i, s ->
                FilterChip(selected = s.session_id == current, onClick = { connect(s) },
                    label = { Text("Sesi ${i + 1}") },
                    trailingIcon = {
                        IconButton(onClick = {
                            val c = client ?: return@IconButton
                            scope.launch {
                                apiCall { c.api.closeTerminal(s.session_id) }
                                if (current == s.session_id) { term.disconnect(); current = null }
                                reload++
                            }
                        }) { Icon(Icons.Default.Close, "Tutup sesi") }
                    }, modifier = Modifier.padding(end = 4.dp))
            }
            IconButton(onClick = { newSession() }) { Icon(Icons.Default.Add, "Sesi baru") }
            Text(status, style = MaterialTheme.typography.labelSmall)
        }
        if (sessions.isEmpty()) Text("Tidak ada sesi. Tekan + untuk membuka terminal di folder proyek (${project?.name ?: "-"}).",
                                     Modifier.padding(8.dp), style = MaterialTheme.typography.bodySmall)
        Box(Modifier.weight(1f).fillMaxWidth()) {
            AndroidView(factory = { term.detach(); term.webView }, modifier = Modifier.fillMaxSize())
        }
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(2.dp)) {
            listOf("ESC", "TAB", "CTRL_C", "CTRL_D", "CTRL_Z", "CTRL_L", "UP", "DOWN", "LEFT", "RIGHT", "HOME", "END").forEach { k ->
                AssistChip(onClick = { term.key(k); term.focus() }, label = { Text(k.replace("CTRL_", "^")) },
                           modifier = Modifier.padding(end = 4.dp))
            }
            listOf("|", "/", "-", "~", "&&", ">").forEach { s ->
                AssistChip(onClick = { term.text(s); term.focus() }, label = { Text(s) }, modifier = Modifier.padding(end = 4.dp))
            }
        }
    }
}
