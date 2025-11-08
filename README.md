# MotoTwist

_Track the Thrill. Rate the Road._

MotoTwist is the ultimate companion for every motorcycle enthusiast. Discover, track, and save your most epic journeys. MotoTwist allows you to rate routes on key criteria like scenery, road quality, and twistiness. Or, for the offroad enthusiasts, you can rate them on surface consistency, technicality, and general flow.

Share your favorite roads with a community of fellow riders and find your next great adventure, recommended by those who've ridden it before.


## Screenshots
![A screenshot of MotoTwist, featuring an expanded Twist and the filter dropdown](docs/screenshot-filters.png)
![A screenshot of MotoTwist, features an expanded unapaved Twist and a few unexpanded Twists](docs/screenshot-unpaved.png)


## Getting Started

### Prerequisites

To get this application running, you will need to have **Docker** and **Docker Compose** installed on your system.

* **Docker:** [Installation Guide](https://docs.docker.com/get-docker/)
* **Docker Compose:** [Installation Guide](https://docs.docker.com/compose/install/)


### Installation

1.  **Download the latest compose file:** 
    Place 
    [`docker-compose.yml`](https://github.com/amot-dev/mototwist/blob/master/docker-compose.yml) in its own directory.

2.  **Configure environment variables:**
    Using [`.env.example`](https://github.com/amot-dev/mototwist/blob/master/.env.example) as a starting point, configure your desired environment variables. These should be placed in a `.env` file in the same directory as your `docker-compose.yml` file.

3.  **Run the containers:**
    From the directory containing your `docker-compose.yml`, run:
    ```bash
    docker compose up -d
    ```

4.  **Access the application:**
    Open your web browser and navigate to `http://localhost:8000`.


### Environment Variables

Below is an overview of all available environment variables for MotoTwist.


#### Application Options

| Variable | Description | Default |
| - | - | - |
| `MOTOTWIST_INSTANCE_NAME` | The friendly name for your instance. Used in email templates and the site title/header. | `"MotoTwist"` |
| `MOTOTWIST_BASE_URL` | The base URL at which MotoTwist is expecting to be hosted. | **This must be changed for production!** | `"http://localhost:8000"` |
| `MOTOTWIST_SECRET_KEY` | A long, random string used to cryptographically sign session cookies, preventing tampering. **This must be changed for production!** | `"changethis"` |
| `OSM_URL` | The URL template for the OpenStreetMap tile server, which provides the visual base map. | `"https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"` |
| `OSRM_URL` | The base URL for the OSRM routing engine, used for calculating routes for new Twists. | `"https://router.project-osrm.org"` |
| `TWIST_SIMPLIFICATION_TOLERANCE_M` | Sets the simplification tolerance for new Twist routes. A higher value (e.g., `"50m"`) removes more points and reduces storage size. Set to `"0m"` to disable. | `"30m"` |
| `DEFAULT_TWISTS_LOADED` | Sets the default number of Twists that are loaded at once. This affects both the infinitely scrolling Twist list and the map. | `20` |
| `MAX_TWISTS_LOADED` | Sets the maximum number of Twists that can be loaded at once. Setting a high number can have performance impacts. | `100` |
| `RATINGS_FETCHED_PER_QUERY` | Sets the number of ratings fetched per query during the infinite scroll when viewing all ratings. Setting it too low or high can have performance impacts. | `20` |

> [!WARNING]
> Keep in mind the [OSM Tile Policy](https://operations.osmfoundation.org/policies/tiles/) and [OSRM Usage Policy](https://map.project-osrm.org/about.html) if you do not plan on changing OSM_URL and/or OSRM_URL.


#### User Options
| Variable | Description | Default |
| - | - | - |
| `MOTOTWIST_ADMIN_EMAIL` | The email to use for creating the initial admin user. Only affects initial container setup. **This should be changed for production!** | `"admin@admin.com"` |
| `MOTOTWIST_ADMIN_PASSWORD` | The password to assign to the initial admin user. Only affects initial container setup. Do not set to final wanted password. | `"password"` |
| `ALLOW_USER_REGISTRATION` | Whether or not users are allowed to register for your instance. If `False`, users may only be created by an administrator. | `False` |
| `DELETED_USER_NAME` | The name to use for resources created by a now deleted user. Prevents creating new users with this name. | `"Deleted User"` |
| `AUTH_COOKIE_MAX_AGE` | The number of seconds a login session should be valid. Set to 0 to disable the limit. | `3600` |
| `AUTH_SLIDING_WINDOW_ENABLED` | Whether or not login sessions should silently re-authenticate themselves. Even if disabled, users can renew their sessions via the expirty warning if that is enabled. | `True` |
| `AUTH_EXPIRY_WARNING_OFFSET` | The number of seconds before the login session ends that the user is warned about it. Set to 0 to disable the warning | `300` |


#### Email Options
| Variable | Description | Default |
| - | - | - |
| `EMAIL_ENABLED` | Set to `True` to enable all email functionality (e.g., verification, password resets). Requires setting all `SMTP_` variables. | `False` |
| `SMTP_HOST` | The hostname of your SMTP server. Required if `EMAIL_ENABLED` is `True`. | `"smtp.example.com"` |
| `SMTP_PORT` | The port for your SMTP server. Typically 587 (TLS) or 465 (SSL). | `587` |
| `SMTP_USERNAME` | The username for authenticating with your SMTP server. Required if `EMAIL_ENABLED` is `True`. | `"changethis"` |
| `SMTP_PASSWORD` | The password for authenticating with your SMTP server. Required if `EMAIL_ENABLED` is `True`. | `"changethis"` |
| `SMTP_FROM_EMAIL` | The email address to use in the 'From' field for all outgoing emails. Must be a valid email for your SMTP server. | `"noreply@example.com"` |
| `SMTP_USE_TLS` | Whether to use Transport Layer Security (TLS) when connecting to the SMTP host. Should be `True` for port 587. | `True` |


#### Database Options

These variables are required to connect to the PostgreSQL database.

| Variable | Description | Default |
| - | - | - |
| `POSTGRES_HOST` | The hostname of the database server. In Docker, this should match the service name. | `"db"` |
| `POSTGRES_PORT` | The port the database is running on. | `5432` |
| `POSTGRES_DB` | The name of the database to connect to. | `"mototwist"` |
| `POSTGRES_USER` | The username for the database connection. | `"mototwist"` |
| `POSTGRES_PASSWORD` | The password for the database connection. **This must be changed for production!** | `"changethis"` |
| `REDIS_URL` | The URL to use to connect to Redis. Do not change unless you have an external instance. | `"redis://redis:6379"` |


#### Developer Options

These settings are useful for local development and debugging.

| Variable | Description | Default |
| - | - | - |
| `LOG_LEVEL` | Sets the application's logging level. Common values are `DEBUG`, `INFO`, `WARNING`. | `INFO` |
| `DEBUG_MODE` | Enables the Debug Menu for administrators. Useful for saving/loading the database state. | `False` |
| `UVICORN_RELOAD` | If set to `true`, the server will automatically restart when code changes are detected. (Also requires mounting the source as a bind mount). | `False` |
| `MOTOTWIST_UPSTREAM` | Sets the repository to check updates from. Modify the default if you are making a fork. | `"amot-dev/mototwist"` |


### Usage
1. **User Management:**
    Twists may be viewed without an account, but creating a Twist requires one. If enabled by an admin, you can create your own account from the login modal.

    a)  **Verification:**
        New accounts need to be verified if `EMAIL_ENABLED` is `True`. Most actions can only be performed by verified users.

    b)  **Deactivation:**
        Accounts may be deactivated. Only an admin can reactivate it.

    c)  **Deletion:**
        Accounts may be deleted. It will be gone forever, but Twists and ratings will remain.

    d)  **Promotion:**
        Only an admin can create or promote more admins. Initially, MotoTwist starts up with exactly one admin user.

2.  **Drawing a New Twist:**
    When you a creating a Twist, your map cursor will be a crosshair. Waypoints can be placed, dragged, named, hidden, and deleted.

    a)  **Placing Waypoints:**
        Placing waypoints is as easy as clicking on the map in the desired location. Note that this should be on or close to a road. Waypoints not near roads will be snapped to a road in the final route.

    b)  **Dragging Waypoints:**
        Clicking and holding a waypoint will allow you to move it around.

    c)  **Naming Waypoints:**
        Clicking on a waypoint will allow naming it. The first and last waypoints must be named.

    d)  **Shaping Points:**
        Waypoints other than the first and last are shaping points by default. These waypoints will be used to determine the Twist's final route, but will never be displayed. Use these as you would use dragging the route in Google Maps to achieve your desired route. You may name them to have them be displayed as part of the Twist.

    e)  **Deleting Waypoints:**
        Clicking on a waypoint will allow deleting it. Keep in mind that at least two waypoints are required to create a Twist.

3.  **Entering Twist Details:**
    Once your route is ready, additional details can be specified for the Twist, including the name and whether it is paved or unpaved.

> [!TIP]
> Twists should be predominantly paved or unpaved. If they're a combination of both, select whichever was "the main attraction" of the Twist, as each type has different criteria they're rated on. If both segments are fun, consider splitting the Twist!

4.  **Rating Twists:**
    From the sidebar, you can now rate your Twist! There's a number of different criteria you can rate it on, and hovering over each will give a brief description.

> [!TIP]
> With some, but minimal, technical knowledge, the available criteria can be changed! Eventually this may be configurable via environment variables. See [#11](https://github.com/amot-dev/mototwist/issues/11).

5.  **Searching/Filtering:**
    Twists may be searched and filtered by a few different criteria. Ratings can be filtered.

6.  **General Use:**

    a) Clicking on a Twist will reveal more information about it.

    b) Double clicking on a Twist will take you to it on the map.

    c) Twists can be hidden.

    d) Twists and Waypoints on the map can be clicked to show their name.

    e) Twists and ratings can be deleted (but not modified).


## Developing

Follow these steps to set up and run the application in development mode.

1.  **Clone the repository:**
    ```bash
    git clone git@github.com:amot-dev/MotoTwist.git
    cd MotoTwist
    ```

2.  **Configure environment variables:**
    Find `.env.example` in the project's root directory. Copy this into your own `.env` file. Uncomment the developer options.

3.  **Build and run the containers:**
    Use Docker Compose to build the image and start the services. A handy `build.sh` script exists that does just this, as well as a few other things.

4.  **Access the application:**
    Open your web browser and navigate to `http://localhost:8000`.

5.  **Load mock data:**
    With debug mode enabled, admin users will have access to the debug page, which allows saving and loading the current database state, as well as seed ratings.

> [!TIP]
> Saving ratings is mostly useless unless you're using debug mode to migrate your data. Prefer saving Twists and seeding rating data after loading.

6.  **Start Developing:**
    More thorough documentation for this is coming (maybe), but I'm sure you can figure it out.

> [!TIP]
> You may run mototwist in an interactive terminal with:
> ```bash
> docker compose run --service-ports mototwist
> ```

> [!TIP]
> Email functionality can be tested with MailHog (included by `docker-compose.override.yml`):
> ```bash
> # Email Options
> EMAIL_ENABLED=True
> SMTP_HOST="mailhog"
> SMTP_PORT=1025
> SMTP_USERNAME="anything"
> SMTP_PASSWORD="anything"
> SMTP_FROM_EMAIL="anything@anything.com"
> SMTP_USE_TLS=False
> ```
> Navigate to `http://localhost:8025` to view the fake inbox.

7.  **Migrate the database if needed:**
    If you make any model changes, you'll need to make a migration from them. All migrations are applied to the database on container restart.
    ```bash
    docker compose run --rm mototwist create-migration "Your very descriptive message"
    ```

> [!TIP]
> If you want to modify criteria, make changes to `PavedRating` and/or `UnpavedRating` in `app/models.py` and run a migration.
