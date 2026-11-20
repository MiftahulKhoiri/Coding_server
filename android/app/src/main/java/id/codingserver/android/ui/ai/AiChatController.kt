package id.codingserver.android.ui.ai

import id.codingserver.android.data.api.AIConversationSummary
import id.codingserver.android.data.api.AIMessage
import id.codingserver.android.data.api.AiEvent
import id.codingserver.android.data.api.AiRequest
import id.codingserver.android.data.api.AiStream
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.apiCall
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
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
)

data class ChatUi(
    val conversationId: Int? = null,
    val title: String = "Percakapan baru",
    val messages: List<ChatMessage> = emptyList(),
    val busy: Boolean = false,
    val conversations: List<AIConversationSummary> = emptyList(),
    val draft: String = "",
)

/** State chat AI yang bertahan saat berpindah layar (dipegang AppViewModel). */
class AiChatController(private val scope: CoroutineScope, private val client: () -> ApiClient?) {
    private val _ui = MutableStateFlow(ChatUi())
    val ui: StateFlow<ChatUi> = _ui.asStateFlow()
    private var stream: AiStream? = null
    private var job: Job? = null

    fun setDraft(text: String) = _ui.update { it.copy(draft = text) }

    fun refreshConversations() {
        val c = client() ?: return
        scope.launch { apiCall { c.api.aiConversations() }.onSuccess { r -> _ui.update { it.copy(conversations = r.conversations) } } }
    }

    fun newConversation() {
        if (_ui.value.busy) return
        _ui.update { it.copy(conversationId = null, title = "Percakapan baru", messages = emptyList()) }
    }

    fun open(id: Int) {
        val c = client() ?: return
        if (_ui.value.busy) return
        scope.launch {
            apiCall { c.api.aiConversation(id) }.onSuccess { d ->
                _ui.update { it.copy(conversationId = d.id, title = d.title, messages = d.messages.map { m -> m.toUi() }) }
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

    private fun AIMessage.toUi() = ChatMessage(role, content, reasoning, model)

    fun send(text: String, projectId: String?, editorText: String?, editorName: String?) {
        val c = client() ?: return
        val content = text.trim()
        if (content.isEmpty() || _ui.value.busy) return
        val shown = if (editorName != null) "$content\n\n📎 $editorName" else content
        _ui.update {
            it.copy(busy = true, draft = "",
                    messages = it.messages + ChatMessage("user", shown) + ChatMessage("assistant", "", streaming = true))
        }
        val s = AiStream(c)
        stream = s
        job = scope.launch {
            c.ensureFreshToken()
            s.send(AiRequest(content, _ui.value.conversationId, projectId, editorText = editorText, editorName = editorName))
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
            is AiEvent.Done -> finishStreaming()
            is AiEvent.Stopped -> updateLast { it.copy(content = it.content + "\n\n[dihentikan]", streaming = false) }
            is AiEvent.Error -> updateLast { it.copy(content = it.content + (if (it.content.isEmpty()) "" else "\n\n") + "⚠ ${ev.message}",
                                                     streaming = false, error = true) }
        }
    }

    private fun finishStreaming() {
        updateLast { it.copy(streaming = false) }
        _ui.update { it.copy(busy = false) }
    }

    fun stop() {
        stream?.stop()
    }
}
