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

| Variable | Description | Default   |
| - | - | - |
| `MOTOTWIST_BASE_URL` | The base URL at which MotoTwist is expecting to be hosted. | **This must be changed for production!** | `"http://localhost:8000"` |
| `MOTOTWIST_SECRET_KEY` | A long, random string used to cryptographically sign session cookies, preventing tampering. **This must be changed for production!** | `"changethis"` |
| `OSM_URL` | The URL template for the OpenStreetMap tile server, which provides the visual base map. | `"https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"` |
| `OSRM_URL` | The base URL for the OSRM routing engine, used for calculating routes for new Twists. | `"https://router.project-osrm.org"` |
| `TWIST_SIMPLIFICATION_TOLERANCE_M` | Sets the simplification tolerance for new Twist routes. A higher value (e.g., `"50m"`) removes more points and reduces storage size. Set to `"0m"` to disable. | `"30m"` |
| `DEFAULT_TWISTS_LOADED` | Sets the default number of Twists that are loaded at once. This affects both the infinitely scrolling Twist list and the map. | `20` |
| `MAX_TWISTS_LOADED` | Sets the maximum number of Twists that can be loaded at once. Setting a high number can have performance impacts. | `100` |

> [!WARNING]
> Keep in mind the [OSM Tile Policy](https://operations.osmfoundation.org/policies/tiles/) and [OSRM Usage Policy](https://map.project-osrm.org/about.html) if you do not plan on changing OSM_URL and/or OSRM_URL.

#### User Options
| Variable | Description | Default   |
| - | - | - |
| `MOTOTWIST_ADMIN_EMAIL` | The email to use for creating the initial admin user. Only affects initial container setup. **This should be changed for production!** | `"admin@admin.com"` |
| `MOTOTWIST_ADMIN_PASSWORD` | The password to assign to the initial admin user. Only affects initial container setup. Do not set to final wanted password. | `"password"` |
| `ALLOW_USER_REGISTRATION` | Whether or not users are allowed to register for your instance. If `False`, users may only be created by an administrator. | `False` |
| `DELETED_USER_NAME` | The name to use for resources created by a now deleted user. Prevents creating new users with this name. | `"Deleted User"` |

#### Database Options

These variables are required to connect to the PostgreSQL database.

| Variable | Description | Default   |
| - | - | - |
| `POSTGRES_HOST` | The hostname of the database server. In Docker, this should match the service name. | `"db"` |
| `POSTGRES_PORT` | The port the database is running on. | `5432` |
| `POSTGRES_DB` | The name of the database to connect to. | `"mototwist"` |
| `POSTGRES_USER` | The username for the database connection. | `"mototwist"` |
| `POSTGRES_PASSWORD` | The password for the database connection. **This must be changed for production!** | `"changethis"` |
| `REDIS_URL` | The URL to use to connect to Redis. Do not change unless you have an external instance. | `"redis://redis:6379"` |

#### Developer Options

These settings are useful for local development and debugging.

| Variable | Description | Default   |
| - | - | - |
| `LOG_LEVEL` | Sets the application's logging level. Common values are `DEBUG`, `INFO`, `WARNING`. | `INFO` |
| `DEBUG_MODE` | Enables the Debug Menu for administrators. Useful for saving/loading the database state. | `False` |
| `UVICORN_RELOAD` | If set to `true`, the server will automatically restart when code changes are detected. (Also requires mounting the source as a bind mount). | `False` |
| `MOTOTWIST_UPSTREAM` | Sets the repository to check updates from. Modify the default if you are making a fork. | `"amot-dev/mototwist"` |

### Usage

1.  **Drawing a New Twist:**
    When you a creating a Twist, your map cursor will be a crosshair. Waypoints can be placed, dragged, named, hidden, and deleted.

    a)  **Placing Waypoints:**
        Placing waypoints is as easy as clicking on the map in the desired location. Note that this should be on or close to a road. Waypoints not near roads will be snapped to a road in the final route.

    b)  **Dragging Waypoints:**
        Clicking and holding a waypoint will allow you to move it around.

    c)  **Naming Waypoints:**
        Clicking on a waypoint will reveal a number of options, including naming. I recommend naming all non-hidden waypoints.

    d)  **Hiding Waypoints:**
        Waypoints other than the first and last can be hidden. These waypoints will be used to determine the Twist's final route, but will not be part of the Twist itself. Use these as you would use dragging the route in Google Maps to achieve your desired route.

    e)  **Deleting Waypoints:**
        Finally, any waypoint can be deleted. Keep in mind that at least two waypoints are required to create a Twist.

2.  **Entering Twist Details:**
    Once your route is ready, additional details can be specified for the Twist, including the name and whether it is paved or unpaved.

> [!TIP]
> Twists should be predominantly paved or unpaved. If they're a combination of both, select whichever was "the main attraction" of the Twist, as each type has different criteria they're rated on. If both segments are fun, consider splitting the Twist!

3.  **Rating Twists:**
    From the sidebar, you can now rate your Twist! There's a number of different criteria you can rate it on, and hovering over each will give a brief description.

> [!TIP]
> With some, but minimal, technical knowledge, the available criteria can be changed! Eventually this may be configurable via environment variables. See [#11](https://github.com/amot-dev/mototwist/issues/11).

4.  **General Use:**

    a) Twists can be shown and hidden. Clicking on a Twist will take you to it, as well as reveal rating information.

    b) Waypoints and tracks on the map can be clicked to show their name.

    c) Twists and ratings can be deleted (but not modified).

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

5.  **Start Developing:**
    More thorough documentation for this is coming (maybe), but I'm sure you can figure it out.

> [!TIP]
> You may run mototwist in an interactive terminal with:
> ```bash
> docker compose run --service-ports mototwist
> ```

6.  **Migrate the database if needed:**
    If you make any model changes, you'll need to make a migration from them. All migrations are applied to the database on container restart.
    ```bash
    docker compose run --rm mototwist create-migration "Your very descriptive message"
    ```

> [!TIP]
> If you want to modify criteria, make changes to `PavedRating` and/or `UnpavedRating` in `app/models.py` and run a migration.
