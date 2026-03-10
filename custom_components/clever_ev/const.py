DOMAIN = "clever_ev"

BASE_URL = "https://mobileapp-backend.clever.dk/api/v6"
FIREBASE_SIGN_IN_URL = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword"
FIREBASE_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
FIREBASE_API_KEY = "AIzaSyCclOhPIonDgWAZoWfn3zInCB-G6h4aD-0"

CONF_REFRESH_TOKEN = "refresh_token"
CONF_EMAIL = "email"

STATIC_HEADERS = {
    "x-api-key": "Basic bW9iaWxlYXBwOmFwaWtleQ==",
    "app-platform": "iOS",
    "app-version": "9.1.0",
    "app-device": "iPhone15,2",
    "app-os": "26.3",
    "content-type": "application/json",
    "accept": "*/*",
    "accept-language": "en",
}

# Firebase Identity Toolkit requires iOS bundle ID headers (API key is iOS-restricted)
FIREBASE_HEADERS = {
    "x-ios-bundle-identifier": "com.clever.cleverapp",
    "x-client-version": "iOS/FirebaseSDK/12.4.0/FirebaseCore-iOS",
    "x-firebase-gmpid": "1:59507274536:ios:b44d817d7acda1f8b4161d",
    "user-agent": "FirebaseAuth.iOS/12.4.0 com.clever.cleverapp/9.1.0 iPhone/26.3 hw/iPhone15_2",
    "content-type": "application/json",
    "accept": "*/*",
    "accept-language": "en",
}

SCAN_INTERVAL_FAST = 60       # seconds — charger state, smart charging
SCAN_INTERVAL_SLOW = 1800     # seconds — consumption, pricing
