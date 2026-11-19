package id.codingserver.android.ui.dashboard

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.Dashboard
import id.codingserver.android.data.api.Project
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.Loading
import id.codingserver.android.ui.common.UsageBar
import id.codingserver.android.ui.common.formatBytes
import id.codingserver.android.ui.common.formatDuration
import kotlinx.coroutines.delay

@Composable
fun DashboardScreen(vm: AppViewModel, onOpenProject: (Project) -> Unit) {
    val client by vm.client.collectAsState()
    val online by vm.online.collectAsState()
    var data by remember { mutableStateOf<Dashboard?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(client) {
        val c = client ?: return@LaunchedEffect
        while (true) {
            apiCall { c.api.dashboard() }.onSuccess { data = it; error = null }.onFailure { error = it.message }
            delay(5000)
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text("Koneksi server", style = MaterialTheme.typography.titleMedium)
                Text("${client?.server?.name ?: "-"} · ${client?.baseUrl ?: ""}")
                Text(
                    if (online == false) "OFFLINE" else if (online == true) "ONLINE" else "…",
                    color = if (online == false) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                )
                data?.let { d ->
                    val ip = d.resources.network.interfaces.flatMap { it.ipv4 }.joinToString()
                    Text("${d.info.board ?: d.info.hostname} · ${d.info.architecture} · IP $ip", style = MaterialTheme.typography.bodySmall)
                    Text("${d.info.os ?: ""} · uptime ${formatDuration(d.info.uptime_seconds)}", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        error?.let { ErrorCard(it) }
        val d = data
        if (d == null && error == null) Loading(Modifier.padding(24.dp))
        if (d != null) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("Sumber daya", style = MaterialTheme.typography.titleMedium)
                    val r = d.resources
                    UsageBar("CPU", r.cpu.percent, "${r.cpu.percent}% · load ${r.cpu.load_avg.joinToString(" ")}")
                    UsageBar("RAM", r.memory.percent, "${formatBytes(r.memory.used)} / ${formatBytes(r.memory.total)}")
                    UsageBar("Disk", r.disk.percent, "${formatBytes(r.disk.used)} / ${formatBytes(r.disk.total)}")
                    r.temperature_c?.let { Text("Suhu CPU: $it °C") }
                }
            }
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("Aktivitas", style = MaterialTheme.typography.titleMedium)
                    Text("Proyek: ${d.projects_count}")
                    Text("Eksekusi aktif: ${d.active_executions.size} (berjalan ${d.jobs.running}/${d.jobs.max_concurrent}, antre ${d.jobs.waiting})")
                    Text("Sesi terminal: ${d.terminal_sessions}")
                    d.active_executions.forEach { j -> Text("• ${j.file} [${j.language}] ${j.status}", style = MaterialTheme.typography.bodySmall) }
                }
            }
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("Proyek terbaru", style = MaterialTheme.typography.titleMedium)
                    if (d.recent_projects.isEmpty()) Text("Belum ada proyek")
                    d.recent_projects.forEach { p ->
                        Text("• ${p.name}  (${p.language.ifBlank { "-" }})",
                             modifier = Modifier.fillMaxWidth().clickable { onOpenProject(p) }.padding(vertical = 6.dp))
                    }
                }
            }
        }
    }
}
