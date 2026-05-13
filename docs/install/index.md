---
next:
    text: Environment Variables
    link: /install/env.md
---


# Installation Guide


## Prerequisites

To get MotoTwist application running, you will need to have **Docker** and **Docker Compose** installed on your system.

- **Docker:** [Installation Guide](https://docs.docker.com/get-docker/)
- **Docker Compose:** [Installation Guide](https://docs.docker.com/compose/install/)


## Steps

1.  **Download the latest compose file:** 
    Place `docker-compose.yml` in its own directory.

    <<< @/../docker-compose.yml

2.  **Configure environment variables:**
    Using `.env.example` as a starting point, configure your desired environment variables. These should be placed in a `.env` file in the same directory as your `docker-compose.yml` file.

    <<< @/../.env.example {dotenv}

    > [!WARNING]
    > Keep in mind the [OSM Tile Policy](https://operations.osmfoundation.org/policies/tiles/) and [OSRM Usage Policy](https://map.project-osrm.org/about.html) if you do not plan on changing OSM_URL and/or OSRM_URL.

    See the full list of environment variables [here](/install/env.md).

3.  **(Optional) Configure criteria:**
    MotoTwist allows using whatever criteria you choose for rating. See [custom criteria](/install/criteria.md) for more information.


3.  **Run the containers:**
    From the directory containing your `docker-compose.yml`, run:
    ```bash
    docker compose up
    ```

4.  **Access the application:**
    Open your web browser and navigate to [`http://localhost:8000`](http://localhost:8000).
