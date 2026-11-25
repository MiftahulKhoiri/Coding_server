package id.codingserver.android.ui.servers

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Circle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import id.codingserver.android.CodingServerApp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.ApiException
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.data.api.normalizeBaseUrl
import id.codingserver.android.data.settings.ServerProfile
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.OkGreen
import kotlinx.coroutines.launch
import androidx.compose.ui.platform.LocalContext

/** Daftar server: tambah, ubah, hapus, uji koneksi, hubungkan, putuskan. */
@Composable
fun ServersScreen(vm: AppViewModel, onConnected: () -> Unit) {
    val servers by vm.servers.collectAsState()
    val activeClient by vm.client.collectAsState()
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    val status = remember { mutableStateMapOf<String, String>() }
    var editing by remember { mutableStateOf<ServerProfile?>(null) }
    var adding by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<ServerProfile?>(null) }

    fun test(p: ServerProfile) {
        status[p.id] = "Menguji…"
        scope.launch {
            val c = ApiClient(p, (ctx.applicationContext as CodingServerApp).tokens) {}
            apiCall { c.health() }
                .onSuccess { status[p.id] = "ONLINE · ${it.name} v${it.version} · sandbox=${if (it.sandbox) "aktif" else "mati"}" }
                .onFailure { status[p.id] = "OFFLINE · ${(it as ApiException).message}" }
        }
    }

    LaunchedEffect(servers.size) { servers.forEach { if (status[it.id] == null) test(it) } }

    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = { adding = true }, icon = { Icon(Icons.Default.Add, null) }, text = { Text("Tambah server") })
        },
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize().padding(12.dp)) {
            Text("Server Raspberry Pi", style = MaterialTheme.typography.headlineSmall)
            Text("Pilih server CODING_SERVER yang ingin dipakai.", style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.padding(6.dp))
            if (servers.isEmpty()) {
                Text("Belum ada server. Tekan \"Tambah server\" lalu isi alamat, mis. 192.168.1.10:8800.")
            }
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(servers, key = { it.id }) { s ->
                    val st = status[s.id] ?: "-"
                    val isActive = activeClient?.server?.id == s.id
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(12.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Circle, null, tint = if (st.startsWith("ONLINE")) OkGreen else ErrRed,
                                     modifier = Modifier.padding(end = 8.dp).width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(s.name + if (isActive) "  (aktif)" else "", style = MaterialTheme.typography.titleMedium)
                                    Text(normalizeBaseUrl(s.baseUrl), style = MaterialTheme.typography.bodySmall)
                                }
                                IconButton(onClick = { editing = s }) { Icon(Icons.Default.Edit, "Ubah") }
                                IconButton(onClick = { deleting = s }) { Icon(Icons.Default.Delete, "Hapus") }
                            }
                            Text(st, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 4.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = { scope.launch { vm.activate(s); onConnected() } }) { Text(if (isActive) "Buka" else "Hubungkan") }
                                OutlinedButton(onClick = { test(s) }) { Text("Tes koneksi") }
                                if (isActive) TextButton(onClick = { vm.disconnect() }) { Text("Putuskan") }
                            }
                        }
                    }
                }
            }
        }
    }

    if (adding || editing != null) {
        ServerDialog(editing, onDismiss = { adding = false; editing = null }) { p ->
            scope.launch { vm.serverStore.upsert(p); test(p) }
        }
    }
    deleting?.let { s ->
        ConfirmDialog("Hapus server", "Hapus \"${s.name}\" dari HP ini? (Data di server tidak terhapus)", "Hapus",
            onConfirm = {
                scope.launch {
                    (ctx.applicationContext as CodingServerApp).tokens.clear(s.id)
                    if (activeClient?.server?.id == s.id) vm.disconnect()
                    vm.serverStore.delete(s.id)
                }
            }, onDismiss = { deleting = null })
    }
}

@Composable
private fun ServerDialog(initial: ServerProfile?, onDismiss: () -> Unit, onSave: (ServerProfile) -> Unit) {
    var name by remember { mutableStateOf(initial?.name ?: "Raspberry Pi 5") }
    var url by remember { mutableStateOf(initial?.baseUrl ?: "") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (initial == null) "Tambah server" else "Ubah server") },
        text = {
            Column {
                OutlinedTextField(name, { name = it }, label = { Text("Nama") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(url, { url = it }, label = { Text("Alamat (IP:port)") }, placeholder = { Text("192.168.1.10:8800") },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Text("Format alamat", style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
                    id.codingserver.android.ui.common.InfoButton("Format alamat",
                        "Isi IP atau nama host Raspberry Pi, mis. 192.168.1.10:8800. Port bawaan 8800 (boleh tidak ditulis).\n\n" +
                            "Gunakan https:// bila server memakai reverse proxy TLS.")
                }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && url.isNotBlank(), onClick = {
                onSave((initial ?: ServerProfile(name = name, baseUrl = url)).copy(name = name.trim(), baseUrl = url.trim()))
                onDismiss()
            }) { Text("Simpan") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}
