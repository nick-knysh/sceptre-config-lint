# Container image that runs your code
#FROM python:3
FROM python:3.10-alpine

RUN pip install --no-cache-dir Jinja2 requests cfn-lint==0.83.5 pathspec==0.12.1

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh
COPY linter.py /linter.py

RUN ["chmod", "+x", "/entrypoint.sh"]
# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT [ "/entrypoint.sh" ]

