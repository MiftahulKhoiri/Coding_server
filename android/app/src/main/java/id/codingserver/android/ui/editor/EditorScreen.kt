package id.codingserver.android.ui.editor

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.filled.Menu
import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.NoteAdd
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.FindInPage
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import id.codingserver.android.data.api.ApiException
import id.codingserver.android.data.api.FileEntry
import id.codingserver.android.data.api.FileCreate
import id.codingserver.android.data.api.FileWrite
import id.codingserver.android.data.api.HistoryEntry
import id.codingserver.android.data.api.RestoreRequest
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.EditorTab
import id.codingserver.android.ui.common.InputDialog
import id.codingserver.android.ui.common.formatTime
import kotlinx.coroutines.launch

/** Code editor: tab, simpan, simpan sebagai, jalankan, build, cari/ganti, undo/redo, simbol, riwayat. */
@Composable
fun EditorScreen(vm: AppViewModel, editor: EditorController, onMenu: () -> Unit = {}, onRunStarted: () -> Unit) {
    val client by vm.client.collectAsState()
    val tabs by vm.tabs.collectAsState()
    val activeId by vm.activeTab.collectAsState()
    val prefs by vm.editorPrefs.collectAsState()
    val cursor by editor.cursorFlow.collectAsState()
    val scope = rememberCoroutineScope()
    var menu by remember { mutableStateOf(false) }
    var conflict by remember { mutableStateOf<EditorTab?>(null) }
    var saveAs by remember { mutableStateOf(false) }
    var gotoLine by remember { mutableStateOf(false) }
    var symbols by remember { mutableStateOf<List<Symbol>?>(null) }
    var history by remember { mutableStateOf<List<HistoryEntry>?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var newFile by remember { mutableStateOf(false) }
    var quickOpen by remember { mutableStateOf(false) }
    val autoSaveJobs = remember { mutableMapOf<String, kotlinx.coroutines.Job>() }
    var colorDialog by remember { mutableStateOf(false) }
    var textColorInput by remember(prefs) { mutableStateOf(prefs.textColor) }
    var backgroundColorInput by remember(prefs) { mutableStateOf(prefs.backgroundColor) }
    var colorError by remember { mutableStateOf<String?>(null) }
    val project by vm.project.collectAsState()
    val active = tabs.firstOrNull { it.id == activeId }
    val me by vm.user.collectAsState()
    val perms = me?.permissions.orEmpty().toSet()
    val canWrite = "write" in perms  // Runner/Viewer: tombol simpan & file baru disembunyikan

    suspend fun save(tab: EditorTab, force: Boolean = false, quiet: Boolean = false): Boolean {
        val c = client ?: return false
        val content = editor.getDoc(tab.id) ?: return false
        val res = apiCall { c.api.write(FileWrite(tab.projectId, tab.path, content, if (force) null else tab.sha256)) }
        res.onSuccess { w ->
            vm.updateTab(tab.id) { it.copy(sha256 = w.sha256, dirty = false) }
            editor.markSaved(tab.id)
            if (!quiet) vm.toast("Tersimpan: ${tab.name}")
        }.onFailure {
            val e = it as ApiException
            if (e.code == "write_conflict") conflict = tab else vm.toast(e.message)
        }
        return res.isSuccess
    }

    suspend fun runActive(build: Boolean) {
        val tab = active ?: return
        if (tab.dirty && !save(tab)) return
        editor.clearDiagnostics()
        vm.execute(FileEntry(tab.name, tab.path, "file"), build, projectId = tab.projectId)
            .onSuccess { onRunStarted() }
            .onFailure { vm.toast(it.message ?: "Gagal menjalankan") }
    }

    // Lompat ke posisi setelah file tujuan go-to-definition dimuat.
    var pendingGoto by remember { mutableStateOf<Triple<String, Int, Int>?>(null) }
    val lspStatus by editor.lspStatus.collectAsState()
    // Proyek / server / pengaturan LSP berubah -> sambung ulang language server.
    LaunchedEffect(client, project?.id, prefs.lsp) { editor.lspReset() }

    // Muat isi file ke editor saat tab aktif berubah.
    LaunchedEffect(activeId, client) {
        val tab = active ?: return@LaunchedEffect
        val c = client ?: return@LaunchedEffect
        loadError = null
        if (!editor.hasTab(tab.id)) {
            loadError = "Memuat file: " + tab.path
            apiCall { c.api.read(tab.projectId, tab.path) }
                .onSuccess { f ->
                    if (activeId != tab.id) return@onSuccess
                    if (f.binary || f.content == null) {
                        loadError = "File tidak dapat ditampilkan sebagai teks: " + tab.path
                    } else {
                        editor.openTab(tab.id, f.content, f.name)
                        vm.updateTab(tab.id) { it.copy(sha256 = f.sha256, language = f.language, dirty = false) }
                        loadError = null
                    }
                }
                .onFailure {
                    if (activeId == tab.id) {
                        loadError = "Gagal membaca " + tab.path + ": " + (it.message ?: "kesalahan tidak diketahui")
                        android.util.Log.e("CodingServerEditor", loadError, it)
                    }
                }
        } else editor.switchTab(tab.id)
        pendingGoto?.let { (id, line, col) -> if (id == tab.id && editor.hasTab(id)) { editor.gotoLine(line, col); pendingGoto = null } }
    }
    LaunchedEffect(prefs) { editor.applyPrefs(prefs.darkTheme, prefs.fontSize, prefs.wordWrap, prefs.tabSize, prefs.textColor, prefs.backgroundColor) }
    LaunchedEffect(Unit) {
        editor.eventsFlow.collect { ev ->
            when (ev) {
                is EditorEvent.Changed -> {
                    vm.updateTab(ev.tabId) { it.copy(dirty = ev.dirty) }
                    // Simpan otomatis ±2 detik setelah berhenti mengetik (tidak untuk peran tanpa hak tulis).
                    autoSaveJobs.remove(ev.tabId)?.cancel()
                    if (ev.dirty && vm.editorPrefs.value.autoSave && vm.user.value?.permissions?.contains("write") == true) {
                        autoSaveJobs[ev.tabId] = scope.launch {
                            kotlinx.coroutines.delay(2_000)
                            vm.tabs.value.firstOrNull { it.id == ev.tabId }?.takeIf { it.dirty }?.let { save(it, quiet = true) }
                            autoSaveJobs.remove(ev.tabId)
                        }
                    }
                }
                is EditorEvent.SaveRequested -> if (vm.user.value?.permissions?.contains("write") == true) vm.tabs.value.firstOrNull { it.id == ev.tabId }?.let { save(it) }
                is EditorEvent.RunRequested -> runActive(false)
                is EditorEvent.OpenFile -> {
                    val pid = project?.id ?: vm.tabs.value.firstOrNull { it.id == activeId }?.projectId
                    if (pid != null) {
                        val tab = EditorTab(pid, ev.path, null)
                        if (editor.hasTab(tab.id)) { vm.setActiveTab(tab.id); editor.switchTab(tab.id); editor.gotoLine(ev.line, ev.column) }
                        else { pendingGoto = Triple(tab.id, ev.line, ev.column); vm.addOrFocusTab(tab) }
                    }
                }
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        // Baris 1 (ringkas): menu samping + tab file. Menggantikan AppBar besar agar area kode lebih luas.
        Row(Modifier.fillMaxWidth().height(40.dp), verticalAlignment = Alignment.CenterVertically) {
            ToolIcon(Icons.Default.Menu, "Menu", onClick = onMenu)
            Row(Modifier.weight(1f).horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically) {
                if (tabs.isEmpty()) Text("Code Editor", style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(start = 4.dp))
                tabs.forEach { t ->
                    FileTab(t.name, t.dirty, t.id == activeId, onClick = { vm.setActiveTab(t.id) }, onClose = {
                        scope.launch {
                            if (t.dirty) vm.toast("${t.name} belum disimpan — perubahan dibuang")
                            editor.closeTab(t.id); vm.closeTab(t.id)
                        }
                    })
                }
            }
        }
        // Baris 2 (ringkas): toolbar
        Row(Modifier.fillMaxWidth().height(38.dp), verticalAlignment = Alignment.CenterVertically) {
            if (canWrite) ToolIcon(Icons.AutoMirrored.Filled.NoteAdd, "File baru", enabled = project != null, onClick = { newFile = true })
            if (canWrite) ToolIcon(Icons.Default.Save, "Simpan", enabled = active != null, onClick = { scope.launch { active?.let { save(it) } } })
            if ("execute" in perms) ToolIcon(Icons.Default.PlayArrow, "Jalankan", enabled = active != null, onClick = { scope.launch { runActive(false) } })
            if ("build" in perms) ToolIcon(Icons.Default.Build, "Build", enabled = active != null, onClick = { scope.launch { runActive(true) } })
            ToolIcon(Icons.AutoMirrored.Filled.Undo, "Undo", enabled = active != null, onClick = { scope.launch { editor.undo() } })
            ToolIcon(Icons.AutoMirrored.Filled.Redo, "Redo", enabled = active != null, onClick = { scope.launch { editor.redo() } })
            ToolIcon(Icons.Default.Search, "Cari & ganti", enabled = active != null, onClick = { scope.launch { editor.openSearch() } })
            ToolIcon(Icons.Default.FindInPage, "Buka file cepat", enabled = project != null, onClick = { quickOpen = true })
            Column(Modifier.weight(1f).padding(start = 4.dp)) {
                Text("${cursor.first}:${cursor.second}", style = MaterialTheme.typography.labelSmall)
                if (prefs.lsp && lspStatus.isNotBlank()) Text(lspStatus, style = MaterialTheme.typography.labelSmall, maxLines = 1,
                                                               color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Box {
                ToolIcon(Icons.Default.MoreVert, "Lainnya", onClick = { menu = true })
                DropdownMenu(menu, { menu = false }) {
                    if (canWrite) DropdownMenuItem({ Text("Simpan sebagai…") }, enabled = active != null, onClick = { menu = false; saveAs = true })
                    DropdownMenuItem({ Text("Ke baris…") }, enabled = active != null, onClick = { menu = false; gotoLine = true })
                    DropdownMenuItem({ Text("Simbol dokumen") }, enabled = active != null, onClick = {
                        menu = false; scope.launch { symbols = editor.symbols() }
                    })
                    DropdownMenuItem({ Text("Ke definisi (kata di kursor)") }, enabled = active != null, onClick = {
                        menu = false; scope.launch { if (!editor.gotoDefinition()) vm.toast("Definisi tidak ditemukan di file ini") }
                    })
                    DropdownMenuItem({ Text("Info simbol di kursor") }, enabled = active != null, onClick = {
                        menu = false; scope.launch { editor.hover() }
                    })
                    DropdownMenuItem({ Text(if (prefs.lsp) "Matikan language server" else "Aktifkan language server") },
                        onClick = { menu = false; vm.setEditorPrefs(prefs.copy(lsp = !prefs.lsp)) })
                    DropdownMenuItem({ Text("Lipat semua / buka semua") }, onClick = {
                        menu = false; scope.launch { editor.foldAll(); editor.unfoldAll() }
                    })
                    DropdownMenuItem({ Text("Buka file cepat…") }, enabled = project != null, onClick = { menu = false; quickOpen = true })
                    DropdownMenuItem({ Text(if (prefs.keyBar) "Sembunyikan tombol ekstra" else "Tampilkan tombol ekstra") },
                        onClick = { menu = false; vm.setEditorPrefs(prefs.copy(keyBar = !prefs.keyBar)) })
                    if (canWrite) DropdownMenuItem({ Text(if (prefs.autoSave) "Matikan simpan otomatis" else "Aktifkan simpan otomatis") },
                        onClick = { menu = false; vm.setEditorPrefs(prefs.copy(autoSave = !prefs.autoSave)) })
                    DropdownMenuItem({ Text(if (prefs.wordWrap) "Matikan word wrap" else "Aktifkan word wrap") },
                        onClick = { menu = false; vm.setEditorPrefs(prefs.copy(wordWrap = !prefs.wordWrap)) })
                    DropdownMenuItem({ Text("Font lebih besar (${prefs.fontSize + 1})") },
                        onClick = { vm.setEditorPrefs(prefs.copy(fontSize = (prefs.fontSize + 1).coerceAtMost(32))) })
                    DropdownMenuItem({ Text("Font lebih kecil (${prefs.fontSize - 1})") },
                        onClick = { vm.setEditorPrefs(prefs.copy(fontSize = (prefs.fontSize - 1).coerceAtLeast(9))) })
                    DropdownMenuItem({ Text("Pengaturan warna editor") }, onClick = { menu = false; textColorInput = prefs.textColor; backgroundColorInput = prefs.backgroundColor; colorError = null; colorDialog = true })
                    DropdownMenuItem({ Text(if (prefs.darkTheme) "Tema terang" else "Tema gelap") },
                        onClick = { menu = false; vm.setEditorPrefs(prefs.copy(darkTheme = !prefs.darkTheme)) })
                    DropdownMenuItem({ Text("Riwayat versi file") }, enabled = active != null, onClick = {
                        menu = false
                        val c = client; val t = active
                        if (c != null && t != null) scope.launch {
                            apiCall { c.api.history(t.projectId, t.path) }.onSuccess { history = it.history }.onFailure { vm.toast(it.message ?: "") }
                        }
                    })
                    DropdownMenuItem({ Text("Muat ulang dari server") }, enabled = active != null, onClick = {
                        menu = false
                        val c = client; val t = active
                        if (c != null && t != null) scope.launch {
                            apiCall { c.api.read(t.projectId, t.path) }.onSuccess { f ->
                                editor.setDoc(t.id, f.content ?: "", true)
                                vm.updateTab(t.id) { it.copy(sha256 = f.sha256, dirty = false) }
                            }
                        }
                    })
                }
            }
        }
        loadError?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(8.dp)) }
        if (tabs.isEmpty()) {
            Text(
                if (project == null) "Belum ada proyek terbuka. Pilih proyek di menu Proyek dulu."
                else "Belum ada file terbuka. Tekan ikon + (File baru) atau buka file dari Project Explorer.",
                Modifier.padding(12.dp), style = MaterialTheme.typography.bodyMedium,
            )
        }
        Box(Modifier.fillMaxWidth().weight(1f, fill = true).heightIn(min = 300.dp)) {
            AndroidView(factory = { editor.detach(); editor.webView }, modifier = Modifier.fillMaxSize().heightIn(min = 300.dp))
        }
        if (prefs.keyBar && active != null) EditorKeyBar(
            onKey = { k -> scope.launch { editor.key(k) } },
            onText = { t -> scope.launch { editor.typeText(t) } },
        )
    }

    if (colorDialog) {
        AlertDialog(
            onDismissRequest = { colorDialog = false },
            title = { Text("Warna editor") },
            text = { Column(Modifier.verticalScroll(androidx.compose.foundation.rememberScrollState()), verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(6.dp)) {
                Text("Preset", style = MaterialTheme.typography.labelLarge)
                EditorPresetRow { preset ->
                    textColorInput = preset.text; backgroundColorInput = preset.background; colorError = null
                    if (preset.dark != prefs.darkTheme) vm.setEditorPrefs(prefs.copy(darkTheme = preset.dark))
                }
                Text("Kosong = warna otomatis. Format HEX: #FFFFFF")
                OutlinedTextField(value = textColorInput, onValueChange = { textColorInput = it.trim(); colorError = null }, label = { Text("Warna teks") }, placeholder = { Text("#FFFFFF") }, singleLine = true)
                OutlinedTextField(value = backgroundColorInput, onValueChange = { backgroundColorInput = it.trim(); colorError = null }, label = { Text("Warna latar") }, placeholder = { Text("#282C34") }, singleLine = true)
                colorError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            } },
            confirmButton = { TextButton(onClick = {
                val hex = Regex("^#([0-9a-fA-F]{6})$")
                if ((textColorInput.isNotBlank() && !hex.matches(textColorInput)) || (backgroundColorInput.isNotBlank() && !hex.matches(backgroundColorInput))) colorError = "HEX tidak valid. Contoh: #AABBCC"
                else { vm.setEditorPrefs(prefs.copy(textColor = textColorInput, backgroundColor = backgroundColorInput)); colorDialog = false }
            }) { Text("Terapkan") } },
            dismissButton = { TextButton(onClick = { textColorInput = ""; backgroundColorInput = ""; colorError = null; vm.setEditorPrefs(prefs.copy(textColor = "", backgroundColor = "")); colorDialog = false }) { Text("Reset") } },
        )
    }

    conflict?.let { t ->
        AlertDialog(
            onDismissRequest = { conflict = null },
            title = { Text("Konflik penyimpanan") },
            text = { Text("${t.name} sudah diubah di server sejak dibuka. Timpa dengan versi di HP, atau muat ulang dari server?") },
            confirmButton = { TextButton(onClick = { conflict = null; scope.launch { save(t, force = true) } }) { Text("Timpa") } },
            dismissButton = {
                TextButton(onClick = {
                    conflict = null
                    val c = client
                    if (c != null) scope.launch {
                        apiCall { c.api.read(t.projectId, t.path) }.onSuccess { f ->
                            editor.setDoc(t.id, f.content ?: "", true)
                            vm.updateTab(t.id) { it.copy(sha256 = f.sha256, dirty = false) }
                        }
                    }
                }) { Text("Muat ulang") }
            },
        )
    }
    if (saveAs) active?.let { t ->
        InputDialog("Simpan sebagai", "Path baru di proyek", initial = t.path, confirmText = "Simpan", onConfirm = { path ->
            val c = client
            if (c != null) scope.launch {
                val content = editor.getDoc(t.id) ?: return@launch
                apiCall { c.api.write(FileWrite(t.projectId, path, content)) }.onSuccess { w ->
                    val tab = EditorTab(t.projectId, w.path, w.sha256)
                    editor.openTab(tab.id, content, w.name)
                    editor.markSaved(tab.id)
                    vm.addOrFocusTab(tab)
                    vm.toast("Disimpan sebagai ${w.path}")
                }.onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { saveAs = false })
    }
    if (newFile) project?.let { p ->
        InputDialog("File baru di ${p.name}", "Nama file (mis. main.py)", confirmText = "Buat", onConfirm = { path ->
            val c = client
            if (c != null) scope.launch {
                apiCall { c.api.create(FileCreate(p.id, path, "file")) }
                    .onSuccess { w -> vm.addOrFocusTab(EditorTab(p.id, w.path, null)) }
                    .onFailure { vm.toast(it.message ?: "Gagal membuat file") }
            }
        }, onDismiss = { newFile = false })
    }
    if (quickOpen) project?.let { p ->
        val c = client
        if (c != null) QuickOpenDialog(c, p.id, onDismiss = { quickOpen = false }) { path ->
            quickOpen = false
            vm.addOrFocusTab(EditorTab(p.id, path, null))
        }
    }
    if (gotoLine) InputDialog("Ke baris", "Nomor baris", onConfirm = { n ->
        n.toIntOrNull()?.let { scope.launch { editor.gotoLine(it) } }
    }, onDismiss = { gotoLine = false })
    symbols?.let { list ->
        AlertDialog(
            onDismissRequest = { symbols = null },
            title = { Text("Simbol dokumen") },
            text = {
                if (list.isEmpty()) Text("Tidak ada simbol terdeteksi")
                LazyColumn(Modifier.heightIn(max = 400.dp)) {
                    items(list) { s ->
                        Text("${s.line}: ${s.name}", Modifier.fillMaxWidth().clickable {
                            symbols = null; scope.launch { editor.gotoLine(s.line) }
                        }.padding(8.dp))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { symbols = null }) { Text("Tutup") } },
        )
    }
    history?.let { list ->
        AlertDialog(
            onDismissRequest = { history = null },
            title = { Text("Riwayat versi") },
            text = {
                if (list.isEmpty()) Text("Belum ada versi tersimpan")
                LazyColumn(Modifier.heightIn(max = 400.dp)) {
                    items(list) { h ->
                        Column(Modifier.fillMaxWidth().clickable {
                            history = null
                            val c = client; val t = active
                            if (c != null && t != null) scope.launch {
                                apiCall { c.api.restore(RestoreRequest(t.projectId, h.id)) }.onSuccess {
                                    apiCall { c.api.read(t.projectId, t.path) }.onSuccess { f ->
                                        editor.setDoc(t.id, f.content ?: "", true)
                                        vm.updateTab(t.id) { it.copy(sha256 = f.sha256, dirty = false) }
                                        vm.toast("Versi #${h.id} dipulihkan")
                                    }
                                }.onFailure { vm.toast(it.message ?: "") }
                            }
                        }.padding(8.dp)) {
                            Text("#${h.id} · ${h.action} · ${formatTime(h.created_at)}")
                            Text("${h.actor_type} ${h.note}", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { history = null }) { Text("Tutup") } },
        )
    }
}

/** Preset warna editor populer (teks + latar). Sorotan sintaks tetap dari tema CodeMirror. */
data class EditorColorPreset(val name: String, val text: String, val background: String, val dark: Boolean)

val EditorColorPresets = listOf(
    EditorColorPreset("One Dark", "#ABB2BF", "#282C34", true),
    EditorColorPreset("Dracula", "#F8F8F2", "#282A36", true),
    EditorColorPreset("Monokai", "#F8F8F2", "#272822", true),
    EditorColorPreset("Nord", "#D8DEE9", "#2E3440", true),
    EditorColorPreset("Solarized Gelap", "#93A1A1", "#002B36", true),
    EditorColorPreset("GitHub Gelap", "#C9D1D9", "#0D1117", true),
    EditorColorPreset("Hitam AMOLED", "#E0E0E0", "#000000", true),
    EditorColorPreset("GitHub Terang", "#24292F", "#FFFFFF", false),
    EditorColorPreset("Solarized Terang", "#586E75", "#FDF6E3", false),
    EditorColorPreset("Kertas", "#3B3B3B", "#F5F1E8", false),
)

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun EditorPresetRow(onPick: (EditorColorPreset) -> Unit) {
    androidx.compose.foundation.layout.FlowRow(
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(6.dp),
    ) {
        EditorColorPresets.forEach { p ->
            val bg = androidx.compose.ui.graphics.Color(android.graphics.Color.parseColor(p.background))
            val fg = androidx.compose.ui.graphics.Color(android.graphics.Color.parseColor(p.text))
            androidx.compose.material3.SuggestionChip(
                onClick = { onPick(p) },
                label = { Text(p.name, color = fg) },
                colors = androidx.compose.material3.SuggestionChipDefaults.suggestionChipColors(containerColor = bg),
            )
        }
    }
}

/** Tombol ikon toolbar ringkas (36dp, ikon 20dp) — default IconButton 48dp memakan tinggi layar. */
@Composable
private fun ToolIcon(icon: androidx.compose.ui.graphics.vector.ImageVector, desc: String, enabled: Boolean = true, onClick: () -> Unit) {
    IconButton(onClick = onClick, enabled = enabled, modifier = Modifier.size(36.dp)) {
        Icon(icon, desc, Modifier.size(20.dp))
    }
}

/** Tab file ringkas (tinggi 28dp) pengganti FilterChip. */
@Composable
private fun FileTab(name: String, dirty: Boolean, selected: Boolean, onClick: () -> Unit, onClose: () -> Unit) {
    val shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)
    Row(
        Modifier.padding(end = 4.dp).height(28.dp)
            .background(if (selected) MaterialTheme.colorScheme.secondaryContainer else androidx.compose.ui.graphics.Color.Transparent, shape)
            .border(1.dp, if (selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.outlineVariant, shape)
            .clickable(onClick = onClick).padding(start = 8.dp, end = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text((if (dirty) "● " else "") + name, style = MaterialTheme.typography.labelMedium, maxLines = 1,
             color = if (selected) MaterialTheme.colorScheme.onSecondaryContainer else MaterialTheme.colorScheme.onSurface)
        Box(Modifier.size(24.dp).clickable(onClick = onClose), contentAlignment = Alignment.Center) {
            Icon(Icons.Default.Close, "Tutup $name", Modifier.size(14.dp))
        }
    }
}

/** Baris tombol ekstra di atas keyboard HP: karakter yang sulit diketik + navigasi & perintah editor. */
@Composable
private fun EditorKeyBar(onKey: (String) -> Unit, onText: (String) -> Unit) {
    val keys = listOf("tab" to "⇥", "untab" to "⇤", "left" to "←", "right" to "→", "up" to "↑", "down" to "↓",
                      "home" to "⇱", "end" to "⇲", "comment" to "//", "complete" to "⌘␣", "duplicate" to "⧉", "deleteLine" to "⌫ln")
    val chars = listOf("{", "}", "(", ")", "[", "]", ";", ":", "\"", "'", "<", ">", "=", "+", "-", "*", "/", "\\",
                       "|", "&", "!", "#", "_", "%", ",", ".")
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant)
            .horizontalScroll(rememberScrollState()).padding(horizontal = 4.dp, vertical = 3.dp),
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        keys.take(2).forEach { (k, l) -> EditorKey(l) { onKey(k) } }
        chars.forEach { ch -> EditorKey(ch) { onText(ch) } }
        keys.drop(2).forEach { (k, l) -> EditorKey(l) { onKey(k) } }
    }
}

@Composable
private fun EditorKey(label: String, onClick: () -> Unit) {
    Box(Modifier.height(34.dp).widthIn(min = 38.dp).background(MaterialTheme.colorScheme.surface,
            androidx.compose.foundation.shape.RoundedCornerShape(6.dp))
            .clickable(onClick = onClick).padding(horizontal = 9.dp),
        contentAlignment = Alignment.Center) {
        Text(label, style = MaterialTheme.typography.labelLarge, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace)
    }
}

/** Buka file cepat: ketik sebagian nama/path, hasil diurutkan (cocok di nama file dulu). */
@Composable
private fun QuickOpenDialog(c: id.codingserver.android.data.api.ApiClient, projectId: String, onDismiss: () -> Unit,
                            onPick: (String) -> Unit) {
    var q by remember { mutableStateOf("") }
    var files by remember { mutableStateOf<List<String>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(projectId) {
        apiCall { c.api.listFiles(projectId) }
            .onSuccess { r -> files = r.files }
            .onFailure { error = it.message }
    }
    val shown = remember(q, files) { quickOpenFilter(files.orEmpty(), q).take(60) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Buka file cepat") },
        text = {
            Column {
                OutlinedTextField(q, { q = it }, singleLine = true, placeholder = { Text("nama file, mis. main") },
                                  modifier = Modifier.fillMaxWidth())
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                if (files == null && error == null) Text("Memuat daftar file…", style = MaterialTheme.typography.bodySmall)
                else if (shown.isEmpty()) Text("Tidak ada file cocok", style = MaterialTheme.typography.bodySmall)
                LazyColumn(Modifier.heightIn(max = 380.dp)) {
                    items(shown) { path ->
                        Column(Modifier.fillMaxWidth().clickable { onPick(path) }.padding(vertical = 7.dp)) {
                            Text(path.substringAfterLast('/'), style = MaterialTheme.typography.bodyMedium)
                            if ('/' in path) Text(path.substringBeforeLast('/'), style = MaterialTheme.typography.labelSmall,
                                                  color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Tutup") } },
    )
}

/** Urutan: nama file diawali kueri → nama file memuat kueri → path memuat kueri → huruf kueri berurutan (fuzzy). */
internal fun quickOpenFilter(files: List<String>, query: String): List<String> {
    val q = query.trim().lowercase()
    if (q.isEmpty()) return files
    fun fuzzy(s: String): Boolean { var i = 0; for (ch in s) if (i < q.length && ch == q[i]) i++; return i == q.length }
    return files.mapNotNull { p ->
        val path = p.lowercase(); val name = path.substringAfterLast('/')
        val rank = when { name.startsWith(q) -> 0; q in name -> 1; q in path -> 2; fuzzy(path) -> 3; else -> return@mapNotNull null }
        rank to p
    }.sortedWith(compareBy({ it.first }, { it.second.length })).map { it.second }
}
