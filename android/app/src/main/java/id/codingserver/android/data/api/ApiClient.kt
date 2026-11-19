package id.codingserver.android.data.api

import id.codingserver.android.data.settings.ServerProfile
import id.codingserver.android.data.settings.TokenStore
import id.codingserver.android.data.settings.Tokens
import kotlinx.serialization.json.Json
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

val ApiJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    encodeDefaults = true
}

class ApiException(val code: String, override val message: String, val status: Int = 0) : Exception(message)

/** Normalisasi URL server: tambah http:// dan port bawaan bila perlu. */
fun normalizeBaseUrl(input: String): String {
    var u = input.trim().trimEnd('/')
    if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://$u"
    val hostPart = u.substringAfter("://").substringBefore('/')
    if (!hostPart.contains(':') && u.startsWith("http://")) u = u.replaceFirst(hostPart, "$hostPart:8800")
    return "$u/"
}

/** Ubah exception apa pun menjadi pesan yang bisa ditampilkan ke pengguna. */
fun Throwable.toApiException(): ApiException = when (this) {
    is ApiException -> this
    is HttpException -> {
        val raw = runCatching { response()?.errorBody()?.string() }.getOrNull()
        val body = raw?.let { runCatching { ApiJson.decodeFromString<ErrorResponse>(it).error }.getOrNull() }
        ApiException(body?.code ?: "http_${code()}", body?.message ?: "Server menjawab ${code()}", code())
    }
    is java.net.ConnectException, is java.net.UnknownHostException, is java.net.NoRouteToHostException ->
        ApiException("offline", "Server tidak bisa dihubungi (offline?)")
    is java.net.SocketTimeoutException -> ApiException("timeout", "Server tidak menjawab (timeout)")
    is IOException -> ApiException("network", "Gangguan jaringan: ${message ?: javaClass.simpleName}")
    else -> ApiException("error", message ?: javaClass.simpleName)
}

suspend fun <T> apiCall(block: suspend () -> T): Result<T> =
    try {
        Result.success(block())
    } catch (e: kotlinx.coroutines.CancellationException) {
        throw e
    } catch (e: Throwable) {
        Result.failure(e.toApiException())
    }

/**
 * Klien untuk satu server. Menyisipkan token Bearer, dan bila token kedaluwarsa (401)
 * otomatis memakai refresh token (rotasi) lalu mengulang request sekali.
 */
class ApiClient(
    val server: ServerProfile,
    private val tokens: TokenStore,
    private val onSessionExpired: () -> Unit,
) {
    val baseUrl: String = normalizeBaseUrl(server.baseUrl)

    private val plain: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val authInterceptor = Interceptor { chain ->
        val t = tokens.get(server.id)
        val req = if (t != null && chain.request().header("Authorization") == null) {
            chain.request().newBuilder().header("Authorization", "Bearer ${t.access}").build()
        } else chain.request()
        chain.proceed(req)
    }

    private val refresher = object : Authenticator {
        override fun authenticate(route: Route?, response: Response): Request? {
            if (response.request.url.encodedPath.contains("/auth/")) return null
            if (responseCount(response) >= 2) return null
            val current = tokens.get(server.id) ?: return null
            synchronized(this) {
                val latest = tokens.get(server.id)
                // Token sudah diperbarui oleh thread lain.
                if (latest != null && latest.access != current.access) {
                    return response.request.newBuilder().header("Authorization", "Bearer ${latest.access}").build()
                }
                val refreshed = refresh(current.refresh)
                if (refreshed == null) {
                    tokens.clear(server.id)
                    onSessionExpired()
                    return null
                }
                tokens.put(server.id, refreshed)
                return response.request.newBuilder().header("Authorization", "Bearer ${refreshed.access}").build()
            }
        }
    }

    private fun responseCount(r: Response): Int {
        var n = 1
        var p = r.priorResponse
        while (p != null) { n++; p = p.priorResponse }
        return n
    }

    private fun refresh(refreshToken: String): Tokens? = try {
        val body = ApiJson.encodeToString(RefreshRequest.serializer(), RefreshRequest(refreshToken))
            .toRequestBody("application/json".toMediaType())
        plain.newCall(Request.Builder().url(baseUrl + "api/v1/auth/refresh").post(body).build()).execute().use { r ->
            if (!r.isSuccessful) null else {
                val tr = ApiJson.decodeFromString(TokenResponse.serializer(), r.body!!.string())
                Tokens(tr.access_token, tr.refresh_token, tr.expires_at)
            }
        }
    } catch (e: Exception) {
        null
    }

    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(330, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .addInterceptor(authInterceptor)
        .authenticator(refresher)
        .build()

    val api: CodingApi = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(http)
        .addConverterFactory(ApiJson.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(CodingApi::class.java)

    fun accessToken(): String? = tokens.get(server.id)?.access

    /** URL WebSocket (ws:// atau wss://) dengan token sebagai query (WebView tidak bisa set header). */
    fun wsUrl(path: String): String {
        val base = baseUrl.replaceFirst("http://", "ws://").replaceFirst("https://", "wss://")
        return base + path.trimStart('/') + "?token=" + (accessToken() ?: "")
    }

    /** Pastikan access token masih berlaku sebelum membuka WebSocket (WS tidak lewat Authenticator). */
    suspend fun ensureFreshToken() {
        val t = tokens.get(server.id) ?: return
        if (t.accessExpiresAt - System.currentTimeMillis() / 1000 > 120) return
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            refresh(t.refresh)?.let { tokens.put(server.id, it) }
        }
    }

    suspend fun login(username: String, password: String): TokenResponse {
        val res = api.login(LoginRequest(username, password))
        tokens.put(server.id, Tokens(res.access_token, res.refresh_token, res.expires_at))
        return res
    }

    suspend fun logout() {
        val t = tokens.get(server.id)
        runCatching { api.logout(LogoutRequest(t?.refresh)) }
        tokens.clear(server.id)
    }

    /** Uji koneksi tanpa autentikasi. */
    suspend fun health(): Health = api.health()
}
