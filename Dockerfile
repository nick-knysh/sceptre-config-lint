# Container image that runs your code
#FROM python:3
FROM alpine/cfn-lint

RUN pip install --no-cache-dir Jinja2==3.1.2 requests==2.31.0

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh
COPY linter.py /linter.py

RUN ["chmod", "+x", "/entrypoint.sh"]
# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT [ "/entrypoint.sh" ]

