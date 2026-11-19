package id.codingserver.android

import android.app.Application
import id.codingserver.android.data.settings.ServerStore
import id.codingserver.android.data.settings.TokenStore

class CodingServerApp : Application() {
    lateinit var servers: ServerStore
        private set
    lateinit var tokens: TokenStore
        private set

    override fun onCreate() {
        super.onCreate()
        servers = ServerStore(this)
        tokens = TokenStore(this)
    }
}
