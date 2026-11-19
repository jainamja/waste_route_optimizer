const { initializeTestEnvironment, assertFails, assertSucceeds } = require('@firebase/rules-unit-testing');
const fs = require('fs');

async function runEmulatorTestSuite() {
    console.log("================================================================================");
    console.log("       TRASHTREKYX — REALTIME DATABASE EMULATOR SECURITY TEST SUITE             ");
    console.log("================================================================================\n");

    const DB_URL = "https://wasteroutelive-default-rtdb.firebaseio.com";
    const rulesContent = fs.readFileSync("firebase.database.rules.json", "utf8");

    const testEnv = await initializeTestEnvironment({
        projectId: "wasteroutelive",
        database: {
            host: "127.0.0.1",
            port: 9000,
            rules: rulesContent
        }
    });

    let passedCount = 0;
    let failedCount = 0;

    async function check(name, testFn) {
        process.stdout.write(`[TEST] ${name.padEnd(65)} ... `);
        try {
            await testFn();
            console.log("PASSED");
            passedCount++;
        } catch (err) {
            console.log("FAILED");
            console.error(`       Error: ${err.message || err}`);
            failedCount++;
        }
    }

    try {
        const unauth = testEnv.unauthenticatedContext().database(DB_URL);
        const admin = testEnv.authenticatedContext("admin_user", { role: "ADMIN", admin_id: "99" }).database(DB_URL);
        const driver1 = testEnv.authenticatedContext("driver_1", { role: "DRIVER", driver_id: "1", truck_id: "1" }).database(DB_URL);
        const driver2 = testEnv.authenticatedContext("driver_2", { role: "DRIVER", driver_id: "2", truck_id: "2" }).database(DB_URL);
        const driverUnassigned = testEnv.authenticatedContext("driver_unassigned", { role: "DRIVER", driver_id: "3", truck_id: null }).database(DB_URL);
        const driver1ReassignedTo2 = testEnv.authenticatedContext("driver_1_reassigned", { role: "DRIVER", driver_id: "1", truck_id: "2" }).database(DB_URL);

        // Pre-seed baseline data via Admin
        await admin.ref("trucks/1").set({
            driverId: "1",
            driverName: "Driver One",
            name: "Truck Alpha",
            status: "online",
            currentLat: 28.5355,
            currentLng: 77.3910
        });
        await admin.ref("trucks/2").set({
            driverId: "2",
            driverName: "Driver Two",
            name: "Truck Beta",
            status: "online",
            currentLat: 28.6139,
            currentLng: 77.2090
        });
        await admin.ref("routes/route_1/stops/101").set({
            id: 101,
            name: "Hospital Stop",
            lat: 28.5355,
            lng: 77.3910,
            status: "PENDING"
        });
        await admin.ref("routes/route_2/stops/201").set({
            id: 201,
            name: "Mall Stop",
            lat: 28.6139,
            lng: 77.2090,
            status: "PENDING"
        });

        // Test 1: Unauthenticated access is denied everywhere
        await check("1. Unauthenticated read / write denied on trucks, routes, status", async () => {
            await assertFails(unauth.ref("trucks/1").get());
            await assertFails(unauth.ref("trucks/1/currentLat").set(28.5));
            await assertFails(unauth.ref("routes/route_1").get());
            await assertFails(unauth.ref("routes/route_1/stops/101/status").set("COMPLETED"));
            await assertFails(unauth.ref("driver_locations/1").get());
            await assertFails(unauth.ref("system_status").get());
        });

        // Test 2: Driver can read assigned truck
        await check("2. Driver 1 can read assigned truck 1", async () => {
            await assertSucceeds(driver1.ref("trucks/1").get());
        });

        // Test 3: Driver cannot read another truck or list all trucks
        await check("3. Driver 1 cannot read truck 2 or list all trucks", async () => {
            await assertFails(driver1.ref("trucks/2").get());
            await assertFails(driver1.ref("trucks").get());
        });

        // Test 4: Driver can update permitted GPS telemetry fields
        await check("4. Driver 1 can update permitted GPS fields on truck 1", async () => {
            await assertSucceeds(driver1.ref("trucks/1/currentLat").set(28.5356));
            await assertSucceeds(driver1.ref("trucks/1/currentLng").set(77.3911));
            await assertSucceeds(driver1.ref("trucks/1/speed").set(35.5));
            await assertSucceeds(driver1.ref("trucks/1/heading").set(180));
            await assertSucceeds(driver1.ref("trucks/1/status").set("active"));
            await assertSucceeds(driver1.ref("trucks/1").update({
                currentLat: 28.5360,
                currentLng: 77.3915,
                speed: 25.0,
                status: "online"
            }));
        });

        // Test 5: Driver cannot overwrite truck administrative fields
        await check("5. Driver 1 cannot overwrite administrative fields or truck root", async () => {
            await assertFails(driver1.ref("trucks/1/driverId").set("999"));
            await assertFails(driver1.ref("trucks/1/driverName").set("Malicious Driver"));
            await assertFails(driver1.ref("trucks/1/name").set("Compromised Truck"));
            await assertFails(driver1.ref("trucks/1").set({ currentLat: 28.5 }));
            await assertFails(driver1.ref("trucks/1").remove());
        });

        // Test 6: Driver cannot change another truck's GPS
        await check("6. Driver 1 cannot update GPS telemetry on truck 2", async () => {
            await assertFails(driver1.ref("trucks/2/currentLat").set(28.5355));
            await assertFails(driver1.ref("trucks/2/currentLng").set(77.3910));
            await assertFails(driver1.ref("trucks/2/status").set("offline"));
        });

        // Test 7: Driver can update permitted stop status on assigned route
        await check("7. Driver 1 can update stop status on assigned route_1", async () => {
            await assertSucceeds(driver1.ref("routes/route_1/stops/101/status").set("COMPLETED"));
            await assertSucceeds(driver1.ref("routes/route_1/stops/101/status").set("SKIPPED"));
            await assertSucceeds(driver1.ref("routes/route_1/stops/101/status").set("PENDING"));
        });

        // Test 8: Driver cannot modify route coordinates or customer info
        await check("8. Driver 1 cannot modify stop coordinates or customer info", async () => {
            await assertFails(driver1.ref("routes/route_1/stops/101/lat").set(99.0));
            await assertFails(driver1.ref("routes/route_1/stops/101/lng").set(99.0));
            await assertFails(driver1.ref("routes/route_1/stops/101/name").set("Spoofed Name"));
            await assertFails(driver1.ref("routes/route_1/stops/101").set({ status: "COMPLETED" }));
            await assertFails(driver1.ref("routes/route_1/stops/101").remove());
        });

        // Test 9: Driver cannot modify another driver's route
        await check("9. Driver 1 cannot modify or read another driver's route_2", async () => {
            await assertFails(driver1.ref("routes/route_2/stops/201/status").set("COMPLETED"));
            await assertFails(driver1.ref("routes/route_2").get());
            await assertFails(driver1.ref("routes").get());
        });

        // Test 10: Driver cannot write another driver's location
        await check("10. Driver 1 cannot write to driver_locations/2", async () => {
            await assertSucceeds(driver1.ref("driver_locations/1/currentLat").set(28.5355));
            await assertSucceeds(driver1.ref("driver_locations/1/status").set("online"));
            await assertFails(driver1.ref("driver_locations/2/currentLat").set(28.5355));
            await assertFails(driver1.ref("driver_locations/2/status").set("online"));
            await assertFails(driver1.ref("driver_locations").get());
        });

        // Test 11: Driver cannot read or write restricted system status
        await check("11. Driver 1 cannot read or write system_status or settings", async () => {
            await assertFails(driver1.ref("system_status").get());
            await assertFails(driver1.ref("system_status").set({ active: true }));
            await assertFails(driver1.ref("settings").get());
            await assertFails(driver1.ref("settings/auto_assign").set(true));
        });

        // Test 12: Admin can perform authorized management operations
        await check("12. Admin can manage trucks, routes, and system status", async () => {
            await assertSucceeds(admin.ref("trucks/1/driverId").set("10"));
            await assertSucceeds(admin.ref("trucks/1/driverName").set("Updated Driver"));
            await assertSucceeds(admin.ref("routes/route_1/stops/101/name").set("Updated Customer"));
            await assertSucceeds(admin.ref("routes/route_1/stops/102").set({ id: 102, status: "PENDING" }));
            await assertSucceeds(admin.ref("system_status").set({ healthy: true, maintenance: false }));
            await assertSucceeds(admin.ref("system_status").get());
            await assertSucceeds(admin.ref("trucks").get());
            await assertSucceeds(admin.ref("routes").get());
        });

        // Test 13: Invalid coordinates and invalid data types are rejected
        await check("13. Invalid coordinates, speed, and status values rejected", async () => {
            await assertFails(driver1.ref("trucks/1/currentLat").set(91.5));
            await assertFails(driver1.ref("trucks/1/currentLat").set(-91.5));
            await assertFails(driver1.ref("trucks/1/currentLat").set("not_a_number"));
            await assertFails(driver1.ref("trucks/1/currentLng").set(181.0));
            await assertFails(driver1.ref("trucks/1/currentLng").set(-181.0));
            await assertFails(driver1.ref("trucks/1/speed").set(-10));
            await assertFails(driver1.ref("trucks/1/speed").set(500));
            await assertFails(driver1.ref("trucks/1/heading").set(-5));
            await assertFails(driver1.ref("trucks/1/heading").set(400));
            await assertFails(driver1.ref("trucks/1/status").set("invalid_status_code"));
            await assertFails(driver1.ref("routes/route_1/stops/101/status").set("DESTROYED"));
            await assertFails(driver1.ref("routes/route_1/stops/101/status").set(12345));
        });

        // Test 14: Unknown fields and unauthorized write paths are rejected
        await check("14. Unknown fields and arbitrary root paths rejected", async () => {
            await assertFails(driver1.ref("trucks/1/unknown_telemetry").set("exploit"));
            await assertFails(driver1.ref("driver_locations/1/unapproved_field").set(123));
            await assertFails(driver1.ref("arbitrary_root_node").set({ hacked: true }));
            await assertFails(driver1.ref("injections").set("malicious"));
        });

        // Test 15: Unassigned driver is denied access to trucks and routes
        await check("15. Unassigned driver (truck_id: null) rejected from trucks, routes, and telemetry", async () => {
            await assertFails(driverUnassigned.ref("trucks/1").get());
            await assertFails(driverUnassigned.ref("trucks/1/currentLat").set(28.5355));
            await assertFails(driverUnassigned.ref("trucks/2").get());
            await assertFails(driverUnassigned.ref("trucks/2/currentLat").set(28.6139));
            await assertFails(driverUnassigned.ref("routes/route_1").get());
            await assertFails(driverUnassigned.ref("routes/route_1/stops/101/status").set("COMPLETED"));
            await assertFails(driverUnassigned.ref("routes/route_2/stops/201/status").set("COMPLETED"));
            await assertFails(driverUnassigned.ref("driver_locations/1/currentLat").set(28.5355));
            // But can write to its own driver_locations/3
            await assertSucceeds(driverUnassigned.ref("driver_locations/3/currentLat").set(28.5355));
            await assertSucceeds(driverUnassigned.ref("driver_locations/3/status").set("online"));
        });

        // Test 16: Driver-to-truck reassignment enforces new truck boundaries immediately
        await check("16. Driver reassignment updates write access (Truck 1 denied, Truck 2 permitted)", async () => {
            // Driver 1 freshly reassigned to Truck 2
            await assertFails(driver1ReassignedTo2.ref("trucks/1/currentLat").set(28.5356));
            await assertFails(driver1ReassignedTo2.ref("routes/route_1/stops/101/status").set("COMPLETED"));
            await assertSucceeds(driver1ReassignedTo2.ref("trucks/2/currentLat").set(28.6140));
            await assertSucceeds(driver1ReassignedTo2.ref("trucks/2/currentLng").set(77.2091));
            await assertSucceeds(driver1ReassignedTo2.ref("routes/route_2/stops/201/status").set("COMPLETED"));
        });

    } finally {
        await testEnv.cleanup();
    }

    console.log("\n================================================================================");
    console.log(`SUMMARY: ${passedCount} PASSED, ${failedCount} FAILED out of ${passedCount + failedCount} TESTS`);
    console.log("================================================================================\n");

    if (failedCount > 0) {
        process.exit(1);
    }
}

runEmulatorTestSuite().catch(e => {
    console.error("Fatal test error:", e);
    process.exit(1);
});
