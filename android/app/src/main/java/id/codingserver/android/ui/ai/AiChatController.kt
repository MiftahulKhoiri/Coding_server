package id.codingserver.android.ui.ai

import id.codingserver.android.data.api.AIConversationSummary
import id.codingserver.android.data.api.AIDecisionIn
import id.codingserver.android.data.api.AIProposalItem
import id.codingserver.android.data.api.AIMessage
import id.codingserver.android.data.api.AiEvent
import id.codingserver.android.data.api.AiRequest
import id.codingserver.android.data.api.AiStream
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.apiCall
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChatMessage(
    val role: String,
    val content: String,
    val reasoning: String = "",
    val model: String = "",
    val streaming: Boolean = false,
    val error: Boolean = false,
    val id: Int = 0,
    /** Editan file yang diusulkan AI dari pesan ini. */
    val edits: List<AIProposalItem> = emptyList(),
)

/** File proyek yang isinya diubah (oleh AI atau dibatalkan) -> tab editor perlu dimuat ulang. */
data class FilesChanged(val projectId: String, val paths: List<String>)

data class ChatUi(
    val conversationId: Int? = null,
    val title: String = "Percakapan baru",
    val messages: List<ChatMessage> = emptyList(),
    val busy: Boolean = false,
    val conversations: List<AIConversationSummary> = emptyList(),
    val draft: String = "",
    val autoApply: Boolean = false,
    /** Proyek tempat percakapan ini mengedit file. */
    val projectId: String? = null,
    /** id proposal yang sedang diproses (tombol dinonaktifkan). */
    val pending: Set<Int> = emptySet(),
)

/** State chat AI yang bertahan saat berpindah layar (dipegang AppViewModel). */
class AiChatController(private val scope: CoroutineScope, private val client: () -> ApiClient?) {
    private val _ui = MutableStateFlow(ChatUi())
    val ui: StateFlow<ChatUi> = _ui.asStateFlow()
    private var stream: AiStream? = null
    private var job: Job? = null
    private val _changed = MutableSharedFlow<FilesChanged>(extraBufferCapacity = 8)
    val changed: SharedFlow<FilesChanged> = _changed

    fun setAutoApply(v: Boolean) = _ui.update { it.copy(autoApply = v) }

    fun setDraft(text: String) = _ui.update { it.copy(draft = text) }

    fun refreshConversations() {
        val c = client() ?: return
        scope.launch { apiCall { c.api.aiConversations() }.onSuccess { r -> _ui.update { it.copy(conversations = r.conversations) } } }
    }

    fun newConversation() {
        if (_ui.value.busy) return
        _ui.update { it.copy(conversationId = null, title = "Percakapan baru", messages = emptyList()) }
    }

    fun open(id: Int, projectId: String?) {
        val c = client() ?: return
        if (_ui.value.busy) return
        scope.launch {
            apiCall { c.api.aiConversation(id) }.onSuccess { d ->
                val edits = if (projectId != null)
                    apiCall { c.api.aiProposals(projectId, d.id) }.getOrNull()?.proposals.orEmpty().groupBy { it.message_id }
                else emptyMap()
                _ui.update {
                    it.copy(conversationId = d.id, title = d.title, projectId = projectId,
                            messages = d.messages.map { m -> m.toUi().copy(edits = edits[m.id].orEmpty().sortedBy { e -> e.id }) })
                }
            }
        }
    }

    fun delete(id: Int, onError: (String) -> Unit) {
        val c = client() ?: return
        scope.launch {
            apiCall { c.api.aiDeleteConversation(id) }.onSuccess {
                if (_ui.value.conversationId == id) newConversation()
                refreshConversations()
            }.onFailure { onError(it.message ?: "Gagal") }
        }
    }

    private fun AIMessage.toUi() = ChatMessage(role, content, reasoning, model, id = id)

    fun send(text: String, projectId: String?, editorText: String?, editorName: String?) {
        val c = client() ?: return
        val content = text.trim()
        if (content.isEmpty() || _ui.value.busy) return
        val shown = if (editorName != null) "$content\n\n📎 $editorName" else content
        _ui.update {
            it.copy(busy = true, draft = "", projectId = projectId ?: it.projectId,
                    messages = it.messages + ChatMessage("user", shown) + ChatMessage("assistant", "", streaming = true))
        }
        val s = AiStream(c)
        stream = s
        job = scope.launch {
            c.ensureFreshToken()
            s.send(AiRequest(content, _ui.value.conversationId, projectId, editorText = editorText, editorName = editorName,
                             autoApply = _ui.value.autoApply && projectId != null))
                .collect { ev -> onEvent(ev) }
            finishStreaming()
            refreshConversations()
        }
    }

    private fun updateLast(f: (ChatMessage) -> ChatMessage) = _ui.update { st ->
        val msgs = st.messages.toMutableList()
        val i = msgs.indexOfLast { it.role == "assistant" }
        if (i >= 0) msgs[i] = f(msgs[i])
        st.copy(messages = msgs)
    }

    private fun onEvent(ev: AiEvent) {
        when (ev) {
            is AiEvent.Conversation -> _ui.update { it.copy(conversationId = ev.id) }
            is AiEvent.Start -> updateLast { it.copy(model = ev.model) }
            is AiEvent.Reasoning -> updateLast { it.copy(reasoning = it.reasoning + ev.text) }
            is AiEvent.Delta -> updateLast { it.copy(content = it.content + ev.text) }
            is AiEvent.Edits -> {
                updateLast { it.copy(id = ev.messageId, edits = ev.items) }
                val applied = ev.items.filter { it.status == "approved" }.map { it.path }
                val pid = _ui.value.projectId
                if (applied.isNotEmpty() && pid != null) _changed.tryEmit(FilesChanged(pid, applied))
            }
            is AiEvent.Done -> { updateLast { it.copy(id = ev.messageId) }; finishStreaming() }
            is AiEvent.Stopped -> updateLast { it.copy(content = it.content + "\n\n[dihentikan]", streaming = false) }
            is AiEvent.Error -> updateLast { it.copy(content = it.content + (if (it.content.isEmpty()) "" else "\n\n") + "⚠ ${ev.message}",
                                                     streaming = false, error = true) }
        }
    }

    private fun finishStreaming() {
        updateLast { it.copy(streaming = false) }
        _ui.update { it.copy(busy = false) }
    }

    private fun replaceEdit(item: AIProposalItem) = _ui.update { st ->
        st.copy(messages = st.messages.map { m -> if (m.edits.any { it.id == item.id }) m.copy(edits = m.edits.map { if (it.id == item.id) item else it }) else m })
    }

    /** approve=true terapkan, false tolak. */
    fun decide(item: AIProposalItem, approve: Boolean, onError: (String) -> Unit) =
        act(item, onError) { c, pid -> c.api.aiDecide(item.id, AIDecisionIn(pid, approve)) }

    fun revert(item: AIProposalItem, onError: (String) -> Unit) =
        act(item, onError) { c, pid -> c.api.aiRevert(item.id, AIDecisionIn(pid)) }

    private fun act(item: AIProposalItem, onError: (String) -> Unit,
                    call: suspend (id.codingserver.android.data.api.ApiClient, String) -> id.codingserver.android.data.api.AIDecisionResult) {
        val c = client() ?: return
        val pid = _ui.value.projectId ?: run { onError("Buka proyeknya dulu"); return }
        _ui.update { it.copy(pending = it.pending + item.id) }
        scope.launch {
            apiCall { call(c, pid) }.onSuccess { r ->
                val updated = r.proposal ?: item.copy(status = r.status)
                replaceEdit(updated)
                if (r.status == "approved" || r.status == "reverted") _changed.tryEmit(FilesChanged(pid, listOf(item.path)))
            }.onFailure { onError(it.message ?: "Gagal") }
            _ui.update { it.copy(pending = it.pending - item.id) }
        }
    }

    fun stop() {
        stream?.stop()
    }
}
