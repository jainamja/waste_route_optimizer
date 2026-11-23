package com.wasteroute.driver;

import android.location.Location;
import android.util.Log;

public class GpsAccuracyValidator {
    private static final String TAG = "GpsAccuracyValidator";

    // Accuracy thresholds in meters
    public static final float ACCURACY_GOOD_THRESHOLD_METERS = 30.0f;
    public static final float ACCURACY_WEAK_THRESHOLD_METERS = 100.0f;

    // Max reasonable vehicle speed: 160 km/h = 44.4 m/s
    public static final float MAX_REASONABLE_SPEED_MPS = 44.4f;

    // Max acceptable GPS fix staleness for live updates: 60 seconds
    public static final long MAX_STALE_AGE_MS = 60_000L;

    public static class ValidationResult {
        public final boolean isValid;
        public final boolean isLiveEligible;
        public final boolean isWeakAccuracy;
        public final String status;
        public final String reason;

        public ValidationResult(boolean isValid, boolean isLiveEligible, boolean isWeakAccuracy, String status, String reason) {
            this.isValid = isValid;
            this.isLiveEligible = isLiveEligible;
            this.isWeakAccuracy = isWeakAccuracy;
            this.status = status;
            this.reason = reason;
        }

        public static ValidationResult validLive(boolean isWeak, String reason) {
            return new ValidationResult(true, true, isWeak, isWeak ? "WEAK_GPS" : "LIVE", reason);
        }

        public static ValidationResult validHistoricalOnly(String status, String reason) {
            return new ValidationResult(true, false, true, status, reason);
        }

        public static ValidationResult invalid(String reason) {
            return new ValidationResult(false, false, false, "INVALID", reason);
        }
    }

    private double lastValidLat = 0.0;
    private double lastValidLng = 0.0;
    private long lastValidTimeMs = 0;

    public synchronized ValidationResult validate(Location loc) {
        if (loc == null) {
            return ValidationResult.invalid("Null location object");
        }
        float accuracy = loc.hasAccuracy() ? loc.getAccuracy() : 0.0f;
        float speed = loc.hasSpeed() ? loc.getSpeed() : 0.0f;
        float bearing = loc.hasBearing() ? loc.getBearing() : 0.0f;
        long captureTime = loc.getTime();
        String provider = loc.getProvider();
        return validate(loc.getLatitude(), loc.getLongitude(), accuracy, speed, bearing, captureTime, provider);
    }

    public synchronized ValidationResult validate(double lat, double lng, float accuracy, float speed, float bearing, long captureTime, String provider) {
        // 1. Check coordinate bounds
        if (Double.isNaN(lat) || Double.isNaN(lng) || Double.isInfinite(lat) || Double.isInfinite(lng)) {
            return ValidationResult.invalid("Non-numeric or infinite coordinates");
        }

        if (lat < -90.0 || lat > 90.0 || lng < -180.0 || lng > 180.0) {
            return ValidationResult.invalid(String.format("Coordinates out of range: %.6f, %.6f", lat, lng));
        }

        // 2. Reject Null Island (0.0, 0.0)
        if (Math.abs(lat) < 0.0001 && Math.abs(lng) < 0.0001) {
            return ValidationResult.invalid("Null island coordinates (0.0, 0.0)");
        }

        // 3. Check capture timestamp freshness
        long now = System.currentTimeMillis();
        if (captureTime <= 0) {
            captureTime = now;
        }
        long age = now - captureTime;

        // Future timestamps beyond 15 seconds drift indicate incorrect device clock
        if (age < -15_000L) {
            return ValidationResult.invalid("Location has timestamp in future (>15s drift)");
        }

        boolean isStale = age > MAX_STALE_AGE_MS;

        // 4. Accuracy evaluation
        if (accuracy <= 0.0f) {
            accuracy = 999.0f;
        }

        boolean isWeak = accuracy > ACCURACY_GOOD_THRESHOLD_METERS;
        boolean isUnusableAccuracy = accuracy > ACCURACY_WEAK_THRESHOLD_METERS;

        // 5. Jump / teleportation filter against last valid fix
        if (lastValidTimeMs > 0 && Math.abs(lastValidLat) > 0.0001) {
            double distanceMeters = haversineMeters(lastValidLat, lastValidLng, lat, lng);
            long timeDeltaMs = captureTime - lastValidTimeMs;

            if (timeDeltaMs > 0) {
                float timeDeltaSec = timeDeltaMs / 1000.0f;
                double impliedSpeed = distanceMeters / timeDeltaSec;

                // If implied speed exceeds 160 km/h with distance jump > 200m, flag as GPS jump
                if (impliedSpeed > MAX_REASONABLE_SPEED_MPS && distanceMeters > 200.0) {
                    safeLogW(TAG, String.format("Suspicious GPS jump: %.1fm in %.1fs (%.1f m/s). Rejected for live tracking.",
                            distanceMeters, timeDeltaSec, impliedSpeed));
                    return ValidationResult.validHistoricalOnly("SUSPICIOUS_JUMP",
                            String.format("Implied speed %.1f m/s exceeds max threshold", impliedSpeed));
                }
            } else if (timeDeltaMs < -5000) {
                return ValidationResult.validHistoricalOnly("OUT_OF_ORDER",
                        "Capture time is older than current live position");
            }
        }

        // If accuracy is unusable (>100m), store in history/offline queue but do not treat as live
        if (isUnusableAccuracy) {
            return ValidationResult.validHistoricalOnly("WEAK_ACCURACY",
                    String.format("Accuracy too coarse: %.1fm", accuracy));
        }

        // If stale (>60s old), eligible for historical queue but not live
        if (isStale) {
            return ValidationResult.validHistoricalOnly("STALE",
                    String.format("Location is %.1fs old", age / 1000.0f));
        }

        // Record as latest valid fix
        lastValidLat = lat;
        lastValidLng = lng;
        lastValidTimeMs = captureTime;

        return ValidationResult.validLive(isWeak, isWeak ? "Weak accuracy" : "Accurate fix");
    }

    public static double haversineMeters(double lat1, double lng1, double lat2, double lng2) {
        final double R = 6371000.0; // Earth radius in meters
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) *
                Math.sin(dLng / 2) * Math.sin(dLng / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    public synchronized void reset() {
        lastValidLat = 0.0;
        lastValidLng = 0.0;
        lastValidTimeMs = 0;
    }

    private static void safeLogW(String tag, String msg) {
        try {
            Log.w(tag, msg);
        } catch (Throwable ignored) {
            System.err.println(tag + ": " + msg);
        }
    }
}
