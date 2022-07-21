FROM alpine:3.15

RUN apk update

# Install Python
RUN apk add wget~=1.21\
            python3~=3.9\
            py3-pip~=20.3

## Build process

# Install build deps
RUN apk add python3-dev~=3.9\
            openssl-dev~=1.1\
            rust~=1.56\
            cargo~=1.56\
            build-base~=0.5\
            libffi-dev~=3.4.2

# Install the deps for the Python script
RUN pip install wheel~=0.37\
                paramiko~=2.11\
                mediawiki-dump~=1.0.0\
                gql~=3.4\
                psycopg~=3.0

# Install a more recent version of Pandoc
RUN wget https://github.com/jgm/pandoc/releases/download/2.18/pandoc-2.18-linux-amd64.tar.gz
RUN tar -xf /pandoc-2.18-linux-amd64.tar.gz pandoc-2.18/bin/pandoc 
RUN cp /pandoc-2.18/bin/pandoc /bin


## Cleanup

# Remove build deps
RUN apk del python3-dev\
            openssl-dev\
            rust\
            cargo\
            build-base\
            libffi-dev

RUN rm -r /pandoc-2.18/bin/pandoc /pandoc-2.18-linux-amd64.tar.gz /root/.cargo /root/.cache

CMD [ "tail", "-f", "/dev/null" ]