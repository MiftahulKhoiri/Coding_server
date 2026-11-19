package id.codingserver.android.ui.servers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(vm: AppViewModel, onLoggedIn: () -> Unit, onChangeServer: () -> Unit) {
    val client by vm.client.collectAsState()
    val online by vm.online.collectAsState()
    var username by remember(client) { mutableStateOf(client?.server?.username?.ifBlank { "admin" } ?: "admin") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Login", style = MaterialTheme.typography.headlineMedium)
        Text("${client?.server?.name ?: "-"} · ${client?.baseUrl ?: ""}", style = MaterialTheme.typography.bodySmall)
        Text(
            when (online) { true -> "Server ONLINE"; false -> "Server OFFLINE - periksa jaringan/alamat"; else -> "Memeriksa server…" },
            color = if (online == false) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
        )
        OutlinedTextField(username, { username = it }, label = { Text("Username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(
            password, { password = it }, label = { Text("Password") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth(),
        )
        error?.let { ErrorCard(it) }
        Button(
            enabled = !busy && username.isNotBlank() && password.isNotBlank(),
            onClick = {
                busy = true; error = null
                scope.launch {
                    vm.login(username.trim(), password)
                        .onSuccess { password = ""; onLoggedIn() }
                        .onFailure { error = it.message }
                    busy = false
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { if (busy) CircularProgressIndicator() else Text("Masuk") }
        TextButton(onClick = onChangeServer) { Text("Ganti server") }
        Text(
            "Password admin awal ada di Raspberry Pi: workspace/metadata/initial_admin_password.txt",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
