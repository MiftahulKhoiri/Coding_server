package id.codingserver.android.ui.http

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.ApiJson
import id.codingserver.android.data.api.HttpCollection
import id.codingserver.android.data.api.HttpRequestIn
import id.codingserver.android.data.api.HttpResponseOut
import id.codingserver.android.data.api.HttpSaved
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InputDialog
import id.codingserver.android.ui.common.formatBytes
import id.codingserver.android.ui.output.statusColor
import id.codingserver.android.ui.theme.Mono
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement

private fun parseKv(text: String): Map<String, String> =
    text.lines().mapNotNull { l ->
        val i = l.indexOf(':').takeIf { it > 0 } ?: l.indexOf('=').takeIf { it > 0 } ?: return@mapNotNull null
        l.substring(0, i).trim() to l.substring(i + 1).trim()
    }.toMap()

private val PrettyJson = kotlinx.serialization.json.Json { prettyPrint = true }

private fun pretty(body: String): String = runCatching {
    PrettyJson.encodeToString(JsonElement.serializer(), ApiJson.parseToJsonElement(body))
}.getOrDefault(body)

/** HTTP Client / API tester (lewat server, dengan perlindungan SSRF) + koleksi request. */
@Composable
fun HttpScreen(vm: AppViewModel) {
    val client by vm.client.collectAsState()
    var method by remember { mutableStateOf("GET") }
    var url by remember { mutableStateOf("https://httpbin.org/get") }
    var headers by remember { mutableStateOf("Accept: application/json") }
    var params by remember { mutableStateOf("") }
    var bodyType by remember { mutableStateOf("none") }
    var body by remember { mutableStateOf("") }
    var resp by remember { mutableStateOf<HttpResponseOut?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var collections by remember { mutableStateOf<List<HttpCollection>>(emptyList()) }
    var saving by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(client, reload) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.httpCollections() }.onSuccess { collections = it.collections }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf("GET", "POST", "PUT", "PATCH", "DELETE").forEach { m -> FilterChip(method == m, { method = m }, label = { Text(m) }) }
        }
        OutlinedTextField(url, { url = it }, label = { Text("URL") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(headers, { headers = it }, label = { Text("Headers (Nama: nilai per baris)") }, textStyle = Mono, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(params, { params = it }, label = { Text("Query params (nama=nilai per baris)") }, textStyle = Mono, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf("none", "json", "form", "raw").forEach { t -> FilterChip(bodyType == t, { bodyType = t }, label = { Text(t) }) }
        }
        if (bodyType != "none") OutlinedTextField(body, { body = it }, label = { Text(if (bodyType == "form") "Form (nama=nilai per baris)" else "Body") },
            textStyle = Mono, modifier = Modifier.fillMaxWidth().heightIn(min = 100.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Button(enabled = !busy && url.isNotBlank(), onClick = {
                val c = client ?: return@Button
                busy = true; error = null
                scope.launch {
                    val req = HttpRequestIn(
                        method = method, url = url.trim(), headers = parseKv(headers), params = parseKv(params),
                        body = body.takeIf { bodyType == "json" || bodyType == "raw" }, body_type = bodyType,
                        form = if (bodyType == "form") parseKv(body) else null,
                    )
                    apiCall { c.api.httpRequest(req) }.onSuccess { resp = it }.onFailure { error = it.message }
                    busy = false
                }
            }) { Text(if (busy) "Mengirim…" else "Kirim") }
            OutlinedButton(onClick = { saving = true }) { Text("Simpan") }
        }
        error?.let { ErrorCard(it) }
        resp?.let { r ->
            Text("${r.status_code} ${r.reason} · ${r.time_ms} ms · ${formatBytes(r.size)}", color = statusColor(if (r.status_code < 400) "COMPLETED" else "FAILED"),
                 style = MaterialTheme.typography.titleSmall)
            Text("Headers", style = MaterialTheme.typography.labelMedium)
            SelectionContainer { Text(r.headers.entries.joinToString("\n") { "${it.key}: ${it.value}" }, style = Mono) }
            Text("Body" + if (r.truncated) " (dipotong)" else "", style = MaterialTheme.typography.labelMedium)
            SelectionContainer { Text(pretty(r.body), style = Mono, modifier = Modifier.horizontalScroll(rememberScrollState())) }
        }
        if (collections.isNotEmpty()) {
            Text("Koleksi", style = MaterialTheme.typography.titleSmall)
            collections.forEach { col ->
                Text(col.name, style = MaterialTheme.typography.labelLarge)
                col.requests.forEach { s ->
                    Text("${s.method} ${s.name} — ${s.url}", style = MaterialTheme.typography.bodySmall,
                         modifier = Modifier.fillMaxWidth().clickable {
                             method = s.method; url = s.url; bodyType = s.body_type; body = s.body ?: ""
                             headers = s.headers.entries.joinToString("\n") { "${it.key}: ${it.value}" }
                             params = s.params.entries.joinToString("\n") { "${it.key}=${it.value}" }
                         }.padding(vertical = 4.dp))
                }
            }
        }
    }
    if (saving) InputDialog("Simpan request", "Nama", onConfirm = { name ->
        val c = client
        if (c != null) scope.launch {
            apiCall { c.api.saveHttp(HttpSaved(name = name, method = method, url = url, headers = parseKv(headers),
                                               params = parseKv(params), body = body.takeIf { bodyType != "none" }, body_type = bodyType)) }
                .onSuccess { reload++; vm.toast("Tersimpan") }.onFailure { vm.toast(it.message ?: "") }
        }
    }, onDismiss = { saving = false })
}
