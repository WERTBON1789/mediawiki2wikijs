FROM alpine:3.18

# Install Python and all build dependencies
RUN apk add --no-cache \ 
    python3 \
    py3-pip \
    pandoc \
    postgresql15-client

RUN pip install --no-cache-dir --break-system-packages \
    mediawiki-dump \
    psycopg[binary] \
    ldap3 \
    wikijspy \
    wikijspy-ext \
    paramiko

COPY ./mediawiki2wikijs.py /mediawiki2wikijs.py

RUN chmod 755 /mediawiki2wikijs.py

RUN mkdir /data

CMD [ "/mediawiki2wikijs.py" ]
