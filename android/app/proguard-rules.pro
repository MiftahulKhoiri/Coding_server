-keepattributes *Annotation*, InnerClasses, Signature, Exceptions
-dontnote kotlinx.serialization.**
-keepclassmembers @kotlinx.serialization.Serializable class ** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class id.codingserver.android.**$$serializer { *; }
-keepclassmembers class id.codingserver.android.** {
    *** Companion;
}
# Retrofit: interface API dipakai lewat refleksi.
-keep,allowobfuscation interface id.codingserver.android.data.api.CodingApi
-keep,allowobfuscation,allowshrinking class kotlin.coroutines.Continuation
-keep,allowobfuscation,allowshrinking class retrofit2.Response
# Jembatan JavaScript WebView
-keepclassmembers class id.codingserver.android.ui.editor.EditorBridge { @android.webkit.JavascriptInterface <methods>; }
-keepclassmembers class id.codingserver.android.ui.terminal.TerminalBridge { @android.webkit.JavascriptInterface <methods>; }
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
