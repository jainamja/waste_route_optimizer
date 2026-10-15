package com.wasteroute.driver;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.PowerManager;
import android.net.Uri;
import android.provider.Settings;
import android.util.Log;

import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "BackgroundLocation")
public class BackgroundLocationPlugin extends Plugin {

    private static final String TAG = "BackgroundLocation";
    private static final String ALERT_CHANNEL_ID = "DispatchAlertChannel";

    @PluginMethod
    public void start(PluginCall call) {
        if (ContextCompat.checkSelfPermission(getContext(), Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            call.reject("Location permission not granted");
            return;
        }

        String driverId = call.getString("driverId");
        String truckId = call.getString("truckId");
        String idToken = call.getString("idToken");

        if (driverId == null && truckId != null) {
            driverId = truckId;
        }
        if (truckId == null && driverId != null) {
            truckId = driverId;
        }

        if (driverId == null) {
            call.reject("Must provide driverId or truckId");
            return;
        }

        Intent intent = new Intent(getContext(), LocationService.class);
        intent.putExtra("driverId", driverId);
        intent.putExtra("truckId", truckId);
        if (idToken != null && !idToken.isEmpty()) {
            intent.putExtra("idToken", idToken);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getContext().startForegroundService(intent);
        } else {
            getContext().startService(intent);
        }

        call.resolve();
    }

    @PluginMethod
    public void stop(PluginCall call) {
        Intent intent = new Intent(getContext(), LocationService.class);
        getContext().stopService(intent);
        call.resolve();
    }

    @PluginMethod
    public void bringToFront(PluginCall call) {
        try {
            Context context = getContext();
            String title = call.getString("title", "🚨 Dispatch Alert");
            String text = call.getString("text", "New message received from Dispatch");

            // 1. Wake screen up
            PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
            if (pm != null) {
                PowerManager.WakeLock wakeLock = pm.newWakeLock(
                    PowerManager.SCREEN_BRIGHT_WAKE_LOCK |
                    PowerManager.ACQUIRE_CAUSES_WAKEUP |
                    PowerManager.ON_AFTER_RELEASE,
                    "wasteroute:dispatch_wake"
                );
                wakeLock.acquire(4000);
            }

            // 2. Bring Activity to Front
            Intent intent = new Intent(context, MainActivity.class);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            intent.putExtra("openChat", true);
            context.startActivity(intent);

            // 3. Post urgent Heads-Up Notification with FullScreenIntent
            showHeadsUpNotification(context, title, text);

            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "bringToFront error", e);
            call.reject(e.getMessage());
        }
    }

    private void showHeadsUpNotification(Context context, String title, String text) {
        try {
            NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager == null) return;

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                NotificationChannel channel = new NotificationChannel(
                    ALERT_CHANNEL_ID,
                    "Dispatch Urgent Alerts",
                    NotificationManager.IMPORTANCE_HIGH
                );
                channel.setDescription("Incoming messages and urgent dispatch notifications");
                channel.enableVibration(true);
                channel.setVibrationPattern(new long[]{0, 400, 150, 400, 150, 400, 150, 800});
                channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
                manager.createNotificationChannel(channel);
            }

            Intent notifyIntent = new Intent(context, MainActivity.class);
            notifyIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            notifyIntent.putExtra("openChat", true);

            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags |= PendingIntent.FLAG_IMMUTABLE;
            }

            PendingIntent pendingIntent = PendingIntent.getActivity(context, 2002, notifyIntent, flags);

            NotificationCompat.Builder builder = new NotificationCompat.Builder(context, ALERT_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setCategory(NotificationCompat.CATEGORY_MESSAGE)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setAutoCancel(true)
                .setContentIntent(pendingIntent)
                .setFullScreenIntent(pendingIntent, true);

            manager.notify(2002, builder.build());
        } catch (Exception e) {
            Log.e(TAG, "showHeadsUpNotification error", e);
        }
    }

    @PluginMethod
    public void checkOverlayPermission(PluginCall call) {
        boolean canDraw = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            canDraw = Settings.canDrawOverlays(getContext());
        }
        JSObject ret = new JSObject();
        ret.put("hasPermission", canDraw);
        call.resolve(ret);
    }

    @PluginMethod
    public void requestOverlayPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!Settings.canDrawOverlays(getContext())) {
                Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + getContext().getPackageName()));
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                getContext().startActivity(intent);
            }
        }
        call.resolve();
    }
}
