package id.codingserver.android

import id.codingserver.android.data.api.ApiJson
import id.codingserver.android.data.api.CodingApi
import id.codingserver.android.data.api.DbCreate
import id.codingserver.android.data.api.DbQuery
import id.codingserver.android.data.api.FileCreate
import id.codingserver.android.data.api.FileWrite
import id.codingserver.android.data.api.GitCommit
import id.codingserver.android.data.api.GitProject
import id.codingserver.android.data.api.HttpSaved
import id.codingserver.android.data.api.LoginRequest
import id.codingserver.android.data.api.ProjectCreate
import id.codingserver.android.data.api.RunRequest
import id.codingserver.android.data.api.TerminalCreate
import id.codingserver.android.data.api.normalizeBaseUrl
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * Uji kontrak API Android <-> backend ASLI. Hanya berjalan bila CS_SERVER_URL & CS_ADMIN_PASSWORD diisi
 * (CI menjalankan backend sungguhan; di Pi: CS_SERVER_URL=http://127.0.0.1:8800).
 * Memastikan semua DTO Kotlin bisa membaca respons server yang sebenarnya.
 */
class BackendIntegrationTest {
    private val url = System.getenv("CS_SERVER_URL").orEmpty()
    private val password = System.getenv("CS_ADMIN_PASSWORD").orEmpty()

    private fun api(token: String? = null): CodingApi {
        val http = OkHttpClient.Builder().addInterceptor { ch ->
            val r = if (token != null) ch.request().newBuilder().header("Authorization", "Bearer $token").build() else ch.request()
            ch.proceed(r)
        }.build()
        return Retrofit.Builder().baseUrl(normalizeBaseUrl(url)).client(http)
            .addConverterFactory(ApiJson.asConverterFactory("application/json".toMediaType())).build()
            .create(CodingApi::class.java)
    }

    @Test fun fullFlow() = runBlocking {
        assumeTrue("CS_SERVER_URL tidak diisi", url.isNotBlank() && password.isNotBlank())
        assertEquals("ok", api().health().status)
        val tok = api().login(LoginRequest("admin", password))
        val a = api(tok.access_token)
        assertEquals("admin", a.me().username)
        assertTrue(a.engines().engines.any { it.engine_id == "python" && it.status == "AVAILABLE" })
        a.dashboard(); a.resources(); a.info()

        val p = a.createProject(ProjectCreate("android-it", language = "python"))
        try {
            val tree = a.tree(p.id)
            assertTrue(tree.children!!.any { it.name == "main.py" })
            val f = a.read(p.id, "main.py")
            a.write(FileWrite(p.id, "main.py", "print('dari android', 6*7)\n", f.sha256))
            a.create(FileCreate(p.id, "lib", "folder"))
            assertTrue(a.search(p.id, "android", content = true).isNotEmpty())

            var job = a.run(RunRequest(p.id, "main.py"))
            repeat(120) { if (!job.finished) { delay(250); job = a.job(job.process_id) } }
            assertEquals("COMPLETED", job.status)
            assertTrue(job.stdout!!.contains("dari android 42"))
            assertTrue(a.executions(p.id).executions.isNotEmpty())

            val t = a.createTerminal(TerminalCreate(p.id))
            assertTrue(a.terminals().any { it.session_id == t.session_id })
            a.closeTerminal(t.session_id)

            a.createDatabase(DbCreate("data.db", p.id))
            a.query(DbQuery("data.db", p.id, "CREATE TABLE t(x); INSERT INTO t VALUES (1),(2);", "write"))
            val q = a.query(DbQuery("data.db", p.id, "SELECT x FROM t"))
            assertEquals(2, q.results[0].rows!!.size)
            assertTrue(a.schema("data.db", p.id).objects.any { it.name == "t" })

            assertTrue(a.gitInit(GitProject(p.id)).ok)
            assertTrue(a.gitCommit(GitCommit(p.id, "awal", true)).ok)
            assertEquals("awal", a.gitLog(p.id).commits.first().message)
            a.gitStatus(p.id); a.gitBranches(p.id)

            a.saveHttp(HttpSaved(name = "it", url = "https://example.com"))
            assertTrue(a.httpCollections().collections.isNotEmpty())
            a.aiStatus(); a.backups(); a.recent(); a.history(p.id)
        } finally {
            a.deleteProject(p.id)
        }
    }
}
