package com.example.safetyroad

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Message
import android.view.View
import android.view.WindowManager
import android.webkit.GeolocationPermissions
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

class MainActivity : ComponentActivity() {

    private lateinit var webView: WebView

    private val locationPermissionRequestCode = 1001

    private val sexOffenderPackage = "com.mogef_android1.app"
    private val sexOffenderStoreUrl = "https://play.google.com/store/apps/details?id=com.mogef_android1.app"

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WindowCompat.setDecorFitsSystemWindows(window, false)

        window.setSoftInputMode(
            WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING
        )

        window.statusBarColor = Color.WHITE
        window.navigationBarColor = Color.WHITE

        val controller = WindowInsetsControllerCompat(window, window.decorView)
        controller.isAppearanceLightStatusBars = true
        controller.isAppearanceLightNavigationBars = true

        requestLocationPermission()

        val root = FrameLayout(this)
        webView = WebView(this)

        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)

        root.addView(
            webView,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(
                systemBars.left,
                systemBars.top,
                systemBars.right,
                systemBars.bottom
            )
            insets
        }

        setContentView(root)

        val settings = webView.settings

        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.setGeolocationEnabled(true)
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        settings.useWideViewPort = false
        settings.loadWithOverviewMode = false
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.javaScriptCanOpenWindowsAutomatically = true
        settings.setSupportMultipleWindows(true)
        settings.setSupportZoom(false)
        settings.userAgentString = "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

        webView.isFocusable = true
        webView.isFocusableInTouchMode = true
        webView.requestFocus()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (!::webView.isInitialized) {
                    showExitDialog()
                    return
                }

                webView.evaluateJavascript(
                    """
                    (function() {
                        try {
                            if (typeof window.safeBack === 'function') {
                                var handled = window.safeBack();
                                return handled ? handled.toString() : "not_handled";
                            }
                            return "not_handled";
                        } catch(e) {
                            return "not_handled";
                        }
                    })();
                    """.trimIndent()
                ) { result ->
                    runOnUiThread {
                        when {
                            result != null && result.contains("exit") -> showExitDialog()
                            result != null && result.contains("handled") -> { /* JS가 처리함 */ }
                            webView.canGoBack() -> webView.goBack()
                            else -> showExitDialog()
                        }
                    }
                }
            }
        })

        webView.webChromeClient = object : WebChromeClient() {

            override fun onGeolocationPermissionsShowPrompt(
                origin: String?,
                callback: GeolocationPermissions.Callback?
            ) {
                callback?.invoke(origin, true, false)
            }

            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: Message?
            ): Boolean {
                val newWebView = WebView(this@MainActivity)
                newWebView.settings.javaScriptEnabled = true
                newWebView.settings.domStorageEnabled = true
                newWebView.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(
                        view: WebView?,
                        request: WebResourceRequest?
                    ): Boolean {
                        val url = request?.url.toString()
                        handleExternalUrl(url)
                        return true
                    }
                }
                val transport = resultMsg?.obj as WebView.WebViewTransport
                transport.webView = newWebView
                resultMsg.sendToTarget()
                return true
            }
        }

        webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean {
                val url = request?.url.toString()

                if (url.contains("/stats_excel")) {
                    openExternal(url)
                    return true
                }

                return if (
                    url.startsWith("intent://") ||
                    url.startsWith("kakaomap://") ||
                    url.startsWith("nmap://") ||
                    url.startsWith("tmap://") ||
                    url.startsWith("kakaonavi://") ||
                    url.startsWith("market://") ||
                    url.contains("sexoffender", ignoreCase = true) ||
                    url.contains("sexoffender.go.kr", ignoreCase = true) ||
                    url.contains("성범죄자", ignoreCase = true)
                ) {
                    handleExternalUrl(url)
                    true
                } else {
                    false
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)

                webView.evaluateJavascript(
                    """
                    (function() {
                        var targets = document.querySelectorAll('a, button');
                        targets.forEach(function(el) {
                            var text = (el.innerText || el.textContent || '').trim();
                            var href = el.getAttribute('href') || '';
                            if (
                                text.includes('안전로드 다운로드') ||
                                text.includes('앱 다운로드') ||
                                href.includes('.apk') ||
                                href.includes('download-apk')
                            ) {
                                el.style.display = 'none';
                            }
                        });

                        var inputs = document.querySelectorAll('input, textarea');
                        inputs.forEach(function(input) {
                            input.removeAttribute('readonly');
                            input.removeAttribute('disabled');
                            input.readOnly = false;
                            input.disabled = false;
                            input.style.pointerEvents = 'auto';
                            input.style.userSelect = 'text';
                            input.style.webkitUserSelect = 'text';
                        });

                        document.addEventListener('focusin', function(e) {
                            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                                e.target.removeAttribute('readonly');
                                e.target.removeAttribute('disabled');
                                e.target.readOnly = false;
                                e.target.disabled = false;
                                e.target.style.pointerEvents = 'auto';
                                e.target.style.userSelect = 'text';
                                e.target.style.webkitUserSelect = 'text';
                            }
                        }, true);
                    })();
                    """.trimIndent(),
                    null
                )
            }
        }

        webView.loadUrl("https://risk-m225.onrender.com/?from_app=1")
    }

    private fun showExitDialog() {
        AlertDialog.Builder(this)
            .setMessage("앱을 종료하시겠습니까?")
            .setPositiveButton("종료") { _, _ -> finishAffinity() }
            .setNegativeButton("취소", null)
            .show()
    }

    private fun handleExternalUrl(url: String) {
        try {
            if (
                url.contains("sexoffender", ignoreCase = true) ||
                url.contains("sexoffender.go.kr", ignoreCase = true) ||
                url.contains("성범죄자", ignoreCase = true)
            ) {
                openSexOffenderAppOrStore()
                return
            }

            if (url.startsWith("intent://")) {
                val intent = Intent.parseUri(url, Intent.URI_INTENT_SCHEME)
                startActivity(intent)
                return
            }

            if (
                url.startsWith("kakaomap://") ||
                url.startsWith("nmap://") ||
                url.startsWith("tmap://") ||
                url.startsWith("kakaonavi://") ||
                url.startsWith("market://")
            ) {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                return
            }

            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))

        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun openSexOffenderAppOrStore() {
        try {
            val launchIntent = packageManager.getLaunchIntentForPackage(sexOffenderPackage)
            if (launchIntent != null) {
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(launchIntent)
                return
            }
            openExternal(sexOffenderStoreUrl)
        } catch (e: Exception) {
            openExternal(sexOffenderStoreUrl)
        }
    }

    private fun openExternal(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e: ActivityNotFoundException) {
        }
    }

    private fun requestLocationPermission() {
        val fineLocationGranted =
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.ACCESS_FINE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED

        if (!fineLocationGranted) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                ),
                locationPermissionRequestCode
            )
        }
    }
}