package id.codingserver.android.ui.monitor

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.EngineStatus
import id.codingserver.android.data.api.Processes
import id.codingserver.android.data.api.Resources
import id.codingserver.android.data.api.SystemInfo
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.UsageBar
import id.codingserver.android.ui.common.formatBytes
import id.codingserver.android.ui.common.formatDuration
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.OkGreen
import kotlinx.coroutines.delay

/** Server Monitor: CPU, RAM, disk, suhu, uptime, jaringan, proses, job, status compiler. */
@Composable
fun MonitorScreen(vm: AppViewModel) {
    val client by vm.client.collectAsState()
    val user by vm.user.collectAsState()
    var info by remember { mutableStateOf<SystemInfo?>(null) }
    var res by remember { mutableStateOf<Resources?>(null) }
    var engines by remember { mutableStateOf<List<EngineStatus>>(emptyList()) }
    var procs by remember { mutableStateOf<Processes?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshEngines by remember { mutableIntStateOf(0) }
    val isAdmin = user?.permissions?.contains("system") == true

    LaunchedEffect(client) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.info() }.onSuccess { info = it }
        while (true) {
            apiCall { c.api.resources() }.onSuccess { res = it; error = null }.onFailure { error = it.message }
            if (isAdmin) apiCall { c.api.processes() }.onSuccess { procs = it }
            delay(3000)
        }
    }
    LaunchedEffect(client, refreshEngines) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.engines(refreshEngines > 0) }.onSuccess { engines = it.engines }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        error?.let { ErrorCard(it) }
        info?.let { i ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(10.dp)) {
                    Text(i.board ?: i.hostname, style = MaterialTheme.typography.titleMedium)
                    Text("${i.os ?: ""} · kernel ${i.kernel} · ${i.architecture} · ${i.cpu_count} core")
                    Text("CODING_SERVER v${i.server_version} · Python ${i.python} · backend jalan ${formatDuration(i.server_uptime_seconds)}",
                         style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        res?.let { r ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(10.dp)) {
                    UsageBar("CPU", r.cpu.percent, "${r.cpu.percent}% · ${r.cpu.freq_mhz?.toInt() ?: "-"} MHz")
                    Text("Per core: " + r.cpu.per_cpu.joinToString { "${it.toInt()}%" }, style = MaterialTheme.typography.bodySmall)
                    UsageBar("RAM", r.memory.percent, "${formatBytes(r.memory.used)} / ${formatBytes(r.memory.total)}")
                    UsageBar("Disk", r.disk.percent, "${formatBytes(r.disk.free)} bebas")
                    Text("Suhu: ${r.temperature_c ?: "-"} °C · uptime ${formatDuration(r.uptime_seconds)}")
                    Text("Jaringan: " + r.network.interfaces.joinToString { "${it.`interface`} ${if (it.up) "UP" else "DOWN"} ${it.ipv4.joinToString()}" },
                         style = MaterialTheme.typography.bodySmall)
                    r.jobs?.let { j -> Text("Job: berjalan ${j.running}/${j.max_concurrent}, antre ${j.waiting}") }
                }
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(10.dp)) {
                Row { Text("Compiler & runtime", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                      OutlinedButton(onClick = { refreshEngines++ }) { Text("Periksa ulang") } }
                engines.forEach { e ->
                    Text("${e.language}: ${e.status}", color = if (e.status == "AVAILABLE") OkGreen else ErrRed)
                    e.version?.let { Text("   $it", style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        procs?.let { p ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(10.dp)) {
                    Text("Proses teratas (RAM) · terminal aktif ${p.terminals}", style = MaterialTheme.typography.titleSmall)
                    p.processes.forEach { pr -> Text("${pr.pid} ${pr.name} ${pr.rss_mb} MB", style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
    }
}
