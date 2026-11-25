package id.codingserver.android.data.api

import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/** Kontrak REST yang sama persis dengan backend (/api/v1, lihat docs/API_REFERENCE.md & /openapi.json). */
interface CodingApi {
    // auth
    @POST("api/v1/auth/login") suspend fun login(@Body body: LoginRequest): TokenResponse
    @POST("api/v1/auth/logout") suspend fun logout(@Body body: LogoutRequest): OkResponse
    @GET("api/v1/auth/me") suspend fun me(): UserOut

    // system
    @GET("api/v1/system/health") suspend fun health(): Health
    @GET("api/v1/system/info") suspend fun info(): SystemInfo
    @GET("api/v1/system/resources") suspend fun resources(): Resources
    @GET("api/v1/system/engines") suspend fun engines(@Query("refresh") refresh: Boolean = false): Engines
    @GET("api/v1/system/processes") suspend fun processes(): Processes
    @GET("api/v1/monitor/dashboard") suspend fun dashboard(): Dashboard

    // projects
    @GET("api/v1/projects") suspend fun projects(): List<Project>
    @POST("api/v1/projects") suspend fun createProject(@Body body: ProjectCreate): Project
    @GET("api/v1/projects/templates") suspend fun templates(): Templates
    @GET("api/v1/projects/{id}") suspend fun project(@Path("id") id: String): Project
    @PUT("api/v1/projects/{id}") suspend fun updateProject(@Path("id") id: String, @Body body: ProjectUpdate): Project
    @DELETE("api/v1/projects/{id}") suspend fun deleteProject(@Path("id") id: String): OkResponse

    // files
    @GET("api/v1/files/tree") suspend fun tree(@Query("project_id") projectId: String, @Query("path") path: String = "",
                                               @Query("depth") depth: Int = 1): FileEntry
    @GET("api/v1/files/read") suspend fun read(@Query("project_id") projectId: String, @Query("path") path: String): FileContent
    @POST("api/v1/files/create") suspend fun create(@Body body: FileCreate): FileWritten
    @PUT("api/v1/files/write") suspend fun write(@Body body: FileWrite): FileWritten
    @POST("api/v1/files/rename") suspend fun rename(@Body body: FileRename): FileWritten
    @POST("api/v1/files/copy") suspend fun copy(@Body body: FileMove): FileWritten
    @POST("api/v1/files/move") suspend fun move(@Body body: FileMove): FileWritten
    @DELETE("api/v1/files/delete") suspend fun delete(@Query("project_id") projectId: String, @Query("path") path: String,
                                                      @Query("recursive") recursive: Boolean = false): OkResponse
    @GET("api/v1/files/search") suspend fun search(@Query("project_id") projectId: String, @Query("q") q: String,
                                                   @Query("content") content: Boolean = false): List<FileEntry>
    @GET("api/v1/files/recent") suspend fun recent(): FileList
    @GET("api/v1/files/favorites") suspend fun favorites(): FileList
    @POST("api/v1/files/favorites") suspend fun addFavorite(@Body body: FavoriteRequest): OkResponse
    @GET("api/v1/files/history") suspend fun history(@Query("project_id") projectId: String, @Query("path") path: String? = null): HistoryList
    @POST("api/v1/files/restore") suspend fun restore(@Body body: RestoreRequest): FileWritten

    // execution
    @POST("api/v1/execution/run") suspend fun run(@Body body: RunRequest): Job
    @POST("api/v1/execution/build") suspend fun build(@Body body: RunRequest): Job
    @GET("api/v1/execution") suspend fun executions(@Query("project_id") projectId: String? = null, @Query("limit") limit: Int = 50): JobList
    @GET("api/v1/execution/{pid}") suspend fun job(@Path("pid") pid: String): Job
    @POST("api/v1/execution/{pid}/stop") suspend fun stop(@Path("pid") pid: String): Job
    @POST("api/v1/execution/{pid}/stdin") suspend fun stdin(@Path("pid") pid: String, @Body body: StdinRequest): OkResponse
    @GET("api/v1/execution/artifacts/{project}") suspend fun artifacts(@Path("project") projectId: String): Artifacts
    @POST("api/v1/preview/token") suspend fun previewToken(@Query("project_id") projectId: String, @Query("path") path: String): PreviewToken

    // terminal
    @POST("api/v1/terminal/sessions") suspend fun createTerminal(@Body body: TerminalCreate): TerminalSession
    @GET("api/v1/terminal/sessions") suspend fun terminals(): List<TerminalSession>
    @DELETE("api/v1/terminal/sessions/{sid}") suspend fun closeTerminal(@Path("sid") sid: String): OkResponse

    // database
    @GET("api/v1/database/list") suspend fun databases(@Query("project_id") projectId: String? = null): DbList
    @POST("api/v1/database/create") suspend fun createDatabase(@Body body: DbCreate): DbItem
    @POST("api/v1/database/query") suspend fun query(@Body body: DbQuery): DbQueryResult
    @GET("api/v1/database/schema") suspend fun schema(@Query("database") db: String, @Query("project_id") projectId: String? = null): DbSchema
    @GET("api/v1/database/export") suspend fun exportCsv(@Query("database") db: String, @Query("table") table: String,
                                                         @Query("project_id") projectId: String? = null): ResponseBody

    // git
    @GET("api/v1/git/status") suspend fun gitStatus(@Query("project_id") projectId: String): GitStatus
    @POST("api/v1/git/init") suspend fun gitInit(@Body body: GitProject): GitResult
    @POST("api/v1/git/commit") suspend fun gitCommit(@Body body: GitCommit): GitResult
    @GET("api/v1/git/log") suspend fun gitLog(@Query("project_id") projectId: String, @Query("limit") limit: Int = 50): GitLog
    @GET("api/v1/git/branches") suspend fun gitBranches(@Query("project_id") projectId: String): GitBranches
    @POST("api/v1/git/branch") suspend fun gitBranch(@Body body: GitBranch): GitResult
    @POST("api/v1/git/checkout") suspend fun gitCheckout(@Body body: GitCheckout): GitResult
    @GET("api/v1/git/diff") suspend fun gitDiff(@Query("project_id") projectId: String, @Query("staged") staged: Boolean = false): GitResult
    @POST("api/v1/git/remote") suspend fun gitRemote(@Body body: GitRemoteSet): GitResult
    @POST("api/v1/git/pull") suspend fun gitPull(@Body body: GitRemoteOp): GitResult
    @POST("api/v1/git/push") suspend fun gitPush(@Body body: GitRemoteOp): GitResult
    @POST("api/v1/git/clone") suspend fun gitClone(@Body body: GitClone): GitCloneResult
    @GET("api/v1/git/credentials") suspend fun gitCredentials(): GitCreds
    @POST("api/v1/git/credentials") suspend fun setGitCredential(@Body body: GitCredential): OkResponse

    // http client
    @POST("api/v1/http/request") suspend fun httpRequest(@Body body: HttpRequestIn): HttpResponseOut
    @GET("api/v1/http/collections") suspend fun httpCollections(): HttpCollections
    @POST("api/v1/http/collections") suspend fun saveHttp(@Body body: HttpSaved): HttpSaved
    @DELETE("api/v1/http/collections/{id}") suspend fun deleteHttp(@Path("id") id: Int): OkResponse

    // backup (admin)
    @GET("api/v1/backup") suspend fun backups(): BackupList
    @POST("api/v1/backup") suspend fun createBackup(@Body body: BackupCreate): BackupInfo

    // AI
    @GET("api/v1/ai/status") suspend fun aiStatus(): AIStatus
    @POST("api/v1/ai/chat") suspend fun aiChat(@Body body: AIChat): AIReply
    @GET("api/v1/ai/presets") suspend fun aiPresets(): AIPresets
    @GET("api/v1/ai/connections") suspend fun aiConnections(): AIConnections
    @POST("api/v1/ai/connections") suspend fun aiAddConnection(@Body body: AIConnectionIn): AIConnection
    @PUT("api/v1/ai/connections/{id}") suspend fun aiUpdateConnection(@Path("id") id: String, @Body body: AIConnectionIn): AIConnection
    @DELETE("api/v1/ai/connections/{id}") suspend fun aiDeleteConnection(@Path("id") id: String): OkResponse
    @GET("api/v1/ai/connections/{id}/models") suspend fun aiModels(@Path("id") id: String): AIModels
    @POST("api/v1/ai/apply") suspend fun aiApply(@Body body: AIApply): AIStatus
    @POST("api/v1/ai/unload") suspend fun aiUnload(): AIStatus
    @PUT("api/v1/ai/settings") suspend fun aiSettings(@Body body: AISettings): AIStatus
    @GET("api/v1/ai/agent-models") suspend fun agentModels(): AgentModels
    /** Body JSON mentah: kunci peran yang dikirim null = kosongkan peran (kembali ke model aktif). */
    @PUT("api/v1/ai/agent-models") suspend fun agentModelsUpdate(@Body body: kotlinx.serialization.json.JsonObject): AgentModels
    @GET("api/v1/ai/bench") suspend fun benchOverview(): BenchOverview
    @POST("api/v1/ai/bench") suspend fun benchStart(@Body body: BenchStart): BenchRuns
    @GET("api/v1/ai/bench/{id}") suspend fun benchRun(@Path("id") id: String): BenchRun
    @POST("api/v1/ai/bench/{id}/cancel") suspend fun benchCancel(@Path("id") id: String): BenchRun
    @DELETE("api/v1/ai/bench/{id}") suspend fun benchDelete(@Path("id") id: String): OkResponse
    @GET("api/v1/ai/conversations") suspend fun aiConversations(): AIConversations
    @GET("api/v1/ai/conversations/{id}") suspend fun aiConversation(@Path("id") id: Int): AIConversationDetail
    @PATCH("api/v1/ai/conversations/{id}") suspend fun aiRenameConversation(@Path("id") id: Int, @Body body: AIConversationIn): AIConversationDetail
    @DELETE("api/v1/ai/conversations/{id}") suspend fun aiDeleteConversation(@Path("id") id: Int): OkResponse
    @GET("api/v1/ai/proposals") suspend fun aiProposals(@Query("project_id") projectId: String,
                                                        @Query("conversation_id") conversationId: Int? = null): AIProposalList
    @POST("api/v1/ai/proposals/{id}/decide") suspend fun aiDecide(@Path("id") id: Int, @Body body: AIDecisionIn): AIDecisionResult
    @POST("api/v1/ai/proposals/{id}/revert") suspend fun aiRevert(@Path("id") id: Int, @Body body: AIDecisionIn): AIDecisionResult

    // AI Coding Agent
    @GET("api/v1/agent/tasks") suspend fun agentTasks(@Query("project_id") projectId: String? = null): AgentTaskList
    @POST("api/v1/agent/tasks") suspend fun agentCreate(@Body body: AgentTaskCreate): AgentTask
    @GET("api/v1/agent/tasks/{id}") suspend fun agentTask(@Path("id") id: String): AgentTask
    @GET("api/v1/agent/tasks/{id}/events") suspend fun agentEvents(@Path("id") id: String, @Query("after") after: Int = 0): AgentEvents
    @GET("api/v1/agent/tasks/{id}/proposals") suspend fun agentProposals(@Path("id") id: String): AIProposalList
    @POST("api/v1/agent/tasks/{id}/cancel") suspend fun agentCancel(@Path("id") id: String): AgentTask
    @POST("api/v1/agent/tasks/{id}/pause") suspend fun agentPause(@Path("id") id: String): AgentTask
    @POST("api/v1/agent/tasks/{id}/resume") suspend fun agentResume(@Path("id") id: String): AgentTask
    @DELETE("api/v1/agent/tasks/{id}") suspend fun agentDelete(@Path("id") id: String): OkResponse
}
