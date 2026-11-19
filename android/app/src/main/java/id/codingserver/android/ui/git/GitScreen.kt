package id.codingserver.android.ui.git

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.Commit
import id.codingserver.android.data.api.GitBranch
import id.codingserver.android.data.api.GitBranches
import id.codingserver.android.data.api.GitCheckout
import id.codingserver.android.data.api.GitCommit
import id.codingserver.android.data.api.GitCredential
import id.codingserver.android.data.api.GitProject
import id.codingserver.android.data.api.GitRemoteOp
import id.codingserver.android.data.api.GitRemoteSet
import id.codingserver.android.data.api.GitResult
import id.codingserver.android.data.api.GitStatus
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InputDialog
import id.codingserver.android.ui.theme.Mono
import kotlinx.coroutines.launch

/** Git Manager: init, status, commit, log, branch, checkout, diff, remote, pull, push, kredensial. */
@Composable
fun GitScreen(vm: AppViewModel) {
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    var status by remember { mutableStateOf<GitStatus?>(null) }
    var branches by remember { mutableStateOf<GitBranches?>(null) }
    var log by remember { mutableStateOf<List<Commit>>(emptyList()) }
    var output by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var notRepo by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    var dialog by remember { mutableStateOf<String?>(null) }
    var credUser by remember { mutableStateOf("") }
    var credToken by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val c = client
    val p = project
    if (c == null || p == null) { Text("Buka proyek dulu.", Modifier.padding(16.dp)); return }

    LaunchedEffect(p.id, reload) {
        error = null
        apiCall { c.api.gitStatus(p.id) }.onSuccess { status = it; notRepo = false }.onFailure {
            notRepo = it.message?.contains("Git") == true; status = null
            if (!notRepo) error = it.message
        }
        if (!notRepo) {
            apiCall { c.api.gitBranches(p.id) }.onSuccess { branches = it }
            apiCall { c.api.gitLog(p.id, 30) }.onSuccess { log = it.commits }.onFailure { log = emptyList() }
        }
    }

    fun op(label: String, block: suspend () -> GitResult) {
        scope.launch {
            output = "$label…"
            apiCall { block() }.onSuccess { r -> output = "$label: ${if (r.ok) "OK" else "GAGAL (exit ${r.exit_code})"}\n${r.stdout}\n${r.stderr}".trim(); reload++ }
                .onFailure { output = "$label gagal: ${it.message}" }
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        error?.let { ErrorCard(it) { reload++ } }
        if (notRepo) {
            Text("Proyek ini belum repository Git.")
            Button(onClick = { op("git init") { c.api.gitInit(GitProject(p.id)) } }) { Text("git init") }
        }
        status?.let { s ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(10.dp)) {
                    Text("Branch: ${s.branch}", style = MaterialTheme.typography.titleSmall)
                    if (s.clean) Text("Bersih, tidak ada perubahan")
                    s.files.forEach { f -> Text("${f.index}${f.worktree} ${f.path}", style = Mono) }
                }
            }
            OutlinedTextField(message, { message = it }, label = { Text("Pesan commit") }, modifier = Modifier.fillMaxWidth())
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(enabled = message.isNotBlank() && !s.clean, onClick = {
                    op("commit") { c.api.gitCommit(GitCommit(p.id, message, true)) }; message = ""
                }) { Text("Commit semua") }
                OutlinedButton(onClick = { op("pull") { c.api.gitPull(GitRemoteOp(p.id)) } }) { Text("Pull") }
                OutlinedButton(onClick = { op("push") { c.api.gitPush(GitRemoteOp(p.id)) } }) { Text("Push") }
                OutlinedButton(onClick = { op("diff") { c.api.gitDiff(p.id) } }) { Text("Diff") }
            }
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = { dialog = "branch" }) { Text("Branch baru") }
                OutlinedButton(onClick = { dialog = "checkout" }) { Text("Checkout") }
                OutlinedButton(onClick = { dialog = "remote" }) { Text("Set remote") }
                OutlinedButton(onClick = { dialog = "cred" }) { Text("Token Git") }
            }
            branches?.let { b -> Text("Branch: ${b.branches.joinToString()} (aktif: ${b.current ?: "-"})", style = MaterialTheme.typography.bodySmall) }
        }
        if (output.isNotBlank()) SelectionContainer {
            Text(output, style = Mono, modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()))
        }
        if (log.isNotEmpty()) {
            Text("Log", style = MaterialTheme.typography.titleSmall)
            log.forEach { cm ->
                Column(Modifier.padding(vertical = 3.dp)) {
                    Text("${cm.hash.take(8)} ${cm.message}", style = Mono)
                    Text("${cm.author} · ${cm.date}", style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }

    when (dialog) {
        "branch" -> InputDialog("Branch baru", "Nama branch", onConfirm = { n -> op("branch $n") { c.api.gitBranch(GitBranch(p.id, n)) } },
            onDismiss = { dialog = null })
        "checkout" -> InputDialog("Checkout", "Branch / ref", initial = branches?.current ?: "",
            onConfirm = { n -> op("checkout $n") { c.api.gitCheckout(GitCheckout(p.id, n)) } }, onDismiss = { dialog = null })
        "remote" -> InputDialog("Remote origin", "https://github.com/user/repo.git",
            onConfirm = { u -> op("remote") { c.api.gitRemote(GitRemoteSet(p.id, "origin", u)) } }, onDismiss = { dialog = null })
        "cred" -> InputDialog("Username GitHub", "Username", initial = credUser, onConfirm = { u -> credUser = u; dialog = "token" },
            onDismiss = { if (dialog == "cred") dialog = null })
        "token" -> InputDialog("Token akses (disimpan terenkripsi di server)", "Personal access token", password = true, onConfirm = { t ->
            credToken = t
            scope.launch {
                apiCall { c.api.setGitCredential(GitCredential("github.com", credUser, credToken)) }
                    .onSuccess { vm.toast("Token disimpan") }.onFailure { vm.toast(it.message ?: "") }
                credToken = ""
            }
        }, onDismiss = { dialog = null })
    }
}
