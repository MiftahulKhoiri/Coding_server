package id.codingserver.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Article
import androidx.compose.material.icons.filled.Code
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.Http
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Monitor
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Science
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material.icons.filled.Terminal
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.AutoFixHigh
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import id.codingserver.android.agent.AgentMonitorService
import id.codingserver.android.data.api.FileEntry
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.AuthState
import id.codingserver.android.ui.EditorTab
import id.codingserver.android.ui.agent.AgentScreen
import id.codingserver.android.ui.ai.AiChatScreen
import id.codingserver.android.ui.ai.AiModelScreen
import id.codingserver.android.ui.ai.ModelBenchScreen
import id.codingserver.android.ui.dashboard.DashboardScreen
import id.codingserver.android.ui.database.DatabaseScreen
import id.codingserver.android.ui.editor.EditorController
import id.codingserver.android.ui.editor.EditorScreen
import id.codingserver.android.ui.git.GitScreen
import id.codingserver.android.ui.http.HttpScreen
import id.codingserver.android.ui.monitor.MonitorScreen
import id.codingserver.android.ui.output.OutputScreen
import id.codingserver.android.ui.projects.ExplorerScreen
import id.codingserver.android.ui.projects.ProjectsScreen
import id.codingserver.android.ui.servers.LoginScreen
import id.codingserver.android.ui.servers.ServersScreen
import id.codingserver.android.ui.settings.SettingsScreen
import id.codingserver.android.ui.terminal.TerminalController
import id.codingserver.android.ui.terminal.TerminalScreen
import id.codingserver.android.ui.theme.CodingServerTheme
import id.codingserver.android.ui.theme.isAppDark
import kotlinx.coroutines.launch

private data class Dest(val route: String, val label: String, val icon: ImageVector, val section: String)

// Menu dikelompokkan per area kerja agar tetap ringkas di layar kecil.
private val DESTS = listOf(
    Dest("dashboard", "Dashboard", Icons.Default.Dashboard, "WORKSPACE"),
    Dest("projects", "Proyek", Icons.Default.Folder, "WORKSPACE"),
    Dest("explorer", "Project Explorer", Icons.Default.FolderOpen, "WORKSPACE"),
    Dest("editor", "Code Editor", Icons.Default.Code, "WORKSPACE"),
    Dest("terminal", "Terminal", Icons.Default.Terminal, "DEVELOPMENT"),
    Dest("output", "Build Output", Icons.AutoMirrored.Filled.Article, "DEVELOPMENT"),
    Dest("ai_chat", "AI Chat", Icons.Default.SmartToy, "AI DEVELOPMENT"),
    Dest("agent", "Agent Tasks", Icons.Default.AutoFixHigh, "AI DEVELOPMENT"),
    Dest("ai_models", "Model AI", Icons.Default.Psychology, "AI DEVELOPMENT"),
    Dest("ai_bench", "Uji Model", Icons.Default.Science, "AI DEVELOPMENT"),
    Dest("git", "Git", Icons.Default.AccountTree, "PROJECT TOOLS"),
    Dest("database", "Database", Icons.Default.Storage, "PROJECT TOOLS"),
    Dest("http", "HTTP Client", Icons.Default.Http, "PROJECT TOOLS"),
    Dest("monitor", "Server Monitor", Icons.Default.Monitor, "SERVER"),
    Dest("servers", "Koneksi Server", Icons.Default.Dns, "SYSTEM"),
    Dest("settings", "Pengaturan", Icons.Default.Settings, "SYSTEM"),
)

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()
    private val editor by lazy { EditorController(this).also { e -> e.lspConfig = { vm.lspConfigJson() } } }
    private val terminal by lazy { TerminalController(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val theme by vm.appTheme.collectAsState()
            val dark = isAppDark(theme)
            // Ikon status bar/navigasi mengikuti tema aplikasi (bukan tema sistem).
            LaunchedEffect(dark) {
                val transparent = android.graphics.Color.TRANSPARENT
                val style = if (dark) androidx.activity.SystemBarStyle.dark(transparent)
                            else androidx.activity.SystemBarStyle.light(transparent, transparent)
                enableEdgeToEdge(statusBarStyle = style, navigationBarStyle = style)
            }
            CodingServerTheme(theme) { App(vm, editor, terminal) }
        }
        handleAgentIntent(intent)
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleAgentIntent(intent)
    }

    /** Notifikasi AI Agent membawa id task yang harus dibuka. */
    private fun handleAgentIntent(intent: android.content.Intent?) {
        val key = AgentMonitorService.EXTRA_OPEN_TASK
        val taskId = intent?.getStringExtra(key) ?: return
        intent.removeExtra(key)
        vm.openAgentTask(taskId)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun App(vm: AppViewModel, editor: EditorController, terminal: TerminalController) {
    val nav = rememberNavController()
    val auth by vm.auth.collectAsState()
    val online by vm.online.collectAsState()
    val project by vm.project.collectAsState()
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val snack = remember { SnackbarHostState() }
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route

    LaunchedEffect(Unit) { vm.messages.collect { snack.showSnackbar(it) } }
    LaunchedEffect(auth) {
        val target = when (auth) {
            AuthState.NO_SERVER -> "servers"
            AuthState.LOGGED_OUT -> "login"
            AuthState.LOGGED_IN -> if (route == null || route == "login" || route == "servers") "dashboard" else null
        }
        if (target != null && target != route) nav.navigate(target) { popUpTo(0) }
    }
    // Dibuka dari notifikasi AI Agent → pindah ke layar Agent Tasks (layar itu yang membuka detail task).
    val agentTarget by vm.agentTarget.collectAsState()
    LaunchedEffect(agentTarget, auth) {
        if (agentTarget != null && auth == AuthState.LOGGED_IN && route != "agent")
            nav.navigate("agent") { launchSingleTop = true; popUpTo("dashboard") }
    }

    fun go(r: String) {
        scope.launch { drawer.close() }
        if (r != route) nav.navigate(r) { launchSingleTop = true; popUpTo("dashboard") }
    }

    val loggedIn = auth == AuthState.LOGGED_IN
    ModalNavigationDrawer(
        drawerState = drawer,
        gesturesEnabled = loggedIn && route != "editor" && route != "terminal" && route != "ai_chat",
        drawerContent = {
            ModalDrawerSheet {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text("CODING_SERVER", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(16.dp))
                    Text("Proyek: ${project?.name ?: "-"}", modifier = Modifier.padding(horizontal = 16.dp),
                         style = MaterialTheme.typography.bodySmall)
                    // Info versi APK juga ada di Pengaturan > Pembaruan aplikasi.
                    Text("Aplikasi v${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})",
                         modifier = Modifier.padding(horizontal = 16.dp), style = MaterialTheme.typography.labelSmall)
                    HorizontalDivider(Modifier.padding(vertical = 8.dp))
                    DESTS.forEachIndexed { i, d ->
                        if (i == 0 || DESTS[i - 1].section != d.section) Text(
                            d.section, style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.padding(start = 28.dp, top = if (i == 0) 0.dp else 10.dp, bottom = 2.dp),
                        )
                        NavigationDrawerItem(label = { Text(d.label) }, icon = { Icon(d.icon, null) },
                            selected = route == d.route, onClick = { go(d.route) }, modifier = Modifier.padding(horizontal = 8.dp))
                    }
                    Spacer(Modifier.height(16.dp))
                }
            }
        },
    ) {
        Scaffold(
            snackbarHost = { SnackbarHost(snack) },
            topBar = {
                // Tanpa AppBar (layar editor) jarak status bar harus diberikan sendiri; TopAppBar biasanya
                // yang menanganinya, dan Scaffold tidak menambahkannya lagi selama topBar ada.
                if (loggedIn) Column(if (route == "editor") Modifier.statusBarsPadding() else Modifier) {
                    // Layar editor punya baris menu+tab ringkas sendiri (area kode lebih luas).
                    if (route != "editor") TopAppBar(
                        title = {
                            Text(DESTS.firstOrNull { it.route == route }?.label ?: "Coding Server", maxLines = 1, overflow = TextOverflow.Ellipsis)
                        },
                        navigationIcon = { IconButton(onClick = { scope.launch { drawer.open() } }) { Icon(Icons.Default.Menu, "Menu") } },
                    )
                    if (online == false) Text(
                        "Server OFFLINE — data tidak bisa dimuat. Mencoba menghubungkan ulang…",
                        color = MaterialTheme.colorScheme.onError,
                        modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.error).padding(6.dp),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            },
        ) { pad ->
            // imePadding: dengan edge-to-edge (Android 15) adjustResize tidak lagi mengecilkan jendela,
            // jadi konten (editor/terminal) harus diberi padding keyboard agar baris yang diketik tidak tertutup.
            NavGraph(nav, vm, editor, terminal, onMenu = { scope.launch { drawer.open() } }, modifier = Modifier.padding(pad).consumeWindowInsets(pad).imePadding().fillMaxSize())
        }
    }
}

@Composable
private fun NavGraph(nav: NavHostController, vm: AppViewModel, editor: EditorController, terminal: TerminalController,
                     onMenu: () -> Unit, modifier: Modifier) {
    fun openFile(e: FileEntry) {
        val p = vm.project.value ?: return
        vm.addOrFocusTab(EditorTab(p.id, e.path, null, language = e.language))
        nav.navigate("editor") { launchSingleTop = true }
    }
    NavHost(nav, startDestination = "servers", modifier = modifier) {
        composable("servers") {
            ServersScreen(vm) {
                if (vm.auth.value == AuthState.LOGGED_IN) nav.navigate("dashboard") { popUpTo(0) }
            }
        }
        composable("login") { LoginScreen(vm, onLoggedIn = {}, onChangeServer = { vm.disconnect() }) }
        composable("dashboard") {
            DashboardScreen(vm) { p -> vm.openProject(p); nav.navigate("explorer") { launchSingleTop = true } }
        }
        composable("projects") { ProjectsScreen(vm) { nav.navigate("explorer") { launchSingleTop = true } } }
        composable("explorer") {
            val scope = rememberCoroutineScope()
            ExplorerScreen(vm, onOpenFile = ::openFile, onRun = { e ->
                vm.toast("Menjalankan ${e.name}…")
                scope.launch {
                    vm.execute(e, build = false).onSuccess { nav.navigate("output") { launchSingleTop = true } }
                        .onFailure { vm.toast(it.message ?: "Gagal") }
                }
            })
        }
        composable("editor") { EditorScreen(vm, editor, onMenu) { nav.navigate("output") { launchSingleTop = true } } }
        composable("terminal") { TerminalScreen(vm, terminal) }
        composable("output") {
            OutputScreen(vm, editor, onGotoEditor = { nav.navigate("editor") { launchSingleTop = true } },
                         onAskAi = { nav.navigate("ai_chat") { launchSingleTop = true } })
        }
        composable("ai_chat") {
            AiChatScreen(vm, editor, onOpenModels = { nav.navigate("ai_models") { launchSingleTop = true } },
                         onOpenEditor = { nav.navigate("editor") { launchSingleTop = true } })
        }
        composable("ai_models") {
            AiModelScreen(vm, onOpenBench = { nav.navigate("ai_bench") { launchSingleTop = true } }) {
                nav.navigate("ai_chat") { launchSingleTop = true }
            }
        }
        composable("ai_bench") { ModelBenchScreen(vm) }
        composable("agent") { AgentScreen(vm, onOpenModels = { nav.navigate("ai_models") { launchSingleTop = true } }) }
        composable("database") { DatabaseScreen(vm) }
        composable("git") { GitScreen(vm) }
        composable("http") { HttpScreen(vm) }
        composable("monitor") { MonitorScreen(vm) }
        composable("settings") { SettingsScreen(vm) { nav.navigate("servers") } }
    }
}
