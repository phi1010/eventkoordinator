# Eventkoordinator


## Running
### First run
* Copy .env.example to .env and fill in the values
* Run `docker compose build` to build the Docker images
* Run `docker compose pull` to pull the latest Docker images
* Run `./prod-manage.sh migrate` to apply database migrations
* Run `docker compose up -d` to start the application
* Install a HTTPS reverse proxy like nginx or caddy to serve the application securely.
  * Block the `/metrics` endpoint from public access.
* Create an admin user using `./prod-manage.sh create_openid_user --username admin --email mail@example.com --is-staff --is-superuser --password admin` using your own credentials. The username should be chosen NOT to match any username in the OpenID connect provider. Conflicting usernames with differing user IDs will be renamed upon import from OpenID and not be matched.

### Dotenv Configuration
```dotenv
# Will not be passed to the container by docker compose for security reasons, but can be used for local development
DJANGO_DEBUG=1
# Configure a mail server to send emails, e.g. for proposal workflow notifications
DJANGO_EMAIL_HOST=
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_HOST_USER=
DJANGO_EMAIL_HOST_PASSWORD=
DJANGO_EMAIL_USE_SSL=0
DJANGO_EMAIL_USE_TLS=1
# This is the sender email address for emails sent by the application, e.g. for proposal workflow notifications
DJANGO_DEFAULT_FROM_EMAIL=
# Configure OpenID Connect for user authentication, e.g. with Keycloak
DJANGO_OIDC_RP_CLIENT_ID=
DJANGO_OIDC_RP_CLIENT_SECRET=
## The ZAM keycloak server is automatically configured using the configuration endpoint, so these values do not need to be set, but the keycloak server must be accessible from the application at startup time.

# Generate a random secret key for Django, e.g. using `openssl rand -base64 32`
DJANGO_SECRET_KEY=
# Configure allowed hosts and CORS settings for development and production
DJANGO_ALLOWED_HOSTS=["127.0.0.1","localhost","backend","eventkoordinator.im.zam.haus"]
DJANGO_CSRF_TRUSTED_ORIGINS=["https://eventkoordinator.im.zam.haus"]
DJANGO_CORS_ALLOWED_ORIGINS=["https://eventkoordinator.im.zam.haus"]
# The port that the docker container (nginx) will listen on.
HTTP_PORT=8000
# The namespace for Prometheus metrics
DJANGO_PROMETHEUS_METRIC_NAMESPACE="eventcoordinator"
# Grafana credentials for accessing the Grafana dashboard, e.g. for monitoring the application with Prometheus and Grafana. Grafana is only included in the debug docker compose configuration, so these credentials will not be used in production.
GF_SECURITY_ADMIN_PASSWORD=
GF_SECURITY_ADMIN_USER=
# The host and the port that the nginx reverse proxy will listen on (use "localhost:8000" for development)
NGINX_PROXY_HOST=eventkoordinator.im.zam.haus
# The database initialization and connection settings for the PostgreSQL database
POSTGRES_PASSWORD=
# The URL base used in emails:
DJANGO_FRONTEND_BASE_URL=https://eventkoordinator.im.zam.haus
```
### In-App Configuration

* Log on using your admin credentials 
* Go to the admin interface in the navbar
* Add "Proposal Areas" such as Holzwerkstatt, 3D-Druck, etc. These are used to categorize proposals
* Add "Proposal Types" such as Workshop, Vortrag, etc. These are used to categorize proposals. Currently, in the hint only two of them (Workshop & Open Offer) are explained, this is fixed in the localization files.
* Add "Proposal Languages" such as German, English. Use the pretix language codes, e.g. "de-informal" for German and "en" for English. These are used to categorize proposals.
* Add a Call
* Add two Sync Base Targets of types:
  * PretixSyncTarget
    * API Token
    * URL, e.g. http://localhost:8282/api/v1
    * Organizer Slug (the part after the organizer/ in the pretix URL)
    * One area association for proposal area mappe to a pretix event in the organizer
      * Adding these after saving via the sidebar entry "Pretix sync target area associations" is easier.
      * Sync Target is the PretixSyncTarget you just created
      * Proposal Area is the proposal area you want to map to a pretix event
      * Event Slug is the part after the event/ in the pretix URL
      * The following fields should be the names or IDs of the products.
  * CalDAVSyncTarget
    * Name: Any name for the sync target
    * URL: The URL of the CalDAV server, e.g. https://cloud.betreiberverein.de/remote.php/dav
    * Username/Password
    * The calendar display name as shown in the nextcloud calendar app, e.g. "Kurse (admin)" when a calendarf "Kurse" was shared by the user "admin"
    * An instance base url which will be added as a metadatum to the calendar entries to see which eventcoordinator instance created the entry.

## Development

### With PyCharm

* Install uv and sync the project using `uv sync` in the terminal
* Install playwright browsers if not present using `uv run playwright install`
* Start the docker containers `db redis` using `docker compose up -d db redis`
* You can optionally use `./debug-docker-compose.sh up -d ...` to also start prometheus and grafana for monitoring the application during development, but this is not necessary for development and will consume more resources.
* Use the existing PyCharm configurations to start
  * `VITE_DJANGO_BASE=true npm run build` to build the frontend assets
    * Only necessary if you want to access the backend development server serving the frontend assets, otherwise the frontend development server, or in production nginx, will serve the assets
  * `cd backend && uv run manage.py runserver` to start the backend development server
  * `npm run dev` to start the frontend development server
    * Vite will forward API requests to the backend development server, so you can access the frontend at `http://localhost:5173` and the backend at `http://localhost:8000` will automatically be used for API requests
* When you changed the Python API, regenerate the OpenAPI schema and the TypeScript types using `./buildnodeclient.sh`
* Run unit and integration tests using `cd backend && uv run manage.py test`
  * Commit changed ARIA test snapshots after review. They should be stable when nothing is changed.