package id.codingserver.android.ui.ai

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.TitleWithInfo

/**
 * Model AI — pusat pengelolaan model, dibagi per fungsi:
 * Ringkasan · Model & Koneksi · AI Agent · Laboratorium (Uji Model/kalibrasi) · Konfigurasi (Profil & Parameter).
 */
@Composable
fun AiModelScreen(vm: AppViewModel, onOpenChat: () -> Unit, onOpenAgentTasks: () -> Unit) {
    val client by vm.client.collectAsState()
    val user by vm.user.collectAsState()
    val tabKey by vm.aiModelTab.collectAsState()
    val c = client ?: return
    val isAdmin = user?.permissions?.contains("admin") == true
    val hub = rememberAiModelHubState(c)
    val tab = AiModelTab.of(tabKey)
    fun open(t: AiModelTab) = vm.selectAiModelTab(t.key)

    Column(Modifier.fillMaxSize()) {
        ScrollableTabRow(selectedTabIndex = tab.ordinal, edgePadding = 4.dp) {
            AiModelTab.entries.forEach { t ->
                Tab(selected = t == tab, onClick = { open(t) },
                    text = { Text(t.label, maxLines = 1, overflow = TextOverflow.Ellipsis) })
            }
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when (tab) {
                AiModelTab.OVERVIEW -> AiModelOverview(vm, hub, isAdmin, onOpenChat = onOpenChat, onOpen = ::open,
                                                       onOpenAgentTasks = onOpenAgentTasks)
                AiModelTab.MODELS -> AiModelConnections(vm, hub, isAdmin, onOpenChat = onOpenChat)
                AiModelTab.AGENT -> AgentModelsSection(vm, hub, isAdmin, onOpenLab = { open(AiModelTab.LAB) },
                                                       onOpenAgentTasks = onOpenAgentTasks)
                AiModelTab.LAB -> ModelBenchScreen(vm, onOpenProfiles = {
                    vm.selectAiConfigSection("profil"); open(AiModelTab.CONFIG)
                })
                AiModelTab.CONFIG -> AiModelSettings(vm, hub, isAdmin, onOpenLab = { open(AiModelTab.LAB) })
            }
        }
    }
}

/** Kartu bagian dengan judul + tombol info; dipakai seragam di semua bagian Model AI. */
@Composable
fun AiSection(title: String, info: String? = null, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (info != null) TitleWithInfo(title, info, style = MaterialTheme.typography.titleSmall)
            else Text(title, style = MaterialTheme.typography.titleSmall)
            content()
        }
    }
}

/** Label status kecil berwarna (SIAP, MEMUAT, GAGAL, …). */
@Composable
fun StatusBadge(text: String, color: Color) {
    Text(text, color = color, style = MaterialTheme.typography.labelMedium,
         modifier = Modifier.background(color.copy(alpha = 0.14f), RoundedCornerShape(6.dp)).padding(horizontal = 8.dp, vertical = 2.dp))
}
