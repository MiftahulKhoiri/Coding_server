package id.codingserver.android.ui.settings

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import id.codingserver.android.BuildConfig
import id.codingserver.android.data.api.BackupCreate
import id.codingserver.android.data.api.BackupInfo
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.data.update.ApkInstaller
import id.codingserver.android.data.update.AppRelease
import id.codingserver.android.data.update.AppUpdater
import id.codingserver.android.data.update.InstallEvent
import id.codingserver.android.data.update.UpdateChecker
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.TitleWithInfo
import id.codingserver.android.ui.common.formatBytes
import id.codingserver.android.ui.common.formatTime
import kotlinx.coroutines.launch
import java.io.File

/**
 * Pengaturan aplikasi — hanya: 1. Profil, 2. Manajer akun, 3. Pembaruan aplikasi, 4. Font, 5. Warna.
 * Pengaturan lain ada di tempatnya: perilaku editor di Code Editor → ⋮ → Pengaturan editor, tampilan terminal di
 * Terminal → ⚙, semua tentang AI di Model AI, backup server di Server Monitor.
 */
@Composable
fun SettingsScreen(vm: AppViewModel, onServers: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionHeader("1 · Profil")
        ProfileSection(vm)
        SectionHeader("2 · Manajer akun")
        AccountManagerSection(vm, onServers)
        SectionHeader("3 · Pembaruan aplikasi")
        UpdateCard()
        SectionHeader("4 · Font")
        FontSettingsCard(vm)
        SectionHeader("5 · Warna")
        ColorSettingsCards(vm)
        Text("Pengaturan lain ada di tempatnya: Code Editor → ⋮ → Pengaturan editor · Terminal → ⚙ · " +
             "Model AI (semua tentang AI) · Server Monitor → Backup.",
             style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
             modifier = Modifier.padding(4.dp))
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(text, style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary,
         modifier = Modifier.padding(start = 4.dp, top = 6.dp))
}

@Composable
private fun UpdateCard() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val install by ApkInstaller.events.collectAsState()
    val autoRelease by UpdateChecker.available.collectAsState()
    var release by remember { mutableStateOf<AppRelease?>(null) }
    var updateMsg by remember { mutableStateOf<String?>(null) }
    var progress by remember { mutableStateOf<Float?>(null) }
    val updater = remember { AppUpdater() }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            TitleWithInfo("Pembaruan aplikasi", "Aplikasi memeriksa APK terbaru di GitHub secara otomatis saat dibuka, " +
                "saat kembali ke aplikasi, dan tiap 6 jam. Bila ada versi baru, muncul notifikasi dan banner biru di atas " +
                "layar — tidak perlu cek manual.\n\nPemasangan tetap butuh konfirmasi \"Perbarui\" dari Android; " +
                "APK hanya diterima bila tanda tangannya sama.")
            Text("Versi terpasang: ${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})")
            autoRelease?.let { if (release == null) Text("⬆️ Tersedia ${it.title}", color = MaterialTheme.colorScheme.primary) }
            OutlinedButton(onClick = {
                updateMsg = "Memeriksa…"
                scope.launch {
                    runCatching { UpdateChecker.check(ctx, force = true) }.onSuccess { r ->
                        release = r
                        updateMsg = if (r != null) "Tersedia ${r.title}" else "Sudah versi terbaru"
                    }.onFailure { updateMsg = it.message }
                }
            }) { Text("Periksa sekarang") }
            updateMsg?.let { Text(it) }
            val r = release ?: autoRelease
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
}

/** Backup server (khusus admin utama) — ditampilkan di Server Monitor. */
@Composable
fun BackupCard(vm: AppViewModel) {
    val client by vm.client.collectAsState()
    val user by vm.user.collectAsState()
    val scope = rememberCoroutineScope()
    var backups by remember { mutableStateOf<List<BackupInfo>?>(null) }
    if (user?.permissions?.contains("system") != true) return
    androidx.compose.runtime.LaunchedEffect(client) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.backups() }.onSuccess { backups = it.backups }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            TitleWithInfo("Backup server", "Membuat salinan database & konfigurasi server lalu memverifikasinya.\n\n" +
                "Restore dilakukan dari server: scripts/backup.py restore NAMA")
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
        }
    }
}
