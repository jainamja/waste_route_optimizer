package com.wasteroute.driver;

import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.os.Build;
import android.os.IBinder;
import android.os.Looper;
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

public class LocationService extends Service {
    private static final String TAG = "LocationService";
    private FusedLocationProviderClient fusedLocationClient;
    private LocationCallback locationCallback;
    private String driverId;
    private String truckId;
    private String idToken;
    private final String CHANNEL_ID = "RouteTrackingChannel";

    @Override
    public void onCreate() {
        super.onCreate();
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this);
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
        
        createNotificationChannel();
        
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
        
        return START_STICKY;
    }

    @SuppressLint("MissingPermission")
    private void startLocationUpdates() {
        if (locationCallback != null) {
            return;
        }

        LocationRequest locationRequest = new LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 4000)
                .setMinUpdateIntervalMillis(2000)
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

        new Thread(() -> {
            try {
                ensureIdToken();
                if (idToken == null || idToken.isEmpty()) {
                    Log.w(TAG, "No valid idToken available for Firebase upload");
                    return;
                }

                String jsonInputString = String.format(Locale.US,
                        "{\"currentLat\": %.6f, \"currentLng\": %.6f, \"speed\": %.2f, \"heading\": %.2f, \"accuracy\": %.1f, \"lastUpdated\": %d, \"timestamp\": %d, \"status\": \"online\", \"truckId\": \"%s\", \"driverId\": \"%s\"}",
                        loc.getLatitude(), loc.getLongitude(), loc.getSpeed(), loc.getBearing(), loc.getAccuracy(),
                        System.currentTimeMillis(), System.currentTimeMillis(), effectiveTruckId, effectiveDriverId);

                // 1. Write to driver_locations node
                patchToFirebase("https://wasteroutelive-default-rtdb.firebaseio.com/driver_locations/" + effectiveDriverId + ".json?auth=" + idToken, jsonInputString);

                // 2. Write to trucks node
                patchToFirebase("https://wasteroutelive-default-rtdb.firebaseio.com/trucks/" + effectiveTruckId + ".json?auth=" + idToken, jsonInputString);

            } catch (Exception e) {
                Log.e(TAG, "sendLocationToFirebase error", e);
            }
        }).start();
    }

    private void patchToFirebase(String urlStr, String jsonPayload) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("PATCH");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);
            conn.setDoOutput(true);

            try (OutputStream os = conn.getOutputStream()) {
                byte[] input = jsonPayload.getBytes("utf-8");
                os.write(input, 0, input.length);
            }

            int code = conn.getResponseCode();
            if (code == 401) {
                Log.w(TAG, "Firebase 401 Unauthorized - clearing token to refresh");
                idToken = null;
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
        if (idToken != null && !idToken.isEmpty()) {
            return;
        }
        try {
            URL url = new URL("https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=AIzaSyAhLnjh0gRa2pf29G90zr-6AMcjLjbQpPg");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
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
                    Log.i(TAG, "Acquired fresh Firebase anonymous token");
                }
            } else {
                Log.w(TAG, "Identity toolkit returned: " + respCode);
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "Failed to acquire anonymous token", e);
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel serviceChannel = new NotificationChannel(
                    CHANNEL_ID,
                    "Route Tracking",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(serviceChannel);
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (fusedLocationClient != null && locationCallback != null) {
            fusedLocationClient.removeLocationUpdates(locationCallback);
            locationCallback = null;
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
