package com.wasteroute.driver;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.util.Log;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

public class GpsDatabaseHelper extends SQLiteOpenHelper {
    private static final String TAG = "GpsDatabaseHelper";
    private static final String DATABASE_NAME = "trashtrekyx_gps_queue.db";
    private static final int DATABASE_VERSION = 1;

    public static final String TABLE_NAME = "gps_queue";
    public static final String COL_ID = "id";
    public static final String COL_EVENT_ID = "event_id";
    public static final String COL_DRIVER_ID = "driver_id";
    public static final String COL_TRUCK_ID = "truck_id";
    public static final String COL_ASSIGNMENT_ID = "assignment_id";
    public static final String COL_LATITUDE = "latitude";
    public static final String COL_LONGITUDE = "longitude";
    public static final String COL_ACCURACY = "accuracy";
    public static final String COL_SPEED = "speed";
    public static final String COL_BEARING = "bearing";
    public static final String COL_PROVIDER = "provider";
    public static final String COL_CAPTURE_TIME = "capture_time";
    public static final String COL_SEQUENCE_NUMBER = "sequence_number";
    public static final String COL_UPLOAD_STATUS = "upload_status";
    public static final String COL_RETRY_COUNT = "retry_count";
    public static final String COL_LAST_RETRY_TIME = "last_retry_time";
    public static final String COL_ERROR_MESSAGE = "error_message";
    public static final String COL_CREATED_AT = "created_at";

    private static final int MAX_STORAGE_CAPACITY = 50_000;
    private static final int MAX_UPLOADED_RETENTION = 5_000;

    private static GpsDatabaseHelper instance;
    private final AtomicLong sequenceGenerator = new AtomicLong(0);

    public static synchronized GpsDatabaseHelper getInstance(Context context) {
        if (instance == null) {
            instance = new GpsDatabaseHelper(context.getApplicationContext());
        }
        return instance;
    }

    private GpsDatabaseHelper(Context context) {
        super(context, DATABASE_NAME, null, DATABASE_VERSION);
        initMaxSequence();
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        String createTableSql = "CREATE TABLE " + TABLE_NAME + " (" +
                COL_ID + " INTEGER PRIMARY KEY AUTOINCREMENT, " +
                COL_EVENT_ID + " TEXT UNIQUE NOT NULL, " +
                COL_DRIVER_ID + " TEXT, " +
                COL_TRUCK_ID + " TEXT, " +
                COL_ASSIGNMENT_ID + " TEXT, " +
                COL_LATITUDE + " REAL NOT NULL, " +
                COL_LONGITUDE + " REAL NOT NULL, " +
                COL_ACCURACY + " REAL, " +
                COL_SPEED + " REAL, " +
                COL_BEARING + " REAL, " +
                COL_PROVIDER + " TEXT, " +
                COL_CAPTURE_TIME + " INTEGER NOT NULL, " +
                COL_SEQUENCE_NUMBER + " INTEGER NOT NULL, " +
                COL_UPLOAD_STATUS + " TEXT NOT NULL DEFAULT 'PENDING', " +
                COL_RETRY_COUNT + " INTEGER NOT NULL DEFAULT 0, " +
                COL_LAST_RETRY_TIME + " INTEGER NOT NULL DEFAULT 0, " +
                COL_ERROR_MESSAGE + " TEXT, " +
                COL_CREATED_AT + " INTEGER NOT NULL" +
                ");";

        db.execSQL(createTableSql);
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_status_seq ON " + TABLE_NAME + " (" + COL_UPLOAD_STATUS + ", " + COL_SEQUENCE_NUMBER + ");");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_event_id ON " + TABLE_NAME + " (" + COL_EVENT_ID + ");");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_capture_time ON " + TABLE_NAME + " (" + COL_CAPTURE_TIME + ");");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // Safe migration if upgraded in future
    }

    private void initMaxSequence() {
        try {
            SQLiteDatabase db = getReadableDatabase();
            try (Cursor cursor = db.rawQuery("SELECT MAX(" + COL_SEQUENCE_NUMBER + ") FROM " + TABLE_NAME, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    long maxSeq = cursor.getLong(0);
                    sequenceGenerator.set(maxSeq);
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Error initializing sequence generator", e);
        }
    }

    public synchronized long insert(GpsRecord record) {
        long seq = sequenceGenerator.incrementAndGet();
        record.sequenceNumber = seq;

        SQLiteDatabase db = getWritableDatabase();
        ContentValues cv = new ContentValues();
        cv.put(COL_EVENT_ID, record.eventId);
        cv.put(COL_DRIVER_ID, record.driverId);
        cv.put(COL_TRUCK_ID, record.truckId);
        cv.put(COL_ASSIGNMENT_ID, record.assignmentId);
        cv.put(COL_LATITUDE, record.latitude);
        cv.put(COL_LONGITUDE, record.longitude);
        cv.put(COL_ACCURACY, record.accuracy);
        cv.put(COL_SPEED, record.speed);
        cv.put(COL_BEARING, record.bearing);
        cv.put(COL_PROVIDER, record.provider);
        cv.put(COL_CAPTURE_TIME, record.captureTime);
        cv.put(COL_SEQUENCE_NUMBER, record.sequenceNumber);
        cv.put(COL_UPLOAD_STATUS, record.uploadStatus != null ? record.uploadStatus : "PENDING");
        cv.put(COL_RETRY_COUNT, record.retryCount);
        cv.put(COL_LAST_RETRY_TIME, record.lastRetryTime);
        cv.put(COL_ERROR_MESSAGE, record.errorMessage);
        cv.put(COL_CREATED_AT, record.createdAt > 0 ? record.createdAt : System.currentTimeMillis());

        long rowId = db.insertWithOnConflict(TABLE_NAME, null, cv, SQLiteDatabase.CONFLICT_IGNORE);
        if (rowId == -1) {
            Log.w(TAG, "Duplicate or ignored insert for eventId: " + record.eventId);
        }

        // Periodic capacity management
        if (seq % 100 == 0) {
            checkAndTrimCapacity();
        }

        return rowId;
    }

    public synchronized List<GpsRecord> getPendingBatch(int limit) {
        List<GpsRecord> records = new ArrayList<>();
        SQLiteDatabase db = getReadableDatabase();

        String selection = COL_UPLOAD_STATUS + " = 'PENDING'";
        String orderBy = COL_SEQUENCE_NUMBER + " ASC";
        String limitStr = String.valueOf(limit > 0 ? limit : 30);

        try (Cursor c = db.query(TABLE_NAME, null, selection, null, null, null, orderBy, limitStr)) {
            while (c != null && c.moveToNext()) {
                GpsRecord r = new GpsRecord();
                r.eventId = c.getString(c.getColumnIndexOrThrow(COL_EVENT_ID));
                r.driverId = c.getString(c.getColumnIndexOrThrow(COL_DRIVER_ID));
                r.truckId = c.getString(c.getColumnIndexOrThrow(COL_TRUCK_ID));
                r.assignmentId = c.getString(c.getColumnIndexOrThrow(COL_ASSIGNMENT_ID));
                r.latitude = c.getDouble(c.getColumnIndexOrThrow(COL_LATITUDE));
                r.longitude = c.getDouble(c.getColumnIndexOrThrow(COL_LONGITUDE));
                r.accuracy = c.getFloat(c.getColumnIndexOrThrow(COL_ACCURACY));
                r.speed = c.getFloat(c.getColumnIndexOrThrow(COL_SPEED));
                r.bearing = c.getFloat(c.getColumnIndexOrThrow(COL_BEARING));
                r.provider = c.getString(c.getColumnIndexOrThrow(COL_PROVIDER));
                r.captureTime = c.getLong(c.getColumnIndexOrThrow(COL_CAPTURE_TIME));
                r.sequenceNumber = c.getLong(c.getColumnIndexOrThrow(COL_SEQUENCE_NUMBER));
                r.uploadStatus = c.getString(c.getColumnIndexOrThrow(COL_UPLOAD_STATUS));
                r.retryCount = c.getInt(c.getColumnIndexOrThrow(COL_RETRY_COUNT));
                r.lastRetryTime = c.getLong(c.getColumnIndexOrThrow(COL_LAST_RETRY_TIME));
                r.errorMessage = c.getString(c.getColumnIndexOrThrow(COL_ERROR_MESSAGE));
                r.createdAt = c.getLong(c.getColumnIndexOrThrow(COL_CREATED_AT));
                records.add(r);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error querying pending batch", e);
        }

        return records;
    }

    public synchronized void markUploaded(List<String> eventIds) {
        if (eventIds == null || eventIds.isEmpty()) return;

        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try {
            ContentValues cv = new ContentValues();
            cv.put(COL_UPLOAD_STATUS, "UPLOADED");
            cv.put(COL_ERROR_MESSAGE, (String) null);

            for (String eventId : eventIds) {
                db.update(TABLE_NAME, cv, COL_EVENT_ID + " = ?", new String[]{eventId});
            }
            db.setTransactionSuccessful();
        } catch (Exception e) {
            Log.e(TAG, "Error marking records uploaded", e);
        } finally {
            db.endTransaction();
        }
    }

    public synchronized void recordRetry(String eventId, String errorMessage) {
        if (eventId == null) return;
        SQLiteDatabase db = getWritableDatabase();
        try {
            db.execSQL("UPDATE " + TABLE_NAME + " SET " +
                    COL_RETRY_COUNT + " = " + COL_RETRY_COUNT + " + 1, " +
                    COL_LAST_RETRY_TIME + " = " + System.currentTimeMillis() + ", " +
                    COL_ERROR_MESSAGE + " = ? WHERE " + COL_EVENT_ID + " = ?",
                    new Object[]{errorMessage, eventId});
        } catch (Exception e) {
            Log.e(TAG, "Error updating retry status", e);
        }
    }

    public synchronized void markQuarantined(String eventId, String reason) {
        if (eventId == null) return;
        SQLiteDatabase db = getWritableDatabase();
        try {
            ContentValues cv = new ContentValues();
            cv.put(COL_UPLOAD_STATUS, "QUARANTINED");
            cv.put(COL_ERROR_MESSAGE, reason);
            db.update(TABLE_NAME, cv, COL_EVENT_ID + " = ?", new String[]{eventId});
        } catch (Exception e) {
            Log.e(TAG, "Error quarantining record", e);
        }
    }

    public synchronized int getPendingCount() {
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor c = db.rawQuery("SELECT COUNT(*) FROM " + TABLE_NAME + " WHERE " + COL_UPLOAD_STATUS + " = 'PENDING'", null)) {
            if (c != null && c.moveToFirst()) {
                return c.getInt(0);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error getting pending count", e);
        }
        return 0;
    }

    public synchronized int getTotalCount() {
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor c = db.rawQuery("SELECT COUNT(*) FROM " + TABLE_NAME, null)) {
            if (c != null && c.moveToFirst()) {
                return c.getInt(0);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error getting total count", e);
        }
        return 0;
    }

    public synchronized long getOldestPendingCaptureTime() {
        SQLiteDatabase db = getReadableDatabase();
        try (Cursor c = db.rawQuery("SELECT MIN(" + COL_CAPTURE_TIME + ") FROM " + TABLE_NAME + " WHERE " + COL_UPLOAD_STATUS + " = 'PENDING'", null)) {
            if (c != null && c.moveToFirst()) {
                return c.getLong(0);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error getting oldest pending time", e);
        }
        return 0;
    }

    private void checkAndTrimCapacity() {
        try {
            int total = getTotalCount();
            if (total > MAX_STORAGE_CAPACITY) {
                SQLiteDatabase db = getWritableDatabase();
                // Purge oldest confirmed uploaded records first
                db.execSQL("DELETE FROM " + TABLE_NAME + " WHERE " + COL_UPLOAD_STATUS + " = 'UPLOADED' AND " +
                        COL_ID + " NOT IN (SELECT " + COL_ID + " FROM " + TABLE_NAME + " WHERE " + COL_UPLOAD_STATUS + " = 'UPLOADED' ORDER BY " + COL_ID + " DESC LIMIT " + MAX_UPLOADED_RETENTION + ");");
                Log.i(TAG, "Trimmed uploaded GPS records due to capacity threshold.");
            }
        } catch (Exception e) {
            Log.e(TAG, "Error trimming capacity", e);
        }
    }
}
