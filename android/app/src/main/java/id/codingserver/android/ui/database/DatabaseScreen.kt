package id.codingserver.android.ui.database

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.ApiException
import id.codingserver.android.data.api.DbCreate
import id.codingserver.android.data.api.DbItem
import id.codingserver.android.data.api.DbQuery
import id.codingserver.android.data.api.DbQueryResult
import id.codingserver.android.data.api.DbSchema
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InputDialog
import id.codingserver.android.ui.common.formatBytes
import id.codingserver.android.ui.theme.Mono
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive

/** Database Manager SQLite: daftar/buat DB, skema, query baca/tulis, konfirmasi operasi destruktif. */
@Composable
fun DatabaseScreen(vm: AppViewModel) {
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    var projectScope by remember { mutableStateOf(false) }
    var dbs by remember { mutableStateOf<List<DbItem>>(emptyList()) }
    var selected by remember { mutableStateOf<String?>(null) }
    var schema by remember { mutableStateOf<DbSchema?>(null) }
    var sql by remember { mutableStateOf("SELECT name FROM sqlite_master;") }
    var writeMode by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<DbQueryResult?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirm by remember { mutableStateOf(false) }
    var creating by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    val pid = if (projectScope) project?.id else null

    LaunchedEffect(client, projectScope, reload) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.databases(pid) }.onSuccess { dbs = it.databases }.onFailure { error = it.message }
    }
    LaunchedEffect(selected) {
        val c = client ?: return@LaunchedEffect
        val db = selected ?: return@LaunchedEffect
        apiCall { c.api.schema(db, pid) }.onSuccess { schema = it }.onFailure { error = it.message }
    }

    fun execute(confirmed: Boolean) {
        val c = client ?: return
        val db = selected ?: return
        error = null
        scope.launch {
            apiCall { c.api.query(DbQuery(db, pid, sql, if (writeMode) "write" else "read", confirmed)) }
                .onSuccess { result = it; if (writeMode) apiCall { c.api.schema(db, pid) }.onSuccess { s -> schema = s } }
                .onFailure {
                    val e = it as ApiException
                    if (e.code == "confirmation_required") confirm = true else error = e.message
                }
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip(!projectScope, { projectScope = false; selected = null }, label = { Text("DB saya") })
            FilterChip(projectScope, { projectScope = true; selected = null }, label = { Text("DB di proyek") }, enabled = project != null)
            OutlinedButton(onClick = { creating = true }) { Text("+ DB") }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            dbs.forEach { d -> FilterChip(selected == d.name, { selected = d.name }, label = { Text("${d.name} (${formatBytes(d.size)})") }) }
        }
        if (dbs.isEmpty()) Text("Belum ada database.", style = MaterialTheme.typography.bodySmall)
        schema?.let { s ->
            Text("Skema", style = MaterialTheme.typography.titleSmall)
            s.objects.forEach { o ->
                Text("${o.type} ${o.name}" + (o.row_count?.let { " · $it baris" } ?: "") +
                     (o.columns?.joinToString(prefix = " (", postfix = ")") { col -> "${col.name} ${col.type}${if (col.pk) " PK" else ""}" } ?: ""),
                     style = MaterialTheme.typography.bodySmall,
                     modifier = Modifier.clickable { sql = "SELECT * FROM \"${o.name}\" LIMIT 100;" })
            }
        }
        OutlinedTextField(sql, { sql = it }, label = { Text("SQL") }, textStyle = Mono, modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip(!writeMode, { writeMode = false }, label = { Text("Baca") })
            FilterChip(writeMode, { writeMode = true }, label = { Text("Tulis") })
            Button(enabled = selected != null, onClick = { execute(false) }) { Text("Jalankan") }
        }
        error?.let { ErrorCard(it) }
        result?.let { res ->
            Text("Selesai dalam ${res.duration_ms} ms (mode ${res.mode})", style = MaterialTheme.typography.labelSmall)
            res.results.forEach { st ->
                if (st.columns != null) ResultTable(st.columns, st.rows ?: emptyList(), st.truncated)
                else Text("OK: ${st.statement.take(60)} — ${st.rowcount ?: 0} baris terpengaruh", style = MaterialTheme.typography.bodySmall)
            }
        }
    }

    if (confirm) ConfirmDialog("Operasi destruktif", "Query ini berisi DROP/DELETE/ALTER. Lanjutkan?", "Lanjutkan",
        onConfirm = { execute(true) }, onDismiss = { confirm = false })
    if (creating) InputDialog("Database baru", if (projectScope) "Path di proyek (mis. data/app.db)" else "Nama (mis. latihan)",
        onConfirm = { name ->
            val c = client
            if (c != null) scope.launch {
                apiCall { c.api.createDatabase(DbCreate(name, pid)) }.onSuccess { reload++ }.onFailure { error = it.message }
            }
        }, onDismiss = { creating = false })
}

@Composable
private fun ResultTable(columns: List<String>, rows: List<List<kotlinx.serialization.json.JsonElement>>, truncated: Boolean) {
    Column(Modifier.horizontalScroll(rememberScrollState()).border(1.dp, Color.Gray)) {
        Row { columns.forEach { Cell(it, header = true) } }
        rows.take(500).forEach { r ->
            Row {
                r.forEach { v ->
                    val s = when (v) { is JsonNull -> "NULL"; is JsonPrimitive -> v.content; else -> v.toString() }
                    Cell(s)
                }
            }
        }
    }
    Text("${rows.size} baris" + if (truncated) " (dipotong)" else "", style = MaterialTheme.typography.labelSmall)
}

@Composable
private fun Cell(text: String, header: Boolean = false) {
    Text(text.take(80), style = if (header) MaterialTheme.typography.labelMedium else Mono,
         modifier = Modifier.width(140.dp).border(0.5.dp, Color.DarkGray).padding(4.dp), maxLines = 2)
}
