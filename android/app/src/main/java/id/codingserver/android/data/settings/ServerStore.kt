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
import id.codingserver.android.ui.theme.BackgroundTone
import id.codingserver.android.ui.theme.AppTheme
import id.codingserver.android.ui.theme.ThemeMode
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
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
    /** Baris tombol ekstra di atas keyboard (Tab, kurung, panah, komentar, …). */
    val keyBar: Boolean = true,
    /** Simpan otomatis ±2 detik setelah berhenti mengetik. */
    val autoSave: Boolean = true,
    /** Ketuk kode = keyboard muncul. Mati: keyboard hanya lewat tombol ⌨ (membaca kode tanpa gangguan). */
    val tapKeyboard: Boolean = true,
    /** Jenis huruf (id di EditorFonts: jetbrains, fira, sourcecode, ubuntu, roboto, plex, system). */
    val fontFamily: String = "jetbrains",
)

/** Pengaturan tampilan terminal (disesuaikan manual seperti terminal pada umumnya). */
data class TerminalPrefs(
    val fontSize: Int = 13,
    val theme: String = "dark",          // dark | light | solarized | monokai | retro
    val cursorStyle: String = "block",   // block | bar | underline
    val cursorBlink: Boolean = true,
    val lineHeight: Float = 1.0f,
    val showKeys: Boolean = true,        // baris tombol khusus (ESC, TAB, ^C …)
    val tapKeyboard: Boolean = true,     // ketuk terminal -> keyboard muncul
    val extraKeys: Boolean = false,      // baris tombol tambahan (^A ^E ^R ^U ^W PGUP PGDN)
    val fontFamily: String = "jetbrains", // jenis huruf (lihat EditorFonts)
)

/** Jenis huruf monospace yang dibundel di aplikasi (aset web/fonts, lisensi SIL OFL). id -> nama tampilan. */
val EditorFonts = linkedMapOf(
    "jetbrains" to "JetBrains Mono", "fira" to "Fira Code", "sourcecode" to "Source Code Pro",
    "ubuntu" to "Ubuntu Mono", "roboto" to "Roboto Mono", "plex" to "IBM Plex Mono", "system" to "Bawaan sistem",
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
    private val kKeyBar = booleanPreferencesKey("editor_key_bar")
    private val kAutoSave = booleanPreferencesKey("editor_auto_save")
    private val kTapKb = booleanPreferencesKey("editor_tap_keyboard")
    private val kOpenTabs = androidx.datastore.preferences.core.stringPreferencesKey("editor_open_tabs")
    private val kLastProject = stringPreferencesKey("last_project")
    private val kThemeMode = stringPreferencesKey("app_theme_mode")
    private val kThemeAccent = stringPreferencesKey("app_theme_accent")
    private val kThemeAmoled = booleanPreferencesKey("app_theme_amoled")
    private val kThemeBg = stringPreferencesKey("app_theme_background")
    private val kThemeFont = stringPreferencesKey("app_theme_font")
    private val kThemeScale = stringPreferencesKey("app_text_scale")
    private val kTermFont = intPreferencesKey("term_font")
    private val kTermTheme = stringPreferencesKey("term_theme")
    private val kTermCursor = stringPreferencesKey("term_cursor")
    private val kTermBlink = booleanPreferencesKey("term_blink")
    private val kTermLine = stringPreferencesKey("term_line_height")
    private val kTermKeys = booleanPreferencesKey("term_keys")
    private val kTermTap = booleanPreferencesKey("term_tap_keyboard")
    private val kTermExtra = booleanPreferencesKey("term_extra_keys")
    private val kTermFamily = stringPreferencesKey("term_font_family")
    private val kEdFamily = stringPreferencesKey("editor_font_family")

    val terminalPrefs: Flow<TerminalPrefs> = context.dataStore.data.map {
        TerminalPrefs(it[kTermFont] ?: 13, it[kTermTheme] ?: "dark", it[kTermCursor] ?: "block", it[kTermBlink] ?: true,
                      it[kTermLine]?.toFloatOrNull() ?: 1.0f, it[kTermKeys] ?: true, it[kTermTap] ?: true, it[kTermExtra] ?: false,
                      it[kTermFamily] ?: "jetbrains")
    }

    suspend fun setTerminalPrefs(p: TerminalPrefs) {
        context.dataStore.edit {
            it[kTermFont] = p.fontSize
            it[kTermTheme] = p.theme
            it[kTermCursor] = p.cursorStyle
            it[kTermBlink] = p.cursorBlink
            it[kTermLine] = p.lineHeight.toString()
            it[kTermKeys] = p.showKeys
            it[kTermTap] = p.tapKeyboard
            it[kTermExtra] = p.extraKeys
            it[kTermFamily] = p.fontFamily
        }
    }

    val servers: Flow<List<ServerProfile>> = context.dataStore.data.map { decode(it[kServers]) }
    val activeId: Flow<String?> = context.dataStore.data.map { it[kActive] }
    val lastProject: Flow<String?> = context.dataStore.data.map { it[kLastProject] }
    val editorPrefs: Flow<EditorPrefs> = context.dataStore.data.map {
        EditorPrefs(it[kDark] ?: true, it[kFont] ?: 14, it[kWrap] ?: false, it[kTab] ?: 4, it[kTextColor] ?: "", it[kBackgroundColor] ?: "", it[kLsp] ?: true,
                    it[kKeyBar] ?: true, it[kAutoSave] ?: true, it[kTapKb] ?: true, it[kEdFamily] ?: "jetbrains")
    }

    val appTheme: Flow<AppTheme> = context.dataStore.data.map {
        AppTheme(ThemeMode.fromKey(it[kThemeMode]), AccentPalette.fromKey(it[kThemeAccent]), it[kThemeAmoled] ?: false,
                 BackgroundTone.fromKey(it[kThemeBg]), it[kThemeFont] ?: "default", it[kThemeScale]?.toFloatOrNull() ?: 1.0f)
    }

    suspend fun setAppTheme(t: AppTheme) {
        context.dataStore.edit {
            it[kThemeMode] = t.mode.key
            it[kThemeAccent] = t.accent.key
            it[kThemeAmoled] = t.amoled
            it[kThemeBg] = t.background.key
            it[kThemeFont] = t.font
            it[kThemeScale] = t.textScale.toString()
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
            it[kKeyBar] = p.keyBar
            it[kAutoSave] = p.autoSave
            it[kTapKb] = p.tapKeyboard
            it[kEdFamily] = p.fontFamily
        }
    }

    /** Tab editor yang terbuka per server (dipulihkan saat aplikasi dibuka lagi). Format JSON {serverId: {tabs, active}}. */
    suspend fun openTabs(serverId: String): Pair<List<String>, String?> {
        val raw = context.dataStore.data.first()[kOpenTabs] ?: return emptyList<String>() to null
        return runCatching {
            val o = kotlinx.serialization.json.Json.parseToJsonElement(raw).jsonObject[serverId]?.jsonObject
                ?: return emptyList<String>() to null
            val tabs = o["tabs"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty()
            tabs to o["active"]?.jsonPrimitive?.contentOrNull
        }.getOrDefault(emptyList<String>() to null)
    }

    suspend fun setOpenTabs(serverId: String, tabs: List<String>, active: String?) {
        context.dataStore.edit { prefs ->
            val all = runCatching { kotlinx.serialization.json.Json.parseToJsonElement(prefs[kOpenTabs] ?: "{}").jsonObject }
                .getOrDefault(kotlinx.serialization.json.JsonObject(emptyMap())).toMutableMap()
            all[serverId] = kotlinx.serialization.json.buildJsonObject {
                put("tabs", kotlinx.serialization.json.JsonArray(tabs.map { kotlinx.serialization.json.JsonPrimitive(it) }))
                put("active", kotlinx.serialization.json.JsonPrimitive(active))
            }
            prefs[kOpenTabs] = kotlinx.serialization.json.JsonObject(all).toString()
        }
    }
}
