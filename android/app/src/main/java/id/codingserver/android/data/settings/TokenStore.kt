package id.codingserver.android.data.settings

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

data class Tokens(val access: String, val refresh: String, val accessExpiresAt: Long)

/**
 * Token disimpan terenkripsi (AES-256-GCM) dengan kunci di Android Keystore.
 * Tidak pernah disimpan plaintext.
 */
class TokenStore(context: Context) {
    private val prefs: SharedPreferences = run {
        val key = MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            context, "cs_tokens", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    @Synchronized
    fun get(serverId: String): Tokens? {
        val a = prefs.getString("$serverId.access", null) ?: return null
        val r = prefs.getString("$serverId.refresh", null) ?: return null
        return Tokens(a, r, prefs.getLong("$serverId.exp", 0))
    }

    @Synchronized
    fun put(serverId: String, t: Tokens) {
        prefs.edit()
            .putString("$serverId.access", t.access)
            .putString("$serverId.refresh", t.refresh)
            .putLong("$serverId.exp", t.accessExpiresAt)
            .apply()
    }

    @Synchronized
    fun clear(serverId: String) {
        prefs.edit().remove("$serverId.access").remove("$serverId.refresh").remove("$serverId.exp").apply()
    }
}
