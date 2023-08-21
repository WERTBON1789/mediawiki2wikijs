FROM alpine:3.18

RUN apk add --no-cache \ 
    python3 \
    py3-pip \
    pandoc \
    postgresql15-client

RUN pip install --no-cache-dir --break-system-packages \
    mediawiki-dump \
    psycopg[binary] \
    ldap3 \
    paramiko

COPY --chmod=755 ./mediawiki2wikijs.py /mediawiki2wikijs.py

VOLUME [ "/data" ]

CMD [ "/mediawiki2wikijs.py" ]

