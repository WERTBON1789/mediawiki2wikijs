FROM alpine:3.18

RUN --mount=type=cache,target=/var/cache/apk apk add \ 
    python3 \
    py3-pip \
    pandoc \
    postgresql15-client \
    py3-pyldap \
    py3-paramiko \
    py3-requests-toolbelt

RUN --mount=type=cache,target=/root/.cache/pip pip install --break-system-packages \
    mediawiki-dump \
    psycopg[binary] \
    gql

COPY --chmod=755 ./mediawiki2wikijs.py /mediawiki2wikijs.py
COPY --chmod=755 ./constants.py /constants.py
COPY --chmod=755 ./query_defs.py query_defs.py

VOLUME [ "/data" ]

CMD [ "/mediawiki2wikijs.py" ]

