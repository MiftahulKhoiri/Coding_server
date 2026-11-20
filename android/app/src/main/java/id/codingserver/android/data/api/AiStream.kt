package id.codingserver.android.data.api

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

sealed interface AiEvent {
    data class Conversation(val id: Int) : AiEvent
    data class Start(val model: String, val connection: String) : AiEvent
    data class Reasoning(val text: String) : AiEvent
    data class Delta(val text: String) : AiEvent
    data class Done(val messageId: Int, val seconds: Double) : AiEvent
    data class Error(val code: String, val message: String) : AiEvent
    data object Stopped : AiEvent
}

data class AiRequest(
    val content: String,
    val conversationId: Int? = null,
    val projectId: String? = null,
    val files: List<String> = emptyList(),
    val editorText: String? = null,
    val editorName: String? = null,
)

/** Chat AI streaming lewat WebSocket /ws/ai/chat (satu koneksi per pertanyaan). */
class AiStream(private val client: ApiClient) {
    private var socket: WebSocket? = null

    fun send(req: AiRequest): Flow<AiEvent> = callbackFlow {
        val ws = client.http.newWebSocket(Request.Builder().url(client.wsUrl("ws/ai/chat")).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val payload = buildJsonObject {
                    put("type", "send")
                    put("content", req.content)
                    req.conversationId?.let { put("conversation_id", it) }
                    req.projectId?.let { put("project_id", it) }
                    if (req.files.isNotEmpty()) put("files", kotlinx.serialization.json.JsonArray(req.files.map { JsonPrimitive(it) }))
                    req.editorText?.let { put("editor_text", it) }
                    req.editorName?.let { put("editor_name", it) }
                }
                webSocket.send(payload.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val o: JsonObject = runCatching { ApiJson.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
                fun str(k: String) = o[k]?.jsonPrimitive?.contentOrNull ?: ""
                val ev: AiEvent? = when (str("type")) {
                    "conversation" -> AiEvent.Conversation(o["id"]?.jsonPrimitive?.intOrNull ?: 0)
                    "start" -> AiEvent.Start(str("model"), str("connection"))
                    "reasoning" -> AiEvent.Reasoning(str("text"))
                    "delta" -> AiEvent.Delta(str("text"))
                    "done" -> AiEvent.Done(o["message_id"]?.jsonPrimitive?.intOrNull ?: 0, o["seconds"]?.jsonPrimitive?.doubleOrNull ?: 0.0)
                    "error" -> AiEvent.Error(str("code"), str("message"))
                    "stopped" -> AiEvent.Stopped
                    else -> null
                }
                if (ev != null) trySend(ev)
                if (ev is AiEvent.Done || ev is AiEvent.Error || ev is AiEvent.Stopped) {
                    webSocket.close(1000, null)
                    close()
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                trySend(AiEvent.Error("network", t.message ?: "Koneksi ke server terputus"))
                close()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { close() }
        })
        socket = ws
        awaitClose { ws.close(1000, null) }
    }

    fun stop() { socket?.send("""{"type":"stop"}""") }
}
