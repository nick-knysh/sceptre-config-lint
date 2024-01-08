# Container image that runs your code
#FROM python:3
FROM alpine/cfn-lint

RUN pip install --no-cache-dir Jinja2==3.1.2

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT [ "/bin/sh", "-c", "/entrypoint.sh" ]

