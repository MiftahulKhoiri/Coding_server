package id.codingserver.android.ui.projects

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.InstallPlan
import id.codingserver.android.data.api.apiCall

/**
 * Dialog instal dependensi proyek. Server mendeteksi requirements.txt / pyproject.toml (pip → .venv proyek),
 * package.json (npm), go.mod, composer.json, lalu menjalankannya di sandbox yang diberi internet KHUSUS
 * untuk langkah instal ini. Program biasa tetap tanpa internet.
 */
@Composable
fun InstallDepsDialog(client: ApiClient, projectId: String, onInstall: (List<String>) -> Unit, onDismiss: () -> Unit) {
    var plan by remember { mutableStateOf<InstallPlan?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var extra by remember { mutableStateOf("") }

    LaunchedEffect(projectId) {
        apiCall { client.api.installPlan(projectId) }.onSuccess { plan = it }.onFailure { error = it.message }
    }
    val packages = extra.split(' ', ',', '\n').map { it.trim() }.filter { it.isNotEmpty() }
    val canInstall = plan != null && (plan!!.kinds.isNotEmpty() || packages.isNotEmpty())

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Instal dependensi") },
        text = {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val p = plan
                when {
                    error != null -> Text(error!!, color = MaterialTheme.colorScheme.error)
                    p == null -> CircularProgressIndicator()
                    else -> {
                        if (p.kinds.isEmpty()) {
                            Text("Belum ada file dependensi (requirements.txt, package.json, go.mod, composer.json). " +
                                "Tulis nama paket di bawah untuk memasang langsung.", style = MaterialTheme.typography.bodySmall)
                        }
                        p.plans.forEach { item ->
                            Text(item.label.ifBlank { item.kind }, style = MaterialTheme.typography.titleSmall)
                            item.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                            item.commands.forEach { cmd ->
                                Text("$ " + cmd.substringAfterLast("/bin/").ifBlank { cmd },
                                    fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                        p.venv?.let { Text("Virtualenv proyek: $it (dipakai otomatis saat Jalankan)", style = MaterialTheme.typography.bodySmall) }
                        if (!p.network) Text("Peringatan: CS_INSTALL_NETWORK=false di server, instal kemungkinan gagal.",
                            color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                        OutlinedTextField(extra, { extra = it }, label = { Text("Paket tambahan (opsional)") },
                            placeholder = { Text("flask requests>=2") }, modifier = Modifier.fillMaxWidth())
                        Text(if (packages.isEmpty()) "Kosong = pasang dari file dependensi di atas."
                             else "Yang dipasang: ${packages.joinToString()}", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        },
        confirmButton = { TextButton(enabled = canInstall, onClick = { onInstall(packages); onDismiss() }) { Text("Instal") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}
