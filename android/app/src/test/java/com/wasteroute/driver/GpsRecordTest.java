package com.wasteroute.driver;

import org.junit.Test;

import static org.junit.Assert.*;

public class GpsRecordTest {

    @Test
    public void testGpsRecordDefaultsAndFields() {
        GpsRecord record = new GpsRecord();
        record.driverId = "12";
        record.truckId = "3";
        record.assignmentId = "3";
        record.latitude = 23.0225;
        record.longitude = 72.5714;
        record.accuracy = 6.5f;
        record.speed = 12.3f;
        record.bearing = 180.0f;
        record.provider = "fused";
        record.captureTime = 1700000000000L;
        record.sequenceNumber = 42L;

        assertNotNull(record.eventId);
        assertTrue(record.eventId.length() > 10);
        assertEquals("PENDING", record.uploadStatus);
        assertEquals(0, record.retryCount);
        assertEquals("12", record.driverId);
        assertEquals("3", record.truckId);
        assertEquals(23.0225, record.latitude, 0.0001);
        assertEquals(72.5714, record.longitude, 0.0001);
        assertEquals(42L, record.sequenceNumber);
        assertEquals(1700000000000L, record.captureTime);
    }
}
