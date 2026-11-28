package id.codingserver.android.ui.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.Identities
import id.codingserver.android.data.api.LinkFlow
import id.codingserver.android.data.api.LinkStart
import id.codingserver.android.data.api.OAuthConfigIn
import id.codingserver.android.data.api.OAuthProviders
import id.codingserver.android.data.api.UserOut
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.TitleWithInfo
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val PROVIDER_NAME = mapOf("github" to "GitHub", "google" to "Google")

/** Kartu "Akun tertaut": tautkan GitHub/Google (device flow) → email aktif terverifikasi, GitHub juga bisa push. */
@Composable
fun LinkedAccountsCard(vm: AppViewModel, u: UserOut, c: ApiClient) {
    val scope = rememberCoroutineScope()
    var reload by remember { mutableIntStateOf(0) }
    var ids by remember { mutableStateOf<Identities?>(null) }
    var providers by remember { mutableStateOf(OAuthProviders()) }
    var linking by remember { mutableStateOf<String?>(null) }
    var unlinking by remember { mutableStateOf<String?>(null) }
    var config by remember { mutableStateOf(false) }
    LaunchedEffect(reload) {
        apiCall { c.api.identities() }.onSuccess { ids = it }
        apiCall { c.api.oauthProviders() }.onSuccess { providers = it }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            TitleWithInfo("Akun tertaut", "Tautkan akun GitHub atau Google untuk memakai email aktif (terverifikasi) di " +
                "profil. GitHub juga bisa dipakai untuk push repo tanpa membuat token manual, dan commit tercatat " +
                "atas nama & emailmu.\n\nCara kerja: aplikasi menampilkan kode, kamu membuka halaman GitHub/Google di " +
                "browser, memasukkan kode, lalu menyetujui. Sandi GitHub/Google tidak pernah melewati server ini.")
            listOf("github", "google").forEach { p ->
                val id = ids?.identities?.firstOrNull { it.provider == p }
                val enabled = if (p == "github") providers.github else providers.google
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(PROVIDER_NAME[p] ?: p, style = MaterialTheme.typography.titleSmall)
                        if (id != null) {
                            Text("@${id.login}" + if (id.git_push) " · push aktif" else "", style = MaterialTheme.typography.bodySmall)
                            id.emails.forEach { e -> Text("✓ $e", style = MaterialTheme.typography.labelSmall,
                                                         color = MaterialTheme.colorScheme.primary) }
                        } else Text(if (enabled) "Belum ditautkan" else "Belum diatur admin utama",
                                    style = MaterialTheme.typography.bodySmall)
                    }
                    if (id != null) TextButton(onClick = { unlinking = p }) { Text("Lepas", color = MaterialTheme.colorScheme.error) }
                    else Button(enabled = enabled, onClick = { linking = p }) { Text("Tautkan") }
                }
            }
            if (u.is_root) OutlinedButton(onClick = { config = true }) { Text("Atur Client ID GitHub/Google") }
        }
    }
    linking?.let { p ->
        LinkDialog(vm, c, p, onDone = { linked ->
            linking = null
            if (linked) scope.launch {
                apiCall { c.api.me() }.onSuccess { vm.setUser(it) }
                reload++
            }
        })
    }
    unlinking?.let { p ->
        ConfirmDialog("Lepas ${PROVIDER_NAME[p]}?", "Email dari akun ini tidak lagi terverifikasi" +
            (if (p == "github") ", dan token push GitHub yang dibuat saat menautkan ikut dihapus." else ".") , "Lepas",
            onConfirm = {
                scope.launch {
                    apiCall { c.api.unlinkIdentity(p) }.onSuccess {
                        apiCall { c.api.me() }.onSuccess { vm.setUser(it) }
                        reload++
                    }.onFailure { vm.toast(it.message ?: "Gagal") }
                }
            }, onDismiss = { unlinking = null })
    }
    if (config) OAuthConfigDialog(vm, c) { config = false; reload++ }
}

@Composable
private fun LinkDialog(vm: AppViewModel, c: ApiClient, provider: String, onDone: (Boolean) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var allowPush by remember { mutableStateOf(true) }
    var flow by remember { mutableStateOf<LinkFlow?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val name = PROVIDER_NAME[provider] ?: provider

    // Periksa status berkala sampai tertaut / ditolak / kedaluwarsa.
    LaunchedEffect(flow?.flow_id) {
        val id = flow?.flow_id ?: return@LaunchedEffect
        while (true) {
            delay(2_500)
            val f = apiCall { c.api.linkFlow(id) }.getOrNull() ?: continue
            flow = f
            if (f.status != "pending") {
                if (f.status == "linked") { vm.toast("$name tertaut: ${f.identity?.emails?.firstOrNull() ?: f.identity?.login}"); onDone(true) }
                break
            }
        }
    }
    fun start() {
        busy = true; error = null
        scope.launch {
            apiCall { c.api.linkIdentity(provider, LinkStart(allow_push = provider == "github" && allowPush)) }
                .onSuccess { flow = it }.onFailure { error = it.message }
            busy = false
        }
    }
    fun openBrowser(f: LinkFlow) {
        (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("kode", f.user_code))
        vm.toast("Kode ${f.user_code} disalin — tempel di halaman $name")
        runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(f.verification_uri)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }

    AlertDialog(
        onDismissRequest = { onDone(false) },
        title = { Text("Tautkan $name") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val f = flow
                if (f == null) {
                    Text("Email terverifikasi dari akun $name akan dipakai sebagai email profilmu.", style = MaterialTheme.typography.bodySmall)
                    if (provider == "github") Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(allowPush, { allowPush = it })
                        Text("Izinkan push ke repo GitHub dari Git Manager (token disimpan terenkripsi di server)",
                             style = MaterialTheme.typography.bodySmall)
                    }
                } else {
                    Text("1. Ketuk tombol di bawah: kode disalin & halaman $name terbuka.\n2. Tempel kode, lalu setujui.\n" +
                         "3. Kembali ke aplikasi — tautan selesai otomatis.", style = MaterialTheme.typography.bodySmall)
                    Text(f.user_code, fontSize = 30.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace,
                         color = MaterialTheme.colorScheme.primary)
                    Text(f.verification_uri, style = MaterialTheme.typography.labelSmall)
                    when (f.status) {
                        "pending" -> { LinearProgressIndicator(Modifier.fillMaxWidth()); Text("Menunggu persetujuan…", style = MaterialTheme.typography.labelSmall) }
                        "linked" -> Text("✓ Tertaut", color = MaterialTheme.colorScheme.primary)
                        else -> Text(f.message.ifBlank { f.status }, color = MaterialTheme.colorScheme.error)
                    }
                }
                if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            val f = flow
            when {
                f == null -> Button(enabled = !busy, onClick = ::start) { Text("Mulai") }
                f.status == "pending" -> Button(onClick = { openBrowser(f) }) { Text("Salin kode & buka $name") }
                else -> Button(onClick = { flow = null }) { Text("Ulangi") }
            }
        },
        dismissButton = { TextButton(onClick = { onDone(false) }) { Text("Tutup") } },
    )
}

/** Admin utama: Client ID GitHub OAuth App (device flow) & Google OAuth client (TV/limited input). */
@Composable
private fun OAuthConfigDialog(vm: AppViewModel, c: ApiClient, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var gh by remember { mutableStateOf("") }
    var gid by remember { mutableStateOf("") }
    var gsecret by remember { mutableStateOf("") }
    var secretSet by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        apiCall { c.api.oauthConfig() }.onSuccess { gh = it.github_client_id; gid = it.google_client_id; secretSet = it.google_secret_set }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Login GitHub / Google") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("GitHub: Settings → Developer settings → OAuth Apps → New OAuth App (Homepage & callback URL " +
                     "boleh http://localhost), lalu centang \"Enable Device Flow\". Salin Client ID.",
                     style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(gh, { gh = it.trim() }, label = { Text("GitHub Client ID") }, singleLine = true)
                Text("Google: console.cloud.google.com → APIs & Services → Credentials → Create OAuth client ID → " +
                     "jenis \"TVs and Limited Input devices\". Salin Client ID & Client secret.",
                     style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(gid, { gid = it.trim() }, label = { Text("Google Client ID") }, singleLine = true)
                OutlinedTextField(gsecret, { gsecret = it.trim() }, singleLine = true,
                    label = { Text(if (secretSet) "Google Client secret (tersimpan; isi untuk mengganti)" else "Google Client secret") })
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                scope.launch {
                    apiCall { c.api.saveOauthConfig(OAuthConfigIn(gh, gid, gsecret.ifBlank { null })) }
                        .onSuccess { vm.toast("Pengaturan login disimpan"); onDismiss() }
                        .onFailure { error = it.message }
                }
            }) { Text("Simpan") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}
