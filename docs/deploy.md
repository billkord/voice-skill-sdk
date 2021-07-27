# Deploying the Skill

Suppose, we have a "Hello, World!" skill defined in `app.py`:

```python
from skill_sdk import skill, Response

@skill.intent_handler("HELLO_INTENT")
def hello() -> Response:
    return Response("Hello, World!")

app = skill.init_app()
app.include(handler=hello)
```

Deploy the skill with built-in [Uvicorn](https://www.uvicorn.org/) server:

`vs run app.py`

Here is a sample startup log (beginning of the log is skipped for readability):
```log
...
INFO:     Started server process [11175]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:4242 (Press CTRL+C to quit)
```

# Deploying with Gunicorn

[Gunicorn](https://gunicorn.org/) is the simplest way to deploy the skill in a production setting. 
Uvicorn includes a gunicorn worker class that means you can get set up with very little configuration.

Deploy the skill with Gunicorn on port 4242 using two workers:

`gunicorn -b :4242 -w 2 -k uvicorn.workers.UvicornWorker app:app`

The sample startup log, notifying about successful startup:

```
[2021-04-09 10:14:42 +0200] [12520] [INFO] Starting gunicorn 20.1.0
[2021-04-09 10:14:42 +0200] [12520] [INFO] Listening at: http://0.0.0.0:4242 (12520)
[2021-04-09 10:14:42 +0200] [12520] [INFO] Using worker: uvicorn.workers.UvicornWorker
[2021-04-09 10:14:42 +0200] [12522] [INFO] Booting worker with pid: 12522
[2021-04-09 10:14:42 +0200] [12523] [INFO] Booting worker with pid: 12523
[2021-04-09 10:14:42 +0200] [12522] [INFO] Started server process [12522]
[2021-04-09 10:14:42 +0200] [12522] [INFO] Waiting for application startup.
[2021-04-09 10:14:42 +0200] [12522] [INFO] Application startup complete.
[2021-04-09 10:14:42 +0200] [12523] [INFO] Started server process [12523]
[2021-04-09 10:14:42 +0200] [12523] [INFO] Waiting for application startup.
[2021-04-09 10:14:42 +0200] [12523] [INFO] Application startup complete.
```

## Logging 

### Configure Logging 

When deploying with Gunicorn server, logging must be explicitly configured, 
either by calling `skill_sdk.log.setup_logging()` helper **before** initializing your skill application:

```python
import logging
from skill_sdk import log, skill 
from skill_sdk.config import FormatType  

log.setup_logging(logging.DEBUG, FormatType.GELF)
app = skill.init_app()
```

OR, setting `configure_logging=True` when initializing the skill:

```python
from skill_sdk import skill

app = skill.init_app(configure_logging=True)
```

in the latter case, logging level and format will be read from the environment.


### Gunicorn Logging 

To output the Gunicorn logs in JSON GrayLog-compatible form, skill SDK implements a log formatter in 
`skill_sdk.log.GunicornLogger` class. This formatter can be specified with `--logger-class` parameter:


`gunicorn -b :4242 -w 2 -k uvicorn.workers.UvicornWorker --logger-class=skill_sdk.log.GunicornLogger app:app`


# Development Mode

Deploy the skill in _development mode_ with built-in [Uvicorn](https://www.uvicorn.org/) server:

`vs develop app.py`


# Kubernetes Integration


Along with Magenta skill-specific invoke and info endpoints, 
skill SDK for Python provides liveness and readiness probes for Kubernetes environment.

Their configuration is defined in skill settings:

- **settings.K8S_READINESS**: Kubernetes readiness probe endpoint. Default: "/k8s/readiness".


- **settings.K8S_LIVENESS**: Kubernetes liveness probe endpoint. Default: "/k8s/liveness".


# Prometheus Metrics


Along with Magenta skill-specific invoke and info endpoints, 
skill SDK for Python provides liveness and readiness probes for Kubernetes environment.

Their configuration is defined in skill settings:

- **settings.PROMETHEUS_ENDPOINT**: Endpoint for Prometheus scraper. Default: "/prometheus".

> **Note**: Prometheus integration is optional: 
> to enable Prometheus metrics exporter, skill SDK must be installed with **all** optional components: `pip install skill-sdk[all]` 
