# Environment Variables


## Application Options

| Variable | Description | Default |
| - | - | - |
| `MOTOTWIST_INSTANCE_NAME` | The friendly name for your instance. Used in email templates and the site title/header. | `"MotoTwist"` |
| `MOTOTWIST_BASE_URL` | The base URL at which MotoTwist is expecting to be hosted. **This must be changed for production!** | `"http://localhost:8000"` |
| `MOTOTWIST_SECRET_KEY` | A long, random string used to cryptographically sign session cookies, preventing tampering. **This must be changed for production!** | `"changethis"` |
| `NEW_VERSION_NOTIFICATION_INTERVAL_S` | The duration in seconds between new version notifications, per user. Set to `-1` to disable notifications. | `86400` |
| `OSM_URL` | The URL template for the OpenStreetMap tile server, which provides the visual base map. | `"https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"` |
| `OSRM_URL` | The base URL for the OSRM routing engine, used for calculating routes for new Twists. | `"https://router.project-osrm.org"` |
| `TWIST_SIMPLIFICATION_TOLERANCE_M` | Sets the simplification tolerance for new Twist routes. [More details](#storage-vs-accuracy-route-simplification). Set to `"0m"` to disable. | `"5m"` |
| `AVERAGE_ROUNDING_DIGITS` | Sets number of digits after the decimal to round to when calculating and displaying rating averages. | `1` |
| `INSIGNIFICANT_RIDE_COUNT_PERCENTILE` | Sets the percentile of ride counts used to establish the confidence threshold for sorting. [More details](#tuning-the-sorting-algorithm). | `25` |
| `TRENDING_TIMEFRAME_DAYS` | Sets the window (in days) used to calculate the "Trending" score based on recent ride activity. | `7` |
| `HIDDEN_GEM_AVERAGE_MULTIPLIER` | The multiplier applied to the global average to determine the minimum quality of a "Hidden Gem". [More details](#tuning-the-sorting-algorithm). | `1.25` |
| `DEFAULT_TWISTS_LOADED` | Sets the default number of Twists that are loaded at once. This affects both the infinitely scrolling Twist list and the map. | `20` |
| `RIDES_FETCHED_PER_QUERY` | Sets the number of rides fetched per query during the infinite scroll when viewing all rides. Setting it too low or high can have performance impacts. | `20` |

> [!WARNING]
> Keep in mind the [OSM Tile Policy](https://operations.osmfoundation.org/policies/tiles/) and [OSRM Usage Policy](https://map.project-osrm.org/about.html) if you do not plan on changing OSM_URL and/or OSRM_URL.


## User Options
| Variable | Description | Default |
| - | - | - |
| `MOTOTWIST_ADMIN_EMAIL` | The email to use for creating the initial admin user. Only affects initial container setup. **This should be changed for production!** | `"admin@admin.com"` |
| `MOTOTWIST_ADMIN_PASSWORD` | The password to assign to the initial admin user. Only affects initial container setup. Do not set to final wanted password. | `"password"` |
| `ALLOW_USER_REGISTRATION` | Whether or not users are allowed to register for your instance. If `False`, users may only be created by an administrator. | `False` |
| `DELETED_USER_NAME` | The name to use for resources created by a now deleted user. Prevents creating new users with this name. | `"Deleted User"` |
| `AUTH_COOKIE_MAX_AGE` | The number of seconds a login session should be valid. Set to 0 to disable the limit. | `3600` |
| `AUTH_SLIDING_WINDOW_ENABLED` | Whether or not login sessions should silently re-authenticate themselves. Even if disabled, users can renew their sessions via the expirty warning if that is enabled. | `True` |
| `AUTH_EXPIRY_WARNING_OFFSET` | The number of seconds before the login session ends that the user is warned about it. Set to 0 to disable the warning | `300` |


## Email Options
| Variable | Description | Default |
| - | - | - |
| `EMAIL_ENABLED` | Set to `True` to enable all email functionality (e.g., verification, password resets). Requires setting all `SMTP_` variables. While disabled, MotoTwist treats unverified users as verified. | `False` |
| `SMTP_HOST` | The hostname of your SMTP server. Required if `EMAIL_ENABLED` is `True`. | `"smtp.example.com"` |
| `SMTP_PORT` | The port for your SMTP server. Typically 587 (TLS) or 465 (SSL). | `587` |
| `SMTP_USERNAME` | The username for authenticating with your SMTP server. Required if `EMAIL_ENABLED` is `True`. | `"changethis"` |
| `SMTP_PASSWORD` | The password for authenticating with your SMTP server. Required if `EMAIL_ENABLED` is `True`. | `"changethis"` |
| `SMTP_FROM_EMAIL` | The email address to use in the 'From' field for all outgoing emails. Must be a valid email for your SMTP server. | `"noreply@example.com"` |
| `SMTP_USE_TLS` | Whether to use Transport Layer Security (TLS) when connecting to the SMTP host. Should be `True` for port 587. | `True` |


## Database Options

These variables are required to connect to the PostgreSQL database.

| Variable | Description | Default |
| - | - | - |
| `POSTGRES_HOST` | The hostname of the database server. In Docker, this should match the service name. | `"db"` |
| `POSTGRES_PORT` | The port the database is running on. | `5432` |
| `POSTGRES_DB` | The name of the database to connect to. | `"mototwist"` |
| `POSTGRES_USER` | The username for the database connection. | `"mototwist"` |
| `POSTGRES_PASSWORD` | The password for the database connection. **This must be changed for production!** | `"changethis"` |
| `REDIS_URL` | The URL to use to connect to Redis. Do not change unless you have an external instance. | `"redis://redis:6379"` |


## Developer Options

These settings are useful for local development and debugging.

| Variable | Description | Default |
| - | - | - |
| `LOG_LEVEL` | Sets the application's logging level. Common values are `DEBUG`, `INFO`, `WARNING`. | `INFO` |
| `DEBUG_MODE` | Enables the Debug Menu for administrators. Useful for saving/loading the database state. | `False` |
| `UVICORN_RELOAD` | If set to `true`, the server will automatically restart when code changes are detected. (Also requires mounting the source as a bind mount). | `False` |
| `MOTOTWIST_UPSTREAM` | Sets the repository to check updates from. Modify the default if you are making a fork. | `"amot-dev/mototwist"` |
