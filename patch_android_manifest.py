import io

with io.open('android/app/src/main/AndroidManifest.xml', 'r', encoding='utf-8') as f:
    text = f.read()

# Add permissions
if 'android.permission.FOREGROUND_SERVICE' not in text:
    text = text.replace('</manifest>', '''
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION" />
</manifest>''')

# Add service
if '.LocationService' not in text:
    text = text.replace('</application>', '''
        <service
            android:name=".LocationService"
            android:enabled="true"
            android:exported="false"
            android:foregroundServiceType="location" />
    </application>''')

with io.open('android/app/src/main/AndroidManifest.xml', 'w', encoding='utf-8', newline='') as f:
    f.write(text)

with io.open('android/app/build.gradle', 'r', encoding='utf-8') as f:
    build = f.read()

if 'play-services-location' not in build:
    build = build.replace("implementation project(':capacitor-cordova-android-plugins')", "implementation project(':capacitor-cordova-android-plugins')\n    implementation 'com.google.android.gms:play-services-location:21.0.1'")
    with io.open('android/app/build.gradle', 'w', encoding='utf-8', newline='') as f:
        f.write(build)

print("Manifest and Build updated")
