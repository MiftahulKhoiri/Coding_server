package id.codingserver.android.ui.settings

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import id.codingserver.android.BuildConfig
import id.codingserver.android.data.api.AIStatus
import id.codingserver.android.data.api.BackupCreate
import id.codingserver.android.data.api.BackupInfo
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.data.update.ApkInstaller
import id.codingserver.android.data.update.AppRelease
import id.codingserver.android.data.update.AppUpdater
import id.codingserver.android.data.update.InstallEvent
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.formatBytes
import id.codingserver.android.ui.common.formatTime
import kotlinx.coroutines.launch
import java.io.File

@Composable
fun SettingsScreen(vm: AppViewModel, onServers: () -> Unit) {
    val prefs by vm.editorPrefs.collectAsState()
    val user by vm.user.collectAsState()
    val client by vm.client.collectAsState()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val install by ApkInstaller.events.collectAsState()
    var release by remember { mutableStateOf<AppRelease?>(null) }
    var updateMsg by remember { mutableStateOf<String?>(null) }
    var progress by remember { mutableStateOf<Float?>(null) }
    var backups by remember { mutableStateOf<List<BackupInfo>?>(null) }
    var ai by remember { mutableStateOf<AIStatus?>(null) }
    val updater = remember { AppUpdater() }
    val isAdmin = user?.permissions?.contains("admin") == true

    LaunchedEffect(client) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.aiStatus() }.onSuccess { ai = it }
        if (isAdmin) apiCall { c.api.backups() }.onSuccess { backups = it.backups }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text("Akun", style = MaterialTheme.typography.titleMedium)
                Text("${user?.username ?: "-"} (${user?.role ?: "-"}) di ${client?.server?.name ?: "-"}")
                Text("Izin: ${user?.permissions?.joinToString() ?: "-"}", style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onServers) { Text("Kelola server") }
                    OutlinedButton(onClick = { vm.logout() }) { Text("Logout") }
                }
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp)) {
                Text("Editor", style = MaterialTheme.typography.titleMedium)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Tema gelap", Modifier.weight(1f)); Switch(prefs.darkTheme, { vm.setEditorPrefs(prefs.copy(darkTheme = it)) })
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Word wrap", Modifier.weight(1f)); Switch(prefs.wordWrap, { vm.setEditorPrefs(prefs.copy(wordWrap = it)) })
                }
                Text("Ukuran font: ${prefs.fontSize}")
                Slider(prefs.fontSize.toFloat(), { vm.setEditorPrefs(prefs.copy(fontSize = it.toInt())) }, valueRange = 9f..28f)
                Text("Lebar tab: ${prefs.tabSize}")
                Slider(prefs.tabSize.toFloat(), { vm.setEditorPrefs(prefs.copy(tabSize = it.toInt())) }, valueRange = 2f..8f, steps = 5)
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Pembaruan aplikasi", style = MaterialTheme.typography.titleMedium)
                Text("Versi terpasang: ${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})")
                Button(onClick = {
                    updateMsg = "Memeriksa…"
                    scope.launch {
                        runCatching { updater.latest() }.onSuccess { r ->
                            release = r
                            updateMsg = if (r.build > BuildConfig.VERSION_CODE) "Tersedia ${r.title}" else "Sudah versi terbaru (${r.title})"
                        }.onFailure { updateMsg = it.message }
                    }
                }) { Text("Periksa pembaruan") }
                updateMsg?.let { Text(it) }
                val r = release
                if (r != null && r.build > BuildConfig.VERSION_CODE) {
                    Button(onClick = {
                        if (!ApkInstaller.canInstall(ctx)) {
                            ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}")))
                            return@Button
                        }
                        scope.launch {
                            val dest = File(ctx.cacheDir, "update/CodingServer.apk")
                            runCatching {
                                updater.download(r, dest) { done, total -> progress = if (total > 0) done.toFloat() / total else null }
                                ApkInstaller.install(ctx, dest)
                            }.onFailure { updateMsg = it.message }
                            progress = null
                        }
                    }) { Text("Unduh & pasang (${formatBytes(r.sizeBytes)})") }
                }
                progress?.let { LinearProgressIndicator(progress = { it }, modifier = Modifier.fillMaxWidth()) }
                when (val e = install) {
                    is InstallEvent.Failed -> Text(e.message, color = MaterialTheme.colorScheme.error)
                    InstallEvent.WaitingUser -> Text("Konfirmasi pemasangan di layar…")
                    InstallEvent.Success -> Text("Pembaruan terpasang")
                    InstallEvent.None -> {}
                }
            }
        }
        ai?.let { a ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("AI Agent (fondasi)", style = MaterialTheme.typography.titleMedium)
                    Text(if (a.configured) "Provider: ${a.provider} · ${a.base_url} · model ${a.model ?: "-"} · ${if (a.reachable == true) "terhubung" else "tidak terjangkau"}"
                         else "Belum dikonfigurasi (CS_AI_BASE_URL di server)")
                    Text("Hak AI: ${a.ai_permissions.joinToString()}", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        if (isAdmin) Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Backup server", style = MaterialTheme.typography.titleMedium)
                Button(onClick = {
                    val c = client ?: return@Button
                    vm.toast("Membuat backup…")
                    scope.launch {
                        apiCall { c.api.createBackup(BackupCreate("android")) }.onSuccess {
                            vm.toast("Backup ${it.name} dibuat & terverifikasi")
                            apiCall { c.api.backups() }.onSuccess { b -> backups = b.backups }
                        }.onFailure { vm.toast(it.message ?: "") }
                    }
                }) { Text("Backup sekarang") }
                backups?.forEach { b -> Text("${b.name} · ${formatBytes(b.size)} · ${formatTime(b.created_at)}", style = MaterialTheme.typography.bodySmall) }
                Text("Restore dilakukan dari server: scripts/backup.py restore NAMA", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
