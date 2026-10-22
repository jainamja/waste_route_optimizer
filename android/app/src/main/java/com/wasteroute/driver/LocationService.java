package com.wasteroute.driver;

import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.Priority;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;
import java.util.Scanner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class LocationService extends Service {
    private static final String TAG = "LocationService";
    private FusedLocationProviderClient fusedLocationClient;
    private LocationCallback locationCallback;
    private String driverId;
    private String truckId;
    private String idToken;
    private long tokenExpiresAt = 0;
    private final ExecutorService locationExecutor = Executors.newSingleThreadExecutor();
    private final String CHANNEL_ID = "RouteTrackingChannel";
    private final String ALERT_CHANNEL_ID = "DispatchAlertChannel";

    private volatile boolean isRunning = true;
    private long lastProcessedAlertTime = 0;
    private boolean alertPollingStarted = false;

    @Override
    public void onCreate() {
        super.onCreate();
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this);
        lastProcessedAlertTime = System.currentTimeMillis();
    }

    @SuppressLint("MissingPermission")
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            if (intent.hasExtra("driverId")) driverId = intent.getStringExtra("driverId");
            if (intent.hasExtra("truckId")) truckId = intent.getStringExtra("truckId");
            if (intent.hasExtra("idToken")) {
                String token = intent.getStringExtra("idToken");
                if (token != null && !token.isEmpty()) idToken = token;
            }
        }
        if (driverId == null && truckId != null) driverId = truckId;
        if (truckId == null && driverId != null) truckId = driverId;
        
        createNotificationChannels();
        
        Intent notificationIntent = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(this,
                0, notificationIntent, PendingIntent.FLAG_IMMUTABLE);
                
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("🚚 Route tracking active")
                .setContentText("Your location is being shared with the fleet dashboard.")
                .setSmallIcon(android.R.drawable.ic_menu_mylocation)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
                
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
        } else {
            startForeground(1, notification);
        }
        
        startLocationUpdates();

        if (!alertPollingStarted) {
            alertPollingStarted = true;
            startAlertPolling();
        }
        
        return START_STICKY;
    }

    private void startAlertPolling() {
        new Thread(() -> {
            Log.i(TAG, "Started native background alert polling thread for truck: " + truckId);
            while (isRunning) {
                try {
                    checkIncomingAlerts();
                    Thread.sleep(1500); // Check every 1.5s
                } catch (InterruptedException e) {
                    break;
                } catch (Exception e) {
                    Log.w(TAG, "checkIncomingAlerts exception: " + e.getMessage());
                    try { Thread.sleep(3000); } catch (Exception ignored) {}
                }
            }
        }).start();
    }

    private void checkIncomingAlerts() {
        final String effectiveTruckId = truckId != null ? truckId : driverId;
        if (effectiveTruckId == null) return;

        ensureIdToken();
        if (idToken == null || idToken.isEmpty()) return;

        String urlStr = "https://wasteroutelive-default-rtdb.firebaseio.com/trucks/" + effectiveTruckId + "/latest_alert.json?auth=" + idToken;
        String responseStr = getFromFirebase(urlStr);
        if (responseStr == null || responseStr.trim().isEmpty() || responseStr.trim().equals("null")) {
            return;
        }

        try {
            JSONObject obj = new JSONObject(responseStr);
            boolean read = obj.optBoolean("read", false);
            long timestamp = obj.optLong("timestamp", 0);
            String text = obj.optString("text", "New message from Dispatch");

            if (!read && timestamp > lastProcessedAlertTime) {
                lastProcessedAlertTime = timestamp;
                Log.i(TAG, "🚨 NEW ALERT DETECTED IN BACKGROUND: " + text);

                // Mark read in latest_alert so it doesn't loop
                patchToFirebase("https://wasteroutelive-default-rtdb.firebaseio.com/trucks/" + effectiveTruckId + "/latest_alert.json?auth=" + idToken, "{\"read\":true}");

                // Wake device, play sound, vibrate, and launch MainActivity
                wakeScreenAndLaunchApp(text);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error parsing latest_alert", e);
        }
    }

    private void wakeScreenAndLaunchApp(String text) {
        try {
            // 1. Wake screen up
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null) {
                @SuppressWarnings("deprecation")
                PowerManager.WakeLock wakeLock = pm.newWakeLock(
                    PowerManager.SCREEN_BRIGHT_WAKE_LOCK |
                    PowerManager.ACQUIRE_CAUSES_WAKEUP |
                    PowerManager.ON_AFTER_RELEASE,
                    "wasteroute:dispatch_wake"
                );
                wakeLock.acquire(5000);
            }

            // 2. Play native alert audio for 3.6s
            playNativeUrgentAlertSound();

            // 3. Vibrate phone
            Vibrator vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (vibrator != null) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator.vibrate(VibrationEffect.createWaveform(new long[]{0, 400, 150, 400, 150, 400, 150, 800, 200, 900}, -1));
                } else {
                    vibrator.vibrate(new long[]{0, 400, 150, 400, 150, 400, 150, 800, 200, 900}, -1);
                }
            }

            // 4. Launch MainActivity
            Intent launchIntent = new Intent(this, MainActivity.class);
            launchIntent.addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK |
                Intent.FLAG_ACTIVITY_REORDER_TO_FRONT |
                Intent.FLAG_ACTIVITY_SINGLE_TOP |
                Intent.FLAG_ACTIVITY_CLEAR_TOP
            );
            launchIntent.putExtra("openChat", true);
            launchIntent.putExtra("alertText", text);
            startActivity(launchIntent);

            // 5. Post high-priority Heads-Up Notification with FullScreenIntent
            showUrgentHeadsUpNotification(text);

        } catch (Exception e) {
            Log.e(TAG, "wakeScreenAndLaunchApp error", e);
        }
    }

    private void playNativeUrgentAlertSound() {
        try {
            Uri soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
            if (soundUri == null) soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
            final Ringtone ringtone = RingtoneManager.getRingtone(getApplicationContext(), soundUri);
            if (ringtone != null) {
                ringtone.play();
                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    try {
                        if (ringtone.isPlaying()) ringtone.stop();
                    } catch (Exception ignored) {}
                }, 3600);
            }
        } catch (Exception e) {
            Log.w(TAG, "playNativeUrgentAlertSound error: " + e.getMessage());
        }
    }

    private void showUrgentHeadsUpNotification(String text) {
        try {
            NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager == null) return;

            Intent notifyIntent = new Intent(this, MainActivity.class);
            notifyIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            notifyIntent.putExtra("openChat", true);

            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags |= PendingIntent.FLAG_IMMUTABLE;
            }

            PendingIntent pendingIntent = PendingIntent.getActivity(this, 3001, notifyIntent, flags);

            NotificationCompat.Builder builder = new NotificationCompat.Builder(this, ALERT_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("🚨 Message from Dispatch")
                .setContentText(text)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setAutoCancel(true)
                .setContentIntent(pendingIntent)
                .setFullScreenIntent(pendingIntent, true);

            manager.notify(3001, builder.build());
        } catch (Exception e) {
            Log.e(TAG, "showUrgentHeadsUpNotification error: " + e.getMessage());
        }
    }

    private String getFromFirebase(String urlStr) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(3000);
            conn.setReadTimeout(3000);
            
            int code = conn.getResponseCode();
            if (code == 401) {
                idToken = null; // refresh next time
                conn.disconnect();
                return null;
            }
            if (code == 200) {
                try (InputStream is = conn.getInputStream();
                     Scanner scanner = new Scanner(is, "UTF-8").useDelimiter("\\A")) {
                    String res = scanner.hasNext() ? scanner.next() : "";
                    conn.disconnect();
                    return res;
                }
            }
            conn.disconnect();
        } catch (Exception ignored) {}
        return null;
    }

    @SuppressLint("MissingPermission")
    private void startLocationUpdates() {
        if (locationCallback != null) {
            return;
        }

        // High-frequency real-time GPS streaming (1.5s interval with 1.0s fastest rate)
        LocationRequest locationRequest = new LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1500)
                .setMinUpdateIntervalMillis(1000)
                .setMinUpdateDistanceMeters(0.5f)
                .build();

        locationCallback = new LocationCallback() {
            @Override
            public void onLocationResult(LocationResult locationResult) {
                if (locationResult == null) return;
                for (Location location : locationResult.getLocations()) {
                    sendLocationToFirebase(location);
                }
            }
        };

        fusedLocationClient.requestLocationUpdates(locationRequest, locationCallback, Looper.getMainLooper());
    }

    private void sendLocationToFirebase(Location loc) {
        if (driverId == null && truckId == null) return;
        
        final String effectiveDriverId = driverId != null ? driverId : truckId;
        final String effectiveTruckId = truckId != null ? truckId : driverId;

        locationExecutor.execute(() -> {
            try {
                ensureIdToken();
                if (idToken == null || idToken.isEmpty()) {
                    Log.w(TAG, "No valid idToken available for Firebase upload");
                    return;
                }

                long now = System.currentTimeMillis();
                String singlePayload = String.format(Locale.US,
                        "{\"currentLat\": %.6f, \"currentLng\": %.6f, \"speed\": %.2f, \"heading\": %.2f, \"accuracy\": %.1f, \"lastUpdated\": %d, \"timestamp\": %d, \"status\": \"online\", \"truckId\": \"%s\", \"driverId\": \"%s\"}",
                        loc.getLatitude(), loc.getLongitude(), loc.getSpeed(), loc.getBearing(), loc.getAccuracy(),
                        now, now, effectiveTruckId, effectiveDriverId);

                // Single atomic root PATCH updating both driver_locations and trucks in 1 HTTP roundtrip
                String multiPathJson = String.format(Locale.US,
                        "{\"driver_locations/%s\": %s, \"trucks/%s\": %s}",
                        effectiveDriverId, singlePayload,
                        effectiveTruckId, singlePayload);

                patchToFirebase("https://wasteroutelive-default-rtdb.firebaseio.com/.json?auth=" + idToken, multiPathJson);

            } catch (Exception e) {
                Log.e(TAG, "sendLocationToFirebase error", e);
            }
        });
    }

    private void patchToFirebase(String urlStr, String jsonPayload) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("PATCH");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Connection", "keep-alive");
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(4000);
            conn.setDoOutput(true);

            try (OutputStream os = conn.getOutputStream()) {
                byte[] input = jsonPayload.getBytes("utf-8");
                os.write(input, 0, input.length);
            }

            int code = conn.getResponseCode();
            if (code == 401) {
                Log.w(TAG, "Firebase 401 Unauthorized - clearing token to refresh");
                idToken = null;
                tokenExpiresAt = 0;
            } else if (code >= 200 && code < 300) {
                Log.d(TAG, "Firebase PATCH success: " + code);
            } else {
                Log.w(TAG, "Firebase PATCH returned: " + code);
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "patchToFirebase exception: " + e.getMessage());
        }
    }

    private synchronized void ensureIdToken() {
        if (idToken != null && !idToken.isEmpty() && System.currentTimeMillis() < tokenExpiresAt) {
            return;
        }
        try {
            URL url = new URL("https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Connection", "keep-alive");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);
            conn.setDoOutput(true);

            String reqBody = "{\"returnSecureToken\":true}";
            try (OutputStream os = conn.getOutputStream()) {
                os.write(reqBody.getBytes("utf-8"));
            }

            int respCode = conn.getResponseCode();
            if (respCode == 200) {
                try (InputStream is = conn.getInputStream();
                     Scanner scanner = new Scanner(is, "UTF-8").useDelimiter("\\A")) {
                    String respStr = scanner.hasNext() ? scanner.next() : "";
                    JSONObject jsonObj = new JSONObject(respStr);
                    idToken = jsonObj.getString("idToken");
                    long expiresInSec = jsonObj.optLong("expiresIn", 3600);
                    tokenExpiresAt = System.currentTimeMillis() + (expiresInSec - 120) * 1000;
                    Log.i(TAG, "Acquired fresh Firebase anonymous token, expires in " + expiresInSec + "s");
                }
            } else {
                Log.w(TAG, "Identity toolkit returned: " + respCode);
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "Failed to acquire anonymous token", e);
        }
    }

    private void createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager == null) return;

            // Route tracking service channel
            NotificationChannel serviceChannel = new NotificationChannel(
                    CHANNEL_ID,
                    "Route Tracking",
                    NotificationManager.IMPORTANCE_LOW
            );
            manager.createNotificationChannel(serviceChannel);

            // Dispatch alert high priority channel
            NotificationChannel alertChannel = new NotificationChannel(
                    ALERT_CHANNEL_ID,
                    "Dispatch Urgent Alerts",
                    NotificationManager.IMPORTANCE_HIGH
            );
            alertChannel.setDescription("Incoming messages and urgent dispatch notifications");
            alertChannel.enableVibration(true);
            alertChannel.setVibrationPattern(new long[]{0, 400, 150, 400, 150, 400, 150, 800, 200, 900});
            alertChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            alertChannel.setBypassDnd(true);
            manager.createNotificationChannel(alertChannel);
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        isRunning = false;

        try {
            locationExecutor.shutdownNow();
        } catch (Exception ignored) {}

        if (fusedLocationClient != null && locationCallback != null) {
            fusedLocationClient.removeLocationUpdates(locationCallback);
            locationCallback = null;
        }

        final String effectiveDriverId = driverId != null ? driverId : truckId;
        final String effectiveTruckId = truckId != null ? truckId : driverId;

        if (effectiveDriverId != null || effectiveTruckId != null) {
            new Thread(() -> {
                try {
                    ensureIdToken();
                    if (idToken != null && !idToken.isEmpty()) {
                        String offlineJson = String.format(Locale.US,
                                "{\"status\": \"offline\", \"speed\": 0.0, \"lastUpdated\": %d}",
                                System.currentTimeMillis());
                        if (effectiveDriverId != null) {
                            patchToFirebase("https://wasteroutelive-default-rtdb.firebaseio.com/driver_locations/" + effectiveDriverId + ".json?auth=" + idToken, offlineJson);
                        }
                        if (effectiveTruckId != null) {
                            patchToFirebase("https://wasteroutelive-default-rtdb.firebaseio.com/trucks/" + effectiveTruckId + ".json?auth=" + idToken, offlineJson);
                        }
                    }
                } catch (Exception e) {
                    Log.e(TAG, "onDestroy offline status update error", e);
                }
            }).start();
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
