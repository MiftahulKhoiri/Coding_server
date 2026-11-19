package id.codingserver.android.ui.projects

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CloudDownload
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import id.codingserver.android.data.api.GitClone
import id.codingserver.android.data.api.Project
import id.codingserver.android.data.api.ProjectCreate
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InputDialog
import id.codingserver.android.ui.common.LANGUAGES
import id.codingserver.android.ui.common.Loading
import id.codingserver.android.ui.common.formatTime
import kotlinx.coroutines.launch

@Composable
fun ProjectsScreen(vm: AppViewModel, onOpen: (Project) -> Unit) {
    val client by vm.client.collectAsState()
    val current by vm.project.collectAsState()
    var projects by remember { mutableStateOf<List<Project>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    var creating by remember { mutableStateOf(false) }
    var cloning by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<Project?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(client, reload) {
        val c = client ?: return@LaunchedEffect
        apiCall { c.api.projects() }.onSuccess { projects = it; error = null }.onFailure { error = it.message }
    }

    Scaffold(floatingActionButton = {
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            SmallFloatingActionButton(onClick = { cloning = true }) { Icon(Icons.Default.CloudDownload, "Clone Git") }
            ExtendedFloatingActionButton(onClick = { creating = true }, icon = { Icon(Icons.Default.Add, null) }, text = { Text("Proyek baru") })
        }
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            error?.let { ErrorCard(it) { reload++ } }
            val list = projects
            if (list == null && error == null) Loading()
            if (list != null && list.isEmpty()) Text("Belum ada proyek. Buat proyek baru atau clone dari Git.", Modifier.padding(16.dp))
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(list ?: emptyList(), key = { it.id }) { p ->
                    Card(Modifier.fillMaxWidth().clickable { vm.openProject(p); onOpen(p) }) {
                        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Folder, null, tint = MaterialTheme.colorScheme.primary)
                            Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                                Text(p.name + if (current?.id == p.id) "  •" else "", style = MaterialTheme.typography.titleMedium)
                                Text("${p.language.ifBlank { "-" }} · diubah ${formatTime(p.updated_at)}", style = MaterialTheme.typography.bodySmall)
                                if (p.description.isNotBlank()) Text(p.description, style = MaterialTheme.typography.bodySmall)
                            }
                            IconButton(onClick = { deleting = p }) { Icon(Icons.Default.Delete, "Hapus") }
                        }
                    }
                }
            }
        }
    }

    if (creating) CreateProjectDialog(onDismiss = { creating = false }) { name, lang, desc ->
        val c = client ?: return@CreateProjectDialog
        scope.launch {
            apiCall { c.api.createProject(ProjectCreate(name, desc, lang)) }
                .onSuccess { vm.openProject(it); reload++; onOpen(it) }
                .onFailure { vm.toast(it.message ?: "Gagal") }
        }
    }
    if (cloning) InputDialog("Clone repository Git", "URL https://…", confirmText = "Clone", onConfirm = { url ->
        val c = client ?: return@InputDialog
        vm.toast("Meng-clone…")
        scope.launch {
            apiCall { c.api.gitClone(GitClone(url)) }
                .onSuccess { vm.openProject(it.project); reload++; vm.toast("Clone selesai") }
                .onFailure { vm.toast(it.message ?: "Clone gagal") }
        }
    }, onDismiss = { cloning = false })
    deleting?.let { p ->
        ConfirmDialog("Hapus proyek", "Hapus \"${p.name}\" beserta SEMUA file-nya di server?", "Hapus", onConfirm = {
            val c = client ?: return@ConfirmDialog
            scope.launch {
                apiCall { c.api.deleteProject(p.id) }.onSuccess {
                    if (current?.id == p.id) vm.closeProject()
                    reload++
                }.onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { deleting = null })
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreateProjectDialog(onDismiss: () -> Unit, onCreate: (String, String, String) -> Unit) {
    var name by remember { mutableStateOf("") }
    var desc by remember { mutableStateOf("") }
    var lang by remember { mutableStateOf("python") }
    var expanded by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Proyek baru") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("Nama proyek") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                    OutlinedTextField(
                        lang, {}, readOnly = true, label = { Text("Bahasa / template") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                        modifier = Modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable).fillMaxWidth(),
                    )
                    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        (LANGUAGES + "kosong").forEach { l ->
                            DropdownMenuItem(text = { Text(l) }, onClick = { lang = l; expanded = false })
                        }
                    }
                }
                OutlinedTextField(desc, { desc = it }, label = { Text("Deskripsi (opsional)") }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank(), onClick = {
                onCreate(name.trim(), if (lang == "kosong") "" else lang, desc.trim()); onDismiss()
            }) { Text("Buat") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}
