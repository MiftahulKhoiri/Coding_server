package id.codingserver.android.ui.settings

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.PasswordChange
import id.codingserver.android.data.api.ProfileUpdate
import id.codingserver.android.data.api.UserCreate
import id.codingserver.android.data.api.UserOut
import id.codingserver.android.data.api.UserUpdate
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.TitleWithInfo
import id.codingserver.android.ui.common.UserAvatar
import id.codingserver.android.ui.common.prepareAvatar
import id.codingserver.android.ui.common.formatTime
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

private val ROLE_LABEL = mapOf(
    "admin" to "Admin", "developer" to "Developer", "runner" to "Runner", "viewer" to "Viewer", "ai" to "AI",
)
private val ROLE_INFO = mapOf(
    "admin" to "semua akses + kelola pengguna & backup",
    "developer" to "baca, tulis, hapus, jalankan, build, terminal",
    "runner" to "baca, jalankan & build saja",
    "viewer" to "hanya melihat",
)
private const val ROOT_NOTE = "Admin utama adalah akun pemulihan: tidak bisa dihapus, dinonaktifkan, atau diubah " +
    "perannya, dan sandinya hanya bisa diganti dari server. Bila sandi akun lain terlupa, login sebagai admin " +
    "utama lalu reset sandinya di \"Pengguna\".\n\nLihat / ganti sandi admin utama di Raspberry Pi:\n" +
    "  scripts/admin_password.sh            (tampilkan)\n" +
    "  scripts/admin_password.sh --set      (ganti)\n" +
    "  scripts/admin_password.sh --random   (acak baru)"

/** Kartu Akun & Profil + (untuk admin) Kelola pengguna. Dipakai di SettingsScreen. */
@Composable
fun AccountSection(vm: AppViewModel, onServers: () -> Unit) {
    val user by vm.user.collectAsState()
    val client by vm.client.collectAsState()
    val u = user
    val c = client
    ProfileCard(vm, u, c, onServers)
    if (u != null && c != null && "admin" in u.permissions) UsersCard(vm, u, c)
}

@Composable
fun RootBadge() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Default.Lock, null, Modifier.size(14.dp), tint = MaterialTheme.colorScheme.tertiary)
        Text(" Admin utama", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.tertiary)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileCard(vm: AppViewModel, u: UserOut?, c: ApiClient?, onServers: () -> Unit) {
    var editProfile by remember { mutableStateOf(false) }
    var editPassword by remember { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            TitleWithInfo("Akun & profil", if (u?.is_root == true) ROOT_NOTE
                else "Ubah nama tampilan, email, bio, dan sandi akunmu. Bila lupa sandi, minta admin utama mereset.")
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                UserAvatar(c, u, 56.dp)
                Column(Modifier.weight(1f)) {
                    Text(u?.shownName ?: "-", style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("@${u?.username ?: "-"} · ${ROLE_LABEL[u?.role] ?: u?.role ?: "-"} · ${c?.server?.name ?: "-"}",
                        style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (u?.is_root == true) RootBadge()
                }
            }
            u?.email?.takeIf { it.isNotBlank() }?.let { Text("✉ $it", style = MaterialTheme.typography.bodySmall) }
            u?.bio?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
            Text("Izin: ${u?.permissions?.joinToString() ?: "-"}", style = MaterialTheme.typography.labelSmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(enabled = u != null, onClick = { editProfile = true }) { Text("Ubah profil") }
                OutlinedButton(enabled = u != null, onClick = { editPassword = true }) { Text("Ganti sandi") }
                OutlinedButton(onClick = onServers) { Text("Kelola server") }
                OutlinedButton(onClick = { vm.logout() }) { Text("Logout") }
            }
        }
    }
    if (editProfile && u != null && c != null) ProfileDialog(vm, u, c) { editProfile = false }
    if (editPassword && u != null && c != null) {
        if (u.is_root) {
            AlertDialog(onDismissRequest = { editPassword = false }, title = { Text("Sandi admin utama") },
                text = { Text(ROOT_NOTE) },
                confirmButton = { TextButton(onClick = { editPassword = false }) { Text("Mengerti") } })
        } else PasswordDialog(vm, c) { editPassword = false }
    }
}

@Composable
private fun ProfileDialog(vm: AppViewModel, u: UserOut, c: ApiClient, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf(u.display_name) }
    var email by remember { mutableStateOf(u.email) }
    var bio by remember { mutableStateOf(u.bio) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var current by remember { mutableStateOf(u) }
    val ctx = LocalContext.current
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        busy = true
        scope.launch {
            runCatching { prepareAvatar(ctx, uri) }.onSuccess { bytes ->
                val part = MultipartBody.Part.createFormData("file", "avatar.jpg",
                    bytes.toRequestBody("image/jpeg".toMediaType()))
                apiCall { c.api.uploadAvatar(part) }
                    .onSuccess { current = it; vm.setUser(it); vm.toast("Foto profil diperbarui") }
                    .onFailure { error = it.message }
            }.onFailure { error = "Gambar tidak bisa dibaca: ${it.message}" }
            busy = false
        }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Ubah profil") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    UserAvatar(c, current, 72.dp)
                    Column {
                        OutlinedButton(enabled = !busy, onClick = {
                            picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                        }) { Text(if (current.avatar_version == null) "Pilih foto" else "Ganti foto") }
                        if (current.avatar_version != null) TextButton(enabled = !busy, onClick = {
                            busy = true
                            scope.launch {
                                apiCall { c.api.deleteAvatar() }.onSuccess { current = it; vm.setUser(it) }
                                    .onFailure { error = it.message }
                                busy = false
                            }
                        }) { Text("Hapus foto", color = MaterialTheme.colorScheme.error) }
                    }
                }
                if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                Text("Username @${u.username} tidak bisa diubah.", style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(name, { name = it.take(80) }, label = { Text("Nama tampilan") }, singleLine = true)
                OutlinedTextField(email, { email = it.take(120) }, label = { Text("Email (opsional)") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                OutlinedTextField(bio, { bio = it.take(500) }, label = { Text("Bio (opsional)") }, minLines = 2, maxLines = 5)
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = {
                busy = true
                scope.launch {
                    apiCall { c.api.updateMe(ProfileUpdate(name, email, bio)) }
                        .onSuccess { vm.setUser(it); vm.toast("Profil disimpan"); onDismiss() }
                        .onFailure { error = it.message }
                    busy = false
                }
            }) { Text("Simpan") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}

@Composable
private fun PasswordField(value: String, onChange: (String) -> Unit, label: String) {
    OutlinedTextField(value, onChange, label = { Text(label) }, singleLine = true,
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
}

@Composable
private fun PasswordDialog(vm: AppViewModel, c: ApiClient, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var old by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var again by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    val problem = when {
        new.isNotEmpty() && new.length < 8 -> "Sandi baru minimal 8 karakter"
        again.isNotEmpty() && again != new -> "Ulangi sandi tidak sama"
        else -> null
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Ganti sandi") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                PasswordField(old, { old = it }, "Sandi lama")
                PasswordField(new, { new = it }, "Sandi baru")
                PasswordField(again, { again = it }, "Ulangi sandi baru")
                (problem ?: error)?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(enabled = old.isNotEmpty() && new.length >= 8 && new == again, onClick = {
                scope.launch {
                    apiCall { c.api.changePassword(PasswordChange(old, new)) }
                        .onSuccess { vm.toast("Sandi diganti"); onDismiss() }
                        .onFailure { error = it.message }
                }
            }) { Text("Simpan") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}

// ---------------- kelola pengguna (admin) ----------------
@Composable
private fun UsersCard(vm: AppViewModel, me: UserOut, c: ApiClient) {
    var users by remember { mutableStateOf<List<UserOut>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var adding by remember { mutableStateOf(false) }
    var reload by remember { mutableStateOf(0) }

    LaunchedEffect(c, reload) {
        apiCall { c.api.users() }.onSuccess { users = it; error = null }.onFailure { error = it.message }
    }
    fun refresh() { reload++ }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) {
                    TitleWithInfo("Pengguna", "Tambah akun untuk orang lain atau untuk dirimu sendiri (profil harian), " +
                        "atur perannya, reset sandi yang terlupa, nonaktifkan, atau hapus. Proyek milik akun yang dihapus " +
                        "dipindahkan ke admin utama.\n\nHanya admin utama yang boleh membuat/mengubah akun berperan Admin.")
                }
                IconButton(onClick = { adding = true }) { Icon(Icons.Default.PersonAdd, "Tambah pengguna") }
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            users?.forEachIndexed { i, u ->
                if (i > 0) HorizontalDivider()
                UserRow(vm, me, u, c, onChanged = ::refresh)
            }
        }
    }
    if (adding) AddUserDialog(me, c, onDone = { adding = false; refresh(); vm.toast("Pengguna ditambahkan") }) { adding = false }
}

@Composable
private fun UserRow(vm: AppViewModel, me: UserOut, u: UserOut, c: ApiClient, onChanged: () -> Unit) {
    val scope = rememberCoroutineScope()
    var menu by remember { mutableStateOf(false) }
    var dlg by remember { mutableStateOf<String?>(null) }
    val self = u.id == me.id
    // Admin utama dilindungi; admin biasa tidak boleh mengatur admin lain.
    val manageable = !u.is_root && !self && (me.is_root || u.role != "admin")

    fun update(body: UserUpdate, ok: String) = scope.launch {
        apiCall { c.api.updateUser(u.id, body) }.onSuccess { vm.toast(ok); onChanged() }.onFailure { vm.toast(it.message ?: "Gagal") }
    }

    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        UserAvatar(c, u, 44.dp)
        Column(Modifier.weight(1f).padding(start = 10.dp)) {
            Text(u.shownName + if (self) " (kamu)" else "", style = MaterialTheme.typography.bodyLarge, maxLines = 1,
                overflow = TextOverflow.Ellipsis)
            Text("@${u.username} · ${ROLE_LABEL[u.role] ?: u.role}" + if (!u.is_active) " · NONAKTIF" else "",
                style = MaterialTheme.typography.bodySmall,
                color = if (u.is_active) Color.Unspecified else MaterialTheme.colorScheme.error)
            if (u.is_root) RootBadge()
            u.last_login_at?.let { Text("Login terakhir ${formatTime(it)}", style = MaterialTheme.typography.labelSmall) }
        }
        if (manageable) Box {
            IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, "Aksi") }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text("Ubah peran") }, onClick = { menu = false; dlg = "role" })
                DropdownMenuItem(text = { Text("Reset sandi") }, onClick = { menu = false; dlg = "password" })
                DropdownMenuItem(text = { Text(if (u.is_active) "Nonaktifkan" else "Aktifkan") }, onClick = {
                    menu = false
                    update(UserUpdate(is_active = !u.is_active), if (u.is_active) "${u.username} dinonaktifkan" else "${u.username} diaktifkan")
                })
                DropdownMenuItem(text = { Text("Hapus", color = MaterialTheme.colorScheme.error) }, onClick = { menu = false; dlg = "delete" })
            }
        }
    }
    when (dlg) {
        "role" -> RoleDialog(u.role, allowAdmin = me.is_root, onPick = { r -> dlg = null; update(UserUpdate(role = r), "Peran ${u.username} → ${ROLE_LABEL[r]}") }) { dlg = null }
        "password" -> ResetPasswordDialog(u, onSave = { pw -> dlg = null; update(UserUpdate(password = pw), "Sandi ${u.username} direset") }) { dlg = null }
        "delete" -> ConfirmDialog("Hapus ${u.username}?", "Akun dihapus permanen. Proyek miliknya dipindahkan ke admin utama.",
            confirmText = "Hapus", onConfirm = {
                scope.launch {
                    apiCall { c.api.deleteUser(u.id) }.onSuccess { vm.toast(it.message); onChanged() }
                        .onFailure { vm.toast(it.message ?: "Gagal") }
                }
            }, onDismiss = { dlg = null })
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun RolePicker(role: String, allowAdmin: Boolean, onPick: (String) -> Unit) {
    val roles = listOfNotNull("developer", "runner", "viewer", if (allowAdmin) "admin" else null)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        roles.forEach { r -> FilterChip(selected = r == role, onClick = { onPick(r) }, label = { Text(ROLE_LABEL[r] ?: r) }) }
    }
    ROLE_INFO[role]?.let { Text(it, style = MaterialTheme.typography.labelSmall) }
}

@Composable
private fun RoleDialog(current: String, allowAdmin: Boolean, onPick: (String) -> Unit, onDismiss: () -> Unit) {
    var role by remember { mutableStateOf(current) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Ubah peran") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { RolePicker(role, allowAdmin) { role = it } } },
        confirmButton = { TextButton(enabled = role != current, onClick = { onPick(role) }) { Text("Simpan") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } })
}

@Composable
private fun ResetPasswordDialog(u: UserOut, onSave: (String) -> Unit, onDismiss: () -> Unit) {
    var pw by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Reset sandi ${u.username}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Berikan sandi baru ini ke pemilik akun; ia bisa menggantinya sendiri setelah login.",
                    style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(pw, { pw = it }, label = { Text("Sandi baru (min 8)") }, singleLine = true)
            }
        },
        confirmButton = { TextButton(enabled = pw.length >= 8, onClick = { onSave(pw) }) { Text("Reset") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } })
}

@Composable
private fun AddUserDialog(me: UserOut, c: ApiClient, onDone: () -> Unit, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var username by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var pw by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("developer") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val validName = username.isNotBlank() && username.all { it.isLetterOrDigit() || it in "_-." }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Tambah pengguna") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(username, { username = it.trim().take(64) }, label = { Text("Username") }, singleLine = true,
                    isError = username.isNotEmpty() && !validName,
                    supportingText = { Text("huruf, angka, _ - .") })
                OutlinedTextField(name, { name = it.take(80) }, label = { Text("Nama tampilan (opsional)") }, singleLine = true)
                OutlinedTextField(pw, { pw = it }, label = { Text("Sandi (min 8)") }, singleLine = true)
                Text("Peran", style = MaterialTheme.typography.labelLarge)
                RolePicker(role, allowAdmin = me.is_root) { role = it }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(enabled = validName && pw.length >= 8 && !busy, onClick = {
                busy = true
                scope.launch {
                    apiCall { c.api.createUser(UserCreate(username, pw, role, display_name = name)) }
                        .onSuccess { onDone() }.onFailure { error = it.message }
                    busy = false
                }
            }) { Text("Tambah") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}
