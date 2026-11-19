package id.codingserver.android.data.api

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

sealed interface JobEvent {
    data class Status(val status: String) : JobEvent
    data class Output(val stream: String, val text: String) : JobEvent
    data class Phase(val phase: String, val argv: String) : JobEvent
    data class End(val job: Job) : JobEvent
    data class Error(val message: String) : JobEvent
}

/** Stream output eksekusi real-time lewat WebSocket /ws/execution/{id}. */
class JobStream(private val client: ApiClient) {
    private var socket: WebSocket? = null

    fun events(processId: String): Flow<JobEvent> = callbackFlow {
        val req = Request.Builder().url(client.wsUrl("ws/execution/$processId")).build()
        val ws = client.http.newWebSocket(req, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val obj: JsonObject = runCatching { ApiJson.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
                val type = obj["type"]?.jsonPrimitive?.contentOrNull
                val ev: JobEvent? = when (type) {
                    "status" -> JobEvent.Status(obj["status"]?.jsonPrimitive?.contentOrNull ?: "")
                    "stdout", "stderr" -> JobEvent.Output(type, obj["data"]?.jsonPrimitive?.contentOrNull ?: "")
                    "phase" -> JobEvent.Phase(obj["phase"]?.jsonPrimitive?.contentOrNull ?: "", obj["argv"]?.toString() ?: "")
                    "end" -> obj["job"]?.let { JobEvent.End(ApiJson.decodeFromJsonElement(Job.serializer(), it)) }
                    "error" -> JobEvent.Error(obj["message"]?.jsonPrimitive?.contentOrNull ?: "error")
                    else -> null
                }
                if (ev != null) trySend(ev)
                if (ev is JobEvent.End) close()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                trySend(JobEvent.Error(t.message ?: "Koneksi stream terputus"))
                close()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                close()
            }
        })
        socket = ws
        awaitClose { ws.close(1000, null) }
    }

    fun sendStdin(text: String, eof: Boolean = false) {
        val payload = buildString {
            append("{\"type\":\"stdin\",\"data\":")
            append(ApiJson.encodeToString(kotlinx.serialization.serializer<String>(), text))
            append(",\"eof\":").append(eof).append("}")
        }
        socket?.send(payload)
    }

    fun stop() {
        socket?.send("{\"type\":\"stop\"}")
    }
}
