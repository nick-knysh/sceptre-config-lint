# Container image that runs your code
FROM python:3

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir Jinja2==3.1.2 cfn-lint==0.83.7
    # Note: we had to merge the two "pip install" package lists here, otherwise
    # the last "pip install" command in the OP may break dependency resolution…

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/entrypoint.sh"]

