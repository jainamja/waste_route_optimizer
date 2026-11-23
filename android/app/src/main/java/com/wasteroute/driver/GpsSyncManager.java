package com.wasteroute.driver;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class GpsSyncManager {
    private static final String TAG = "GpsSyncManager";

    public interface TokenProvider {
        String getFlaskToken();
        String getFirebaseIdToken();
        void refreshTokens();
    }

    private final Context context;
    private final GpsDatabaseHelper dbHelper;
    private final TokenProvider tokenProvider;
    private final ExecutorService syncExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private final AtomicBoolean isNetworkConnected = new AtomicBoolean(false);
    private final AtomicBoolean isSyncing = new AtomicBoolean(false);

    private ConnectivityManager.NetworkCallback networkCallback;
    private int backoffSeconds = 1;

    public GpsSyncManager(Context context, GpsDatabaseHelper dbHelper, TokenProvider tokenProvider) {
        this.context = context.getApplicationContext();
        this.dbHelper = dbHelper;
        this.tokenProvider = tokenProvider;
        registerNetworkCallback();
    }

    private void registerNetworkCallback() {
        try {
            ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
            if (cm == null) return;

            Network activeNet = cm.getActiveNetwork();
            if (activeNet != null) {
                NetworkCapabilities caps = cm.getNetworkCapabilities(activeNet);
                isNetworkConnected.set(caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET));
            }

            NetworkRequest req = new NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .build();

            networkCallback = new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    Log.i(TAG, "🌐 Network connectivity RESTORED. Triggering automatic background sync.");
                    isNetworkConnected.set(true);
                    backoffSeconds = 1;
                    triggerSync();
                }

                @Override
                public void onLost(Network network) {
                    Log.w(TAG, "❌ Network connectivity LOST. Switched to offline queue mode.");
                    isNetworkConnected.set(false);
                }
            };

            cm.registerNetworkCallback(req, networkCallback);
        } catch (Exception e) {
            Log.e(TAG, "Error registering network callback", e);
        }
    }

    public boolean isConnected() {
        return isNetworkConnected.get();
    }

    public void triggerSync() {
        if (!isNetworkConnected.get()) {
            return;
        }

        if (isSyncing.compareAndSet(false, true)) {
            syncExecutor.execute(this::runSyncLoop);
        }
    }

    private void runSyncLoop() {
        try {
            while (isNetworkConnected.get()) {
                int pendingCount = dbHelper.getPendingCount();
                if (pendingCount == 0) {
                    break;
                }

                List<GpsRecord> batch = dbHelper.getPendingBatch(30);
                if (batch.isEmpty()) {
                    break;
                }

                boolean success = uploadBatchToBackend(batch);
                if (success) {
                    List<String> eventIds = new ArrayList<>();
                    for (GpsRecord r : batch) {
                        eventIds.add(r.eventId);
                    }
                    dbHelper.markUploaded(eventIds);
                    backoffSeconds = 1; // reset backoff on success
                    Log.i(TAG, String.format(Locale.US, "✅ Synced batch of %d records. %d remaining in offline queue.",
                            batch.size(), dbHelper.getPendingCount()));
                } else {
                    // Record retry for batch and apply exponential backoff
                    for (GpsRecord r : batch) {
                        dbHelper.recordRetry(r.eventId, "Backend sync error or network timeout");
                    }
                    int sleepMs = Math.min(backoffSeconds * 1000, 30_000);
                    backoffSeconds = Math.min(backoffSeconds * 2, 30);
                    Log.w(TAG, "Sync failed; backing off for " + (sleepMs / 1000) + "s");
                    Thread.sleep(sleepMs);
                    break;
                }
            }
        } catch (InterruptedException ignored) {
        } catch (Exception e) {
            Log.e(TAG, "Exception during runSyncLoop", e);
        } finally {
            isSyncing.set(false);
        }
    }

    private boolean uploadBatchToBackend(List<GpsRecord> batch) {
        String flaskToken = tokenProvider.getFlaskToken();
        if (flaskToken == null || flaskToken.isEmpty()) {
            tokenProvider.refreshTokens();
            flaskToken = tokenProvider.getFlaskToken();
            if (flaskToken == null || flaskToken.isEmpty()) {
                Log.w(TAG, "No valid flaskToken for telemetry sync");
                return false;
            }
        }

        HttpURLConnection conn = null;
        try {
            JSONArray recordsArray = new JSONArray();
            for (GpsRecord r : batch) {
                recordsArray.put(r.toJsonObject());
            }

            JSONObject requestPayload = new JSONObject();
            requestPayload.put("records", recordsArray);

            URL url = new URL("https://waste-route-optimizer-190z.onrender.com/api/driver/telemetry_sync");
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Authorization", "Bearer " + flaskToken);
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(10000);
            conn.setDoOutput(true);

            byte[] jsonBytes = requestPayload.toString().getBytes("utf-8");
            try (OutputStream os = conn.getOutputStream()) {
                os.write(jsonBytes);
            }

            int code = conn.getResponseCode();
            if (code == 401 || code == 403) {
                Log.w(TAG, "Telemetry sync got " + code + "; requesting token refresh.");
                tokenProvider.refreshTokens();
                return false;
            }

            if (code >= 200 && code < 300) {
                try (InputStream is = conn.getInputStream();
                     Scanner s = new Scanner(is, "UTF-8").useDelimiter("\\A")) {
                    String respStr = s.hasNext() ? s.next() : "";
                    JSONObject respJson = new JSONObject(respStr);
                    return respJson.optBoolean("success", false);
                }
            }

            Log.w(TAG, "Telemetry sync backend returned code: " + code);
            return false;
        } catch (Exception e) {
            Log.w(TAG, "Telemetry sync upload exception: " + e.getMessage());
            return false;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    public void unregister() {
        try {
            if (networkCallback != null) {
                ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
                if (cm != null) {
                    cm.unregisterNetworkCallback(networkCallback);
                }
            }
            syncExecutor.shutdownNow();
        } catch (Exception ignored) {}
    }
}
