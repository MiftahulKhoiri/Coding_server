package id.codingserver.android.data.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import id.codingserver.android.ui.theme.AccentPalette
import id.codingserver.android.ui.theme.AppTheme
import id.codingserver.android.ui.theme.ThemeMode
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.UUID

/** Profil server Raspberry Pi yang disimpan di HP (tanpa token; token ada di [TokenStore]). */
@Serializable
data class ServerProfile(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val baseUrl: String,
    val username: String = "",
)

data class EditorPrefs(
    val darkTheme: Boolean = true,
    val fontSize: Int = 14,
    val wordWrap: Boolean = false,
    val tabSize: Int = 4,
    val textColor: String = "",
    val backgroundColor: String = "",
    /** Language server (clangd/pyright) untuk autocomplete, diagnostik, definisi. */
    val lsp: Boolean = true,
)

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "coding_server")

class ServerStore(private val context: Context) {
    private val json = Json { ignoreUnknownKeys = true }
    private val kServers = stringPreferencesKey("servers")
    private val kActive = stringPreferencesKey("active_server")
    private val kDark = booleanPreferencesKey("editor_dark")
    private val kFont = intPreferencesKey("editor_font")
    private val kWrap = booleanPreferencesKey("editor_wrap")
    private val kTab = intPreferencesKey("editor_tab")
    private val kTextColor = stringPreferencesKey("editor_text_color")
    private val kBackgroundColor = stringPreferencesKey("editor_background_color")
    private val kLsp = booleanPreferencesKey("editor_lsp")
    private val kLastProject = stringPreferencesKey("last_project")
    private val kThemeMode = stringPreferencesKey("app_theme_mode")
    private val kThemeAccent = stringPreferencesKey("app_theme_accent")
    private val kThemeAmoled = booleanPreferencesKey("app_theme_amoled")

    val servers: Flow<List<ServerProfile>> = context.dataStore.data.map { decode(it[kServers]) }
    val activeId: Flow<String?> = context.dataStore.data.map { it[kActive] }
    val lastProject: Flow<String?> = context.dataStore.data.map { it[kLastProject] }
    val editorPrefs: Flow<EditorPrefs> = context.dataStore.data.map {
        EditorPrefs(it[kDark] ?: true, it[kFont] ?: 14, it[kWrap] ?: false, it[kTab] ?: 4, it[kTextColor] ?: "", it[kBackgroundColor] ?: "", it[kLsp] ?: true)
    }

    val appTheme: Flow<AppTheme> = context.dataStore.data.map {
        AppTheme(ThemeMode.fromKey(it[kThemeMode]), AccentPalette.fromKey(it[kThemeAccent]), it[kThemeAmoled] ?: false)
    }

    suspend fun setAppTheme(t: AppTheme) {
        context.dataStore.edit {
            it[kThemeMode] = t.mode.key
            it[kThemeAccent] = t.accent.key
            it[kThemeAmoled] = t.amoled
        }
    }

    private fun decode(raw: String?): List<ServerProfile> =
        raw?.let { runCatching { json.decodeFromString<List<ServerProfile>>(it) }.getOrNull() } ?: emptyList()

    suspend fun upsert(p: ServerProfile) {
        context.dataStore.edit { prefs ->
            val list = decode(prefs[kServers]).filterNot { it.id == p.id } + p
            prefs[kServers] = json.encodeToString(list)
        }
    }

    suspend fun delete(id: String) {
        context.dataStore.edit { prefs ->
            prefs[kServers] = json.encodeToString(decode(prefs[kServers]).filterNot { it.id == id })
            if (prefs[kActive] == id) prefs.remove(kActive)
        }
    }

    suspend fun setActive(id: String?) {
        context.dataStore.edit { if (id == null) it.remove(kActive) else it[kActive] = id }
    }

    suspend fun setLastProject(id: String?) {
        context.dataStore.edit { if (id == null) it.remove(kLastProject) else it[kLastProject] = id }
    }

    suspend fun current(): ServerProfile? {
        val id = activeId.first() ?: return null
        return servers.first().firstOrNull { it.id == id }
    }

    suspend fun setEditorPrefs(p: EditorPrefs) {
        context.dataStore.edit {
            it[kDark] = p.darkTheme
            it[kFont] = p.fontSize
            it[kWrap] = p.wordWrap
            it[kTab] = p.tabSize
            it[kTextColor] = p.textColor
            it[kBackgroundColor] = p.backgroundColor
            it[kLsp] = p.lsp
        }
    }
}
