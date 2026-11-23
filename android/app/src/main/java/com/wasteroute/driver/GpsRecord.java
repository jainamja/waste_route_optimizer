package com.wasteroute.driver;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.UUID;

public class GpsRecord {
    public String eventId;
    public String driverId;
    public String truckId;
    public String assignmentId;
    public double latitude;
    public double longitude;
    public float accuracy;
    public float speed;
    public float bearing;
    public String provider;
    public long captureTime;
    public long sequenceNumber;
    public String uploadStatus; // PENDING, UPLOADING, UPLOADED, QUARANTINED
    public int retryCount;
    public long lastRetryTime;
    public String errorMessage;
    public long createdAt;

    public GpsRecord() {
        this.eventId = UUID.randomUUID().toString();
        this.createdAt = System.currentTimeMillis();
        this.uploadStatus = "PENDING";
        this.retryCount = 0;
        this.lastRetryTime = 0;
    }

    public JSONObject toJsonObject() throws JSONException {
        JSONObject obj = new JSONObject();
        obj.put("event_id", eventId);
        obj.put("driver_id", driverId != null ? driverId : "");
        obj.put("truck_id", truckId != null ? truckId : "");
        obj.put("assignment_id", assignmentId != null ? assignmentId : "");
        obj.put("latitude", latitude);
        obj.put("longitude", longitude);
        obj.put("accuracy", (double) accuracy);
        obj.put("speed", (double) speed);
        obj.put("bearing", (double) bearing);
        obj.put("provider", provider != null ? provider : "fused");
        obj.put("capture_time", captureTime);
        obj.put("sequence_number", sequenceNumber);
        return obj;
    }

    public static GpsRecord fromJsonObject(JSONObject obj) {
        GpsRecord record = new GpsRecord();
        record.eventId = obj.optString("event_id", UUID.randomUUID().toString());
        record.driverId = obj.optString("driver_id", "");
        record.truckId = obj.optString("truck_id", "");
        record.assignmentId = obj.optString("assignment_id", "");
        record.latitude = obj.optDouble("latitude", 0.0);
        record.longitude = obj.optDouble("longitude", 0.0);
        record.accuracy = (float) obj.optDouble("accuracy", 0.0);
        record.speed = (float) obj.optDouble("speed", 0.0);
        record.bearing = (float) obj.optDouble("bearing", 0.0);
        record.provider = obj.optString("provider", "fused");
        record.captureTime = obj.optLong("capture_time", System.currentTimeMillis());
        record.sequenceNumber = obj.optLong("sequence_number", 0);
        return record;
    }
}
