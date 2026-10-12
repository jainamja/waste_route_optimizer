package com.wasteroute.driver;

import android.content.Intent;
import android.os.Build;
import android.Manifest;
import android.content.pm.PackageManager;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;

@CapacitorPlugin(name = "BackgroundLocation")
public class BackgroundLocationPlugin extends Plugin {

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
}
