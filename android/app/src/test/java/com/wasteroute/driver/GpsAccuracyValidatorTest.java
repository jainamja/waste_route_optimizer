package com.wasteroute.driver;

import org.junit.Before;
import org.junit.Test;

import static org.junit.Assert.*;

public class GpsAccuracyValidatorTest {

    private GpsAccuracyValidator validator;

    @Before
    public void setUp() {
        validator = new GpsAccuracyValidator();
    }

    @Test
    public void testValidGpsReading() {
        long now = System.currentTimeMillis();
        GpsAccuracyValidator.ValidationResult res = validator.validate(23.0225, 72.5714, 8.5f, 5.2f, 90.0f, now, "gps");
        assertTrue(res.isValid);
        assertTrue(res.isLiveEligible);
        assertFalse(res.isWeakAccuracy);
        assertEquals("LIVE", res.status);
    }

    @Test
    public void testInvalidLatitudeRejection() {
        long now = System.currentTimeMillis();
        GpsAccuracyValidator.ValidationResult resHigh = validator.validate(95.0, 72.5714, 10.0f, 0f, 0f, now, "gps");
        assertFalse(resHigh.isValid);
        assertEquals("INVALID", resHigh.status);

        GpsAccuracyValidator.ValidationResult resLow = validator.validate(-91.5, 72.5714, 10.0f, 0f, 0f, now, "gps");
        assertFalse(resLow.isValid);
    }

    @Test
    public void testInvalidLongitudeRejection() {
        long now = System.currentTimeMillis();
        GpsAccuracyValidator.ValidationResult resEast = validator.validate(23.0, 185.0, 10.0f, 0f, 0f, now, "gps");
        assertFalse(resEast.isValid);

        GpsAccuracyValidator.ValidationResult resWest = validator.validate(23.0, -181.0, 10.0f, 0f, 0f, now, "gps");
        assertFalse(resWest.isValid);
    }

    @Test
    public void testNullIslandRejection() {
        long now = System.currentTimeMillis();
        GpsAccuracyValidator.ValidationResult res = validator.validate(0.0, 0.0, 5.0f, 0f, 0f, now, "gps");
        assertFalse(res.isValid);
        assertTrue(res.reason.contains("Null island"));
    }

    @Test
    public void testStaleFixRejectionForLiveTracking() {
        long fiveMinutesAgo = System.currentTimeMillis() - 300_000L;
        GpsAccuracyValidator.ValidationResult res = validator.validate(23.0225, 72.5714, 10.0f, 0f, 0f, fiveMinutesAgo, "gps");
        assertTrue(res.isValid); // Still valid for historical queue
        assertFalse(res.isLiveEligible); // Not live
        assertEquals("STALE", res.status);
    }

    @Test
    public void testWeakAccuracyClassification() {
        long now = System.currentTimeMillis();
        // 45 meters: weak but acceptable for degraded live tracking
        GpsAccuracyValidator.ValidationResult resWeak = validator.validate(23.0225, 72.5714, 45.0f, 0f, 0f, now, "gps");
        assertTrue(resWeak.isValid);
        assertTrue(resWeak.isLiveEligible);
        assertTrue(resWeak.isWeakAccuracy);
        assertEquals("WEAK_GPS", resWeak.status);

        // 150 meters: unusable accuracy, rejected for live position
        GpsAccuracyValidator.ValidationResult resUnusable = validator.validate(23.0225, 72.5714, 150.0f, 0f, 0f, now, "gps");
        assertTrue(resUnusable.isValid);
        assertFalse(resUnusable.isLiveEligible);
        assertEquals("WEAK_ACCURACY", resUnusable.status);
    }

    @Test
    public void testMissingSpeedAndBearingHandling() {
        long now = System.currentTimeMillis();
        GpsAccuracyValidator.ValidationResult res = validator.validate(23.0225, 72.5714, 10.0f, 0.0f, 0.0f, now, "gps");
        assertTrue(res.isValid);
        assertTrue(res.isLiveEligible);
    }

    @Test
    public void testSuspiciousGpsJumpDetection() {
        long now = System.currentTimeMillis();
        validator.validate(23.0225, 72.5714, 10.0f, 10.0f, 0.0f, now, "gps");

        // 2 seconds later, jump ~2km north (latitude 23.0405 vs 23.0225 is ~2000m)
        // 2000m in 2s = 1000 m/s >> 44.4 m/s max threshold
        GpsAccuracyValidator.ValidationResult resJump = validator.validate(23.0405, 72.5714, 10.0f, 10.0f, 0.0f, now + 2000L, "gps");
        assertTrue(resJump.isValid);
        assertFalse(resJump.isLiveEligible);
        assertEquals("SUSPICIOUS_JUMP", resJump.status);
    }

    @Test
    public void testHaversineDistanceAccuracy() {
        // Distance between two known points in Ahmedabad:
        // Point A: 23.0225, 72.5714
        // Point B: 23.0325, 72.5714 (0.01 deg lat diff ~ 1112 meters)
        double dist = GpsAccuracyValidator.haversineMeters(23.0225, 72.5714, 23.0325, 72.5714);
        assertTrue("Distance should be ~1112m", dist > 1100 && dist < 1125);
    }
}
