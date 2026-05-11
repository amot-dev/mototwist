---
next:
    text: Environment Variables
    link: /install/env.md
---


# Installation Guide


## Prerequisites

To get MotoTwist application running, you will need to have **Docker** and **Docker Compose** installed on your system.

* **Docker:** [Installation Guide](https://docs.docker.com/get-docker/)
* **Docker Compose:** [Installation Guide](https://docs.docker.com/compose/install/)


## Steps

1.  **Download the latest compose file:** 
    Place 
    [`docker-compose.yml`](https://github.com/amot-dev/mototwist/blob/master/docker-compose.yml) in its own directory.

2.  **Configure environment variables:**
    Using [`.env.example`](https://github.com/amot-dev/mototwist/blob/master/.env.example) as a starting point, configure your desired environment variables. These should be placed in a `.env` file in the same directory as your `docker-compose.yml` file.
    
    See the full list of environment variables [here](/install/env.md).

3.  **Run the containers:**
    From the directory containing your `docker-compose.yml`, run:
    ```bash
    docker compose up -d
    ```

4.  **Access the application:**
    Open your web browser and navigate to `http://localhost:8000`.
